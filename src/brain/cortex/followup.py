"""
Followup firing — deferred responses that Mina scheduled via schedule_followup().

When a followup fires:
  - Fresh state is loaded and advanced
  - Emotion is adjudicated against the deferred context (not current conversation)
  - KAG/RAG memory is built using the deferred context as the query
  - NO conversation history — the history at fire time is irrelevant
  - Response is delivered directly via discord_send
"""
from __future__ import annotations

import asyncio
import json
import os
import time

from src.config.config import FOLLOWUP_QUEUE_FILE
from src.application.infra import discord_send as _discord_send
from src.application.infra.log import log


def load_queue() -> list[dict]:
    try:
        with open(FOLLOWUP_QUEUE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_queue(queue: list[dict]) -> None:
    os.makedirs(os.path.dirname(FOLLOWUP_QUEUE_FILE), exist_ok=True)
    with open(FOLLOWUP_QUEUE_FILE, "w") as f:
        json.dump(queue, f, indent=2)


def pop_due(queue: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split queue into (due, remaining) based on current time."""
    now = time.time()
    due = [e for e in queue if e.get("fires_at", 0) <= now]
    remaining = [e for e in queue if e.get("fires_at", 0) > now]
    return due, remaining


async def fire_followup(entry: dict) -> None:
    """
    Fire a single deferred followup. Runs a fresh Mina turn against the stored
    context with no conversation history — only emotion adjudication + KAG/RAG.
    """
    from src.brain.brainstem.state import load_and_advance, save_state
    from src.brain.hippocampus.hippocampus import build_kag_context, build_rag_context_bucketed
    from src.application.infra import token_stats
    from src.application.infra.client import chat_create, MODEL
    from src.brain.amygdala.stimulus_encoder import encode_response
    from src.brain.brainstem.state import apply_deltas
    from src.brain.subconscious.decoder import build_rag_context
    from src.brain.cortex.emotional_reasoner import run_emotion_pillar, format_emotional_state_block

    context = entry.get("context", "")
    scheduled_at = entry.get("scheduled_at", time.time())
    delay_str = entry.get("delay_str", "")

    elapsed_seconds = time.time() - scheduled_at
    if elapsed_seconds < 3600:
        elapsed_label = f"{int(elapsed_seconds / 60)} minutes"
    elif elapsed_seconds < 86400:
        elapsed_label = f"{elapsed_seconds / 3600:.1f} hours"
    else:
        elapsed_label = f"{elapsed_seconds / 86400:.1f} days"

    log("FOLLOWUP", f"Firing: scheduled {elapsed_label} ago — {context}")

    state = load_and_advance()

    # Adjudicate emotion against the deferred context, not current conversation
    stimulus = f"[DEFERRED — {elapsed_label} ago] {context}"

    kag_context = build_kag_context()
    rag_recent, rag_semi_recent, rag_historical = build_rag_context_bucketed(context)

    _emotion_result, memory_context = await asyncio.gather(
        asyncio.to_thread(run_emotion_pillar, state, stimulus, "active"),
        asyncio.to_thread(build_rag_context,
                          context,
                          kag_context,
                          rag_recent,
                          "",
                          rag_historical),
    )

    # Assemble system prompt — NO conversation history
    system_parts = []
    if memory_context:
        system_parts.append(memory_context)
    if _emotion_result:
        system_parts.append(format_emotional_state_block(_emotion_result))
    system_prompt = "\n\n---\n\n".join(system_parts) if system_parts else "You are Mina."

    # Single user turn — the deferred context is all she gets
    user_message = (
        f"[DEFERRED FOLLOWUP]\n"
        f"You scheduled this response {elapsed_label} ago (delay: {delay_str}).\n"
        f"The context you left yourself:\n\n{context}\n\n"
        f"Respond now. No conversation history is available — this is a standalone response."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    response = await asyncio.to_thread(
        chat_create,
        model=MODEL,
        messages=messages,
        temperature=0.85,
    )
    token_stats.record_response("followup", response)
    reply = (response.choices[0].message.content or "").strip()

    if not reply:
        log("FOLLOWUP/ERR", "Empty response — skipping delivery")
        return

    log("FOLLOWUP/REPLY", reply)

    await _discord_send.send(content=reply)

    # Apply biological effect of having expressed this
    response_deltas = await asyncio.to_thread(
        encode_response, state, reply
    )
    if response_deltas:
        state = apply_deltas(state, response_deltas)

    save_state(state)


async def process_due_followups() -> None:
    """Check the queue and fire any expired entries. Called by the gateway watcher."""
    queue = load_queue()
    if not queue:
        return

    due, remaining = pop_due(queue)
    if not due:
        return

    # Persist the trimmed queue before firing — so a crash doesn't re-fire
    save_queue(remaining)

    for entry in due:
        try:
            await fire_followup(entry)
        except Exception as e:
            log("FOLLOWUP/ERR", f"Failed to fire followup: {e}")
