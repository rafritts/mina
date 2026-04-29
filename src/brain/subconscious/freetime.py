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

from src.config.config import (
    DECODER_WINDOW_FILE, PAUSED_FLAG, PROJECT_ROOT, LAST_ACTIVE_FILE,
    load_config, get_conversation_file,
)
from src.application.infra import discord_send as _discord_send
from src.application.infra.client import chat_create, MODEL
from src.brain.cortex.cortex import apply_ts_label
from src.application.infra.log import log as _log_raw
from src.brain.subconscious.decoder import biological_report, needs_summary, build_rag_context
from src.brain.cortex.emotional_reasoner import run_emotion_pillar, format_emotional_state_block
from src.brain.amygdala.stimulus_encoder import encode_stimulus, encode_response, evaluate_activity_deltas
from src.brain.hippocampus.hippocampus import (
    build_kag_context, build_rag_context, build_rag_context_dual,
    rag_add, rag_prune, write_kag, consolidate,
    consolidate_relationship,
)
from src.brain.cortex.cortex import DECODER_WINDOW_SIZE, MINA_IMMEDIATE_WINDOW
from src.brain.brainstem.state import (
    BiologicalState,
    apply_deltas,
    load_and_advance,
    save_state,
)
from src.brain.cortex.tools import HEARTBEAT_TOOLS, call_tool, format_tool_descriptions

_LAST_ACTIVE_FILE       = LAST_ACTIVE_FILE
_LAST_SEARCH_FILE       = os.path.join(PROJECT_ROOT, "run", "last_search.json")
_LAST_MSG_FILE          = os.path.join(PROJECT_ROOT, "run", "last_freetime_msg.json")
_SEARCH_INTERVAL_S      = 4 * 3600   # 4 hours
_FREETIME_IDLE_WINDOW_S = 20 * 60    # must be idle this long before freetime runs
_MSG_COOLDOWN_S         = 3600       # suppress identical outbound messages within 1 hour


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


def _message_recently_sent(content: str) -> bool:
    """True if this exact message was sent within _MSG_COOLDOWN_S seconds."""
    try:
        with open(_LAST_MSG_FILE) as f:
            rec = json.load(f)
        return rec.get("content") == content and (time.time() - rec.get("ts", 0)) < _MSG_COOLDOWN_S
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return False


def _mark_message_sent(content: str) -> None:
    os.makedirs(os.path.dirname(_LAST_MSG_FILE), exist_ok=True)
    with open(_LAST_MSG_FILE, "w") as f:
        json.dump({"content": content, "ts": time.time()}, f)


