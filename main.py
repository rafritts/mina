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
from subconscious import run_mode1
from tools_mina import TOOLS, call_tool, handle_generate_image

MODEL = os.getenv("MODEL", "grok-4-1-fast-reasoning")
BASE_URL = os.getenv("BASE_URL", "https://api.x.ai/v1")
API_KEY = os.getenv("XAI_API_KEY", os.getenv("OPENAI_API_KEY", "sk-placeholder"))

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_HISTORY_FILE = os.path.join(_PROJECT_ROOT, "conversation.json")
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

    response = _get_client().chat.completions.create(
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
                _apply_do_deltas(state, extra)

        new_entries.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": str(result),
        })

    follow_messages = api_messages(history, system_prompt) + new_entries
    follow_response = _get_client().chat.completions.create(
        model=MODEL,
        messages=follow_messages,
        temperature=0.85,
    )
    follow_msg = follow_response.choices[0].message
    new_entries.append({"role": "assistant", "content": follow_msg.content or ""})

    return new_entries, state, image_paths


def _apply_do_deltas(state, pending: dict) -> None:
    """Ask subconscious for biological deltas from a `do` activity."""
    from subconscious import _get_client as sc_client, MODEL as SC_MODEL, _format_state_for_subconscious
    import re

    activity = pending.get("activity", "")
    description = pending.get("description", "")
    prompt = (
        f"{_format_state_for_subconscious(state)}\n\n"
        f"Mina just did:\nActivity: {activity}\nDescription: {description}\n\n"
        f"Output ONLY a JSON object of biological deltas (e.g. {{\"dopamine\": 8}}). "
        f"No explanation. Small, realistic values."
    )
    try:
        response = sc_client().chat.completions.create(
            model=SC_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        raw = response.choices[0].message.content or ""
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            deltas = json.loads(m.group())
            apply_deltas(state, deltas)
            save_state(state)
            print(f"  [do deltas] {deltas}")
    except Exception as e:
        print(f"  [do deltas error] {e}")


# ---------------------------------------------------------------------------
# Shared run_turn — called by both CLI and discord_gateway
# ---------------------------------------------------------------------------

async def run_turn(user_input: str, username: str = "user") -> tuple[str, list[str]]:
    """
    Execute one full Mina turn.

    Args:
        user_input: The message text.
        username: Display name of the speaker (prefixed in history).

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

    kag_context = build_kag_context()
    rag_context = build_rag_context(user_input)

    history = load_history()

    admin = consume_admin_instructions()
    if admin:
        history.append({"role": "system", "content": f"[ADMIN]\n{admin}"})
        print("  [admin] Instructions consumed.")

    history.append({"role": "user", "content": f"{username}: {user_input}"})

    deltas, system_prompt = run_mode1(state, history, kag_context, rag_context)
    if not system_prompt:
        system_prompt = "You are Mina. Respond naturally."

    print(f"[MONOLOGUE] {system_prompt}")
    if deltas:
        print(f"[DELTAS] {deltas}")

    state = apply_deltas(state, deltas)
    save_state(state)

    new_entries, state, image_paths = await _mina_turn(system_prompt, history, state)
    save_state(state)

    reply = ""
    for entry in reversed(new_entries):
        if entry.get("role") == "assistant" and entry.get("content"):
            reply = entry["content"]
            break

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

async def _cli_main() -> None:
    cfg = _load_config()
    print(f"Mina CLI — time_compression={cfg.get('time_compression_factor', 1.0)}x\n")

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

        reply, image_paths = await run_turn(user_input, username="user")
        print(f"\nMina: {reply}\n")
        for path in image_paths:
            print(f"  [image] {path}")


if __name__ == "__main__":
    asyncio.run(_cli_main())
