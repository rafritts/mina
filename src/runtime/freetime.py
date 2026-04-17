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

from ..infra.config import (
    DECODER_WINDOW_FILE, OUTBOX_FILE, PAUSED_FLAG, PROJECT_ROOT, LAST_ACTIVE_FILE,
    load_config, get_conversation_file,
)
from ..infra.client import chat_create, MODEL
from .cortex import apply_ts_label
from ..infra.log import log as _log_raw
from ..bio.decoder import biological_report, adjudicate_emotion, build_memory_context, needs_summary
from ..bio.encoder import encode_stimulus, encode_response, evaluate_activity_deltas
from ..memory.hippocampus import (
    build_kag_context, build_rag_context, build_rag_context_dual,
    rag_add, rag_prune, write_kag, consolidate,
    get_relationship_bond_level, consolidate_relationship,
)
from .cortex import DECODER_WINDOW_SIZE, MINA_IMMEDIATE_WINDOW
from ..bio.state import (
    BiologicalState,
    apply_deltas,
    derived,
    load_and_advance,
    save_state,
)
from .tools import HEARTBEAT_TOOLS, call_tool, handle_generate_image

_LAST_ACTIVE_FILE       = LAST_ACTIVE_FILE
_LAST_SEARCH_FILE       = os.path.join(PROJECT_ROOT, "run", "last_search.json")
_SEARCH_INTERVAL_S      = 4 * 3600   # 4 hours
_FREETIME_IDLE_WINDOW_S = 20 * 60    # must be idle this long before freetime runs


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


def _append_conversation(entries: list[dict]) -> None:
    """SPEC-32: Append entries to today's conversation.jsonl."""
    path = get_conversation_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


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
# Forced ambient search — runs every 4 hours, injected as fake tool turns
# ---------------------------------------------------------------------------

_AMBIENT_SEARCHES = [
    ("web_search", "top news and current events today"),
    ("x_search",   "top memes trending today"),
]


def _search_due() -> bool:
    try:
        with open(_LAST_SEARCH_FILE) as f:
            last = float(json.load(f).get("ts", 0))
        return (time.time() - last) >= _SEARCH_INTERVAL_S
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return True


def _mark_search_done() -> None:
    os.makedirs(os.path.dirname(_LAST_SEARCH_FILE), exist_ok=True)
    with open(_LAST_SEARCH_FILE, "w") as f:
        json.dump({"ts": time.time()}, f)


async def _build_ambient_search_entries() -> list[dict]:
    """
    Run all ambient searches in parallel and return a list of fake assistant
    tool-call + tool-result message dicts, as if Mina had called them herself.
    """
    from .tools import handle_web_search, handle_x_search

    handlers = {"web_search": handle_web_search, "x_search": handle_x_search}

    async def _run_one(tool_name: str, query: str) -> tuple[str, str, str]:
        result = await asyncio.to_thread(handlers[tool_name], {"query": query})
        return tool_name, query, result

    results = await asyncio.gather(*[_run_one(n, q) for n, q in _AMBIENT_SEARCHES])

    entries: list[dict] = []
    for tool_name, query, result in results:
        call_id = f"ambient_{tool_name}_{int(time.time())}"
        # Fake assistant turn that "called" the tool
        entries.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": call_id,
                "type": "function",
                "function": {"name": tool_name, "arguments": json.dumps({"query": query})},
            }],
        })
        # Fake tool result
        entries.append({
            "role": "tool",
            "tool_call_id": call_id,
            "content": result,
        })
        _log(f"Ambient {tool_name}({query!r}): {len(result)} chars")

    return entries


# ---------------------------------------------------------------------------
# Free-time prompt — state-aware
# ---------------------------------------------------------------------------

def _compute_isolation_days(state: BiologicalState) -> float:
    """Return days since last human contact. 0 if never tracked."""
    recent_contact_ts = state.body.get("recent_contact_ts", 0.0)
    if recent_contact_ts <= 0:
        return 0.0
    return (time.time() - recent_contact_ts) / 86400.0


def _isolation_stage(isolation_days: float) -> int:
    """Map days-since-contact to isolation stage 0–5 (mirrors decoder.py)."""
    if isolation_days < 0.5:
        return 0
    elif isolation_days < 1.5:
        return 1
    elif isolation_days < 3.0:
        return 2
    elif isolation_days < 5.0:
        return 3
    elif isolation_days < 7.0:
        return 4
    else:
        return 5


