"""
Heartbeat — autonomous cron-driven invocation.

Three phases:
  1. Subconscious reflection (Mode 2): consolidate history → RAG + KAG updates
  2. Mina's free time: she gets a turn with her tools, user isn't here
  3. State update: apply any `do` activity deltas + save

Run directly to fire one heartbeat:
    python heartbeat.py

Or import and call run_heartbeat() from a scheduler.
"""
import asyncio
import json
import os
import time

from openai import OpenAI

from memory import build_kag_context, build_rag_context, rag_add, read_kag, write_kag
from state import (
    BiologicalState,
    apply_deltas,
    derived,
    load_and_advance,
    log_state,
    save_state,
)
from subconscious import run_mode1, run_mode2
from tools_mina import TOOLS, call_tool, handle_generate_image

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_HISTORY_FILE = os.path.join(_PROJECT_ROOT, "conversation.json")
_LAST_ACTIVE_FILE = os.path.join(_PROJECT_ROOT, ".last_user_active")
_CONFIG_FILE = os.path.join(_PROJECT_ROOT, "config.json")

MODEL = os.getenv("MODEL", "grok-4-1-fast-reasoning")
BASE_URL = os.getenv("BASE_URL", "https://api.x.ai/v1")
API_KEY = os.getenv("XAI_API_KEY", os.getenv("OPENAI_API_KEY", "sk-placeholder"))


def _load_config() -> dict:
    try:
        with open(_CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _load_history() -> list[dict]:
    try:
        with open(_HISTORY_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_history(history: list[dict]) -> None:
    with open(_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def _user_recently_active(window_seconds: int = 60) -> bool:
    try:
        with open(_LAST_ACTIVE_FILE) as f:
            last = float(f.read().strip())
        return (time.time() - last) < window_seconds
    except (FileNotFoundError, ValueError):
        return False


def _log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[HEARTBEAT] {ts} {msg}")


# ---------------------------------------------------------------------------
# Free-time prompt
# ---------------------------------------------------------------------------

_FREETIME_SUFFIX = """\

---

You have some free time right now. The user isn't here at the moment. Check in with yourself. \
Do what you need or want — rest, eat, read something, just sit with it. Whatever feels right. \
You have your tools available.

If something from PENDING.md is still sitting there, you might notice it. Or not. Up to you."""


# ---------------------------------------------------------------------------
# Phase 2 — Mina's free-time turn
# ---------------------------------------------------------------------------

async def _run_mina_free_time(
    state: BiologicalState,
    system_prompt: str,
    history: list[dict],
) -> tuple[list[dict], dict]:
    """
    Give Mina one free-time turn. She may call tools.
    Returns (new_history_entries, pending_do_activity).
    """
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    full_system = system_prompt + _FREETIME_SUFFIX

    # Only pass user/assistant/tool messages — strip internal system markers
    messages = [{"role": "system", "content": full_system}]
    for msg in history[-10:]:
        role = msg.get("role", "")
        if role == "system":
            continue  # skip [HEARTBEAT] and [ADMIN] markers
        messages.append(msg)

    new_entries = [{"role": "system", "content": "[HEARTBEAT]"}]
    pending_do = {}

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
        temperature=0.9,
    )

    msg = response.choices[0].message
    assistant_entry = {"role": "assistant", "content": msg.content or ""}

    # Handle tool calls
    if msg.tool_calls:
        assistant_entry["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in msg.tool_calls
        ]

        new_entries.append(assistant_entry)

        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}

            if name == "generate_image":
                result = await handle_generate_image(args)
                tool_result = result if result else "[Image blocked or failed]"
            else:
                tool_result, state, extra = call_tool(name, args, state)
                if name == "do" and extra:
                    pending_do = extra

            new_entries.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_result,
            })

        # Follow-up response after tool calls
        follow_messages = messages + new_entries[1:]  # skip the [HEARTBEAT] marker
        follow_response = client.chat.completions.create(
            model=MODEL,
            messages=follow_messages,
            temperature=0.9,
        )
        follow_msg = follow_response.choices[0].message
        new_entries.append({"role": "assistant", "content": follow_msg.content or ""})

    else:
        new_entries.append(assistant_entry)

    save_state(state)
    return new_entries, pending_do


