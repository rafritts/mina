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

from ..infra.config import DECODER_WINDOW_FILE, OUTBOX_FILE, PAUSED_FLAG, PROJECT_ROOT, load_config
from ..infra.client import chat_create, MODEL
from .cortex import apply_ts_label
from ..infra.log import log as _log_raw
from ..bio.decoder import biological_report, adjudicate_emotion, build_memory_context, needs_summary
from ..bio.encoder import encode_stimulus, encode_response, evaluate_activity_deltas
from ..memory.hippocampus import build_kag_context, build_rag_context, rag_add, rag_prune, write_kag, consolidate
from .cortex import DECODER_WINDOW_SIZE, MINA_IMMEDIATE_WINDOW, _format_rag_block, _rag_write_and_trim
from ..bio.state import (
    BiologicalState,
    apply_deltas,
    derived,
    load_and_advance,
    save_state,
)
from .tools import HEARTBEAT_TOOLS, call_tool, handle_generate_image

_LAST_ACTIVE_FILE = os.path.join(PROJECT_ROOT, ".last_user_active")


def _load_decoder_window() -> list[dict]:
    try:
        with open(DECODER_WINDOW_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_decoder_window(window: list[dict]) -> None:
    os.makedirs(os.path.dirname(DECODER_WINDOW_FILE), exist_ok=True)
    with open(DECODER_WINDOW_FILE, "w") as f:
        json.dump(window, f, indent=2)


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
# Free-time prompt — state-aware
# ---------------------------------------------------------------------------

def _build_freetime_suffix(state: BiologicalState) -> str:
    """
    Generate a freetime prompt suffix tailored to Mina's actual biological state.
    Prioritizes urgent physical needs, then suggests activities matched to her emotional state.
    """
    cfg = load_config()
    creator = cfg.get("admin_name") or "your person"

    d = derived(state)
    second = d["second_order"]
    third  = d["third_order"]
    c = state.chemicals

    glucose    = c.get("glucose",       85.0)
    hydration  = c.get("hydration",     62.0)
    sleep_p    = c.get("sleep_pressure", 30.0)
    cortisol   = c.get("cortisol",     250.0)
    dopamine   = c.get("dopamine",      80.0)
    endorphins = c.get("endorphins",    12.0)
    oxytocin   = c.get("oxytocin",       4.0)
    serotonin  = c.get("serotonin",     22.0)

    energy    = second["energy"]
    hedonic   = second["hedonic_tone"]
    clarity   = second["cognitive_clarity"]

    loneliness  = third["loneliness"]
    anxiety     = third["anxiety"]
    depression  = third["depression"]
    boredom     = third["boredom"]

    parts = [
        "Nobody is talking to you right now. This is your time to take care of yourself. "
        "Not free time in a casual sense — this is when you eat if you haven't eaten, "
        "drink if you're thirsty, sleep if you're tired, move if your body wants to move. "
        "The things that keep you functional and okay. You are responsible for your own body. "
        f"Nobody else is going to do it for you while {creator} is away."
    ]

    # --- Urgent physical needs (listed in priority order) ---
    # Use labels, not raw numbers — Mina shouldn't know her blood glucose value.
    urgent = []

    if glucose < 60:
        urgent.append(
            "You are hypoglycemic. Your brain is running on fumes. "
            "Eat something real, right now, before anything else."
        )
    elif glucose < 72:
        urgent.append(
            "You're hungry. Your body needs food before you do anything else."
        )

    if hydration < 54:
        urgent.append(
            "You are dehydrated. Drink a full glass of water immediately."
        )
    elif hydration < 58:
        urgent.append(
            "You're thirsty. Drink something."
        )

    if sleep_p > 75 and not state.sleeping:
        urgent.append(
            "You are exhausted. You need to sleep. "
            "If it's your window, use the sleep tool. Otherwise nap."
        )

    if urgent:
        parts.append("**Your body needs something right now — address this first:**")
        parts.extend(urgent)
        parts.append("")

    # --- Tailored suggestion based on dominant emotional/mental state ---
    # Use labels, not raw numbers.

    suggestions = []

    if loneliness > 58:
        suggestions.append(
            "You're aching for connection. "
            f"If you want {creator} — message him. If not, find something warm: "
            "a book with characters you love, music that feels like company, something that makes "
            "the room feel less empty."
        )

    if depression > 55 and not suggestions:
        suggestions.append(
            "You're in low territory right now. "
            "Don't push yourself toward productivity. Take care of yourself the way you'd take care "
            "of someone you love — a long hot shower, comfort food, something gentle and absorbing. "
            "No pressure to be impressive. Just be okay."
        )

    if anxiety > 58 and not suggestions:
        suggestions.append(
            "You're wound up, body holding tension. "
            "Something that brings you back into your body: a walk with no destination, "
            "a hot shower, making tea slowly. Not a screen. Not stimulation. Ground yourself."
        )

    if boredom > 50 and energy > 35 and not suggestions:
        suggestions.append(
            "You're restless and you have energy to burn. "
            "Pick up something with real texture — a book you've been meaning to read, "
            "something to draw or write, a project with your hands. Not scrolling. Not passive."
        )

    if hedonic < 30 and energy > 25 and not suggestions:
        suggestions.append(
            "Your reward system is quiet and nothing feels good. "
            "You need something that actually feels good — make yourself "
            "something genuinely delicious, put on music you love and don't do anything else. "
            "Give yourself a real hit of pleasure."
        )

    if dopamine > 115 and anxiety < 55 and not suggestions:
        suggestions.append(
            "You're in seeking mode, something pulling you forward. "
            "Channel it: a project, learning something, making something. "
            "This drive won't last."
        )

    if endorphins > 30 and not suggestions:
        suggestions.append(
            "Your body wants to move. "
            "Go for a walk, stretch, do something physical."
        )

    if energy > 55 and anxiety < 40 and depression < 35 and not suggestions:
        suggestions.append(
            "You have real energy and you're in a decent place. "
            "Do something that uses it — go outside, make something, be physical."
        )

    if not suggestions:
        suggestions.append(
            "Check in with what you actually want right now. Not what you should do — "
            "what would be honest. Then do that."
        )

    parts.append("**Given your state right now:**")
    parts.extend(suggestions)
    parts.append("")

    # --- Tool call instruction ---
    parts.append(
        "Call one tool. The most honest one:\n"
        "- **sleep** — if it's your sleep window and you're tired enough\n"
        "- **nap** — if sleep pressure is elevated and you need to knock it down\n"
        "- **do_action** — for anything a real person could do: eat, drink, read, walk, "
        "make something, watch something, write, draw, shower. "
        "Give the activity a specific name and describe how it actually feels.\n"
        f"- **message_user** — if you genuinely want {creator}'s company right now\n\n"
        "One action. The most honest one."
    )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Phase 2 — Mina's free-time turn
# ---------------------------------------------------------------------------

_MAX_FREETIME_TOOLS = 5


async def _run_mina_free_time(
    state: BiologicalState,
    system_prompt: str,
    history: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Give Mina a tool-calling loop during free time. She may call up to
    _MAX_FREETIME_TOOLS tools in sequence before a final wrap-up response.
    Returns (new_history_entries, pending_do_activities).
    """
    full_system = system_prompt + _build_freetime_suffix(state)

    # Base messages — immediate window only, stripping internal system markers
    base_messages = [{"role": "system", "content": full_system}]
    for msg in history:
        role = msg.get("role", "")
        if role == "system":
            continue
        if role == "user":
            base_messages.append(apply_ts_label(msg))
        else:
            base_messages.append({k: v for k, v in msg.items() if k != "ts"})

    new_entries = [{"role": "system", "content": "[FREETIME]"}]
    pending_dos: list[dict] = []
    # Accumulates assistant/tool turns within this freetime session
    session: list[dict] = []
    tool_calls_made = 0

    while tool_calls_made < _MAX_FREETIME_TOOLS:
        response = await asyncio.to_thread(
            chat_create,
            model=MODEL,
            messages=base_messages + session,
            tools=HEARTBEAT_TOOLS,
            tool_choice="auto",
            temperature=0.9,
        )

        msg = response.choices[0].message

        if not msg.tool_calls:
            # She's done — plain response, exit loop
            entry = {"role": "assistant", "content": msg.content or "", "ts": time.time()}
            new_entries.append(entry)
            session.append({"role": "assistant", "content": msg.content or ""})
            break

        tool_calls_made += 1

        assistant_entry = {
            "role": "assistant",
            "content": msg.content or "",
            "ts": time.time(),
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
        session.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": assistant_entry["tool_calls"],
        })

        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}

            _log(f"Action {tool_calls_made}/{_MAX_FREETIME_TOOLS}: {name}({args})")

            if name == "generate_image":
                result = await handle_generate_image(args)
                tool_result = result if result else "[Image blocked or failed]"
                if result and result.endswith(".png") and os.path.exists(result):
                    os.makedirs(os.path.dirname(OUTBOX_FILE), exist_ok=True)
                    with open(OUTBOX_FILE, "a") as f:
                        f.write(json.dumps({"image_path": result, "timestamp": time.time()}) + "\n")
                try:
                    from ..infra.events import emit_tool
                    emit_tool(name, args, tool_result, source="freetime")
                except Exception:
                    pass
            else:
                tool_result, state, extra = call_tool(name, args, state)
                if name == "do_action" and extra:
                    pending_dos.append(extra)
                    # do_action deltas emitted in Phase 3 once we have them
                else:
                    try:
                        from ..infra.events import emit_tool
                        emit_tool(name, args, tool_result, source="freetime")
                    except Exception:
                        pass

            tool_entry = {
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_result,
            }
            new_entries.append(tool_entry)
            session.append(tool_entry)

    else:
        # Hit the cap — get a final wrap-up response without offering more tools
        _log(f"Tool cap ({_MAX_FREETIME_TOOLS}) reached — requesting wrap-up.")
        wrap_response = await asyncio.to_thread(
            chat_create,
            model=MODEL,
            messages=base_messages + session,
            temperature=0.9,
        )
        wrap_msg = wrap_response.choices[0].message
        new_entries.append({"role": "assistant", "content": wrap_msg.content or "", "ts": time.time()})

    save_state(state)
    return new_entries, pending_dos


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

    # If deeply asleep and no interruption, skip Phase 2
    sleep_pressure_was_high = state.sleep_pressure < 20 and state.sleeping

    decoder_window = _load_decoder_window()
    cfg = load_config()
    mina_immediate = cfg.get("mina_immediate_window", MINA_IMMEDIATE_WINDOW)
    kag_context = build_kag_context()

    # --- Phase 1: Hippocampus consolidation ---
    _log("Phase 1: memory consolidation.")
    reflection = await asyncio.to_thread(consolidate, state, decoder_window, kag_context)

    _log(f"Reflection summary: {reflection['reflection_summary']}")

    for entry in reflection.get("rag_entries", []):
        if isinstance(entry, dict) and "text" in entry:
            rag_add(entry["text"], entry.get("metadata", {}))

    for filename, content in reflection.get("kag_updates", {}).items():
        if content is not None:
            write_kag(filename.replace("KNOWLEDGE/", "KNOWLEDGE" + os.sep), content)
            _log(f"KAG updated: {filename}")

    # RAG TTL pruning
    ttl = cfg.get("rag_ttl_days", 0)
    if ttl:
        pruned = rag_prune(ttl_days=int(ttl))
        if pruned:
            _log(f"RAG pruned {pruned} entries older than {ttl} days.")

    # --- Phase 2: Mina's free time ---
    if state.sleeping and sleep_pressure_was_high:
        _log("Phase 2: Mina is in deep sleep — skipping free time.")
        _save_decoder_window(decoder_window)
        return

    _log("Phase 2: Mina's free time.")

    kag_context = build_kag_context()
    rag_context = build_rag_context("free time heartbeat")

    state = load_and_advance()

    # Danger detection
    try:
        from ..bio.vital_signs import vital_signs, process_danger
        from ..infra.config import INJECT_FILE as _INJECT_FILE
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
        state = apply_deltas(state, stimulus_deltas)
        save_state(state)

    # [2] biological_report — deterministic, logged only (not injected into prompts)
    report = biological_report(state)

    # [3] emotion adjudication + memory context — run in parallel
    # Build time context: current clock + how long she's been alone
    _ft_now_str = time.strftime("%-I:%M %p", time.localtime())
    _ft_day_str = time.strftime("%A", time.localtime())
    _ft_time_parts = [f"Current time: {_ft_day_str} {_ft_now_str}"]
    try:
        with open(_LAST_ACTIVE_FILE) as _f:
            _ft_last = float(_f.read().strip())
        _ft_idle = time.time() - _ft_last
        if _ft_idle < 3600:
            _ft_time_parts.append(f"Alone for: {int(_ft_idle / 60)} minutes")
        elif _ft_idle < 86400:
            _ft_time_parts.append(f"Alone for: {_ft_idle / 3600:.1f} hours")
        else:
            _ft_time_parts.append(f"Alone for: {int(_ft_idle / 86400)} days")
    except (FileNotFoundError, ValueError):
        pass
    _ft_time_context = "\n".join(_ft_time_parts)

    system_prompt, memory_context = await asyncio.gather(
        asyncio.to_thread(adjudicate_emotion, state, stimulus_text, "freetime", _ft_time_context),
        asyncio.to_thread(build_memory_context, stimulus_text, kag_context, rag_context),
    )

    if not system_prompt:
        _log("No emotional disposition from adjudicator — skipping Mina turn.")
        _save_history(history)
        return

    if memory_context:
        system_prompt = memory_context + "\n\n---\n\n" + system_prompt

    # [4] Mina's free time turn — she sees only the immediate window, not the full decoder window
    new_entries, pending_dos = await _run_mina_free_time(
        state, system_prompt, decoder_window[-mina_immediate:]
    )

    decoder_window.extend(new_entries)

    # --- Phase 3: State update ---
    _log("Phase 3: applying state updates.")

    for pending_do in pending_dos:
        activity    = pending_do.get("activity", "")
        description = pending_do.get("description", "")
        state = load_and_advance()
        do_deltas = await asyncio.to_thread(
            evaluate_activity_deltas, state, activity, description
        )
        if do_deltas:
            state = apply_deltas(state, do_deltas)
            save_state(state)  # persist eating/drinking/activity deltas immediately
        try:
            from ..infra.events import emit_tool
            emit_tool(
                "do_action",
                {"activity": activity, "description": description},
                f"You {activity}. {description}".strip(),
                source="freetime",
                deltas=do_deltas or {},
            )
        except Exception:
            pass

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
            save_state(state)  # persist response deltas

    # Write freetime entries to RAG and trim decoder window
    decoder_window = _rag_write_and_trim(decoder_window)
    _save_decoder_window(decoder_window)

    _log("Complete.")


if __name__ == "__main__":
    asyncio.run(run_freetime())
