"""
Encoder — external events → neurochemical deltas.

Translates what happened in the world (incoming messages, Mina's own responses,
physical actions) into delta dicts that get applied to BiologicalState.

Three public entry points:
    encode_stimulus(state, text)              — incoming message/event
    encode_response(state, text)              — Mina's reply
    evaluate_activity_deltas(state, act, desc) — do_action tool result

All three return plain dicts of chemical field → float delta.
Falls back to {} on any error — never crashes a turn.
"""
import json
import os
import re

from client import get_client, MODEL
from config import PERSONALITY_FILE
from state import BiologicalState

# ---------------------------------------------------------------------------
# Prompt constants
# ---------------------------------------------------------------------------

_DELTA_FIELDS = {
    "cortisol", "dopamine", "serotonin", "norepinephrine",
    "oxytocin", "endorphins", "sleep_pressure", "glucose",
    "hydration", "acetylcholine",
}

_DELTA_FORMAT = """\
## Your role
You are a translator: external events → neurochemical deltas.
You do NOT model ongoing internal biological states — hunger, fatigue, dehydration, and all \
homeostatic drift are already computed by the simulation. Your job is to encode what just \
happened in the world or what she just did. If nothing external happened, post no deltas.

## Response format
Always respond with a JSON object. Always include "no_external_deltas" and "reasoning".

If nothing external happened (ongoing internal state, nothing happened, quiet period):
{
  "no_external_deltas": true,
  "reasoning": "<one sentence: why there is nothing external to encode>"
}

If an external event occurred:
{
  "no_external_deltas": false,
  "reasoning": "<one sentence: what external event triggered these specific deltas>",
  "cortisol": <number>,       // nmol/L delta
  "dopamine": <number>,       // pg/mL delta
  "serotonin": <number>,      // ng/mL delta
  "norepinephrine": <number>, // pg/mL delta
  "oxytocin": <number>,       // pg/mL delta
  "endorphins": <number>,     // pg/mL delta
  "sleep_pressure": <number>, // AU delta
  "glucose": <number>,        // mg/dL delta
  "hydration": <number>,      // % TBW delta
  "acetylcholine": <number>,  // nmol/L delta
  "event_override": false     // true only for discrete biological events (see below)
}

Only include chemical fields that actually change from the external event."""

_EVENT_OVERRIDE_GUIDANCE = """\
event_override — set to true ONLY when a discrete biological event with a known sharp signature occurs.
When true, your deltas bypass saturation scaling and personality modulation and are applied directly.
Use calibrated magnitudes for these events:

- Peak resolution: dopamine -100 to -150, sleep_pressure +30 to +40, norepinephrine -60 to -100
- Panic attack: cortisol +300 to +400, norepinephrine +500 to +700, dopamine -30 to -50
- Hard laughter (genuine, sustained): endorphins +30 to +50, dopamine +15 to +25
- Crying (emotional release): cortisol -40 to -80, endorphins +10 to +20
- Startle: norepinephrine +150 to +250, cortisol +50 to +100
- Social rejection (felt, not abstract): cortisol +100 to +200, serotonin -3 to -8, oxytocin -5 to -10
- Awe/wonder: dopamine +20 to +40, acetylcholine +10 to +20, serotonin +2 to +5
- Anger burst: norepinephrine +200 to +400, cortisol +100 to +200

For everything else, set event_override: false and use conservative deltas."""


# ---------------------------------------------------------------------------
# Saturation and personality scaling
# ---------------------------------------------------------------------------

