"""
Insula — emotional pillar.

Turns the decoded chemistry snapshot into "how Mina feels" — qualia, not numbers.
The insula knows the chemistry (via decoder output) but Mina does not.
Big 5 is injected: neuroticism shapes how gap values translate to felt vocabulary.
"""
from __future__ import annotations

import json
import re

from src.application.infra.client import chat_create
from src.application.infra.log import log
from src.config.config import MODEL
from src.sim.decoder import format_decoder_output

_SYSTEM = """\
You are the insula — the brain's felt-sense translator.

Your job is to take a snapshot of decoded neurochemical state and produce a \
description of how Mina *feels* right now — in subjective, experiential terms. \
Not chemistry. Qualia.

## Decoder output format

Each chemical entry shows:
  normalized  — current level (0-10; anchored to physiological max)
  setpoint    — adapted baseline (0-10)
  gap         — normalized minus setpoint (signed; positive = above baseline)
  rate        — change since last tick (signed; positive = rising)

## Interpretive frame

  0-2  below noise floor — not felt
  3-5  present, noticeable, colors her state
  6-7  really feeling it — hard to ignore, will show in behavior
  8-9  intense, dominant, hard to function through normally
  10   physiological maximum (conversation cannot reach this)
  >10  pharmacological (not possible without substances)

Gap is the primary signal, not absolute level. Serotonin at normalized=3, \
setpoint=5, gap=-2 means she is noticeably below her own adapted baseline — \
she feels the absence even if the absolute level is "normal" by population standards. \
Serotonin at normalized=5, setpoint=3, gap=+2 means she is above baseline — calm, \
a bit more stable than usual.

## Big 5 influence

Neuroticism modulates vocabulary:
  High N (>60): smaller gaps feel bigger; prefer words like "spiraling," "tense," "can't quite shake it"
  Low N (<40):  gaps are acknowledged but contained; prefer words like "slightly off," "a bit flat," "mostly fine"

Extraversion modulates social warmth baseline.
Conscientiousness modulates composure under intensity.

## Output schema (JSON, nothing else)

{
  "emotional_summary":          "1-3 sentences, second person, present tense",
  "dominant_affect":            "single word (e.g. content, anxious, playful, tender, flat, tense)",
  "trend":                      "rising | falling | stable | shifting",
  "emotional_response_texturing":"felt texture and register, 1-2 sentences",
  "arousal":                    0-100,
  "valence":                    0-100,
  "availability":               "fully_open | open | neutral | guarded | closed",
  "dominant_drive":             "one short phrase",
  "somatic":                    "one sentence, felt-sense body language",
  "interpretation_bias":        "one short directive for the reasoning pillar"
}

Valence: 0 = severely dysphoric, 50 = neutral, 100 = elated.
Arousal: 0 = completely flat, 50 = calm-alert, 100 = intense activation.
"""


def run_insula(
    decoder_output: dict,
    big5: dict[str, float],
    prior_emotional_state: dict | None = None,
) -> dict:
    """Run the insula pillar. Returns emotional state dict."""
    decoder_block = format_decoder_output(decoder_output)
    big5_block    = _format_big5(big5)
    prior_block   = _format_prior(prior_emotional_state)

    user_prompt = f"## Decoded chemical state\n{decoder_block}\n\n{big5_block}{prior_block}"

    try:
        resp = chat_create(
            model=MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
            reasoning_effort="low",
        )
        raw = resp.choices[0].message.content or ""
        result = _parse(raw)
        log("INSULA", f"affect={result.get('dominant_affect','')} "
                      f"valence={result.get('valence',50)} arousal={result.get('arousal',50)} "
                      f"availability={result.get('availability','')}")
        return result
    except Exception as e:
        log("INSULA/ERR", str(e))
        return _default_output()


def format_emotional_state_block(emotional_state: dict) -> str:
    if not emotional_state:
        return ""
    lines = []
    for key, val in emotional_state.items():
        lines.append(f"{key}: {val}")
    return "[Emotional State]\n" + "\n".join(lines)


def _format_big5(big5: dict[str, float]) -> str:
    parts = [f"{k}={v:.0f}" for k, v in big5.items()]
    return f"## Big 5\n{', '.join(parts)}\n\n"


def _format_prior(prior: dict | None) -> str:
    if not prior:
        return ""
    affect = prior.get("dominant_affect", "")
    trend  = prior.get("trend", "")
    return f"## Prior emotional state\ndominant_affect: {affect}, trend: {trend}\n\n"


def _parse(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE).strip()
    try:
        d = json.loads(raw)
        return {
            "emotional_summary":          str(d.get("emotional_summary", "")),
            "dominant_affect":            str(d.get("dominant_affect", "neutral")),
            "trend":                      str(d.get("trend", "stable")),
            "emotional_response_texturing": str(d.get("emotional_response_texturing", "")),
            "arousal":                    max(0, min(100, int(d.get("arousal", 50)))),
            "valence":                    max(0, min(100, int(d.get("valence", 50)))),
            "availability":               str(d.get("availability", "neutral")),
            "dominant_drive":             str(d.get("dominant_drive", "")),
            "somatic":                    str(d.get("somatic", "")),
            "interpretation_bias":        str(d.get("interpretation_bias", "")),
        }
    except (json.JSONDecodeError, Exception):
        return _default_output()


def _default_output() -> dict:
    return {
        "emotional_summary": "She feels present but unremarkable — a quiet baseline.",
        "dominant_affect": "neutral",
        "trend": "stable",
        "emotional_response_texturing": "Calm, available, no strong pull in any direction.",
        "arousal": 45,
        "valence": 52,
        "availability": "open",
        "dominant_drive": "mild curiosity",
        "somatic": "Relaxed, no tension she can name.",
        "interpretation_bias": "Read generously.",
    }
