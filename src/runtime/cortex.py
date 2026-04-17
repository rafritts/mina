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

from ..infra.client import chat_create, MODEL
from ..infra.config import (
    HISTORY_FILE, DECODER_WINDOW_FILE, LAST_ACTIVE_FILE, ADMIN_FILE, PAUSED_FLAG,
    load_config, get_conversation_file,
)
from ..infra.log import log
from ..infra.turn_log import log_context_window, log_conversation
from ..bio.decoder import biological_report, biological_report_compact, adjudicate_emotion, build_memory_context, needs_summary
from ..memory.hippocampus import build_kag_context, build_rag_context, build_rag_context_dual
from ..bio.encoder import encode_stimulus, encode_response, evaluate_activity_deltas, compute_relationship_modifier
from ..bio.state import apply_deltas, load_and_advance, load_state, save_state
from .tools import TOOLS, call_tool, handle_generate_image

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


# Backward-compat constants — gateway imports these for display/checks
HISTORY_MAX      = DECODER_WINDOW_SIZE      # used by /context display
HISTORY_FORCE_AT = DECODER_WINDOW_SIZE + 1  # disables gateway force-compact check
HISTORY_KEEP     = MINA_IMMEDIATE_WINDOW    # no longer used for compaction


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
        from ..memory.hippocampus import rag_add as _rag_add
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
    log_context_window(messages)
    new_entries: list[dict] = []
    image_paths: list[str] = []
    from ..infra import token_stats as _ts

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

            tool_deltas: dict = {}
            tool_content: str = ""
            if name == "generate_image":
                result = await handle_generate_image(args)
                if result and result.endswith(".png") and os.path.exists(result):
                    image_paths.append(result)
                    # Tell Mina the image is delivered as an attachment so she never
                    # invents a fake URL or filename in her reply.
                    tool_content = (
                        "Image generated and queued as a Discord file attachment. "
                        "It will appear in the channel automatically. "
                        "Do NOT include any URL, filename, or link in your reply — just respond naturally."
                    )
                    # Inject a synthetic message so Mina can see what she generated next turn.
                    try:
                        from ..infra.image_utils import normalise_image
                        with open(result, "rb") as _f:
                            _b64, _mime = normalise_image(_f.read())
                        new_entries.append({
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"[image you just generated: {os.path.basename(result)}]"},
                                {"type": "image_url", "image_url": {"url": f"data:{_mime};base64,{_b64}"}},
                            ],
                            "ts": time.time(),
                        })
                        log("VISION", f"Injected generated image into context: {os.path.basename(result)}")
                    except Exception as _e:
                        log("VISION/ERR", f"Failed to inject image into context: {_e}")
                elif result and result.startswith("[Image generation failed"):
                    tool_content = result
                else:
                    tool_content = "[Image was blocked or generation produced no output.]"
                log("IMAGE", result or "blocked/failed")
            else:
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
                        tool_deltas = do_deltas
                        state = apply_deltas(state, do_deltas)
                        save_state(state)
                        log("DO/DELTA", str(do_deltas))

            try:
                from ..infra.events import emit_tool
                emit_tool(name, args, tool_content or str(result), source="cortex", deltas=tool_deltas)
            except Exception:
                pass

            new_entries.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_content if name == "generate_image" else str(result),
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
    img_count = len(images) if images else 0
    img_tag = f" [{img_count} image(s)]" if img_count else ""
    print("=" * 20 + "MESSAGE START" + "=" * 20, flush=True)
    log("USER", f"{username}: {user_input}{img_tag}")

    # [1] encode_stimulus — biological response to incoming message
    stimulus = f"{username}: {user_input}" + (f" [sent {img_count} image(s)]" if img_count else "")
    stimulus_deltas = await asyncio.to_thread(encode_stimulus, state, stimulus)
    if stimulus_deltas:
        state = apply_deltas(state, stimulus_deltas)

    # [1a] SPEC-33: relationship modifier — applied once per owner message
    # Stable disposition from relationship file, not raw oxytocin.
    _admin_name = load_config().get("admin_name", "")
    if _admin_name and username.lower() == _admin_name.lower():
        try:
            from ..memory.hippocampus import _get_net_relationship_dimensions
            _net_dims = _get_net_relationship_dimensions(_admin_name)
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
        from ..bio.vital_signs import vital_signs as _vs, process_danger as _pd
        from ..infra.config import INJECT_FILE as _INJECT
        _danger = _pd(state, _vs(state))
        if _danger:
            log("DANGER", _danger[:120])
            os.makedirs(os.path.dirname(_INJECT), exist_ok=True)
            with open(_INJECT, "w") as _f:
                _f.write(_danger)
    except Exception as _e:
        log("DANGER/ERROR", str(_e))

    # [2] biological_report — deterministic, logged only (not injected into prompts)
    log("BIO/REPORT", biological_report_compact(state))

    decoder_window = load_decoder_window()
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

    # [3] emotion adjudication + memory context — run in parallel
    # adjudicate_emotion: derived emotional profile + stimulus → concrete emotional disposition
    kag_context = build_kag_context()
    rag_recent, rag_historical = build_rag_context_dual(user_input)
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

    system_prompt, memory_context = await asyncio.gather(
        # Full decoder window gives adjudicator conversational context to name shifts
        asyncio.to_thread(adjudicate_emotion, state, stimulus, "active", _time_context, decoder_window),
        asyncio.to_thread(build_memory_context, stimulus, kag_context, rag_recent, rag_historical, decoder_window, mina_immediate),
    )
    if not system_prompt:
        system_prompt = "You are Mina. Respond naturally."
    if memory_context:
        system_prompt = memory_context + "\n\n---\n\n" + system_prompt

    # SPEC-35: extract adjudicator JSON so it can be attached to the assistant entry
    _adj_json: dict | None = None
    _adj_match = re.search(r'\[EMOTIONAL DISPOSITION\]\s*(\{.*?\})', system_prompt, re.DOTALL)
    if _adj_match:
        try:
            _adj_json = json.loads(_adj_match.group(1))
        except json.JSONDecodeError:
            pass

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

    from ..infra import token_stats as _ts
    _ts.increment_turns()

    log_conversation(username, user_input, reply)
    touch_last_active()
    return reply, image_paths


async def compact_history_if_needed() -> None:
    """No-op — compaction replaced by RAG aging in SPEC-27. Kept for gateway compat."""
    pass
