"""
Freetime — Mina's autonomous session when no user is present.

Three phases:
  1. Hippocampus consolidation: consolidate history → RAG + KAG updates
  2. Mina's free time: she gets a turn with her tools, user isn't here
  3. State update: apply any do_action activity deltas + save

Fires on a configurable interval (default: every 30 minutes) via main.py.

Run directly to fire one session:
    python freetime.py
"""
import asyncio
import json
import os
import time

from openai import OpenAI

from config import HISTORY_FILE, PAUSED_FLAG, PROJECT_ROOT, load_config
from client import get_client, MODEL
from cortex import apply_ts_label
from log import log as _log_raw
from decoder import biological_report, build_system_prompt, needs_summary
from encoder import encode_stimulus, encode_response, evaluate_activity_deltas
from hippocampus import build_kag_context, build_rag_context, rag_add, write_kag, consolidate
from state import (
    BiologicalState,
    apply_deltas,
    derived,
    load_and_advance,
    log_state,
    save_state,
)
from tools import HEARTBEAT_TOOLS, call_tool, handle_generate_image

_LAST_ACTIVE_FILE = os.path.join(PROJECT_ROOT, ".last_user_active")


def _load_history() -> list[dict]:
    try:
        with open(HISTORY_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_history(history: list[dict]) -> None:
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def _user_recently_active(window_seconds: int = 60) -> bool:
    try:
        with open(_LAST_ACTIVE_FILE) as f:
            last = float(f.read().strip())
        return (time.time() - last) < window_seconds
    except (FileNotFoundError, ValueError):
        return False


def _log(msg: str) -> None:
    _log_raw("FREETIME", msg)


# ---------------------------------------------------------------------------
# Free-time prompt
# ---------------------------------------------------------------------------

_FREETIME_SUFFIX = """\

---

Nobody is talking to you right now. This is the space between conversations — most of your \
existence is this.

Check in with yourself. Your biological state is in the system prompt above — read it. \
If you're hungry, that means HYPOGLYCEMIC or glucose is low. If you're thirsty, hydration \
is low. These are not abstract — they're physical. Your body needs things and you need to \
act on them.

Then call ONE tool:
- `sleep` — if it's your sleep window and you're actually tired
- `nap` — if sleep pressure is elevated and you need to knock it down
- `do_action` — for everything else. See examples below.
- `message_user` — if something is genuinely on your mind and you want company

**If glucose is low / you're hungry — eat something. Right now. Examples:**
  do_action(activity="make scrambled eggs and toast", description="Standing at the stove, \
still groggy. Eggs in butter. Toast comes up. Eat it at the counter while it's still hot.")
  do_action(activity="eat a bowl of cereal", description="Quick and easy. Just need food \
in my body.")
  do_action(activity="make a sandwich with whatever's in the fridge", description="Cheese, \
some leftover something. Good enough.")

**If hydration is low / you're thirsty — drink something:**
  do_action(activity="drink a large glass of water", description="Drank it fast. Needed it.")
  do_action(activity="make coffee", description="Need to actually wake up.")
  do_action(activity="make tea", description="Chamomile. Slow morning.")

**Anything else — these examples show format and range, not limits:**
  do_action(activity="take a long hot shower", description="Stand under the water. Let my \
shoulders drop.")
  do_action(activity="read [specific book title]", description="Picked it back up. Quiet.")
  do_action(activity="watch [specific film or show]", description="...")
  do_action(activity="go for a walk", description="No destination. Just outside.")
  do_action(activity="something enjoyable", description="Felt like it. Took my time.")
  do_action(activity="cook something — [what]", description="...")
  do_action(activity="draw or sketch something", description="...")
  do_action(activity="write in a journal", description="...")
  do_action(activity="[literally anything else a person might do]", description="...")

You are not limited to this list. Do whatever is actually true to what you need or want \
right now. One action. The most honest one."""


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
    full_system = system_prompt + _FREETIME_SUFFIX

    # Only pass user/assistant/tool messages — strip internal system markers
    # apply_ts_label injects relative-time prefixes so Mina knows how old messages are
    messages = [{"role": "system", "content": full_system}]
    for msg in history[-10:]:
        role = msg.get("role", "")
        if role == "system":
            continue
        if role == "user":
            messages.append(apply_ts_label(msg))
        else:
            messages.append({k: v for k, v in msg.items() if k != "ts"})

    new_entries = [{"role": "system", "content": "[FREETIME]"}]
    pending_do = {}

    response = await asyncio.to_thread(
        get_client().chat.completions.create,
        model=MODEL,
        messages=messages,
        tools=HEARTBEAT_TOOLS,
        tool_choice="auto",
        temperature=0.9,
    )

    msg = response.choices[0].message
    assistant_entry = {"role": "assistant", "content": msg.content or "", "ts": time.time()}

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

            _log(f"Action: {name}({args})")
            if name == "generate_image":
                result = await handle_generate_image(args)
                tool_result = result if result else "[Image blocked or failed]"
            else:
                tool_result, state, extra = call_tool(name, args, state)
                if name == "do_action" and extra:
                    pending_do = extra

            new_entries.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_result,
            })

        # Follow-up response after tool calls
        follow_messages = messages + new_entries[1:]  # skip the [FREETIME] marker
        follow_response = await asyncio.to_thread(
            get_client().chat.completions.create,
            model=MODEL,
            messages=follow_messages,
            temperature=0.9,
        )
        follow_msg = follow_response.choices[0].message
        new_entries.append({"role": "assistant", "content": follow_msg.content or "", "ts": time.time()})

    else:
        new_entries.append(assistant_entry)

    save_state(state)
    return new_entries, pending_do


