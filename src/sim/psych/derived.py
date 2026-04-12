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


def ei_balance(s) -> float:
    """
    Excitatory/Inhibitory balance: −1.0 (maximally inhibited) to +1.0 (maximally excited).
    0.0 = healthy balance.

    Derived from glutamate (0–20 µmol/L) and GABA (0–12 µmol/L).
    Positive = excited/anxious; Negative = inhibited/sedated.
    """
    glu  = s.chemicals.get("glutamate", 4.0)
    gaba = s.chemicals.get("gaba", 3.0)
    glu_n  = min(1.0, max(0.0, (glu  - 0.5) / 19.5))
    gaba_n = min(1.0, max(0.0, (gaba - 0.5) / 11.5))
    return round(glu_n - gaba_n, 3)


def derived(s) -> dict:
    """Compute second and third-order values. Never stored. All outputs 0-100."""
    # --- Receptor-sensitivity-adjusted dopamine ---
    d1_sens = s.receptor_sensitivity.get("dopamine", {}).get("D1", 1.0)
    d2_sens = s.receptor_sensitivity.get("dopamine", {}).get("D2", 1.0)
    # D1: prefrontal/cognitive dopamine; D2: mesolimbic reward/motivation
    effective_da_cognitive = _n("dopamine", s) * d1_sens
    effective_da_reward    = _n("dopamine", s) * d2_sens
    # Blend: motivation weighting (reward D2 dominates hedonic/drive signals)
    effective_dopamine = (effective_da_cognitive * 0.4 + effective_da_reward * 0.6)

    # Old substance tolerance scalar — kept for backward compat during transition
    tol_d = s.tolerance.get("dopamine", 0.0)
    if tol_d > 0:
        effective_dopamine = effective_dopamine * (1.0 - tol_d)

    # --- SSRI reuptake block: effective serotonin level multiplied ---
    from src.sim.neuro.substances import get_effective_reuptake_mults
    reuptake_mults  = get_effective_reuptake_mults(s)
    serotonin_mult  = reuptake_mults.get("serotonin", 1.0)
    # 5HT1A autoreceptors: downregulation (lower sens) means less self-inhibition →
    # more serotonin release. Inverse relationship: factor = 2 - sens.
    # TODO SPEC-24: refine when psych/emotions.py is implemented.
    ht1a_sens = s.receptor_sensitivity.get("serotonin", {}).get("5HT1A", 1.0)
    effective_serotonin = _n("serotonin", s) * serotonin_mult * (2.0 - ht1a_sens)
    effective_serotonin = _clamp(effective_serotonin)

    # --- E/I balance contribution ---
    ei = ei_balance(s)
    # Positive E/I (glutamate-dominant) amplifies arousal/anxiety
    # Negative E/I (GABA-dominant) amplifies sedation/depression
    ei_arousal_bonus     =  max(0.0, ei) * 15.0  # up to +15 arousal when excitation-dominant
    ei_sedation_penalty  = -min(0.0, ei) * 10.0  # up to +10 energy penalty when inhibition-dominant

    # --- sleep_pressure from body["adenosine"] via property ---
    sp_n = s.sleep_pressure  # 0-100 AU, already normalized

    # Melatonin circadian drag on arousal and clarity
    melatonin_drag = max(0.0, _n("melatonin", s) - 40.0) * 0.25

    energy = _clamp(
        20
        + (_n("glucose", s) * 0.4)
        + (_n("norepinephrine", s) * 0.3)
        - (sp_n * 0.3)
        - melatonin_drag
        - ei_sedation_penalty
    )
    cognitive_clarity = _clamp(
        20
        + (_n("acetylcholine", s) * 0.4)
        + (_n("glucose", s) * 0.2)
        - (sp_n * 0.25)
        - (_n("cortisol", s) * 0.15)
        - melatonin_drag * 0.6
    )
    hedonic_tone = _clamp(
        5
        + (effective_dopamine * 0.5)
        + (_n("endorphins", s) * 0.3)
        + (effective_serotonin * 0.2)
    )
    social_warmth = _clamp(
        10
        + (_n("oxytocin", s) * 0.5)
        + (effective_serotonin * 0.3)
        - (_n("cortisol", s) * 0.2)
    )
    arousal = _clamp(
        15
        + (_n("norepinephrine", s) * 0.5)
        + (_n("cortisol", s) * 0.3)
        - (sp_n * 0.2)
        - melatonin_drag * 0.8
        + ei_arousal_bonus
    )
    mood_valence = _clamp(
        10
        + (effective_serotonin * 0.4)
        + (effective_dopamine * 0.35)
        - (_n("cortisol", s) * 0.25)
    )

    anxiety = _clamp(
        (arousal * 0.4)
        + (100 - cognitive_clarity) * 0.3
        + (100 - social_warmth) * 0.3
        - 20
        + max(0.0, ei) * 20.0   # high E/I ratio amplifies anxiety
    )
    depression = _clamp(
        (100 - mood_valence) * 0.4
        + (100 - hedonic_tone) * 0.4
        + (100 - energy) * 0.2
        - 20
    )
    boredom = _clamp(
        (100 - arousal) * 0.5
        + (100 - hedonic_tone) * 0.3
        + (100 - energy) * 0.2
        - 20
    )
    loneliness = _clamp(
        (100 - social_warmth) * 0.6
        + (100 - _n("oxytocin", s)) * 0.4
        - 25
    )
    flow = _clamp(
        (cognitive_clarity * 0.4)
        + (hedonic_tone * 0.35)
        + (arousal * 0.25)
        - anxiety * 0.3
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
