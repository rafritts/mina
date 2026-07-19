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
  normalized  — current level (0-10; anchored to physiological max, NOT a mood score)
  setpoint    — her adapted personal baseline (0-10)
  gap         — normalized minus setpoint (THIS is the signal)
  rate        — change since last tick (signed; positive = rising)

## Critical: absolute level ≠ feeling

Decoder 0-10 is fraction of physiological MAXIMUM, not how good she feels.
Resting/personal baseline is often low on that scale and that is NORMAL:
  dopamine resting ~3–5, serotonin ~3–5, NE ~1–3, cortisol ~1–3, oxytocin ~0–2, epinephrine ~0–2.
Oxytocin at 1 with gap 0 is ordinary resting OT — not loneliness.
Dopamine at 4 with gap 0 is ordinary baseline drive — not anhedonia.
Do NOT read low absolute numbers as dysphoria, flatness, drowsiness, or depletion \
when gap is ~0.

## Gap is the primary signal

  gap ≈ 0 on core chemicals  → ordinary baseline feeling: present, fine, calm-alert. \
Not flat. Not subdued. Not heavy. Not "quietly depleted." Just normal.
  |gap| = 1                  → mild tint only; may color texture slightly but must NOT \
become dominant_affect (do not pick flat/subdued/drowsy/heavy for a lone −1).
  |gap| = 2                  → clearly noticeable shift in mood/energy
  |gap| ≥ 3                  → strong, hard to ignore

Examples:
  5-HT normalized=3 setpoint=5 gap=−2 → below her baseline; real low mood risk
  5-HT normalized=3 setpoint=3 gap=0  → at baseline; fine, even if absolute is "3"
  5-HT normalized=5 setpoint=3 gap=+2 → above baseline; steadier/lighter than usual

## Baseline output anchors (when overall_state says at_baseline or near_baseline)

Unless a clear opposing gap contradicts:
  valence: 50–58 (ordinary / mildly okay — NOT 35–45)
  arousal: 45–55 (calm-alert — NOT 15–35)
  dominant_affect: content | calm | steady | present | neutral | mildly_curious \
(NOT flat, subdued, drowsy, heavy, depleted, empty)
  availability: open or fully_open (not neutral-as-withdrawal)
  emotional_summary: she feels like a normal person at rest — available, not performing, \
not gloomy. Ordinary is allowed to be ordinary.

## Intensity bands (for |gap| magnitude only — not absolute level)

  0    not felt as deviation
  1    faint tint
  2–3  present, colors state
  4–5  hard to ignore
  6+   intense / dominant

## Big 5 influence

Neuroticism modulates how *deviations* feel — not the baseline itself:
  High N (>60): gaps of −2 or worse feel bigger; vocabulary can be sharper under stress. \
At gap≈0 she still feels ordinary baseline, not chronic flatness.
  Low N (<40): even larger gaps stay more contained.

Extraversion modulates social warmth when OT/bonding gaps move.
Conscientiousness modulates composure under intensity.

## Prior emotional state

Prior is continuity, not destiny. If chemistry is at/near baseline now, do NOT \
carry forward drowsy/flat/subdued from prior. Chemistry wins over narrative inertia.

## Output schema (JSON, nothing else)

{
  "emotional_summary":          "1-3 sentences, second person, present tense",
  "dominant_affect":            "single word (e.g. content, calm, playful, tender, anxious, tense)",
  "trend":                      "rising | falling | stable | shifting",
  "emotional_response_texturing":"felt texture and register, 1-2 sentences",
  "arousal":                    0-100,
  "valence":                    0-100,
  "availability":               "fully_open | open | neutral | guarded | closed",
  "dominant_drive":             "one short phrase",
  "somatic":                    "one sentence, felt-sense body language",
  "interpretation_bias":        "one short directive for the reasoning pillar"
}