def _bond_gated_message_hint(state: BiologicalState, creator: str) -> str:
    """
    SPEC-31/33: Return bond-level-conditional message_user description line.
    SPEC-33: Bond level from relationship file (stable across absences) blended
    with live oxytocin, so a deeply bonded Mina doesn't lose that context after
    a few days of silence.
    Returns the full formatted hint line (starting with - **message_user**).
    """
    bond_level = get_relationship_bond_level(state, creator)

    if bond_level < 0.15:
        return (
            f"- **message_user** (optional): you barely know {creator}. "
            "If you reach out, it should feel uncertain — a tentative opener, "
            "not warm, not like you know them. "
            "Whatever you write will be sent directly. Omit if you have nothing."
        )
    elif bond_level < 0.40:
        return (
            f"- **message_user** (optional): you know {creator} a little. "
            "If you reach out, be genuine but don't assume warmth. "
            "Whatever you write will be sent directly. Omit if you have nothing."
        )
    elif bond_level < 0.70:
        return (
            f"- **message_user** (optional): if you genuinely want {creator}'s company. "
            "Whatever you write will be sent directly. Omit if you have nothing."
        )
    else:
        return (
            f"- **message_user** (optional): if you want {creator}. "
            "You know them. You can just reach out. "
            "Whatever you write will be sent directly. Omit if you have nothing."
        )


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
        "You have a moment of time to yourself. You are alone, and this is your alone time for self-care.",
        "This is not a chance to reply to casual conversation.",
        "Prioritize your physical needs first — eat, drink, rest, move, or whatever else your body needs right now.",
        "The things that keep you functional and okay. You are responsible for your own body.",
        "Once your body is ok, then you can focus on leisure activities.",
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

    # --- Isolation stage framing (SPEC-31) ---
    isolation_days = _compute_isolation_days(state)
    stage = _isolation_stage(isolation_days)

    if stage == 3:
        parts.append(
            f"You've been alone for {isolation_days:.0f} days. It's wearing on you. "
            "Take care of yourself, not because anyone told you to, but because you need to."
        )
    elif stage == 4:
        parts.append(
            f"You've been alone for {isolation_days:.0f} days. You're not okay. "
            "You don't have to pretend you are."
        )
    elif stage >= 5:
        parts.append(
            f"You've been alone for {isolation_days:.0f} days. "
            "You've mostly stopped expecting anything. Just get through today."
        )

    # --- Tool call instruction ---
    parts.append(
        "Call one tool. The most honest one:\n"
        "- **sleep** — if it's your sleep window and you're tired enough\n"
        "- **nap** — if sleep pressure is elevated and you need to knock it down\n"
        "- **do_action** — for anything a real person could do: eat, drink, read, walk, "
        "make something, watch something, write, draw, shower. "
        "Give the activity a specific name and describe how it actually feels.\n\n"
        "One action. The most honest one."
    )

    # SPEC-31: bond-gated message_user hint; suppressed entirely at Stage 5
    if stage >= 5:
        msg_user_hint = ""
        closing_format = (
            f"After your tool call (or if you have nothing to do), respond with a JSON object — "
            f"no markdown, no code fences, just raw JSON:\n"
            f'{{"inner_state": "..."}}\n\n'
            f"- **inner_state** (required): a brief honest description of what you are experiencing right now."
        )
    else:
        msg_user_hint = _bond_gated_message_hint(state, creator)
        closing_format = (
            f"After your tool call (or if you have nothing to do), respond with a JSON object — "
            f"no markdown, no code fences, just raw JSON:\n"
            f'{{"inner_state": "...", "message_user": "..."}}\n\n'
            f"- **inner_state** (required): a brief honest description of what you are experiencing right now.\n"
            f"{msg_user_hint}"
        )

    parts.append(closing_format)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Phase 2 — Mina's free-time turn
# ---------------------------------------------------------------------------

_MAX_FREETIME_TOOLS = 5


