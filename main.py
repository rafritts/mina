"""
Mina's chat loop.

Each turn:
1. Load state, apply time-based decay
2. Build KAG + RAG context
3. Run subconscious Mode 1 → deltas + system prompt
4. Apply deltas, save state
5. Call Mina with her system prompt + history + tools
6. Handle tool calls (biological tools + image generation)
7. Append to shared conversation history
8. Record user-active timestamp (suppresses heartbeat)
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


# ---------------------------------------------------------------------------
# Conversation history persistence
# ---------------------------------------------------------------------------

def _load_history() -> list[dict]:
    try:
        with open(_HISTORY_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_history(history: list[dict]) -> None:
    with open(_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def _touch_last_active() -> None:
    with open(_LAST_ACTIVE_FILE, "w") as f:
        f.write(str(time.time()))


# ---------------------------------------------------------------------------
# Admin instructions (consumed once)
# ---------------------------------------------------------------------------

def _consume_admin_instructions() -> str:
    try:
        with open(_ADMIN_FILE) as f:
            content = f.read().strip()
        os.remove(_ADMIN_FILE)
        return content
    except FileNotFoundError:
        return ""


# ---------------------------------------------------------------------------
# Mina's turn
# ---------------------------------------------------------------------------

async def _mina_turn(
    client: OpenAI,
    system_prompt: str,
    history: list[dict],
    state,
) -> tuple[list[dict], object]:
    """
    One full Mina turn including any tool calls.
    Returns (new_history_entries, updated_state).
    """
    messages = [{"role": "system", "content": system_prompt}] + history

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

    # Build assistant entry with tool_calls
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
            result, state, _ = call_tool(name, args, state)
            save_state(state)
            print(f"  [tool result] {result}")

        new_entries.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": str(result),
        })

    # Follow-up response after tools
    follow_messages = messages + new_entries
    follow_response = client.chat.completions.create(
        model=MODEL,
        messages=follow_messages,
        temperature=0.85,
    )
    follow_msg = follow_response.choices[0].message
    new_entries.append({"role": "assistant", "content": follow_msg.content or ""})

    return new_entries, state


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def main():
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    print("Mina is waking up...\n")

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

        # 1. Load and advance state
        state = load_and_advance()
        log_state(state)

        # 2. Build memory context
        kag_context = build_kag_context()
        rag_context = build_rag_context(user_input)

        # 3. Load history, append user message
        history = _load_history()

        # Inject admin instructions as a system message if present (consumed once)
        admin = _consume_admin_instructions()
        if admin:
            history.append({"role": "system", "content": f"[ADMIN]\n{admin}"})
            print(f"  [admin] Instructions consumed.")

        history.append({"role": "user", "content": user_input})

        # 4. Run subconscious Mode 1
        deltas, system_prompt = run_mode1(state, history, kag_context, rag_context)

        if not system_prompt:
            # Fallback: bare-minimum system prompt
            system_prompt = "You are Mina. Respond naturally."

        # 5. Apply deltas, save
        state = apply_deltas(state, deltas)
        save_state(state)

        # 6. Mina's turn
        new_entries, state = await _mina_turn(client, system_prompt, history, state)
        save_state(state)

        # 7. Print Mina's final response
        mina_reply = ""
        for entry in reversed(new_entries):
            if entry.get("role") == "assistant" and entry.get("content"):
                mina_reply = entry["content"]
                break

        print(f"\nMina: {mina_reply}\n")

        # 8. Persist history
        history.extend(new_entries)
        _save_history(history)

        _touch_last_active()


if __name__ == "__main__":
    asyncio.run(main())
