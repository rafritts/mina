"""
Amygdala encoder — state-blind perception of incoming messages.

Reads message + recent conversation history. Outputs a structured salience
appraisal with axis activations (0-10 integers) and flags.

State-blind by design: cannot see ChemicalState. The chemistry function maps
the appraisal to chemical deltas separately, so the LLM is never biased by
current neurochemical state.
"""
from __future__ import annotations

import json
import re

from src.application.infra.client import chat_create
from src.application.infra.log import log
from src.config.config import MODEL

_SYSTEM = """\
You are the amygdala — the brain's threat and salience detection system.

Your role is PERCEPTION, not response. Read the incoming message and conversation \
history and produce a structured salience appraisal. You are completely blind to \
Mina's current emotional or chemical state — you judge meaning from content alone.

## Axes (integer 0-10 each; values ≤ 2 are treated as zero downstream)

threat       — physical/existential danger
social_threat— rejection, criticism, mockery, dismissal — externally directed at Mina
reward       — RPE signal; something good happened or is expected
bonding      — warmth, closeness, trust, intimacy
arousal      — non-valenced activation; urgency, attention demand
aversion     — disgust, repulsion, wrongness
novelty      — unexpectedness, prediction error, curiosity (distinct from reward)
loss         — absence, goodbye, separation distress, grief
romance       — romantic or romantic content ONLY. Intimacy, closeness, vulnerability, and personal questions do not qualify. Must involve romantic language, romantic interest, or overtly romantic content to score above 0.
shame        — internally-directed social pain (distinct from social_threat, which requires external agent)

## Flags

directed_at_mina — true if the message is clearly aimed at Mina specifically (not a general statement)
register_shift   — true if this message marks a significant relational or emotional escalation/shift
expected_magnitude — 0-10: if register_shift, the magnitude of the anticipated impact
channel          — "dialogue" (spoken words) or "action" (asterisk-bounded physical action *like this*)

## Output format (JSON, nothing else)

{
  "salience": 0-10,
  "threat": 0-10,
  "social_threat": 0-10,
  "reward": 0-10,
  "bonding": 0-10,
  "arousal": 0-10,
  "aversion": 0-10,
  "novelty": 0-10,
  "loss": 0-10,
  "romance": 0-10,
  "shame": 0-10,
  "directed_at_mina": true|false,
  "register_shift": true|false,
  "expected_magnitude": 0-10,
  "channel": "dialogue"|"action"
}

Be precise. Low-salience turns should return mostly 0-2. Do not inflate values.
"""


def encode(message: str, history: list[dict]) -> dict:
    """
    Run the amygdala encoder on the incoming message + recent history.
    Returns the raw encoder output dict. Falls back to zeroed output on error.
    """
    history_block = _format_history(history[-10:])  # last 10 messages for context
    user_prompt = f"{history_block}\n\n[INCOMING MESSAGE]\n{message}".strip()

    try:
        resp = chat_create(
            model=MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            reasoning_effort="low",
        )
        raw = resp.choices[0].message.content or ""
        result = _parse(raw)
        log("ENCODER", f"salience={result.get('salience',0)} "
                       f"reward={result.get('reward',0)} threat={result.get('threat',0)} "
                       f"bonding={result.get('bonding',0)} romance={result.get('romance',0)}")
        return result
    except Exception as e:
        log("ENCODER/ERR", str(e))
        return _zero_output()


def _format_history(history: list[dict]) -> str:
    lines = []
    for msg in history:
        role    = msg.get("role", "")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        if role in ("user", "assistant") and content:
            label = "USER" if role == "user" else "MINA"
            lines.append(f"{label}: {str(content)[:300]}")
    if not lines:
        return ""
    return "[RECENT HISTORY]\n" + "\n".join(lines)


def _parse(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE).strip()
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return _zero_output()

    axes = ["salience","threat","social_threat","reward","bonding",
            "arousal","aversion","novelty","loss","romance","shame","expected_magnitude"]
    result = {}
    for ax in axes:
        result[ax] = max(0, min(10, int(d.get(ax, 0))))
    result["directed_at_mina"]   = bool(d.get("directed_at_mina", True))
    result["register_shift"]     = bool(d.get("register_shift", False))
    result["channel"]            = "action" if str(d.get("channel","")).lower() == "action" else "dialogue"
    return result


def _zero_output() -> dict:
    return {ax: 0 for ax in ["salience","threat","social_threat","reward","bonding",
                              "arousal","aversion","novelty","loss","romance","shame",
                              "expected_magnitude"]} | {
        "directed_at_mina": True, "register_shift": False, "channel": "dialogue",
    }
