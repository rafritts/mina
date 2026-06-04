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

_DECODER_WINDOW_MAX = 20  # rolling window of raw messages for context assembly
_MINA_WINDOW        = 8   # messages Mina receives directly


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
) -> str:
    """
    Run the full per-turn pipeline. Returns Mina's reply.
    """
    ts = time.time()
    log("USER", f"{username}: {message[:120]}")

    # Load rolling window
    decoder_window = _load_decoder_window()

    # Append user message to window and conversation log
    decoder_window.append({"role": "user", "content": message, "ts": ts})
    _append_conversation("user", message)

    # ── 1. Encoder (state-blind) ────────────────────────────────────────────
    encoder_output = await asyncio.to_thread(encode, message, decoder_window[:-1])

    # ── 2. Chemistry function → sim ─────────────────────────────────────────
    # Get relationship modifier from hippocampus (async fetch in parallel below)
    # For now, use 1.0; relationship state feeds in via KAG
    await asyncio.to_thread(
        sim.apply_chemistry_from_encoder, encoder_output, 1.0
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

    # ── 11. Mina LLM call ──────────────────────────────────────────────────
    mina_window = decoder_window[-_MINA_WINDOW:]
    messages = [{"role": "system", "content": system_prompt}] + [
        {"role": m["role"], "content": m["content"]}
        for m in mina_window
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]

    resp = await asyncio.to_thread(
        chat_create,
        model=MODEL,
        messages=messages,
        max_tokens=1024,
        reasoning_effort="none",
    )
    reply = resp.choices[0].message.content or ""
    log("MINA", reply[:120])

    # ── 12. Post-turn bookkeeping ───────────────────────────────────────────
    decoder_window.append({"role": "assistant", "content": reply, "ts": time.time()})
    _append_conversation("assistant", reply)
    asyncio.create_task(_sliding_rag_write_async(decoder_window))

    _save_prior_emotional_state(insula_output)
    _trim_and_save_window(decoder_window)

    return reply


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