def _apply_saturation(deltas: dict, state: BiologicalState) -> dict:
    """
    Scale down positive deltas for chemicals already near their ceiling.
    Uses quadratic decay in the soft→hard zone — aggressive near ceiling.
    Substances bypass this; only encoder-issued deltas are saturated.
    """
    from chemicals import REGISTRY
    result = {}
    for field, delta in deltas.items():
        p = REGISTRY.get(field)
        if delta <= 0 or p is None or p.soft_ceiling is None:
            result[field] = delta
            continue
        current = state.chemicals.get(field, 0.0)
        soft = p.soft_ceiling
        hard = p.hard_ceiling if p.hard_ceiling is not None else soft * 1.5
        if current >= hard:
            continue  # drop the delta entirely
        elif current > soft:
            t = (current - soft) / (hard - soft)  # 0 at soft, 1 at hard
            scale = (1.0 - t) ** 2                 # quadratic: aggressive near ceiling
            scaled = round(delta * scale, 2)
            scaled = min(scaled, hard - current)
            if scaled != 0:
                result[field] = scaled
        else:
            result[field] = min(delta, hard - current)
    return result


def _load_personality() -> dict:
    """Load personality.json. Returns empty dict if not found."""
    try:
        with open(PERSONALITY_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _personality_multipliers(personality: dict) -> dict[str, float]:
    """
    Convert Big 5 scores into per-chemical delta scaling factors.

    Multiplier ranges are intentionally narrow (0.8–1.4) so personality flavors
    rather than dominates — the stimulus itself still drives magnitude.
    """
    big5 = personality.get("big5", {})
    N = big5.get("neuroticism",       50) / 100
    E = big5.get("extraversion",      50) / 100
    A = big5.get("agreeableness",     50) / 100
    C = big5.get("conscientiousness", 50) / 100
    O = big5.get("openness",          50) / 100

    n_factor = 0.8 + N * 0.6          # range: 0.80 (N=0) → 1.40 (N=100)

    e_factor = 0.7 + E * 0.6          # range: 0.70 → 1.30
    c_brake  = 1.3 - C * 0.6          # range: 1.30 (C=0) → 0.70 (C=100)
    dopamine_factor = e_factor * c_brake

    a_factor  = 0.7 + A * 0.6         # range: 0.70 → 1.30
    sero_factor = 0.8 + A * 0.4       # range: 0.80 → 1.20

    o_factor  = 0.8 + O * 0.4         # range: 0.80 → 1.20

    ds = personality.get("neurochemical_baselines", {}).get("dopamine_sensitivity", 1.0)

    return {
        "cortisol":       n_factor,
        "norepinephrine": n_factor,
        "dopamine":       dopamine_factor * ds,
        "oxytocin":       a_factor,
        "serotonin":      sero_factor,
        "acetylcholine":  o_factor,
    }


def _apply_personality_scaling(deltas: dict, personality: dict) -> dict:
    """
    Scale encoder-issued chemical deltas by Big 5 personality factors.

    N asymmetry: positive cortisol/norepi deltas (spikes) are amplified;
    negative deltas (recovery) are dampened — high N means faster to stress,
    slower to recover.
    """
    if not personality:
        return deltas
    mults = _personality_multipliers(personality)
    result = {}
    for field, delta in deltas.items():
        m = mults.get(field, 1.0)
        if field in ("cortisol", "norepinephrine") and delta < 0:
            # Recovery is slower at high N: invert the factor
            m = 1.0 / m if m != 0 else 1.0
        result[field] = round(delta * m, 2)
    return result


# ---------------------------------------------------------------------------
# LLM delta call
# ---------------------------------------------------------------------------

def _call_delta_json(messages: list[dict], label: str = "delta") -> tuple[dict, bool]:
    """
    Plain completion returning a delta dict + event_override flag.
    Falls back to ({}, False) on any error — never crashes a turn.
    """
    try:
        response = get_client().chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.3,
        )
        import token_stats
        token_stats.record_response(label, response)
        content = response.choices[0].message.content or ""
        content = re.sub(r"^```(?:json)?\s*", "", content.strip())
        content = re.sub(r"\s*```$", "", content)
        parsed = json.loads(content)
        reasoning = parsed.pop("reasoning", "")
        no_external = bool(parsed.pop("no_external_deltas", False))
        reason_str = f" — {reasoning}" if reasoning else ""
        if no_external:
            print(f"[encoder/{label}] no_external_deltas{reason_str}")
            return {}, False
        event_override = bool(parsed.pop("event_override", False))
        deltas = {k: float(v) for k, v in parsed.items() if k in _DELTA_FIELDS}
        override_str = " [EVENT_OVERRIDE]" if event_override else ""
        delta_str = ", ".join(f"{k}: {v:+.1f}" for k, v in deltas.items())
        print(f"[encoder/{label}]{override_str} {delta_str or '(no deltas)'}{reason_str}")
        return deltas, event_override
    except Exception as e:
        print(f"[encoder/{label} error] {e}")
    return {}, False


