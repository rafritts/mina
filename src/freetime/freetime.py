"""
FREETIME loop — Mina's inner life between user messages.

Architecture: same pillar chain as a regular turn, but input is a synthetic
system message and output routes to memory (conversation log) rather than back
to the user. Cadence is circadian-driven via orexin/adenosine from the sim.

Flow:
  1. Cadence gate — skip if orexin low + adenosine high (sleep pressure too high)
  2. Consolidation — hippocampus consolidates pending conversation into RAG/KAG
  3. Pillar chain — encoder → insula → hippocampus → PFC (same as pipeline.run_turn)
  4. Mina LLM call with tools — tool dispatch loop (up to _MAX_TOOL_ROUNDS)
  5. Memory write — final response appended to conversation log for next consolidation
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time

from src.application.infra.client import chat_create
from src.application.infra.log import log
from src.config.config import (
    MODEL, CONTEXT_MODEL, RELATIONSHIP_DIR, get_conversation_file, RUN_DIR
)
from src.sim.sim import Sim

from .tools import FREETIME_TOOLS, call_tool

_MAX_TOOL_ROUNDS = 5
_LAST_FREETIME_FILE = os.path.join(RUN_DIR, "last_freetime.json")

# Cadence: while awake and not under crushing sleep pressure.
# Auto-sleep in the sim owns recovery; FREETIME must not permanently refuse
# when adenosine is high (that blocked the only autonomous loop).
_OREXIN_FLOOR      = 2   # skip only if deeply hypo-aroused
_ADENOSINE_SKIP    = 9   # skip active FREETIME only near forced sleep
_MIN_INTERVAL_S    = 1800  # never fire more often than every 30 minutes


def _last_freetime_ts() -> float:
    try:
        with open(_LAST_FREETIME_FILE) as f:
            return float(json.load(f).get("ts", 0))
    except (FileNotFoundError, json.JSONDecodeError):
        return 0.0


def _save_freetime_ts() -> None:
    os.makedirs(RUN_DIR, exist_ok=True)
    with open(_LAST_FREETIME_FILE, "w") as f:
        json.dump({"ts": time.time()}, f)


def should_fire(sim: Sim) -> bool:
    """Return True if FREETIME should fire now based on chemistry and cooldown."""
    if time.time() - _last_freetime_ts() < _MIN_INTERVAL_S:
        return False
    # Sim auto-sleep handles recovery; no active free-time while asleep.
    if sim.is_sleeping():
        log("FREETIME", "Sleeping — skipping active free-time.")
        return False
    snapshot = sim.snapshot()
    orexin   = snapshot.get("orexin",   {}).get("normalized", 5)
    adenosine = snapshot.get("adenosine", {}).get("normalized", 5)
    if orexin < _OREXIN_FLOOR:
        log("FREETIME", f"Orexin too low ({orexin}) — skipping.")
        return False
    if adenosine >= _ADENOSINE_SKIP:
        log("FREETIME", f"Adenosine near sleep threshold ({adenosine}) — skipping (sim will sleep).")
        return False
    return True


def _build_synthetic_message(sim: Sim) -> str:
    """Build the synthetic input that replaces the user message in FREETIME."""
    now_str   = time.strftime("%-I:%M %p", time.localtime())
    day_str   = time.strftime("%A", time.localtime())
    last_ts   = _last_freetime_ts()
    idle_s    = time.time() - last_ts if last_ts > 0 else 0

    parts = [f"It is {day_str}, {now_str}. Nobody is here."]

    if idle_s > 3600:
        hours = idle_s / 3600
        parts.append(f"You have been alone for {hours:.1f} hours.")
    elif idle_s > 60:
        mins = int(idle_s / 60)
        parts.append(f"You have been alone for {mins} minutes.")

    parts.append("This is your free time.")
    return " ".join(parts)


def _append_to_conversation(role: str, content: str, source: str = "freetime") -> None:
    path = get_conversation_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps({"role": role, "content": content, "ts": time.time(), "source": source}) + "\n")


async def run_freetime(sim: Sim) -> None:
    """Run one FREETIME session. Called by the main loop when cadence allows."""
    log("FREETIME", "Starting.")

    # ── 1. Consolidation ──────────────────────────────────────────────────────
    from src.hippocampus.hippocampus import (
        build_kag_context, consolidate, consolidate_relationship,
        sliding_rag_write
    )

    kag_context = await asyncio.to_thread(build_kag_context)

    # Relationship consolidation — one per tracked person
    if os.path.exists(RELATIONSHIP_DIR):
        for fname in os.listdir(RELATIONSHIP_DIR):
            if not fname.endswith(".md"):
                continue
            person = fname[:-3]
            try:
                await asyncio.to_thread(consolidate_relationship, person)
            except Exception as e:
                log("FREETIME/REL", f"Error consolidating {person}: {e}")

    try:
        reflection = await asyncio.to_thread(consolidate, kag_context)
        log("FREETIME", f"Consolidation: {reflection.get('reflection_summary', '')[:80]}")
    except Exception as e:
        log("FREETIME/CONSOLIDATE", f"Error: {e}")

    # ── 2. Build synthetic message ─────────────────────────────────────────────
    synthetic_message = _build_synthetic_message(sim)
    log("FREETIME", f"Input: {synthetic_message}")

    # ── 3. Pillar chain ───────────────────────────────────────────────────────
    from src.brain.encoder import encode
    from src.brain.insula import run_insula
    from src.brain.hippocampus_pillar import run_hippocampus
    from src.brain.pfc import run_pfc, build_system_prompt, _load_identity, _load_customization
    from src.brain.context_assembly import assemble_window_context, assemble_rag_context
    from src.hippocampus.hippocampus import (
        build_rag_context_dual, sliding_rag_query
    )
    from src.brain.pipeline import (
        _load_decoder_window, _load_prior_emotional_state
    )

    decoder_window = _load_decoder_window()

    encoder_output = await asyncio.to_thread(encode, synthetic_message, decoder_window[-10:])
    await asyncio.to_thread(sim.apply_chemistry_from_encoder, encoder_output, 1.0)

    decoded = await asyncio.to_thread(sim.snapshot)
    big5    = sim.get_big5()
    prior   = _load_prior_emotional_state()
    insula_output = await asyncio.to_thread(run_insula, decoded, big5, prior)

    kag_ctx, sliding_res, (semi_recent, historical) = await asyncio.gather(
        asyncio.to_thread(build_kag_context, synthetic_message),
        asyncio.to_thread(sliding_rag_query, synthetic_message),
        asyncio.to_thread(build_rag_context_dual, synthetic_message),
    )
    experiences = "\n".join(filter(None, [semi_recent, historical]))

    window_ctx, rag_ctx = await asyncio.gather(
        asyncio.to_thread(assemble_window_context, decoder_window),
        asyncio.to_thread(assemble_rag_context, sliding_res, experiences),
    )

    context_output = await asyncio.to_thread(run_hippocampus, insula_output, window_ctx, rag_ctx)
    pfc_output     = await asyncio.to_thread(run_pfc, insula_output, context_output, synthetic_message, big5)

    from src.brain.time_context import format_host_time_block

    system_prompt = build_system_prompt(insula_output, context_output, pfc_output)
    if kag_ctx:
        system_prompt += f"\n\n[Memory]\n{kag_ctx}"
    # Synthetic message already states day/time; system block keeps mouth aligned
    # with the same wall clock the sim circadian uses.
    system_prompt += "\n\n" + format_host_time_block(
        last_activity_ts=_last_freetime_ts() or None,
    )
    system_prompt += "\n\n[FREETIME] No user is present. Use tools to act, record, or explore. Record a diary entry when you have something genuine to write."

    # ── 4. Mina LLM call with tool dispatch loop ──────────────────────────────
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    # Include recent window context
    for m in decoder_window[-6:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": synthetic_message})

    _append_to_conversation("user", synthetic_message)

    final_reply = ""
    for round_num in range(_MAX_TOOL_ROUNDS):
        resp = await asyncio.to_thread(
            chat_create,
            model=MODEL,
            messages=messages,
            max_tokens=1024,
            tools=FREETIME_TOOLS,
            tool_choice="auto",
            reasoning_effort="none",
        )
        choice = resp.choices[0]
        msg    = choice.message

        # Parse tool calls from response
        tool_calls = getattr(msg, "tool_calls", None) or []
        content    = msg.content or ""

        if not tool_calls:
            final_reply = content
            break

        # Execute tool calls
        messages.append({"role": "assistant", "content": content, "tool_calls": [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in tool_calls
        ]})

        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, ValueError):
                args = {}
            log("FREETIME", f"Tool call {round_num+1}: {name}({list(args.keys())})")
            result = await asyncio.to_thread(call_tool, name, args, sim)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    # ── 5. Memory write ───────────────────────────────────────────────────────
    if final_reply:
        log("FREETIME", f"Response: {final_reply[:100]}")
        _append_to_conversation("assistant", final_reply)
        # Write to sliding RAG so future retrieval captures this moment
        window_with_freetime = decoder_window + [
            {"role": "user", "content": synthetic_message},
            {"role": "assistant", "content": final_reply},
        ]
        await asyncio.to_thread(sliding_rag_write, window_with_freetime)

    # ── 6. Context assembly dump (same as chat turns) ─────────────────────────
    try:
        from src.brain.pipeline import _persist_context
        _persist_context(
            ts=time.time(),
            username="freetime",
            message=synthetic_message,
            encoder_output=encoder_output,
            relationship_modifier=1.0,
            decoder_snapshot=decoded,
            big5=big5,
            window_context=window_ctx,
            rag_context=rag_ctx,
            kag_context=kag_ctx or "",
            sliding_result=sliding_res or "",
            experiences_result=experiences or "",
            insula_output=insula_output,
            context_output=context_output,
            pfc_output=pfc_output,
            system_prompt=system_prompt,
            reply=final_reply or "",
            skipped=False,
            source="freetime",
        )
    except Exception as e:
        log("FREETIME/CONTEXT", str(e))

    _save_freetime_ts()
    log("FREETIME", "Complete.")