# ---------------------------------------------------------------------------
# do-activity delta evaluation via subconscious
# ---------------------------------------------------------------------------

def _evaluate_do_deltas(state: "BiologicalState", activity: str, description: str) -> dict:
    """Ask the subconscious to determine biological deltas for a `do` activity."""
    from subconscious import _get_client, MODEL as SC_MODEL, _format_state_for_subconscious

    prompt = (
        f"{_format_state_for_subconscious(state)}\n\n"
        f"Mina just did the following during free time:\n"
        f"Activity: {activity}\n"
        f"Description: {description}\n\n"
        f"Output ONLY a JSON object of biological deltas "
        f"(e.g. {{\"dopamine\": 8, \"cortisol\": -5}}). "
        f"No explanation. Small, realistic values. "
        f"Consider her current state when deciding the effect."
    )

    try:
        response = _get_client().chat.completions.create(
            model=SC_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        raw = response.choices[0].message.content or ""
        import re as _re
        m = _re.search(r"\{.*\}", raw, _re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:
        _log(f"do-delta evaluation error: {e}")

    return {}


# ---------------------------------------------------------------------------
# Main heartbeat entry point
# ---------------------------------------------------------------------------

async def run_heartbeat() -> None:
    if _user_recently_active():
        _log("User recently active — skipping heartbeat.")
        return

    _log("Starting.")

    # --- Load and advance state ---
    state = load_and_advance()
    log_state(state)

    # If deeply asleep and no interruption, skip Phase 2
    d = derived(state)
    sleep_pressure_was_high = state.sleep_pressure < 20 and state.sleeping
    # (sleep_pressure < 20 means she's well into a deep sleep cycle)

    history = _load_history()
    kag_context = build_kag_context()

    # --- Phase 1: Subconscious reflection (Mode 2) ---
    _log("Phase 1: subconscious reflection.")
    reflection = run_mode2(state, history, kag_context)

    _log(f"Reflection summary: {reflection['reflection_summary']}")

    # Write RAG entries
    for entry in reflection.get("rag_entries", []):
        if isinstance(entry, dict) and "text" in entry:
            rag_add(entry["text"], entry.get("metadata", {}))

    # Apply KAG updates
    for filename, content in reflection.get("kag_updates", {}).items():
        if content is not None:
            write_kag(filename.replace("KNOWLEDGE/", "KNOWLEDGE" + os.sep), content)
            _log(f"KAG updated: {filename}")

    # --- Phase 2: Mina's free time ---
    if state.sleeping and sleep_pressure_was_high:
        _log("Phase 2: Mina is in deep sleep — skipping free time.")
        _save_history(history)
        return

    _log("Phase 2: Mina's free time.")

    # Rebuild kag_context after potential updates
    kag_context = build_kag_context()
    rag_context = build_rag_context("free time heartbeat")

    # Run subconscious Mode 1 to get Mina's system prompt
    state = load_and_advance()  # re-advance in case time passed
    deltas, system_prompt = run_mode1(state, history, kag_context, rag_context)
    state = apply_deltas(state, deltas)
    save_state(state)

    if not system_prompt:
        _log("No system prompt from subconscious — skipping Mina turn.")
        _save_history(history)
        return

    new_entries, pending_do = await _run_mina_free_time(state, system_prompt, history)

    # Append heartbeat entries to shared history
    history.extend(new_entries)

    # --- Phase 3: State update ---
    _log("Phase 3: applying state updates.")

    if pending_do:
        activity = pending_do.get("activity", "")
        description = pending_do.get("description", "")
        state = load_and_advance()  # fresh advance before evaluation
        do_deltas = _evaluate_do_deltas(state, activity, description)
        state = apply_deltas(state, do_deltas)
        _log(f"Do activity '{activity}' deltas: {do_deltas}")

    # Final time advance + save
    state = load_and_advance()
    save_state(state)
    _save_history(history)

    _log("Complete.")


if __name__ == "__main__":
    asyncio.run(run_heartbeat())
