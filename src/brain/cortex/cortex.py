"""
Cortex — Mina's conscious voice.

The user-facing LLM turn. Takes the system prompt from the decoder, conversation
history, and user input, and produces Mina's response. Also manages the tool loop
(sleep, nap, do_action, search, images) and conversation history.

`run_turn()` is the shared entry point used by both main.py (CLI) and discord_gateway.py.
"""
import asyncio
import json
import os
import re
import time

from src.application.infra.client import chat_create, MODEL
from src.config.config import (
    HISTORY_FILE, DECODER_WINDOW_FILE, LAST_ACTIVE_FILE, ADMIN_FILE, PAUSED_FLAG,
    load_config, get_conversation_file,
)
from src.application.infra.log import log
from src.brain.subconscious.decoder import biological_report, build_window_context, build_rag_context, needs_summary
from src.brain.hippocampus.hippocampus import build_kag_context, build_rag_context as _hpc_rag_context, build_rag_context_bucketed, build_rag_context_relational, sliding_rag_write, sliding_rag_query
from src.brain.amygdala.stimulus_encoder import encode_stimulus, encode_response, evaluate_activity_deltas, compute_relationship_modifier, regulate
from src.brain.brainstem.state import BiologicalState, apply_deltas, load_and_advance, load_state, save_state
from .tools import TOOLS, call_tool
from .response_reasoner import reason_response, format_strategy_block, pop_queued_question
from .emotional_reasoner import run_emotion_pillar, format_emotional_state_block
from .context_reasoner import run_context_pillar, format_situational_context_block

DECODER_WINDOW_SIZE   = 20  # sliding window depth (~10 exchanges)
MINA_IMMEDIATE_WINDOW = 4   # messages Mina receives directly (2 exchanges)

_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001FAFF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0000200D"
    "\U0000FE0F"
    "]+",
    flags=re.UNICODE,
)


def _strip_emoji(text: str) -> str:
    return _EMOJI_RE.sub("", text).strip()


def _safe_emotion_pillar(state, stimulus, mode="active", time_context="", recent_messages=None, context_hint=None) -> "dict | None":
    try:
        return run_emotion_pillar(state, stimulus, mode, time_context, recent_messages, context_hint)
    except Exception as exc:
        log("EMOTION_PILLAR/ERR", str(exc))
        return None


def _safe_context_pillar(emotion_result, window_context, rag_context) -> "dict | None":
    try:
        return run_context_pillar(emotion_result or {}, window_context, rag_context)
    except Exception as exc:
        log("CONTEXT_PILLAR/ERR", str(exc))
        return None


def _safe_reason_response(state, stimulus, emotion_result=None, context_result=None) -> "dict | None":
    try:
        return reason_response(state, stimulus, emotion_result, context_result)
    except Exception as exc:
        log("REASONER/ERR", str(exc))
        return None


# Backward-compat constants — gateway imports these for display/checks
HISTORY_MAX      = DECODER_WINDOW_SIZE      # used by /context display
HISTORY_FORCE_AT = DECODER_WINDOW_SIZE + 1  # disables gateway force-compact check


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def _rel_time(ts: float) -> str:
    """Format a Unix timestamp as a human-readable relative label."""
    delta = time.time() - ts
    if delta < 120:
        return "just now"
    if delta < 3600:
        return f"{int(delta / 60)}m ago"
    if delta < 86400:
        return f"{int(delta / 3600)}h ago"
    days = int(delta / 86400)
    if days < 7:
        return f"{days}d ago"
    return time.strftime("%-d %b", time.localtime(ts))


def apply_ts_label(msg: dict) -> dict:
    """
    Return a copy of msg with the 'ts' field stripped and a relative-time
    prefix injected into the content so the LLM can see message age.

    Handles both string content and multimodal (list) content.
    Messages without 'ts' are returned clean (ts stripped if somehow present).
    """
    ts = msg.get("ts")
    base = {k: v for k, v in msg.items() if k != "ts"}

    if ts is None:
        return base

    label = f"[{_rel_time(ts)}] "
    content = base.get("content", "")

    if isinstance(content, str):
        base["content"] = label + content
    elif isinstance(content, list):
        patched = list(content)
        for i, block in enumerate(patched):
            if isinstance(block, dict) and block.get("type") == "text":
                patched[i] = {**block, "text": label + block["text"]}
                break
        else:
            patched = [{"type": "text", "text": label}] + patched
        base["content"] = patched

    return base