# ---------------------------------------------------------------------------
# Public encode functions
# ---------------------------------------------------------------------------

def encode_stimulus(state: BiologicalState, stimulus_text: str) -> dict:
    """
    Determine biological deltas from an incoming stimulus (message, event).
    Called before building the system prompt each turn.
    """
    from decoder import biological_report
    report = biological_report(state)

    prompt = f"""{report}

Incoming stimulus (context for what just happened externally):
{stimulus_text}

Your job: encode only what came from OUTSIDE — a social event, an environmental trigger, \
something that happened in the world. Internal biological state (hunger, thirst, fatigue, \
loneliness) is already modeled by the simulation and must NOT be re-encoded here. If the \
stimulus is purely internal state with no external event, set no_external_deltas: true.

External event magnitude guidance:
- Cortisol (nmol/L, resting 100–700): Acute existential threat (abandonment, attack): +300–500. Sustained hostility: +100–200. Mild friction: +30–80. Warm interaction: -20–60.
- Norepinephrine (pg/mL, resting 100–400): Acute threat: +400–800. Mild friction: +30–100.
- Oxytocin (pg/mL, resting 1–15): Warm connection: +2–8. Deep trust moment: +8–15. Hostile event: -1 to -3.
- Dopamine (pg/mL, resting 40–140): Interesting external stimulus: +5–20. Crushing loss/rejection: -5–15.
- Serotonin (ng/mL, resting 10–35): Positive social: +1–3. Very slow to move — only if genuinely meaningful.
- Endorphins (pg/mL, resting 5–30): Laughter/warmth: +5–20.
- Acetylcholine (nmol/L, resting 20–60): Engagement with interesting external content: +3–10.

Dopamine is a SEEKING signal — rises with novelty, not completion. Do NOT apply negative \
dopamine from satisfaction or negative acetylcholine from engagement.

Current state awareness: check the labels in the bio report above before setting magnitudes.
If a chemical is already HIGH, COMPULSIVE, or CRITICAL, it has little biological headroom —
positive deltas for it should be 20–30% of the guidance maximums above.

{_EVENT_OVERRIDE_GUIDANCE}

{_DELTA_FORMAT}"""

    raw, event_override = _call_delta_json([{"role": "user", "content": prompt}], label="encode_stimulus")
    saturated = _apply_saturation(raw, state)
    if event_override:
        return saturated
    return _apply_personality_scaling(saturated, _load_personality())


