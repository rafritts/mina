"""
Mina's core turn logic + CLI entry point.

`run_turn()` is the shared coroutine used by both the CLI and discord_gateway.py.
The CLI loop at the bottom is for development/testing only — Discord is the primary interface.
"""
import asyncio
import json
import os
import sys
import time
from openai import OpenAI

from memory import build_kag_context, build_rag_context
from state import apply_deltas, load_and_advance, load_state, log_state, save_state
from bio_report import biological_report
from subconscious import encode_response, encode_stimulus, evaluate_activity_deltas, run_mode1
from tools_mina import TOOLS, call_tool, handle_generate_image

MODEL = os.getenv("MODEL", "grok-4-1-fast-reasoning")
BASE_URL = os.getenv("BASE_URL", "https://api.x.ai/v1")
API_KEY = os.getenv("XAI_API_KEY", os.getenv("OPENAI_API_KEY", "sk-placeholder"))

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_HISTORY_FILE = os.path.join(_PROJECT_ROOT, "run", "conversation.json")
_LAST_ACTIVE_FILE = os.path.join(_PROJECT_ROOT, ".last_user_active")
_ADMIN_FILE = os.path.join(_PROJECT_ROOT, "ADMIN_INSTRUCTIONS.md")
_CONFIG_FILE = os.path.join(_PROJECT_ROOT, "config.json")
_PAUSED_FLAG = os.path.join(_PROJECT_ROOT, "run", ".paused")

HISTORY_MAX = 200

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    return _client


def _load_config() -> dict:
    try:
        with open(_CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

def load_history() -> list[dict]:
    try:
        with open(_HISTORY_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_history(history: list[dict]) -> None:
    if len(history) > HISTORY_MAX:
        history = history[-HISTORY_MAX:]
    os.makedirs(os.path.dirname(_HISTORY_FILE), exist_ok=True)
    with open(_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def touch_last_active() -> None:
    with open(_LAST_ACTIVE_FILE, "w") as f:
        f.write(str(time.time()))


def consume_admin_instructions() -> str:
    try:
        with open(_ADMIN_FILE) as f:
            content = f.read().strip()
        os.remove(_ADMIN_FILE)
        return content
    except FileNotFoundError:
        return ""


def api_messages(history: list[dict], system_prompt: str) -> list[dict]:
    """Build the messages array for the API — single system message, no internal markers."""
    messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        if msg.get("role") == "system":
            continue
        messages.append(msg)
    return messages


# ---------------------------------------------------------------------------
# Mina's turn
# ---------------------------------------------------------------------------

async def _mina_turn(
    system_prompt: str,
    history: list[dict],
    state,
) -> tuple[list[dict], object, list[str]]:
    """
    One full Mina turn. Resolves all tool calls.
    Returns (new_history_entries, updated_state, image_paths).
    """
    messages = api_messages(history, system_prompt)
    new_entries: list[dict] = []
    image_paths: list[str] = []

    response = await asyncio.to_thread(
        _get_client().chat.completions.create,
        model=MODEL,
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
        temperature=0.85,
    )

    msg = response.choices[0].message
    finish = response.choices[0].finish_reason

    if finish != "tool_calls" or not msg.tool_calls:
        new_entries.append({"role": "assistant", "content": msg.content or ""})
        return new_entries, state, image_paths

    assistant_entry = {
        "role": "assistant",
        "content": msg.content or "",
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in msg.tool_calls
        ],
    }
    new_entries.append(assistant_entry)

    for tc in msg.tool_calls:
        name = tc.function.name
        try:
            args = json.loads(tc.function.arguments)
        except json.JSONDecodeError:
            args = {}

        print(f"  [tool] {name}({args})")

        if name == "generate_image":
            result = await handle_generate_image(args)
            if result and result.endswith(".png") and os.path.exists(result):
                image_paths.append(result)
            print(f"  [image] {result or 'blocked/failed'}")
        else:
            result, state, extra = call_tool(name, args, state)
            save_state(state)
            print(f"  [result] {result}")
            if name == "do" and extra:
                activity = extra.get("activity", "")
                description = extra.get("description", "")
                do_deltas = await asyncio.to_thread(evaluate_activity_deltas, state, activity, description)
                if do_deltas:
                    state = apply_deltas(state, do_deltas)
                    save_state(state)
                    print(f"  [do deltas] {do_deltas}")

        new_entries.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": str(result),
        })

    follow_messages = api_messages(history, system_prompt) + new_entries
    follow_response = await asyncio.to_thread(
        _get_client().chat.completions.create,
        model=MODEL,
        messages=follow_messages,
        temperature=0.85,
    )
    follow_msg = follow_response.choices[0].message
    new_entries.append({"role": "assistant", "content": follow_msg.content or ""})

    return new_entries, state, image_paths



# ---------------------------------------------------------------------------
# Shared run_turn — called by both CLI and discord_gateway
# ---------------------------------------------------------------------------

