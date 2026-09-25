"""
Hippocampus pillar — context / memory LLM call.

Inputs: insula output, window context, RAG context.
Outputs: situational summary, social context, urgency, notable.

Unchanged from v1 contract.
"""
from __future__ import annotations

import json
import re

from src.application.infra.client import chat_create
from src.application.infra.log import log
from src.config.config import CONTEXT_MODEL

_SYSTEM = """\
You are the hippocampus — Mina's context and memory integrator.

You receive Mina's current emotional state, assembled conversation/memory context, and \
(when present) her prior live scene snapshot (clothing, positions, fiction time, timeline, \
plans — authored by her last reply and stored by the host).

Your job: synthesize what is situationally relevant given how she feels.

Ground physical/situational facts in the live scene when it is present — do not invent \
a different location, outfit, or fiction-time. Window context is dialogue texture; live \
scene is durable body/place/time state.

Felt state reframes what counts as notable. If she is anxious, ambiguous signals matter more. \
If she is content, minor friction may not register. Let the emotional state guide what you flag.

## Output schema (JSON, nothing else)

{
  "situational_summary": "1-5 paragraphs, second person, present tense. What is happening, \
who is present, what the dynamic is, what matters right now.",
  "social_context": "short label, e.g. 'one-on-one, familiar' or 'alone'",
  "urgency": "none | low | high",
  "notable": null or "1-3 sentences on something genuinely worth flagging to the PFC"
}

Do not manufacture urgency. Do not flag things that are not genuinely notable.
"""


def run_hippocampus(
    insula_output: dict,
    window_context: str,
    rag_context: str,
    scene_block: str = "",
    *,
    stage_directions: list[str] | None = None,
) -> dict:
    """Run the hippocampus context pillar."""
    emotional_block = "\n".join(f"{k}: {v}" for k, v in insula_output.items())
    parts = [
        f"## Emotional state\n{emotional_block}",
    ]
    if scene_block and scene_block.strip():
        parts.append(f"## Live scene (prior snapshot — ground truth for place/clothes/time)\n{scene_block.strip()}")
    from src.brain.stage_direction import format_hippocampus_block

    direction_block = format_hippocampus_block(stage_directions or [])
    if direction_block:
        parts.append(direction_block)
    parts.append(f"## Window context\n{window_context or '(none)'}")
    parts.append(f"## Memory context\n{rag_context or '(none)'}")
    user_prompt = "\n\n".join(parts)

    try:
        resp = chat_create(
            model=CONTEXT_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
            reasoning_effort="none",
        )
        raw = resp.choices[0].message.content or ""
        result = _parse(raw)
        log("HIPPOCAMPUS", f"urgency={result.get('urgency','')} social={result.get('social_context','')}")
        return result
    except Exception as e:
        log("HIPPOCAMPUS/ERR", str(e))
        return _default_output()


def _parse(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE).strip()
    try:
        d = json.loads(raw)
        urgency = str(d.get("urgency", "none")).lower()
        if urgency not in ("none", "low", "high"):
            urgency = "none"
        return {
            "situational_summary": str(d.get("situational_summary", "")),
            "social_context":      str(d.get("social_context", "one-on-one")),
            "urgency":             urgency,
            "notable":             d.get("notable"),
        }
    except (json.JSONDecodeError, Exception):
        return _default_output()


def _default_output() -> dict:
    return {
        "situational_summary": "You are in conversation. The current exchange feels present and engaged.",
        "social_context": "one-on-one",
        "urgency": "none",
        "notable": None,
    }