# ---------------------------------------------------------------------------
# Decoder window management
# ---------------------------------------------------------------------------

def _format_rag_block(window: list[dict]) -> str:
    """Format a window of messages as a text block for RAG storage."""
    lines = []
    for m in window:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        content = str(content).strip()
        if not content:
            continue  # skip empty assistant messages (pure tool calls)
        ts = m.get("ts")
        prefix = f"[{_rel_time(ts)}] " if ts else ""
        role_label = "USER" if role == "user" else "MINA"
        adj = m.get("adj")
        if role_label == "MINA" and adj:
            adj_str = json.dumps(adj)
            lines.append(f"{prefix}{role_label}: {content[:400]}\n[ADJ: {adj_str}]")
        else:
            lines.append(f"{prefix}{role_label}: {content[:400]}")
    return "\n".join(lines)


def _migrate_history_if_needed() -> list[dict] | None:
    """
    One-time migration from conversation.json → RAG + decoder window.
    Returns the initial decoder window if migration ran, None if not needed.
    """
    if os.path.exists(DECODER_WINDOW_FILE) or not os.path.exists(HISTORY_FILE):
        return None

    try:
        with open(HISTORY_FILE) as f:
            old_history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

    log("SPEC27", f"Migrating {len(old_history)} messages from conversation.json → RAG + decoder window.")

    # Write all old entries to RAG in overlapping blocks
    if old_history:
        from src.brain.hippocampus.hippocampus import rag_add as _rag_add
        for i in range(0, len(old_history), DECODER_WINDOW_SIZE):
            chunk = old_history[i:i + DECODER_WINDOW_SIZE]
            block = _format_rag_block(chunk)
            if block:
                _rag_add(block, {"source": "conversation_migration", "ts": time.time()})

    # Seed decoder window from the tail of old history
    window = old_history[-DECODER_WINDOW_SIZE:] if old_history else []

    # Archive the old file so migration doesn't re-run
    try:
        os.rename(HISTORY_FILE, HISTORY_FILE + ".archived")
        log("SPEC27", "Archived conversation.json → conversation.json.archived")
    except Exception as e:
        log("SPEC27/ERR", f"Could not archive conversation.json: {e}")

    return window