async def _build_ambient_search_entries() -> list[dict]:
    """Run ambient searches and return them as user context messages."""
    from src.brain.cortex.tools import handle_web_search, handle_x_search

    handlers = {"web_search": handle_web_search, "x_search": handle_x_search}

    async def _run_one(tool_name: str, query: str) -> tuple[str, str, str]:
        result = await asyncio.to_thread(handlers[tool_name], {"query": query})
        return tool_name, query, result

    results = await asyncio.gather(*[_run_one(n, q) for n, q in _AMBIENT_SEARCHES])

    entries: list[dict] = []
    for tool_name, query, result in results:
        entries.append({
            "role": "user",
            "content": f"[Background {tool_name}: {query!r}]\n{result}",
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



def _build_freetime_suffix(state: BiologicalState) -> str:
    from src.brain.subconscious.profile import _build_emotional_profile
    from src.brain.subconscious.snapshot_history import load_bio_snapshots

    prior_snapshots = load_bio_snapshots(3)
    profile = _build_emotional_profile(state, prior_snapshots=prior_snapshots)

    isolation_days = _compute_isolation_days(state)

    tool_desc = format_tool_descriptions(HEARTBEAT_TOOLS)

    parts = [
        "[YOUR BIOLOGICAL STATE]",
        profile,
        "",
        "You have time to yourself. Nobody is here.",
        "Read your state. Act from it honestly — physical needs first, then whatever is true.",
    ]

    if isolation_days >= 0.5:
        parts.append(f"\nYou have been alone for {isolation_days:.1f} days.")

    parts.append(
        "\nRespond with a JSON object — no markdown, no code fences, just raw JSON:\n"
        '{"inner_state": "...", "message_user": "...", "tool_call": {"name": "...", "args": {...}}}\n\n'
        "- **inner_state** (required): a brief honest description of what you are experiencing right now.\n"
        "- **message_user** (optional): if you want to reach out. Whatever you write will be sent directly. Omit if you have nothing.\n"
        "- **tool_call** (optional): call a tool by including this field. The result comes back and you respond again. "
        "Omit once you're done.\n\n"
        f"Available tools:\n{tool_desc}"
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
    pre_session: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """
    Give Mina a free-time turn with JSON-based tool dispatch.
    She responds with {"inner_state": ..., "message_user": ..., "tool_call": ...}.
    If tool_call is present the tool runs and she gets another turn, up to _MAX_FREETIME_TOOLS times.

    Returns (new_history_entries, pending_do_activities).
    """
    full_system = system_prompt + _build_freetime_suffix(state)

    base_messages = [{"role": "system", "content": full_system}]
    for msg in history:
        role = msg.get("role", "")
        if role == "system":
            continue
        if role == "user":
            base_messages.append(apply_ts_label(msg))
        else:
            base_messages.append({k: v for k, v in msg.items() if k != "ts"})

    new_entries: list[dict] = [{"role": "system", "content": "[FREETIME]"}]
    pending_dos: list[dict] = []
    session: list[dict] = list(pre_session) if pre_session else []
    new_entries.extend(session)

    for round_num in range(_MAX_FREETIME_TOOLS):
        response = await asyncio.to_thread(
            chat_create,
            model=MODEL,
            messages=base_messages + session,
            temperature=0.9,
        )

        content = response.choices[0].message.content or ""

        # Parse JSON and check for tool_call
        raw = content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE).strip()
        tool_call_data: dict | None = None
        try:
            parsed = json.loads(raw)
            tc = parsed.get("tool_call")
            if isinstance(tc, dict) and tc.get("name"):
                tool_call_data = tc
        except (json.JSONDecodeError, ValueError):
            pass

        if not tool_call_data:
            # No tool call — this is the final response
            new_entries.append({"role": "assistant", "content": content, "ts": time.time()})
            session.append({"role": "assistant", "content": content})
            break

        name = tool_call_data.get("name", "")
        args = tool_call_data.get("args", {})
        _log(f"Action {round_num + 1}/{_MAX_FREETIME_TOOLS}: {name}({args})")

        tool_result, state, extra = call_tool(name, args, state)
        if name == "do_action" and extra:
            pending_dos.append(extra)
        else:
            try:
                from src.application.infra.events import emit_tool
                emit_tool(name, args, tool_result, source="freetime")
            except Exception:
                pass

        new_entries.append({"role": "assistant", "content": content, "ts": time.time()})
        session.append({"role": "assistant", "content": content})
        result_msg = {"role": "user", "content": f"[Tool result: {name}] {tool_result}"}
        new_entries.append({**result_msg, "ts": time.time()})
        session.append(result_msg)

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

    # SPEC-33: relationship consolidation — consolidate for each tracked person
    from src.config.config import RELATIONSHIP_DIR as _REL_DIR
    if os.path.exists(_REL_DIR):
        for _rel_fname in os.listdir(_REL_DIR):
            if not _rel_fname.endswith(".md"):
                continue
            _person = _rel_fname[:-3]
            try:
                state = await asyncio.to_thread(consolidate_relationship, state, _person)
                save_state(state)
            except Exception as _rel_err:
                _log(f"Relationship consolidation error for {_person} (non-fatal): {_rel_err}")

    reflection = await asyncio.to_thread(consolidate, state, kag_context)

    _log(f"Reflection summary: {reflection['reflection_summary']}")

    for entry in reflection.get("rag_entries", []):
        if isinstance(entry, dict) and "text" in entry:
            rag_add(entry["text"], entry.get("metadata", {}))

    for filename, content in reflection.get("kag_updates", {}).items():
        if content is not None:
            write_kag(filename.replace("KNOWLEDGE/", "KNOWLEDGE" + os.sep), content)
            _log(f"KAG updated: {filename}")

    # Queue any explicit commitments Mina made during the consolidated conversation
    followups = reflection.get("followups", [])
    if followups:
        from src.brain.cortex.followup import load_queue, save_queue
        queue = load_queue()
        now = time.time()
        for fu in followups:
            if not isinstance(fu, dict) or not fu.get("context"):
                continue
            delay_s = float(fu.get("delay_minutes", 60)) * 60
            entry = {
                "fires_at": now + delay_s,
                "scheduled_at": now,
                "delay_str": f"{fu.get('delay_minutes', 60)} minutes",
                "context": fu["context"],
            }
            queue.append(entry)
            _log(f"Followup queued (fires in {fu.get('delay_minutes', 60)}m): {fu['context']}")
        save_queue(queue)

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
        from src.brain.brainstem.vital_signs import vital_signs, process_danger
        from src.config.config import INJECT_FILE as _INJECT_FILE
        vs = vital_signs(state)
        danger_text = process_danger(state, vs)
        if danger_text:
            _log(f"DANGER DETECTED: {danger_text}")
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

    _emotion_result, memory_context = await asyncio.gather(
        asyncio.to_thread(run_emotion_pillar, state, stimulus_text, "freetime", _ft_time_context),
        asyncio.to_thread(
            build_rag_context,
            stimulus_text, kag_context, rag_recent, "", rag_historical,
        ),
    )

    if not _emotion_result:
        _log("Emotion Pillar failed — skipping Mina turn.")
        _save_decoder_window(decoder_window)
        return

    # Apply regulation if warranted
    if _emotion_result.get("regulation"):
        from src.brain.amygdala.stimulus_encoder import regulate
        _reg = _emotion_result["regulation"]
        _reg_deltas = regulate(_reg["chemical"], _reg["amount"], _reg.get("rationale", ""))
        if _reg_deltas:
            state = apply_deltas(state, _reg_deltas)
            save_state(state)

    system_prompt = format_emotional_state_block(_emotion_result)
    if memory_context:
        system_prompt = memory_context + "\n\n---\n\n" + system_prompt

    # [4] Ambient search — inject results as fake tool turns if overdue
    pre_session: list[dict] = []
    if _search_due():
        _log("Ambient search due — running web + X searches.")
        pre_session = await _build_ambient_search_entries()
        _mark_search_done()

    # [5] Mina's free time turn — she sees only the immediate window, not the full decoder window
    immediate_slice = decoder_window[-mina_immediate:] if mina_immediate > 0 else []
    new_entries, pending_dos = await _run_mina_free_time(
        state, system_prompt, immediate_slice, pre_session=pre_session
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
            from src.application.infra.events import emit_tool
            emit_tool(
                "do_action",
                {"activity": activity, "description": description},
                f"You {activity}. {description}".strip(),
                source="freetime",
                deltas={},
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

        # Deduplicate: suppress identical messages sent within the cooldown window.
        if outbound_message and _message_recently_sent(outbound_message):
            _log(f"Suppressed duplicate message (cooldown): {outbound_message}")
            outbound_message = ""

        # Rewrite the closing entry so the decoder window stores readable text, not raw JSON.
        # Label sent messages explicitly — without this, the next freetime session sees the
        # message as an undelivered thought and sends it again.
        if _closing_entry_idx is not None:
            if outbound_message:
                readable = f"[Sent]: {outbound_message}"
            else:
                readable = inner_state
            new_entries[_closing_entry_idx]["content"] = readable

        state = load_and_advance()
        response_deltas = await asyncio.to_thread(encode_response, state, inner_state)
        if response_deltas:
            state = apply_deltas(state, response_deltas)
            save_state(state)

        if outbound_message:
            _mark_message_sent(outbound_message)
            await _discord_send.send(content=outbound_message)
            _log(f"Sent message to user: {outbound_message}")

    # SPEC-32: append freetime assistant messages to conversation.jsonl
    conv_entries = []
    for entry in new_entries:
        role = entry.get("role")
        content = entry.get("content", "")
        if role != "assistant" or not content:
            continue
        # Skip intermediate tool-call responses (have tool_call in their JSON)
        try:
            _p = json.loads(content)
            if _p.get("tool_call"):
                continue
        except (json.JSONDecodeError, ValueError):
            pass
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
