"""
Context assembly — synthesizes raw memory retrieval into pillar-ready summaries.

Two LLM passes (following v1 pattern):
  1. Window synthesis  — present-moment facts from recent conversation window
  2. RAG synthesis     — memory context from episodic + sliding retrieval

Results feed into the hippocampus pillar prompt.
"""
from __future__ import annotations

from src.application.infra.client import chat_create
from src.config.config import CONTEXT_MODEL

_WINDOW_SYSTEM = """\
You are synthesizing the recent conversation window into concise, present-tense facts.

Given the recent exchange, identify:
- What topic or event is active right now
- The emotional register and dynamic between speakers
- Any unresolved threads, pending items, or open questions
- The current "scene" — where things stand this moment

Write 2-4 sentences in second person ("You are..."), present tense.
Be factual and specific. Do not editorialize.
"""

_RAG_SYSTEM = """\
You are synthesizing retrieved memory context into a useful background summary.

The retrieved memories span different time horizons. Your job is to identify:
- What relevant history or pattern is present here
- What context from the past matters for understanding this moment
- Any recurring dynamics, established facts, or meaningful prior moments

Write 2-4 sentences. Second person, present tense. Do not repeat the retrieved text verbatim.
Be selective — only surface what genuinely matters for right now.
"""


def assemble_window_context(decoder_window: list[dict]) -> str:
    """Synthesize the recent conversation window into a present-moment summary."""
    if not decoder_window:
        return ""

    formatted = _format_window(decoder_window[-20:])  # last 20 messages

    try:
        resp = chat_create(
            model=CONTEXT_MODEL,
            messages=[
                {"role": "system", "content": _WINDOW_SYSTEM},
                {"role": "user",   "content": formatted},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content or ""
    except Exception:
        return formatted[:500]  # fallback: raw excerpt


def assemble_rag_context(sliding_result: str, experiences_result: str) -> str:
    """Synthesize sliding + episodic RAG results into a memory context summary."""
    parts = []
    if sliding_result:
        parts.append(f"[Recent context]\n{sliding_result}")
    if experiences_result:
        parts.append(f"[Memory]\n{experiences_result}")
    if not parts:
        return ""

    combined = "\n\n".join(parts)
    try:
        resp = chat_create(
            model=CONTEXT_MODEL,
            messages=[
                {"role": "system", "content": _RAG_SYSTEM},
                {"role": "user",   "content": combined},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content or ""
    except Exception:
        return combined[:600]


def _format_window(messages: list[dict]) -> str:
    from src.brain.stage_direction import visible_speech

    lines = []
    for msg in messages:
        role    = msg.get("role", "")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        if role == "user":
            spoken = visible_speech(content)
            if not spoken:
                continue
            content = spoken
        if role in ("user", "assistant") and content:
            label = "USER" if role == "user" else "MINA"
            lines.append(f"{label}: {str(content)[:400]}")
    return "\n".join(lines)
