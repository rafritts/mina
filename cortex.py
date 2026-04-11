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

from client import get_client, MODEL
from config import (
    HISTORY_FILE, LAST_ACTIVE_FILE, ADMIN_FILE, PAUSED_FLAG, load_config
)
from log import log
from decoder import biological_report, build_system_prompt
from encoder import encode_stimulus, encode_response, evaluate_activity_deltas
from hippocampus import build_kag_context, build_rag_context
from state import apply_deltas, load_and_advance, load_state, log_state, save_state
from tools import TOOLS, call_tool, handle_generate_image

HISTORY_MAX = 200
HISTORY_KEEP = 10
HISTORY_COMPACT_AT = 22


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
# History management
# ---------------------------------------------------------------------------

def load_history() -> list[dict]:
    try:
        with open(HISTORY_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_history(history: list[dict]) -> None:
    if len(history) > HISTORY_MAX:
        history = history[-HISTORY_MAX:]
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def _compact_history(history: list[dict]) -> list[dict]:
    """
    Summarize all but the last HISTORY_KEEP messages into a compact block.
    Returns [compact_system_msg] + last HISTORY_KEEP messages.
    Falls back to uncompacted history on LLM error — never loses messages.
    """
    overflow = history[:-HISTORY_KEEP]
    recent   = history[-HISTORY_KEEP:]

    to_summarize = [m for m in overflow if m.get("role") in ("user", "assistant")]
    if not to_summarize:
        return recent

    lines = []
    for m in to_summarize:
        role = m.get("role", "?")
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        ts = m.get("ts")
        time_prefix = f"[{_rel_time(ts)}] " if ts else ""
        lines.append(f"{time_prefix}{role.upper()}: {content[:400]}")

    try:
        response = get_client().chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": (
                    "Summarize this conversation excerpt in 4-8 bullet points. "
                    "Cover: what was discussed, notable moments, things to remember. "
                    "Be concise. No preamble."
                )},
                {"role": "user", "content": "\n".join(lines)},
            ],
            temperature=0.3,
            max_tokens=400,
        )
        import token_stats as _ts
        _ts.record_response("compact", response)
        summary = response.choices[0].message.content or ""
    except Exception as e:
        log("COMPACT/ERROR", str(e))
        return history  # fall back to uncompacted on error

    if not summary:
        return recent

    compact_msg = {"role": "system", "content": f"[COMPACT]\n{summary}"}
    log("COMPACT", f"Summarized {len(overflow)} messages into {len(summary)} chars")
    return [compact_msg] + recent


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
        conversation.append(apply_ts_label(msg))

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
    import token_stats as _ts

    max_tool_rounds = 5
    for round_num in range(max_tool_rounds):
        is_first = round_num == 0
        response = await asyncio.to_thread(
            get_client().chat.completions.create,
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

            if name == "generate_image":
                result = await handle_generate_image(args)
                if result and result.endswith(".png") and os.path.exists(result):
                    image_paths.append(result)
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
                        state = apply_deltas(state, do_deltas)
                        save_state(state)
                        log("DO/DELTA", str(do_deltas))

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
    image_b64: str | None = None,
    image_mime: str = "image/jpeg",
) -> tuple[str, list[str]]:
    """
    Execute one full Mina turn.

    Args:
        user_input: The message text.
        username: Display name of the speaker (prefixed in history).
        image_b64: Optional base64-encoded image for vision.
        image_mime: MIME type of the image (default image/jpeg).

    Returns:
        (reply_text, image_paths) — reply is the final assistant text;
        image_paths is a list of generated .png file paths (may be empty).
    """
    touch_last_active()

    paused = os.path.exists(PAUSED_FLAG)
    state = load_state() if paused else load_and_advance()
    if paused:
        log("STATE", "Biological updates paused — time not advanced.")
    log_state(state)

    # [1] encode_stimulus — biological response to incoming message
    stimulus = f"{username}: {user_input}" + (" [sent an image]" if image_b64 else "")
    stimulus_deltas = await asyncio.to_thread(encode_stimulus, state, stimulus)
    if stimulus_deltas:
        log("STIM/DELTA", str(stimulus_deltas))
        state = apply_deltas(state, stimulus_deltas)
        save_state(state)

    # [2] biological_report — deterministic, from updated state
    report = biological_report(state)
    log("BIO/REPORT", f"\n{report}")

    kag_context = build_kag_context()
    rag_context = build_rag_context(user_input)
    history = load_history()

    # Build user content — multimodal if image attached
    if image_b64:
        user_content = [
            {"type": "text", "text": f"{username}: {user_input}"},
            {"type": "image_url", "image_url": {"url": f"data:{image_mime};base64,{image_b64}"}},
        ]
        log("VISION", f"Image attached ({image_mime})")
    else:
        user_content = f"{username}: {user_input}"
    history.append({"role": "user", "content": user_content, "ts": time.time()})

    # [3] build_system_prompt — decoder reads biological report + observations → returns system prompt
    system_prompt = await asyncio.to_thread(
        build_system_prompt, report, history, kag_context, rag_context
    )
    if not system_prompt:
        system_prompt = "You are Mina. Respond naturally."

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

    # Log just the "## Right now" / observations section
    _rn_match = re.search(r"## Right now\n(.*?)(?=\n##|\Z)", system_prompt, re.DOTALL)
    _rn_text = _rn_match.group(1).strip() if _rn_match else "(not found)"
    log("DECODER/RN", _rn_text)

    # Re-inject current state near end of context to counter conversation momentum
    _state_note_parts = [f"[Your current state, right now: {_rn_text}]"]
    if state.substances:
        _full_report = biological_report(state)
        _cog_lines = [l for l in _full_report.splitlines() if "COGNITIVE STATE" in l]
        if _cog_lines:
            _state_note_parts.append("[" + " ".join(_cog_lines) + "]")
    state_note = "\n".join(_state_note_parts)

    # [4] Mina responds
    new_entries, state, image_paths = await _mina_turn(system_prompt, history, state, state_note)
    save_state(state)

    reply = ""
    for entry in reversed(new_entries):
        if entry.get("role") == "assistant" and entry.get("content"):
            reply = entry["content"]
            break

    # [5] encode_response — biological effect of what Mina just expressed
    if reply:
        response_deltas = await asyncio.to_thread(encode_response, state, reply)
        if response_deltas:
            log("RESP/DELTA", str(response_deltas))
            state = apply_deltas(state, response_deltas)
            save_state(state)

    history.extend(new_entries)
    if len(history) > HISTORY_COMPACT_AT:
        history = await asyncio.to_thread(_compact_history, history)
    save_history(history)

    import token_stats as _ts
    _ts.increment_turns()

    touch_last_active()
    return reply, image_paths
