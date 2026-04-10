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

from bio_report import biological_report, needs_summary
from memory import build_kag_context, build_rag_context, rag_add, read_kag, write_kag
import checkpoints
from state import (
    BiologicalState,
    apply_deltas,
    derived,
    load_and_advance,
    log_state,
    save_state,
)
from subconscious import encode_response, encode_stimulus, evaluate_activity_deltas, run_mode1, run_mode2
from tools_mina import HEARTBEAT_TOOLS, call_tool, handle_generate_image

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_HISTORY_FILE = os.path.join(_PROJECT_ROOT, "run", "conversation.json")
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

Nobody is talking to you right now. This is the space between conversations — most of your \
existence is this.

Check in with yourself. How do you actually feel right now? What does your body need? What's \
on your mind?

Then do ONE thing in response to that. If you're hungry, eat. If you're tired, sleep or rest. \
If you're thirsty, drink something. If you're restless or bored, do something (read, listen to \
music, whatever actually sounds good). If you want company or have something on your mind, \
message the user.

One action. The most honest one. Then you're done."""


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

    response = await asyncio.to_thread(
        client.chat.completions.create,
        model=MODEL,
        messages=messages,
        tools=HEARTBEAT_TOOLS,
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

            _log(f"Action: {name}({args})")
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
        follow_response = await asyncio.to_thread(
            client.chat.completions.create,
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
# Main heartbeat entry point
# ---------------------------------------------------------------------------

async def run_heartbeat(force: bool = False) -> None:
    if not force and _user_recently_active():
        _log("User recently active — skipping heartbeat.")
        return

    _log("Starting.")

    # --- Checkpoint before doing anything else ---
    try:
        ckpt = checkpoints.save(label="heartbeat")
        _log(f"Checkpoint saved: {os.path.basename(ckpt)}")
    except Exception as e:
        _log(f"Checkpoint failed (non-fatal): {e}")

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
    reflection = await asyncio.to_thread(run_mode2, state, history, kag_context)

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

    # Re-advance state in case time passed during Mode 2
    state = load_and_advance()

    # --- Danger detection (SPEC-11) ---
    try:
        from vital_signs import vital_signs, process_danger
        _INJECT_FILE = os.path.join(_PROJECT_ROOT, "run", "subconscious_inject.md")
        vs = vital_signs(state)
        danger_text = process_danger(state, vs)
        if danger_text:
            _log(f"DANGER DETECTED: {danger_text[:120]}...")
            # Write to inject file — picked up by run_mode1 system prompt
            os.makedirs(os.path.dirname(_INJECT_FILE), exist_ok=True)
            with open(_INJECT_FILE, "w") as _f:
                _f.write(danger_text)
    except Exception as _e:
        _log(f"Danger detection error (non-fatal): {_e}")

    # [1] encode_stimulus — biological response to elapsed time + current needs
    elapsed_minutes = (time.time() - (state.last_updated or time.time())) / 60.0
    stimulus_text = needs_summary(state, elapsed_minutes)
    _log(f"Heartbeat stimulus: {stimulus_text}")
    stimulus_deltas = await asyncio.to_thread(encode_stimulus, state, stimulus_text)
    if stimulus_deltas:
        _log(f"Stimulus deltas: {stimulus_deltas}")
        state = apply_deltas(state, stimulus_deltas)
        save_state(state)

    # [2] biological_report — deterministic, from updated state
    report = biological_report(state)

    # [3] generate_system_prompt — Mode 1
    system_prompt = await asyncio.to_thread(run_mode1, report, history, kag_context, rag_context)

    if not system_prompt:
        _log("No system prompt from subconscious — skipping Mina turn.")
        _save_history(history)
        return

    # [4] Mina's free time turn
    new_entries, pending_do = await _run_mina_free_time(state, system_prompt, history)

    # Append heartbeat entries to shared history
    history.extend(new_entries)

    # --- Phase 3: State update ---
    _log("Phase 3: applying state updates.")

    # [5a] do-activity deltas (if she used the do tool)
    if pending_do:
        activity = pending_do.get("activity", "")
        description = pending_do.get("description", "")
        state = load_and_advance()
        do_deltas = await asyncio.to_thread(evaluate_activity_deltas, state, activity, description)
        if do_deltas:
            state = apply_deltas(state, do_deltas)
            _log(f"Do activity '{activity}' deltas: {do_deltas}")

    # [5b] encode_response — biological effect of what Mina said/did during free time
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

    # Final time advance + save
    state = load_and_advance()
    save_state(state)
    _save_history(history)

    _log("Complete.")


if __name__ == "__main__":
    asyncio.run(run_heartbeat())