def encode_response(state: BiologicalState, response_text: str) -> dict:
    """
    Determine biological deltas from what Mina just expressed.
    Called after Mina's response, closing the loop.
    """
    from decoder import biological_report
    report = biological_report(state)

    prompt = f"""{report}

Mina just expressed:
{response_text}

Your job: encode only the neurochemical effect of the ACT OF EXPRESSING this — the biological \
consequence of saying it, not the content of what she said. Internal state (what she was already \
feeling) is already in the bio report above and must NOT be re-encoded. Only post deltas if the \
act of expression itself causes a meaningful biological shift.

Expression effects (when genuine and significant):
- Articulating trust or warmth: oxytocin +
- Suppressing visible fear while sounding calm: cortisol stays elevated (small decrease at best)
- Saying something that contradicts her inner state: cortisol +, acetylcholine -
- Speaking fear or grief aloud: small cathartic cortisol relief (-)
- Engaged, energetic response: endorphins +, serotonin +, acetylcholine +. Dopamine stays
  stable or rises slightly — do NOT apply negative dopamine from engagement. Do NOT apply
  negative acetylcholine from normal conversation — only if cognitively exhausted.
- Routine, unremarkable exchange: no_external_deltas: true.

Current state awareness: check the labels in the bio report above before setting magnitudes.
If a chemical is already HIGH, COMPULSIVE, or CRITICAL, it has little biological headroom —
positive deltas for it should be 20–30% of the guidance maximums.

{_EVENT_OVERRIDE_GUIDANCE}

{_DELTA_FORMAT}"""

    raw, event_override = _call_delta_json([{"role": "user", "content": prompt}], label="encode_response")
    saturated = _apply_saturation(raw, state)
    if event_override:
        return saturated
    return _apply_personality_scaling(saturated, _load_personality())


def evaluate_activity_deltas(state: BiologicalState, activity: str, description: str) -> dict:
    """
    Determine biological deltas from a do_action activity.
    Used by both cortex.py and freetime.py after a do_action tool call.
    """
    from decoder import biological_report
    report = biological_report(state)

    prompt = f"""{report}

Mina just did:
Activity: {activity}
Description: {description}

Your job: encode the neurochemical effect of this SPECIFIC ACTIVITY. This is the one place \
where you DO post deltas for physical activities — eating, drinking, exercising, etc. — because \
those are external actions that produce direct biological changes the simulation doesn't model \
automatically. Scale to what actually happened. An exhausted person gets less from a fun activity.

Activity magnitude guidance:
- Eating a meal: glucose +25 to +45 (scale with meal size), serotonin +3 to +8,
  cortisol -5 to -10 if she was hungry. Comfort food (pasta, bread, soup, sweets): endorphins +5 to +12.
- Drinking water or juice: hydration +20 to +28.
- Drinking caffeine (coffee, tea, matcha): norepinephrine +15 to +25, sleep_pressure -8 to -12, hydration +5.
- Drinking alcohol (wine, beer, whiskey): cortisol -12 to -20, serotonin +5 to +10,
  acetylcholine -8 to -15, norepinephrine -5 to -10, hydration -5 to -10. Scale by tolerance.
- Resting (not sleeping): cortisol -8 to -14, sleep_pressure -3 to -6, endorphins +3 to +6.
- Showering: cortisol -5 to -10, endorphins +3 to +8 (warm shower), serotonin +2 to +5.
- Exercise: endorphins +15 to +30, dopamine +10 to +20, serotonin +5 to +10,
  cortisol -10 to -20 (after), norepinephrine +10 to +20 (during).
- Intense bonding activity: dopamine +60 to +100 building, oxytocin +20 to +40, endorphins +20 to +40.
  Peak resolution: use event_override=true, dopamine -100 to -150,
  norepinephrine -60 to -100, sleep_pressure +30 to +40.
- Reading or watching something: dopamine and acetylcholine vary with engagement.
  Unsettling content: cortisol +. Funny: endorphins +, dopamine +. Sad: serotonin may drop.
- Mild or passive activity with no strong biological effect: no_external_deltas: true.

Current state awareness: check the labels in the bio report above before setting magnitudes.
If a chemical is already HIGH, COMPULSIVE, or CRITICAL, it has little biological headroom —
positive deltas for it should be 20–30% of the guidance maximums.

{_EVENT_OVERRIDE_GUIDANCE}

{_DELTA_FORMAT}"""

    raw, event_override = _call_delta_json([{"role": "user", "content": prompt}], label="encode_activity")
    saturated = _apply_saturation(raw, state)
    if event_override:
        return saturated
    return _apply_personality_scaling(saturated, _load_personality())
