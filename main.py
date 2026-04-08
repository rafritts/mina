"""
Mina's chat loop + heartbeat scheduler.

Run:  python main.py

The heartbeat fires automatically in the background based on config.json's
heartbeat_interval_seconds. The chat loop and heartbeat share conversation.json.
"""
import asyncio
import json
import os
import sys
import time
from openai import OpenAI

from memory import build_kag_context, build_rag_context
from state import apply_deltas, load_and_advance, log_state, save_state
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

# Keep at most this many messages in conversation.json.
# Older messages are trimmed from the front (preserving recency).
HISTORY_MAX = 200


def _load_config() -> dict:
    try:
        with open(_CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# ---------------------------------------------------------------------------
# Conversation history
# ---------------------------------------------------------------------------

def _load_history() -> list[dict]:
    try:
        with open(_HISTORY_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_history(history: list[dict]) -> None:
    # Compact: keep only the last HISTORY_MAX messages
    if len(history) > HISTORY_MAX:
        history = history[-HISTORY_MAX:]
    with open(_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def _touch_last_active() -> None:
    with open(_LAST_ACTIVE_FILE, "w") as f:
        f.write(str(time.time()))


def _consume_admin_instructions() -> str:
    try:
        with open(_ADMIN_FILE) as f:
            content = f.read().strip()
        os.remove(_ADMIN_FILE)
        return content
    except FileNotFoundError:
        return ""


def _api_messages(history: list[dict], system_prompt: str) -> list[dict]:
    """
    Build the messages array for the LLM API call.

    - Starts with a single system message (the subconscious-generated prompt).
    - Includes conversation history, but filters out internal system messages
      ([HEARTBEAT], [ADMIN]) which the API doesn't need and may reject.
    - Keeps user, assistant, and tool messages intact.
    """
    messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        role = msg.get("role", "")
        content = msg.get("content", "")
        # Drop internal system markers
        if role == "system":
            continue
        messages.append(msg)
    return messages


# ---------------------------------------------------------------------------
# Mina's turn (one round-trip, tool calls resolved)
# ---------------------------------------------------------------------------

async def _mina_turn(
    client: OpenAI,
    system_prompt: str,
    history: list[dict],
    state,
) -> tuple[list[dict], object]:
    """
    One full Mina turn. Resolves all tool calls.
    Returns (new_history_entries, updated_state).
    """
    messages = _api_messages(history, system_prompt)
    new_entries: list[dict] = []

    response = client.chat.completions.create(
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
        return new_entries, state

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
            print(f"  [image] {result or 'blocked/failed'}")
        else:
            result, state, extra = call_tool(name, args, state)
            save_state(state)
            print(f"  [result] {result}")

            # `do` activity: evaluate with subconscious for biological deltas
            if name == "do" and extra:
                _apply_do_deltas_via_subconscious(state, extra)

        new_entries.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": str(result),
        })

    # Follow-up after tools
    follow_messages = _api_messages(history, system_prompt) + new_entries
    follow_response = client.chat.completions.create(
        model=MODEL,
        messages=follow_messages,
        temperature=0.85,
    )
    follow_msg = follow_response.choices[0].message
    new_entries.append({"role": "assistant", "content": follow_msg.content or ""})

    return new_entries, state


def _apply_do_deltas_via_subconscious(state, pending: dict) -> None:
    """
    Ask the subconscious to determine biological deltas for a `do` activity.
    Applies them to state in-place and saves.
    """
    from subconscious import _get_client, MODEL as SC_MODEL, _format_state_for_subconscious

    activity = pending.get("activity", "")
    description = pending.get("description", "")

    prompt = (
        f"{_format_state_for_subconscious(state)}\n\n"
        f"Mina just did the following during free time:\n"
        f"Activity: {activity}\n"
        f"Description: {description}\n\n"
        f"Output ONLY a JSON object of biological deltas (e.g. {{\"dopamine\": 8, \"cortisol\": -5}}). "
        f"No explanation. Small, realistic values."
    )

    try:
        response = _get_client().chat.completions.create(
            model=SC_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        raw = response.choices[0].message.content or ""
        # Extract JSON from response
        import re
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            deltas = json.loads(m.group())
            apply_deltas(state, deltas)
            save_state(state)
            print(f"  [do deltas] {deltas}")
    except Exception as e:
        print(f"  [do deltas error] {e}")


# ---------------------------------------------------------------------------
# Heartbeat scheduler (background task)
# ---------------------------------------------------------------------------

async def _heartbeat_loop() -> None:
    """Run heartbeat on the configured interval. Fires in background while chat loop runs."""
    from heartbeat import run_heartbeat

    while True:
        cfg = _load_config()
        interval = int(cfg.get("heartbeat_interval_seconds", 1800))
        await asyncio.sleep(interval)
        print(f"\n[HEARTBEAT] Firing (interval={interval}s)...")
        try:
            await run_heartbeat()
        except Exception as e:
            print(f"[HEARTBEAT ERROR] {e}")


# ---------------------------------------------------------------------------
# Main chat loop
# ---------------------------------------------------------------------------

async def main() -> None:
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    # Start heartbeat in background
    asyncio.create_task(_heartbeat_loop())

    cfg = _load_config()
    compression = cfg.get("time_compression_factor", 1.0)
    interval = cfg.get("heartbeat_interval_seconds", 1800)
    print(f"Mina starting. time_compression={compression}x, heartbeat_interval={interval}s\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            sys.exit(0)

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            print("Bye.")
            sys.exit(0)

        _touch_last_active()

        # Load + advance state
        state = load_and_advance()
        log_state(state)

        # Build memory context
        kag_context = build_kag_context()
        rag_context = build_rag_context(user_input)

        # Load history, inject admin if present
        history = _load_history()
        admin = _consume_admin_instructions()
        if admin:
            history.append({"role": "system", "content": f"[ADMIN]\n{admin}"})
            print("  [admin] Instructions consumed.")

        history.append({"role": "user", "content": user_input})

        # Subconscious Mode 1
        deltas, system_prompt = run_mode1(state, history, kag_context, rag_context)
        if not system_prompt:
            system_prompt = "You are Mina. Respond naturally."

        state = apply_deltas(state, deltas)
        save_state(state)

        # Mina's turn
        new_entries, state = await _mina_turn(client, system_prompt, history, state)
        save_state(state)

        # Print Mina's reply
        mina_reply = ""
        for entry in reversed(new_entries):
            if entry.get("role") == "assistant" and entry.get("content"):
                mina_reply = entry["content"]
                break
        print(f"\nMina: {mina_reply}\n")

        # Persist history
        history.extend(new_entries)
        _save_history(history)

        _touch_last_active()


if __name__ == "__main__":
    asyncio.run(main())