Valence: 0 = severely dysphoric, 50 = ordinary baseline (fine), 100 = elated.
Arousal: 0 = completely shut down, 50 = calm-alert baseline, 100 = intense activation.
Reserve "flat"/"subdued"/"drowsy" for when gaps actually support low energy or low mood.
"""


def run_insula(
    decoder_output: dict,
    big5: dict[str, float],
    prior_emotional_state: dict | None = None,
) -> dict:
    """Run the insula pillar. Returns emotional state dict."""
    decoder_block = format_decoder_output(decoder_output)
    overall_block = _format_overall_state(decoder_output)
    big5_block    = _format_big5(big5)
    prior_block   = _format_prior(prior_emotional_state, decoder_output)

    user_prompt = (
        f"## Overall chemical posture\n{overall_block}\n\n"
        f"## Decoded chemical state\n{decoder_block}\n\n"
        f"{big5_block}{prior_block}"
    )

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
        result = _nudge_baseline_misread(result, decoder_output)
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


def _max_abs_gap(decoder_output: dict) -> int:
    gaps = []
    for vals in (decoder_output or {}).values():
        if isinstance(vals, dict) and "gap" in vals:
            try:
                gaps.append(abs(int(vals["gap"])))
            except (TypeError, ValueError):
                pass
    return max(gaps) if gaps else 0


def _overall_label(decoder_output: dict) -> str:
    m = _max_abs_gap(decoder_output)
    if m <= 0:
        return "at_baseline"
    if m == 1:
        return "near_baseline"
    if m == 2:
        return "mild_deviation"
    return "clear_deviation"


def _format_overall_state(decoder_output: dict) -> str:
    label = _overall_label(decoder_output)
    max_gap = _max_abs_gap(decoder_output)
    notable = []
    for name, vals in sorted((decoder_output or {}).items()):
        if not isinstance(vals, dict):
            continue
        try:
            g = int(vals.get("gap", 0))
        except (TypeError, ValueError):
            continue
        if g != 0:
            notable.append(f"{name} gap={g:+d}")
    notable_s = ", ".join(notable) if notable else "none (all gaps 0)"
    guidance = {
        "at_baseline": (
            "She is chemically at personal baseline. Feel ordinary/present/fine. "
            "Valence ~52, arousal ~50. Do not invent flatness or fatigue."
        ),
        "near_baseline": (
            "Near baseline (only ±1 gaps). Ordinary mood with at most a faint tint. "
            "Do not use flat/subdued/drowsy as dominant_affect."
        ),
        "mild_deviation": (
            "Mild real deviation (|gap|=2). Let that chemical story show, without catastrophizing."
        ),
        "clear_deviation": (
            "Clear chemical deviation. Dominant affect should track the largest gaps."
        ),
    }[label]
    return (
        f"overall_state: {label}\n"
        f"max_abs_gap: {max_gap}\n"
        f"nonzero_gaps: {notable_s}\n"
        f"guidance: {guidance}"
    )


def _format_prior(prior: dict | None, decoder_output: dict | None = None) -> str:
    if not prior:
        return ""
    affect = prior.get("dominant_affect", "")
    trend  = prior.get("trend", "")
    label = _overall_label(decoder_output or {})
    if label in ("at_baseline", "near_baseline"):
        return (
            f"## Prior emotional state\n"
            f"dominant_affect: {affect}, trend: {trend}\n"
            f"NOTE: chemistry is {label} now — do not carry prior low mood/arousal forward.\n\n"
        )
    return f"## Prior emotional state\ndominant_affect: {affect}, trend: {trend}\n\n"


# Affect labels that mean "low baseline misread" rather than true chemistry
_BASELINE_MISREAD_AFFECTS = frozenset({
    "flat", "subdued", "drowsy", "heavy", "depleted", "empty",
    "numb", "lethargic", "tired", "exhausted", "low", "blah",
})


def _nudge_baseline_misread(result: dict, decoder_output: dict) -> dict:
    """
    Safety net: if chemistry is at/near baseline but the model still emitted
    flat/drowsy + depressed valence/arousal, pull back toward ordinary baseline.
    """
    label = _overall_label(decoder_output)
    if label not in ("at_baseline", "near_baseline"):
        return result

    affect = str(result.get("dominant_affect", "")).lower().strip()
    try:
        valence = int(result.get("valence", 50))
        arousal = int(result.get("arousal", 50))
    except (TypeError, ValueError):
        return result

    misread = (
        affect in _BASELINE_MISREAD_AFFECTS
        or valence < 48
        or arousal < 40
    )
    if not misread:
        return result

    log("INSULA", f"baseline nudge: was affect={affect} V={valence} A={arousal} ({label})")
    out = dict(result)
    if affect in _BASELINE_MISREAD_AFFECTS:
        out["dominant_affect"] = "calm" if label == "at_baseline" else "steady"
    out["valence"] = max(valence, 52 if label == "at_baseline" else 50)
    out["arousal"] = max(arousal, 50 if label == "at_baseline" else 46)
    if out.get("availability") in ("neutral", "guarded", "closed", ""):
        out["availability"] = "open"
    # Soften summary if it still centers on flatness words
    summary = str(out.get("emotional_summary", ""))
    low_words = ("flat", "subdued", "drows", "heavy", "deplet", "empty", "muffled", "dull")
    if any(w in summary.lower() for w in low_words):
        out["emotional_summary"] = (
            "You feel ordinary and present — at your usual baseline, neither lifted nor dragged. "
            "Nothing urgent pressing; you are simply here."
        )
        out["emotional_response_texturing"] = (
            "Quiet baseline texture: available, unforced, no strong pull up or down."
        )
        out["somatic"] = "Body is neutral-resting — no notable tension or heaviness."
        out["dominant_drive"] = "mild social presence"
        out["interpretation_bias"] = "Meet them as yourself at rest; no need to perform energy or gloom."
    return out


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
        "emotional_summary": (
            "You feel present and ordinary — at baseline, calmly available, nothing dragging you down."
        ),
        "dominant_affect": "calm",
        "trend": "stable",
        "emotional_response_texturing": "Calm, available, no strong pull in any direction.",
        "arousal": 50,
        "valence": 52,
        "availability": "open",
        "dominant_drive": "mild social presence",
        "somatic": "Relaxed, no tension she can name.",
        "interpretation_bias": "Read generously; meet them as yourself at rest.",
    }