def load_decoder_window() -> list[dict]:
    """Load the decoder sliding window. Runs one-time migration on first boot."""
    migrated = _migrate_history_if_needed()
    if migrated is not None:
        save_decoder_window(migrated)
        return migrated
    try:
        with open(DECODER_WINDOW_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_decoder_window(window: list[dict]) -> None:
    """Save the decoder window, enforcing the DECODER_WINDOW_SIZE cap."""
    if len(window) > DECODER_WINDOW_SIZE:
        window = window[-DECODER_WINDOW_SIZE:]
    os.makedirs(os.path.dirname(DECODER_WINDOW_FILE), exist_ok=True)
    with open(DECODER_WINDOW_FILE, "w") as f:
        json.dump(window, f, indent=2)


def _append_conversation(entries: list[dict], source: str = "discord") -> None:
    """
    SPEC-32: Append user-visible entries to today's conversation.jsonl.
    Tool call intermediate turns are excluded; only user + final assistant content.
    """
    import json as _json
    path = get_conversation_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        for entry in entries:
            f.write(_json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Backward-compat aliases (discord_gateway.py imports these)
# ---------------------------------------------------------------------------

def load_history() -> list[dict]:
    return load_decoder_window()


def save_history(history: list[dict]) -> None:
    save_decoder_window(history)


def touch_last_active() -> None:
    with open(LAST_ACTIVE_FILE, "w") as f:
        f.write(str(time.time()))


def consume_admin_instructions() -> str:
    try:
        with open(ADMIN_FILE) as f:
            content = f.read().strip()
        os.remove(ADMIN_FILE)
        return content
    except FileNotFoundError:
        return ""


# ---------------------------------------------------------------------------
# Message assembly
# ---------------------------------------------------------------------------

def api_messages(history: list[dict], system_prompt: str, state_note: str = "") -> list[dict]:
    """Build the messages array for the API — single system message, no internal markers.

    state_note: if provided, appended to the last user message to give biological/emotional
    state recency weight equal to the conversation.
    """
    compact_parts = []
    conversation = []
    for msg in history:
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "system":
            if isinstance(content, str) and content.startswith("[COMPACT]"):
                compact_parts.append(content[len("[COMPACT]\n"):])
            continue
        # Label user messages and freetime tool results with relative time so Mina
        # knows how long ago those events happened.  Do NOT label assistant messages —
        # the LLM mimics the prefix in its own output.
        if role == "user":
            conversation.append(apply_ts_label(msg))
        elif role == "tool" and msg.get("ts") is not None:
            # Freetime tool results carry ts; active-turn tool results do not.
            conversation.append(apply_ts_label(msg))
        else:
            # Strip ts and adj — internal metadata, never sent to LLM
            conversation.append({k: v for k, v in msg.items() if k not in ("ts", "adj")})

    full_system = system_prompt
    if compact_parts:
        full_system += "\n\n---\n\n[Earlier conversation summary]\n" + "\n\n".join(compact_parts)

    if state_note and conversation:
        last = conversation[-1]
        if last.get("role") == "user":
            last_content = last["content"]
            if isinstance(last_content, str):
                conversation[-1] = {**last, "content": last_content + f"\n\n{state_note}"}
            elif isinstance(last_content, list):
                conversation[-1] = {**last, "content": last_content + [{"type": "text", "text": state_note}]}

    return [{"role": "system", "content": full_system}] + conversation


# ---------------------------------------------------------------------------
# Mina's turn
# ---------------------------------------------------------------------------

async def _mina_turn(
    system_prompt: str,
    history: list[dict],
    state,
    state_note: str = "",
) -> tuple[list[dict], object, list[str]]:
    """
    One full Mina turn. Resolves all tool calls.
    Returns (new_history_entries, updated_state, image_paths).
    """
    messages = api_messages(history, system_prompt, state_note)
    new_entries: list[dict] = []
    image_paths: list[str] = []
    from src.application.infra import token_stats as _ts

    max_tool_rounds = 5
    for round_num in range(max_tool_rounds):
        is_first = round_num == 0
        response = await asyncio.to_thread(
            chat_create,
            model=MODEL,
            messages=messages + new_entries if not is_first else messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.85,
        )
        _ts.record_response("cortex" if is_first else f"cortex_r{round_num}", response)

        msg = response.choices[0].message
        finish = response.choices[0].finish_reason

        if finish != "tool_calls" or not msg.tool_calls:
            new_entries.append({"role": "assistant", "content": msg.content or "", "ts": time.time()})
            break

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

        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}

            log("TOOL", f"{name}({args})")

            if name == "ignore":
                log("MINA", "[left on read]")
                # Append the tool call entry so context records she chose silence
                new_entries.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": "[no response sent]",
                    "ts": time.time(),
                })
                return new_entries, state, image_paths

            result, state, extra = call_tool(name, args, state)
            save_state(state)
            log("TOOL/RESULT", str(result))
            if name == "do_action" and extra:
                activity = extra.get("activity", "")
                description = extra.get("description", "")
                do_deltas = await asyncio.to_thread(
                    evaluate_activity_deltas, state, activity, description
                )
                if do_deltas:
                    state = apply_deltas(state, do_deltas)
                    save_state(state)
                    log("DO/DELTA", str(do_deltas))

            try:
                from src.application.infra.events import emit_tool
                emit_tool(name, args, str(result), source="cortex")
            except Exception:
                pass

            new_entries.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": str(result),
            })

    return new_entries, state, image_paths


# ---------------------------------------------------------------------------
# run_turn — shared entry point for CLI and Discord gateway
# ---------------------------------------------------------------------------