async def run_turn(
    user_input: str,
    username: str = "user",
    image_b64: str | None = None,
    image_mime: str = "image/jpeg",
) -> tuple[str, list[str]]:
    """
    Execute one full Mina turn.

    Args:
        user_input: The message text.
        username: Display name of the speaker (prefixed in history).
        image_b64: Optional base64-encoded image for vision.
        image_mime: MIME type of the image (default image/jpeg).

    Returns:
        (reply_text, image_paths) — reply is the final assistant text;
        image_paths is a list of generated .png file paths (may be empty).
    """
    touch_last_active()

    paused = os.path.exists(_PAUSED_FLAG)
    state = load_state() if paused else load_and_advance()
    if paused:
        print("[STATE] Biological updates paused — time not advanced.")
    log_state(state)

    # [1] encode_stimulus — biological response to incoming message
    stimulus = f"{username}: {user_input}" + (" [sent an image]" if image_b64 else "")
    stimulus_deltas = await asyncio.to_thread(encode_stimulus, state, stimulus)
    if stimulus_deltas:
        print(f"[STIMULUS DELTAS] {stimulus_deltas}")
        state = apply_deltas(state, stimulus_deltas)
        save_state(state)

    # [2] biological_report — deterministic, from updated state
    report = biological_report(state)
    print(f"[BIO REPORT]\n{report}")

    kag_context = build_kag_context()
    rag_context = build_rag_context(user_input)
    history = load_history()

    admin = consume_admin_instructions()
    if admin:
        history.append({"role": "system", "content": f"[ADMIN]\n{admin}"})
        print("  [admin] Instructions consumed.")

    # Build user content — multimodal if image attached
    if image_b64:
        user_content = [
            {"type": "text", "text": f"{username}: {user_input}"},
            {"type": "image_url", "image_url": {"url": f"data:{image_mime};base64,{image_b64}"}},
        ]
        print(f"[VISION] Image attached ({image_mime})")
    else:
        user_content = f"{username}: {user_input}"
    history.append({"role": "user", "content": user_content})

    # [3] generate_system_prompt — Mode 1 reads biological report + monologue → writes monologue, returns system prompt
    system_prompt = await asyncio.to_thread(run_mode1, report, history, kag_context, rag_context)
    if not system_prompt:
        system_prompt = "You are Mina. Respond naturally."

    print(f"[SYSTEM PROMPT]\n{system_prompt}")

    # [4] Mina responds
    new_entries, state, image_paths = await _mina_turn(system_prompt, history, state)
    save_state(state)

    reply = ""
    for entry in reversed(new_entries):
        if entry.get("role") == "assistant" and entry.get("content"):
            reply = entry["content"]
            break

    # [5] encode_response — biological effect of what Mina just expressed
    if reply:
        response_deltas = await asyncio.to_thread(encode_response, state, reply)
        if response_deltas:
            print(f"[RESPONSE DELTAS] {response_deltas}")
            state = apply_deltas(state, response_deltas)
            save_state(state)

    history.extend(new_entries)
    save_history(history)

    touch_last_active()
    return reply, image_paths


# ---------------------------------------------------------------------------
# Heartbeat background loop (shared — started by both CLI and gateway)
# ---------------------------------------------------------------------------

async def bio_tick_loop() -> None:
    """Advance biological state every 60 seconds, deterministically (no LLM)."""
    while True:
        await asyncio.sleep(60)
        if os.path.exists(_PAUSED_FLAG):
            continue
        try:
            load_and_advance()  # saves internally
        except Exception as e:
            print(f"[BIO TICK ERROR] {e}")


async def heartbeat_loop() -> None:
    from heartbeat import run_heartbeat
    while True:
        cfg = _load_config()
        interval = int(cfg.get("heartbeat_interval_seconds", 1800))
        await asyncio.sleep(interval)
        if os.path.exists(_PAUSED_FLAG):
            print("[HEARTBEAT] Paused — skipping.")
            continue
        print(f"\n[HEARTBEAT] Firing (interval={interval}s)...")
        try:
            await run_heartbeat()
        except Exception as e:
            print(f"[HEARTBEAT ERROR] {e}")


# ---------------------------------------------------------------------------
# CLI entry point (development only)
# ---------------------------------------------------------------------------

def _cli_run_command(cmd: str) -> bool:
    """
    Handle a CLI slash command. Returns True if handled, False if not a command.
    """
    import checkpoints as _ckpts
    from state import load_and_advance, log_state

    parts = cmd.strip().split()
    name = parts[0].lower()

    if name == "/reset":
        print(_ckpts.reset())
        return True

    if name == "/factory-reset":
        confirm = input("This wipes everything including her identity. Type YES to confirm: ").strip()
        if confirm == "YES":
            print(_ckpts.factory_reset())
        else:
            print("Cancelled.")
        return True

    if name == "/checkpoints":
        ckpts = _ckpts.list_checkpoints()
        if not ckpts:
            print("No checkpoints yet.")
        else:
            print("Available checkpoints (0 = most recent):")
            for c in ckpts[:20]:
                print(f"  {c['index']}  {c['created']}  ({c['label']})")
        return True

    if name == "/rollback":
        index = int(parts[1]) if len(parts) > 1 else 0
        try:
            print(_ckpts.restore(index))
        except ValueError as e:
            print(f"Error: {e}")
        return True

    if name == "/state":
        state = load_and_advance()
        log_state(state)
        return True

    if name in {"/help", "/?"}:
        print(
            "Commands:\n"
            "  /state           — show current biological state\n"
            "  /checkpoints     — list available checkpoints\n"
            "  /rollback [N]    — restore checkpoint N (default 0 = most recent)\n"
            "  /reset           — wipe relationship/RAG/knowledge/history; keep biomarkers + identity\n"
            "  /factory-reset   — same as /reset + reset biomarkers; identity (MINA.md/APPEARANCE.md) always preserved\n"
            "  exit / quit      — exit"
        )
        return True

    return False


async def _cli_main() -> None:
    cfg = _load_config()
    print(f"Mina CLI — time_compression={cfg.get('time_compression_factor', 1.0)}x  (type /help for commands)\n")

    asyncio.create_task(bio_tick_loop())
    asyncio.create_task(heartbeat_loop())

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            sys.exit(0)

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            sys.exit(0)
        if user_input.startswith("/"):
            if _cli_run_command(user_input):
                continue

        reply, image_paths = await run_turn(user_input, username="user")
        print(f"\nMina: {reply}\n")
        for path in image_paths:
            print(f"  [image] {path}")


if __name__ == "__main__":
    asyncio.run(_cli_main())
