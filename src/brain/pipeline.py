"""
Pipeline — per-turn orchestration.

For each incoming message:
  1. Encoder (amygdala) — state-blind perception
  2. Chemistry function — encoder → Class 1 deltas
  3. Decoder snapshot — ChemicalState → pillar-legible JSON
  4. Insula pillar — decoded chemistry → felt state
  5. Memory retrieval — parallel: KAG + RAG (sliding + episodic)
  6. Context assembly — synthesize raw memory into summaries
  7. Hippocampus pillar — felt state + context → situational summary
  8. PFC pillar — everything → response strategy + system prompt
  9. Mina LLM call — system prompt + conversation window → reply

Conversation window and JSONL log are managed here.
Sliding RAG write is called after each message (user and Mina).
Optional send_photo tool (comfy-fe) when image_count allows.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

from src.application.infra.client import chat_create
from src.application.infra.log import log
from src.config.config import MODEL, get_conversation_file, RUN_DIR
from src.sim.sim import Sim
from src.sim.decoder import format_decoder_output

from .encoder import encode
from .insula import run_insula, format_emotional_state_block
from .hippocampus_pillar import run_hippocampus
from .pfc import run_pfc, build_system_prompt
from .context_assembly import assemble_window_context, assemble_rag_context
from .chat_tools import (
    CHAT_TOOLS,
    call_chat_tool,
    max_photos,
    parse_tool_args,
    photo_turn_context,
)

_DECODER_WINDOW_MAX = 20  # rolling window of raw messages for context assembly
_MINA_WINDOW        = 8   # messages Mina receives directly
_MAX_TOOL_ROUNDS    = 6


def _load_decoder_window() -> list[dict]:
    path = os.path.join(RUN_DIR, "decoder_window.json")
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_decoder_window(window: list[dict]) -> None:
    path = os.path.join(RUN_DIR, "decoder_window.json")
    os.makedirs(RUN_DIR, exist_ok=True)
    with open(path, "w") as f:
        json.dump(window, f)


def _append_conversation(role: str, content) -> None:
    path = get_conversation_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps({"role": role, "content": content, "ts": time.time()}) + "\n")


def _load_prior_emotional_state() -> dict | None:
    path = os.path.join(RUN_DIR, "prior_emotional_state.json")
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _save_prior_emotional_state(state: dict) -> None:
    path = os.path.join(RUN_DIR, "prior_emotional_state.json")
    os.makedirs(RUN_DIR, exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f)


async def run_turn(
    message: str,
    username: str,
    sim: Sim,
    *,
    image_count: str | int = "auto",
    image_aspect: str = "square",
) -> str:
    """
    Run the full per-turn pipeline. Returns Mina's reply.

    image_count: "auto" | 0 | 1..5 — UI pic preference (hard cap on send_photo).
    image_aspect: landscape | square | portrait — forced on host generate.
    """
    ts = time.time()
    log("USER", f"{username}: {message[:120]}")
    photo_cap = max_photos(image_count)
    aspect = image_aspect if image_aspect in ("landscape", "square", "portrait") else "square"

    # Load rolling window
    decoder_window = _load_decoder_window()

    # Append user message to window and conversation log
    decoder_window.append({"role": "user", "content": message, "ts": ts})
    _append_conversation("user", message)

    # ── 1. Encoder (state-blind) ────────────────────────────────────────────
    encoder_output = await asyncio.to_thread(encode, message, decoder_window[:-1])

    # ── 2. Relationship modifier + chemistry function ────────────────────────
    from src.hippocampus.hippocampus import get_relationship_modifier
    relationship_modifier = await asyncio.to_thread(get_relationship_modifier, username)
    log("PIPELINE", f"relationship_modifier({username})={relationship_modifier}")

    await asyncio.to_thread(
        sim.apply_chemistry_from_encoder, encoder_output, relationship_modifier
    )

    # ── 3. Sliding RAG write (post-user-message) ─────────────────────────────
    asyncio.create_task(_sliding_rag_write_async(decoder_window))

    # ── 4. Decoder snapshot ─────────────────────────────────────────────────
    decoded = await asyncio.to_thread(sim.snapshot)
    big5    = sim.get_big5()

    # ── 5. Insula pillar ────────────────────────────────────────────────────
    prior_emotional = _load_prior_emotional_state()
    insula_output = await asyncio.to_thread(
        run_insula, decoded, big5, prior_emotional
    )

    # ── 6. Memory retrieval (parallel) ──────────────────────────────────────
    from src.hippocampus.hippocampus import (
        build_kag_context, sliding_rag_query, build_rag_context_dual
    )

    kag_context, sliding_result, (semi_recent, historical) = await asyncio.gather(
        asyncio.to_thread(build_kag_context, message),
        asyncio.to_thread(sliding_rag_query, message),
        asyncio.to_thread(build_rag_context_dual, message),
    )
    experiences_result = "\n".join(filter(None, [semi_recent, historical]))

    # ── 7. Context assembly ──────────────────────────────────────────────────
    window_context, rag_context = await asyncio.gather(
        asyncio.to_thread(assemble_window_context, decoder_window),
        asyncio.to_thread(assemble_rag_context, sliding_result, experiences_result),
    )

    # ── 8. Hippocampus pillar ────────────────────────────────────────────────
    context_output = await asyncio.to_thread(
        run_hippocampus, insula_output, window_context, rag_context
    )

    # ── 9. PFC pillar ────────────────────────────────────────────────────────
    pfc_output = await asyncio.to_thread(
        run_pfc, insula_output, context_output, message, big5
    )

    if pfc_output.get("skip_primary_response"):
        log("PIPELINE", "PFC chose silence.")
        _save_prior_emotional_state(insula_output)
        _trim_and_save_window(decoder_window)
        return ""

    # ── 10. Build system prompt ─────────────────────────────────────────────
    system_prompt = build_system_prompt(insula_output, context_output, pfc_output)

    # Append KAG context to system prompt
    if kag_context:
        system_prompt += f"\n\n[Memory]\n{kag_context}"

    system_prompt += "\n\n" + photo_turn_context(image_count, aspect)

    # ── 11. Mina LLM call (+ optional send_photo tool loop) ────────────────
    mina_window = decoder_window[-_MINA_WINDOW:]
    messages: list[dict] = [{"role": "system", "content": system_prompt}] + [
        {"role": m["role"], "content": m["content"]}
        for m in mina_window
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]

    tools = CHAT_TOOLS if photo_cap > 0 else None
    photo_units: list[str] = []
    photos_sent = 0
    reply = ""

    for round_num in range(_MAX_TOOL_ROUNDS):
        create_kwargs: dict = dict(
            model=MODEL,
            messages=messages,
            max_tokens=1024,
            reasoning_effort="none",
        )
        if tools and photos_sent < photo_cap:
            create_kwargs["tools"] = tools
            create_kwargs["tool_choice"] = "auto"

        resp = await asyncio.to_thread(chat_create, **create_kwargs)
        msg = resp.choices[0].message
        content = msg.content or ""
        tool_calls = getattr(msg, "tool_calls", None) or []

        if not tool_calls:
            reply = content
            break

        messages.append({
            "role": "assistant",
            "content": content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ],
        })

        for tc in tool_calls:
            name = tc.function.name
            args = parse_tool_args(tc.function.arguments)
            if name == "send_photo" and photos_sent >= photo_cap:
                result = f"[send_photo skipped: already sent {photo_cap} this turn]"
            else:
                log("PIPELINE", f"Tool {round_num+1}: {name}")
                result = await asyncio.to_thread(
                    call_chat_tool, name, args, image_aspect=aspect
                )
                if name == "send_photo" and "![" in result and "/images/" in result:
                    photos_sent += 1
                    photo_units.append(result)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })
    else:
        # Exhausted tool rounds without a pure text finish
        reply = content if content else ""

    # Attach host photos after text if the model didn't already embed them
    if photo_units:
        units = "\n\n".join(photo_units)
        if reply.strip():
            # Drop model-invented fake image markdown; host photos are authoritative
            reply = _strip_fake_images(reply)
            if not any(u in reply for u in photo_units):
                reply = f"{reply.rstrip()}\n\n{units}"
        else:
            reply = units

    log("MINA", (reply[:120] if reply else "(empty)"))

    # ── 12. Post-turn bookkeeping ───────────────────────────────────────────
    decoder_window.append({"role": "assistant", "content": reply, "ts": time.time()})
    _append_conversation("assistant", reply)
    asyncio.create_task(_sliding_rag_write_async(decoder_window))

    _save_prior_emotional_state(insula_output)
    _trim_and_save_window(decoder_window)

    # ── 13. Full turn log ───────────────────────────────────────────────────
    _write_turn_log(
        ts=ts,
        username=username,
        message=message,
        encoder_output=encoder_output,
        relationship_modifier=relationship_modifier,
        decoder_snapshot=decoded,
        big5=big5,
        insula_output=insula_output,
        context_output=context_output,
        pfc_output=pfc_output,
        reply=reply,
    )

    return reply


def _strip_fake_images(text: str) -> str:
    """Remove model-invented image markdown that is not host /images/ or /api/generate/."""
    import re
    def keep(m: re.Match) -> str:
        url = m.group(2)
        if url.startswith("/images/") or url.startswith("/api/generate/"):
            return m.group(0)
        return ""
    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", keep, text).strip()


def _write_turn_log(
    ts: float,
    username: str,
    message: str,
    encoder_output: dict,
    relationship_modifier: float,
    decoder_snapshot: dict,
    big5: dict,
    insula_output: dict,
    context_output: dict,
    pfc_output: dict,
    reply: str,
) -> None:
    path = os.path.join(RUN_DIR, "turns.jsonl")
    os.makedirs(RUN_DIR, exist_ok=True)
    record = {
        "ts":                   ts,
        "ts_human":             time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)),
        "username":             username,
        "message":              message,
        "encoder":              encoder_output,
        "relationship_modifier": relationship_modifier,
        "sim_snapshot":         decoder_snapshot,
        "big5":                 big5,
        "insula":               insula_output,
        "hippocampus":          context_output,
        "pfc":                  pfc_output,
        "reply":                reply,
    }
    try:
        with open(path, "a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as e:
        log("PIPELINE/LOG/ERR", str(e))


def _trim_and_save_window(window: list[dict]) -> None:
    if len(window) > _DECODER_WINDOW_MAX:
        window[:] = window[-_DECODER_WINDOW_MAX:]
    _save_decoder_window(window)


async def _sliding_rag_write_async(window: list[dict]) -> None:
    try:
        from src.hippocampus.hippocampus import sliding_rag_write
        await asyncio.to_thread(sliding_rag_write, window)
    except Exception as e:
        log("PIPELINE/RAG/ERR", str(e))