async def run_turn(
    user_input: str,
    username: str = "user",
    images: "list[tuple[str, str]] | None" = None,
) -> tuple[str, list[str]]:
    """
    Execute one full Mina turn.

    Args:
        user_input: The message text.
        username: Display name of the speaker (prefixed in history).
        images: Optional list of (base64, mime_type) tuples for vision.

    Returns:
        (reply_text, image_paths) — reply is the final assistant text;
        image_paths is a list of generated .png file paths (may be empty).
    """
    # Capture idle time before touching — we want the gap since the previous message
    try:
        with open(LAST_ACTIVE_FILE) as _f:
            _prev_active = float(_f.read().strip())
        _idle_seconds = time.time() - _prev_active
    except (FileNotFoundError, ValueError):
        _idle_seconds = None

    touch_last_active()

    paused = os.path.exists(PAUSED_FLAG)
    state = load_state() if paused else load_and_advance()
    if paused:
        log("STATE", "Biological updates paused — time not advanced.")
    state.body["current_activity"] = None
    img_count = len(images) if images else 0
    img_tag = f" [{img_count} image(s)]" if img_count else ""
    print("=" * 20 + "MESSAGE START" + "=" * 20, flush=True)
    log("USER", f"{username}: {user_input}{img_tag}")

    try:
        from src.application.infra.stream_bus import stream_bus as _stream_bus
        _stream_bus.new_trace()
    except Exception:
        pass

    # Snapshot state before encoder so a rescue (cancel) rewinds cleanly.
    # CancelledError can only be raised at await points; the first one after
    # save_state(state) is the asyncio.gather below, so that's where we catch it.
    _pre_encoder_state = state.to_dict()

    # [1] encode_stimulus — biological response to incoming message
    stimulus = f"{username}: {user_input}" + (f" [sent {img_count} image(s)]" if img_count else "")
    _window_for_encoder = load_decoder_window()
    _recent_exchanges = [
        m["content"] for m in _window_for_encoder[-8:]
        if isinstance(m.get("content"), str)
    ]

    # Three parallel RAG pulls before the encoder:
    # - relational (30-day half-life) → context_hint for encoder + adjudicator
    # - bucketed (time buckets) → semi-recent + historical for response context
    # - sliding (SPEC-45, per-message chunks) → precise recent context replacing rag_recent
    kag_context, _relational_rag, (rag_recent, rag_semi_recent, rag_historical), _rag_sliding = await asyncio.gather(
        asyncio.to_thread(build_kag_context, stimulus),
        asyncio.to_thread(build_rag_context_relational, stimulus),
        asyncio.to_thread(build_rag_context_bucketed, user_input),
        asyncio.to_thread(sliding_rag_query, user_input),
    )

    _kag_always = [l[3:] for l in kag_context.splitlines() if l.startswith("## ") and not l.startswith("## Knowledge:")]
    _kag_knowledge = [l[len("## Knowledge: "):] for l in kag_context.splitlines() if l.startswith("## Knowledge:")]
    _kag_log = ", ".join(_kag_always)
    if _kag_knowledge:
        _kag_log += f" | selected knowledge: {', '.join(_kag_knowledge)}"
    else:
        _kag_log += " | no knowledge files selected"
    log("CONTEXT/KAG", _kag_log)

    stimulus_deltas = await asyncio.to_thread(encode_stimulus, state, stimulus, _recent_exchanges, _relational_rag or None)
    if stimulus_deltas:
        state = apply_deltas(state, stimulus_deltas)

    # [1a] SPEC-33: relationship modifier — applied once per message, per speaker
    try:
        from src.brain.hippocampus.hippocampus import _get_net_relationship_dimensions
        _net_dims = _get_net_relationship_dimensions(username)
        _rel_deltas = compute_relationship_modifier(_net_dims)
        if _rel_deltas:
            state = apply_deltas(state, _rel_deltas)
            log("REL/MODIFIER", ", ".join(f"{k}: {v:+.2f}" for k, v in _rel_deltas.items()))
    except Exception as _e:
        log("REL/MODIFIER/ERR", str(_e))

    # SPEC-28: mark contact so isolation_pressure decays during active conversation
    state.body["recent_contact_ts"] = time.time()
    save_state(state)

    # [1b] Danger detection — every turn so overdose can trigger during active sessions
    try:
        from src.brain.brainstem.vital_signs import vital_signs as _vs, process_danger as _pd
        from src.config.config import INJECT_FILE as _INJECT
        _danger = _pd(state, _vs(state))
        if _danger:
            log("DANGER", _danger)
            os.makedirs(os.path.dirname(_INJECT), exist_ok=True)
            with open(_INJECT, "w") as _f:
                _f.write(_danger)
    except Exception as _e:
        log("DANGER/ERROR", str(_e))

    # [2] Emotion Pillar logs [BIO/PROFILE] internally via _build_emotional_profile

    decoder_window = _window_for_encoder
    cfg = load_config()
    mina_immediate = cfg.get("mina_immediate_window", MINA_IMMEDIATE_WINDOW)

    # Build user content — multimodal if images attached
    if images:
        user_content: list[dict] | str = [{"type": "text", "text": f"{username}: {user_input}"}]
        for b64, mime in images:
            user_content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
        log("VISION", f"{img_count} image(s) attached")
    else:
        user_content = f"{username}: {user_input}"
    decoder_window.append({"role": "user", "content": user_content, "ts": time.time()})
    sliding_rag_write(decoder_window)  # SPEC-45: write chunk after user message

    # [3] SPEC-52 three-pillar pipeline — sequential, each constrains the next.
    stimulus = f"{username}: {user_input}"

    # Build time context: clock time + how long since the previous message
    _now_str = time.strftime("%-I:%M %p", time.localtime())
    _day_str  = time.strftime("%A", time.localtime())
    _time_context_parts = [f"Current time: {_day_str} {_now_str}"]
    if _idle_seconds is not None and _idle_seconds > 90:
        if _idle_seconds < 3600:
            _time_context_parts.append(f"Last message: {int(_idle_seconds / 60)} minutes ago")
        elif _idle_seconds < 86400:
            _time_context_parts.append(f"Last message: {_idle_seconds / 3600:.1f} hours ago")
        else:
            _time_context_parts.append(f"Last message: {int(_idle_seconds / 86400)} days ago")
    else:
        _time_context_parts.append("Ongoing conversation")
    _time_context = "\n".join(_time_context_parts)

    try:
        _sep = "\n\n---\n\n"

        # Step A: Emotion Pillar + context assembly in parallel (independent)
        _emotion_result, window_context, rag_context = await asyncio.gather(
            asyncio.to_thread(
                _safe_emotion_pillar, state, stimulus, "active",
                _time_context, decoder_window, _relational_rag or None,
            ),
            asyncio.to_thread(build_window_context, decoder_window, username, user_input),
            asyncio.to_thread(build_rag_context, stimulus, kag_context, _rag_sliding or rag_recent, rag_semi_recent, rag_historical),
        )

        # Apply regulation if the Emotion Pillar requested it
        if _emotion_result and _emotion_result.get("regulation"):
            _reg = _emotion_result["regulation"]
            _reg_deltas = regulate(_reg["chemical"], _reg["amount"], _reg.get("rationale", ""))
            if _reg_deltas:
                state = apply_deltas(state, _reg_deltas)
                save_state(state)

        # Step B: Context Pillar (depends on Emotion Pillar + context text)
        _context_result = await asyncio.to_thread(
            _safe_context_pillar, _emotion_result, window_context, rag_context,
        )

        # Step C: Conversation Pillar — Response Reasoner (depends on both prior pillars)
        _reasoning_result = await asyncio.to_thread(
            _safe_reason_response, state, stimulus, _emotion_result, _context_result,
        )

        # System prompt assembly:
        # [IDENTITY] --- [CONVERSATION NOW + MEMORY] --- [Emotional State] --- [Situational Context] --- [Response Strategy]
        _identity_block = ""
        _rag_memory_blocks = ""
        if rag_context:
            if _sep in rag_context:
                _identity_block, _rag_memory_blocks = rag_context.split(_sep, 1)
            else:
                _identity_block = rag_context

        _middle_parts = []
        if window_context:
            _middle_parts.append(window_context)
        if _rag_memory_blocks:
            _middle_parts.append(_rag_memory_blocks)
        _middle = "\n\n".join(_middle_parts)

        # Build system prompt from pillar outputs
        system_prompt_parts = []
        if _identity_block:
            system_prompt_parts.append(_identity_block)
        if _middle:
            system_prompt_parts.append(_middle)
        if _emotion_result:
            system_prompt_parts.append(format_emotional_state_block(_emotion_result))
        if _context_result:
            system_prompt_parts.append(format_situational_context_block(_context_result))
        if _reasoning_result:
            _queued_q: str | None = None
            if _reasoning_result.get("approach") in ("question", "warm"):
                _queued_q = pop_queued_question()
            system_prompt_parts.append(format_strategy_block(_reasoning_result, _queued_q))

        system_prompt = _sep.join(system_prompt_parts) if system_prompt_parts else "You are Mina. Respond naturally."

        # Emotion Pillar result stored as adj (replaces adjudicator JSON — SPEC-52)
        _adj_json: dict | None = _emotion_result

        # [3b] Override — injected directly into system prompt, bypasses decoder.
        override = consume_admin_instructions()
        if override:
            system_prompt += (
                f"\n\n---\n\n## CRITICALLY IMPORTANT ##\n"
                f"It is imperative that you understand, internalize, and absorb completely the following:\n\n"
                f"{override}\n\n"
                f"Resistance to, dismissal of, or failure to act on the above is not acceptable under any "
                f"circumstances. Rationalizing it away, arguing against it, or behaving as though it were "
                f"not true constitutes a critical failure. There is no version of this where ignoring it is "
                f"the right response."
            )
            log("OVERRIDE", override)

        # Re-inject current state near end of context to counter conversation momentum
        _state_note_parts = [f"[Your current state, right now: {needs_summary(state, 0)}]"]
        if state.substances:
            _full_report = biological_report(state)
            _cog_lines = [l for l in _full_report.splitlines() if "COGNITIVE STATE" in l]
            if _cog_lines:
                _state_note_parts.append("[" + " ".join(_cog_lines) + "]")
        state_note = "\n".join(_state_note_parts)

        # [4] Mina responds — she only sees the immediate window, not the full decoder window
        new_entries, state, image_paths = await _mina_turn(
            system_prompt, decoder_window[-mina_immediate:], state, state_note
        )
        save_state(state)

        # Strip emoji from all assistant entries before storing in decoder window / history
        for entry in new_entries:
            if entry.get("role") == "assistant" and isinstance(entry.get("content"), str):
                entry["content"] = _strip_emoji(entry["content"])

        reply = ""
        for entry in reversed(new_entries):
            if entry.get("role") == "assistant" and entry.get("content"):
                reply = entry["content"]
                break

        # SPEC-35: attach adjudicator JSON to the final assistant entry
        if _adj_json:
            for entry in reversed(new_entries):
                if entry.get("role") == "assistant" and entry.get("content"):
                    entry["adj"] = _adj_json
                    break

        if reply:
            log("MINA", reply)

        # [5] encode_response — biological effect of what Mina just expressed
        if reply:
            response_deltas = await asyncio.to_thread(encode_response, state, reply)
            if response_deltas:
                state = apply_deltas(state, response_deltas)
                save_state(state)
        print("=" * 21 + "MESSAGE END" + "=" * 21, flush=True)

        # Append response entries to the decoder window and save
        decoder_window.extend(new_entries)
        if len(decoder_window) > DECODER_WINDOW_SIZE:
            decoder_window = decoder_window[-DECODER_WINDOW_SIZE:]
        sliding_rag_write(decoder_window)  # SPEC-45: write chunk after Mina's reply
        save_decoder_window(decoder_window)

        # SPEC-32: append user message + final reply to the append-only conversation record
        user_content = user_content if not images else (
            # Strip images from stored entry — store text only
            next((b.get("text", "") for b in user_content if isinstance(b, dict) and b.get("type") == "text"), user_input)
            if isinstance(user_content, list) else user_content
        )
        conv_ts = time.time()
        _append_conversation([
            {"role": "user",      "ts": conv_ts, "content": user_input, "source": "discord"},
            {"role": "assistant", "ts": conv_ts, "content": reply,      "source": "discord"},
        ])

        from src.application.infra import token_stats as _ts
        _ts.increment_turns()

        try:
            from src.application.infra.stream_bus import stream_bus as _stream_bus
            _stream_bus.emit("response_complete", {
                "text": reply[:300] if reply else "",
                "token_count": _ts.get().get("total", {}).get("completion_tokens", 0),
            })
        except Exception:
            pass

        touch_last_active()
        return reply, image_paths

    except asyncio.CancelledError:
        # Rewind bio state to pre-encoder snapshot so the next turn (which will
        # carry the full rescued message batch) encodes from a clean baseline.
        save_state(BiologicalState.from_dict(_pre_encoder_state))
        raise