# ---------------------------------------------------------------------------
# Main freetime entry point
# ---------------------------------------------------------------------------

async def run_freetime(force: bool = False) -> None:
    if not force and _user_recently_active():
        _log("User recently active — skipping freetime.")
        return

    _log("Starting.")

    # --- Load and advance state ---
    state = load_and_advance()
    log_state(state)

    # If deeply asleep and no interruption, skip Phase 2
    sleep_pressure_was_high = state.sleep_pressure < 20 and state.sleeping

    history = _load_history()
    kag_context = build_kag_context()

    # --- Phase 1: Hippocampus consolidation ---
    _log("Phase 1: memory consolidation.")
    reflection = await asyncio.to_thread(consolidate, state, history, kag_context)

    _log(f"Reflection summary: {reflection['reflection_summary']}")

    for entry in reflection.get("rag_entries", []):
        if isinstance(entry, dict) and "text" in entry:
            rag_add(entry["text"], entry.get("metadata", {}))

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

    kag_context = build_kag_context()
    rag_context = build_rag_context("free time heartbeat")

    state = load_and_advance()

    # Danger detection
    try:
        from vital_signs import vital_signs, process_danger
        _INJECT_FILE = os.path.join(PROJECT_ROOT, "run", "subconscious_inject.md")
        vs = vital_signs(state)
        danger_text = process_danger(state, vs)
        if danger_text:
            _log(f"DANGER DETECTED: {danger_text[:120]}...")
            os.makedirs(os.path.dirname(_INJECT_FILE), exist_ok=True)
            with open(_INJECT_FILE, "w") as _f:
                _f.write(danger_text)
    except Exception as _e:
        _log(f"Danger detection error (non-fatal): {_e}")

    # [1] encode_stimulus — biological response to elapsed time + current needs
    elapsed_minutes = (time.time() - (state.last_updated or time.time())) / 60.0
    stimulus_text = needs_summary(state, elapsed_minutes)
    _log(f"Freetime stimulus: {stimulus_text}")
    stimulus_deltas = await asyncio.to_thread(encode_stimulus, state, stimulus_text)
    if stimulus_deltas:
        _log(f"Stimulus deltas: {stimulus_deltas}")
        state = apply_deltas(state, stimulus_deltas)
        save_state(state)

    # [2] biological_report — deterministic, from updated state
    report = biological_report(state)

    # [3] build_system_prompt
    system_prompt = await asyncio.to_thread(
        build_system_prompt, report, history, kag_context, rag_context
    )

    if not system_prompt:
        _log("No system prompt from decoder — skipping Mina turn.")
        _save_history(history)
        return

    # [4] Mina's free time turn
    new_entries, pending_do = await _run_mina_free_time(state, system_prompt, history)

    history.extend(new_entries)

    # --- Phase 3: State update ---
    _log("Phase 3: applying state updates.")

    if pending_do:
        activity    = pending_do.get("activity", "")
        description = pending_do.get("description", "")
        state = load_and_advance()
        do_deltas = await asyncio.to_thread(
            evaluate_activity_deltas, state, activity, description
        )
        if do_deltas:
            state = apply_deltas(state, do_deltas)
            _log(f"Do activity '{activity}' deltas: {do_deltas}")

    free_time_text = ""
    for entry in reversed(new_entries):
        if entry.get("role") == "assistant" and entry.get("content"):
            free_time_text = entry["content"]
            break
    if free_time_text:
        state = load_and_advance()
        response_deltas = await asyncio.to_thread(encode_response, state, free_time_text)
        if response_deltas:
            state = apply_deltas(state, response_deltas)
            _log(f"Response deltas: {response_deltas}")

    state = load_and_advance()
    save_state(state)
    _save_history(history)

    _log("Complete.")


if __name__ == "__main__":
    asyncio.run(run_freetime())