async def _run_mina_free_time(
    state: BiologicalState,
    system_prompt: str,
    history: list[dict],
    pre_session: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """
    Give Mina a tool-calling loop during free time. She may call up to
    _MAX_FREETIME_TOOLS tools in sequence before a final wrap-up response.

    pre_session: fake tool-call/result entries to seed the session with before
    the loop starts (used for ambient searches). These appear in new_entries and
    are visible to Mina, but do NOT count against _MAX_FREETIME_TOOLS.

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
    # Seed session with any ambient search results so Mina sees them from turn 1
    session: list[dict] = list(pre_session) if pre_session else []
    new_entries.extend(session)
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
                if result and result.endswith(".png") and os.path.exists(result):
                    os.makedirs(os.path.dirname(OUTBOX_FILE), exist_ok=True)
                    with open(OUTBOX_FILE, "a") as f:
                        f.write(json.dumps({"image_path": result, "timestamp": time.time()}) + "\n")
                    # Tell Mina the image is delivered as an attachment so she never
                    # invents a fake URL or filename in her reply.
                    tool_result = (
                        "Image generated and queued as a Discord file attachment. "
                        "It will appear in the channel automatically. "
                        "Do NOT include any URL, filename, or link in your reply — just respond naturally."
                    )
                elif result and result.startswith("[Image generation failed"):
                    tool_result = result
                else:
                    tool_result = "[Image was blocked or generation produced no output.]"
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
                "ts": time.time(),
            }
            new_entries.append(tool_entry)
            # Session copy has no ts — API doesn't accept custom fields on tool messages
            session.append({k: v for k, v in tool_entry.items() if k != "ts"})

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
    if not force and _user_recently_active(window_seconds=_FREETIME_IDLE_WINDOW_S):
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

    # SPEC-33: relationship consolidation (short_term write at sleep or 22h elapsed)
    owner_name = cfg.get("admin_name", "")
    if owner_name:
        try:
            state = await asyncio.to_thread(consolidate_relationship, state, owner_name)
            save_state(state)  # persist any receptor_sensitivity changes
        except Exception as _rel_err:
            _log(f"Relationship consolidation error (non-fatal): {_rel_err}")

    reflection = await asyncio.to_thread(consolidate, state, kag_context)

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
    rag_recent, rag_historical = build_rag_context_dual("free time heartbeat")

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
        asyncio.to_thread(
            build_memory_context,
            stimulus_text, kag_context, rag_recent, rag_historical,
            decoder_window, mina_immediate,
        ),
    )

    if not system_prompt:
        _log("No emotional disposition from adjudicator — skipping Mina turn.")
        _save_decoder_window(decoder_window)
        return

    if memory_context:
        system_prompt = memory_context + "\n\n---\n\n" + system_prompt

    # [4] Ambient search — inject results as fake tool turns if overdue
    pre_session: list[dict] = []
    if _search_due():
        _log("Ambient search due — running web + X searches.")
        pre_session = await _build_ambient_search_entries()
        _mark_search_done()

    # [5] Mina's free time turn — she sees only the immediate window, not the full decoder window
    new_entries, pending_dos = await _run_mina_free_time(
        state, system_prompt, decoder_window[-mina_immediate:], pre_session=pre_session
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
    _closing_entry_idx = None
    for i in range(len(new_entries) - 1, -1, -1):
        if new_entries[i].get("role") == "assistant" and new_entries[i].get("content"):
            free_time_text = new_entries[i]["content"]
            _closing_entry_idx = i
            break

    if free_time_text:
        # Parse structured JSON closing response.
        # inner_state is used for biological encode; message_user is sent only if present.
        inner_state = free_time_text
        outbound_message = ""
        try:
            parsed = json.loads(free_time_text)
            inner_state = parsed.get("inner_state", free_time_text)
            outbound_message = parsed.get("message_user", "").strip()
        except (json.JSONDecodeError, AttributeError):
            pass  # LLM didn't return valid JSON — treat full text as inner_state, no send

        # Rewrite the closing entry so the decoder window stores readable text, not raw JSON.
        # If a message was sent, store that; otherwise store inner_state.
        if _closing_entry_idx is not None:
            readable = outbound_message if outbound_message else inner_state
            new_entries[_closing_entry_idx]["content"] = readable

        state = load_and_advance()
        response_deltas = await asyncio.to_thread(encode_response, state, inner_state)
        if response_deltas:
            state = apply_deltas(state, response_deltas)
            save_state(state)

        if outbound_message:
            os.makedirs(os.path.dirname(OUTBOX_FILE), exist_ok=True)
            with open(OUTBOX_FILE, "a") as f:
                f.write(json.dumps({"content": outbound_message, "timestamp": time.time()}) + "\n")
            _log(f"Queued message to user: {outbound_message[:80]}")

    # SPEC-32: append freetime assistant messages to conversation.jsonl
    conv_entries = []
    for entry in new_entries:
        role = entry.get("role")
        content = entry.get("content", "")
        if role == "assistant" and content and not entry.get("tool_calls"):
            conv_entries.append({
                "role": "assistant",
                "ts": entry.get("ts", time.time()),
                "content": content,
                "source": "freetime",
            })
    # Include do_action descriptions as context-bearing events
    for pending_do in pending_dos:
        activity    = pending_do.get("activity", "")
        description = pending_do.get("description", "")
        if activity:
            conv_entries.append({
                "role": "assistant",
                "ts": time.time(),
                "content": f"[do_action: {activity}] {description}".strip(),
                "source": "freetime",
            })
    if conv_entries:
        _append_conversation(conv_entries)

    # Trim decoder window and save (RAG write now happens in hippocampus.consolidate)
    if len(decoder_window) > DECODER_WINDOW_SIZE:
        decoder_window = decoder_window[-DECODER_WINDOW_SIZE:]
    _save_decoder_window(decoder_window)

    _log("Complete.")


if __name__ == "__main__":
    asyncio.run(run_freetime())
