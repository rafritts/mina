"""
Second and third-order derived values.

Never stored in state — computed on demand.
All outputs normalized to 0-100 for compatibility with existing formulas.

SPEC-24: Updated to incorporate BDNF, allostatic load, inflammation, pain,
T3 (thyroid), ghrelin (hunger), vasopressin, anandamide, and receptor
sensitivity adjustments for all major neurotransmitter pathways.
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

    # --- New SPEC-24 inputs ---
    gaba      = s.chemicals.get("gaba",      3.0)
    glutamate = s.chemicals.get("glutamate", 4.0)
    bdnf      = s.neuroplasticity.get("bdnf",              9000.0)
    al        = s.neuroplasticity.get("allostatic_load",      0.0)
    infl      = s.immune.get("inflammation_index",            0.0)
    pain_int  = s.pain.get("pain_intensity",                  0.0)
    t3        = s.neuroendocrine.get("t3",                  120.0)
    ghrelin   = s.neuroendocrine.get("ghrelin",             400.0)
    adenosine = s.body.get("adenosine",                      25.0)

    # Normalize new inputs to 0-100 scale
    gaba_n     = min(100.0, max(0.0, (gaba - 0.5) / 0.095))   # 0.5→0, 10→100
    ei         = (glutamate - gaba) / max(gaba, 0.5)           # signed ratio
    t3_n       = min(100.0, max(0.0, (t3 - 20.0) / 1.8))      # 20→0, 200→100
    bdnf_n     = min(100.0, max(0.0, (bdnf - 1000.0) / 190.0)) # 1000→0, 20000→100
    hunger_n   = min(100.0, max(0.0, (ghrelin - 200.0) / 8.0)) # 200→0, 1000→100
    adenosine_n = min(100.0, max(0.0, (adenosine - 20.0) / 0.6)) # matches sleep_pressure

    # --- Receptor sensitivity adjustments ---
    d1_sens     = s.receptor_sensitivity.get("dopamine",  {}).get("D1",    1.0)
    d2_sens     = s.receptor_sensitivity.get("dopamine",  {}).get("D2",    1.0)
    ht1a_sens   = s.receptor_sensitivity.get("serotonin", {}).get("5HT1A", 1.0)
    gaba_a_sens = s.receptor_sensitivity.get("gaba",      {}).get("GABA_A",1.0)

    # SSRI reuptake block: effective serotonin level multiplied
    from src.sim.neuro.substances import get_effective_reuptake_mults
    reuptake_mults = get_effective_reuptake_mults(s)
    serotonin_mult = reuptake_mults.get("serotonin", 1.0)
    # 5HT1A autoreceptors: downregulation → less self-inhibition → more release
    effective_serotonin = _n("serotonin", s) * serotonin_mult * (2.0 - ht1a_sens)
    effective_serotonin = _clamp(effective_serotonin)

    # Old substance tolerance scalar — kept for backward compat during transition
    tol_d = s.tolerance.get("dopamine", 0.0)

    effective_dopamine_reward   = _n("dopamine", s) * d2_sens * (1.0 - tol_d)
    effective_dopamine_cognitive = _n("dopamine", s) * d1_sens * (1.0 - tol_d)
    effective_gaba = gaba_n * gaba_a_sens

    # Vasopressin and anandamide (normalized)
    vasopressin_n = min(100.0, s.neuroendocrine.get("vasopressin", 2.0) / 0.15)
    anandamide_n  = min(100.0, s.body.get("anandamide", 1.5) / 0.15)

    melatonin_drag = max(0.0, _n("melatonin", s) - 40.0) * 0.25

    # --- Second-order values ---

    # ENERGY: glucose drives ATP; norepinephrine mobilizes; T3 (metabolism) sustains.
    # Fatigue from adenosine, hunger, inflammation, melatonin drag.
    energy = _clamp(
        20
        + (_n("glucose", s) * 0.35)
        + (_n("norepinephrine", s) * 0.25)
        + (t3_n * 0.15)
        - (adenosine_n * 0.20)
        - (hunger_n * 0.05)
        - melatonin_drag
        - (infl * 0.15)   # inflammation fatigue ("sickness behavior")
    )

    # COGNITIVE CLARITY: ACh (attention/encoding), glucose (fuel), BDNF (neuroplasticity).
    # Impaired by fatigue, cortisol hyperactivation, pain distraction.
    cognitive_clarity = _clamp(
        20
        + (_n("acetylcholine", s) * 0.35)
        + (_n("glucose", s) * 0.15)
        + (bdnf_n * 0.10)
        - (adenosine_n * 0.20)
        - (_n("cortisol", s) * 0.15)
        - (pain_int * 0.10)
        - melatonin_drag * 0.6
    )

    # HEDONIC TONE: reward (D2), endorphins (natural opioids), serotonin (contentment),
    # anandamide (bliss molecule). Blunted by inflammation (anhedonia) and allostatic load.
    hedonic_tone = _clamp(
        5
        + (effective_dopamine_reward * 0.40)
        + (_n("endorphins", s) * 0.25)
        + (effective_serotonin * 0.20)
        + (anandamide_n * 0.15)
        - (infl * 0.10)    # anhedonia from sickness
        - (al * 0.10)      # allostatic load blunts pleasure
    )

    # SOCIAL WARMTH: oxytocin (bonding), serotonin (security), vasopressin (pair-bond).
    # Reduced by cortisol (threat response) and pain.
    social_warmth = _clamp(
        10
        + (_n("oxytocin", s) * 0.45)
        + (effective_serotonin * 0.25)
        + (vasopressin_n * 0.10)
        - (_n("cortisol", s) * 0.15)
        - (pain_int * 0.05)
    )

    # AROUSAL: norepinephrine (locus coeruleus), cortisol (HPA), E/I balance.
    # Calmed by GABA and adenosine; melatonin drags it down.
    arousal = _clamp(
        15
        + (_n("norepinephrine", s) * 0.40)
        + (_n("cortisol", s) * 0.25)
        + (max(0.0, ei) * 5.0)   # high E/I → more arousal
        - (effective_gaba * 0.20) # GABAergic inhibition calms
        - (adenosine_n * 0.15)
        - melatonin_drag * 0.8
    )

    # MOOD VALENCE: serotonin (positive baseline), dopamine (motivation/agency),
    # T3 (metabolic mood support), BDNF (neuroplasticity = capacity for wellbeing).
    # Cortisol and allostatic load shift it negative.
    mood_valence = _clamp(
        10
        + (effective_serotonin * 0.35)
        + (effective_dopamine_cognitive * 0.25)
        + (t3_n * 0.10)
        + (bdnf_n * 0.10)
        - (_n("cortisol", s) * 0.20)
        - (al * 0.10)
    )

    # Pain awareness: raw pain amplified by arousal (hypervigilance)
    pain_awareness = _clamp(pain_int * (1.0 + arousal * 0.003))

    # --- Third-order emotional states ---

    anxiety = _clamp(
        (arousal * 0.35)
        + (100 - cognitive_clarity) * 0.25
        + (100 - social_warmth) * 0.25
        + (pain_awareness * 0.10)
        + (max(0.0, ei) * 5.0)     # high E/I (glutamate-dominant) → anxious
        - (effective_gaba * 0.20)   # GABA is anxiolytic
        - 20
    )

    depression = _clamp(
        (100 - mood_valence) * 0.35
        + (100 - hedonic_tone) * 0.35
        + (100 - energy) * 0.15
        + (infl * 0.10)   # inflammatory depression (cytokine-mediated)
        + (al * 0.05)     # allostatic load contributes to hopelessness
        - 20
    )

    boredom = _clamp(
        (100 - arousal) * 0.45
        + (100 - hedonic_tone) * 0.30
        + (100 - energy) * 0.20
        + (100 - cognitive_clarity) * 0.05
        - 20
    )

    loneliness = _clamp(
        (100 - social_warmth) * 0.55
        + (100 - _n("oxytocin", s)) * 0.35
        + (infl * 0.10)   # sickness behavior increases perceived isolation
        - 25
    )

    flow = _clamp(
        (cognitive_clarity * 0.40)
        + (hedonic_tone * 0.30)
        + (arousal * 0.20)
        + (effective_gaba * 0.10)   # relaxed alertness enables flow
        - anxiety * 0.35
    )

    # Physical distress: pain + inflammation + hunger + fatigue
    physical_distress = _clamp(
        (pain_awareness * 0.50)
        + (infl * 0.25)
        + (hunger_n * 0.10)
        + (100 - energy) * 0.15
        - 15
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
            "anxiety":           round(anxiety, 1),
            "depression":        round(depression, 1),
            "boredom":           round(boredom, 1),
            "loneliness":        round(loneliness, 1),
            "flow":              round(flow, 1),
            "physical_distress": round(physical_distress, 1),
        },
    }
