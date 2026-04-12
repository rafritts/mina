"""
Second and third-order derived values.

Never stored in state — computed on demand.
All outputs normalized to 0-100 for compatibility with existing formulas.
"""
from __future__ import annotations

from src.sim.chem.units import normalize as _normalize_chem
from src.sim.bio.defaults import CHEMICAL_DEFAULTS


def _n(name: str, s) -> float:
    """Normalize a chemical to 0-100 equivalent for use in derived formulas."""
    return _normalize_chem(name, s.chemicals.get(name, CHEMICAL_DEFAULTS.get(name, 0.0))) * 100.0


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def derived(s) -> dict:
    """Compute second and third-order values. Never stored. All outputs 0-100."""
    tol_d = s.tolerance.get("dopamine", 0.0)
    effective_dopamine = _n("dopamine", s) * (1.0 - tol_d)

    # Melatonin circadian drag on arousal and clarity
    melatonin_drag = max(0.0, _n("melatonin", s) - 40) * 0.25

    energy = _clamp(
        20 + (_n("glucose", s) * 0.4) + (_n("norepinephrine", s) * 0.3)
        - (_n("sleep_pressure", s) * 0.3) - melatonin_drag
    )
    cognitive_clarity = _clamp(
        20 + (_n("acetylcholine", s) * 0.4) + (_n("glucose", s) * 0.2)
        - (_n("sleep_pressure", s) * 0.25) - (_n("cortisol", s) * 0.15)
        - melatonin_drag * 0.6
    )
    hedonic_tone = _clamp(
        5 + (effective_dopamine * 0.5) + (_n("endorphins", s) * 0.3)
        + (_n("serotonin", s) * 0.2)
    )
    social_warmth = _clamp(
        10 + (_n("oxytocin", s) * 0.5) + (_n("serotonin", s) * 0.3)
        - (_n("cortisol", s) * 0.2)
    )
    arousal = _clamp(
        15 + (_n("norepinephrine", s) * 0.5) + (_n("cortisol", s) * 0.3)
        - (_n("sleep_pressure", s) * 0.2) - melatonin_drag * 0.8
    )
    mood_valence = _clamp(
        10 + (_n("serotonin", s) * 0.4) + (effective_dopamine * 0.35)
        - (_n("cortisol", s) * 0.25)
    )

    anxiety = _clamp(
        (arousal * 0.4) + (100 - cognitive_clarity) * 0.3
        + (100 - social_warmth) * 0.3 - 20
    )
    depression = _clamp(
        (100 - mood_valence) * 0.4 + (100 - hedonic_tone) * 0.4
        + (100 - energy) * 0.2 - 20
    )
    boredom = _clamp(
        (100 - arousal) * 0.5 + (100 - hedonic_tone) * 0.3
        + (100 - energy) * 0.2 - 20
    )
    loneliness = _clamp(
        (100 - social_warmth) * 0.6 + (100 - _n("oxytocin", s)) * 0.4 - 25
    )
    flow = _clamp(
        (cognitive_clarity * 0.4) + (hedonic_tone * 0.35)
        + (arousal * 0.25) - anxiety * 0.3
    )

    return {
        "second_order": {
            "energy":            round(energy, 1),
            "cognitive_clarity": round(cognitive_clarity, 1),
            "hedonic_tone":      round(hedonic_tone, 1),
            "social_warmth":     round(social_warmth, 1),
            "arousal":           round(arousal, 1),
            "mood_valence":      round(mood_valence, 1),
        },
        "third_order": {
            "anxiety":    round(anxiety, 1),
            "depression": round(depression, 1),
            "boredom":    round(boredom, 1),
            "loneliness": round(loneliness, 1),
            "flow":       round(flow, 1),
        },
    }
