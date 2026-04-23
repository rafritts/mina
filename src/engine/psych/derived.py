"""
Second and third-order derived values.

Never stored in state — computed on demand.
All outputs normalized to 0-100 for compatibility with existing formulas.

SPEC-24: Updated to incorporate BDNF, allostatic load, inflammation, pain,
T3 (thyroid), ghrelin (hunger), vasopressin, anandamide, and receptor
sensitivity adjustments for all major neurotransmitter pathways.
SPEC-25: All numeric literals replaced with named constants.
"""
from __future__ import annotations

from src.engine.chem.units import normalize as _normalize_chem
from src.engine.bio.defaults import CHEMICAL_DEFAULTS
from src.engine.constants import (
    ANXIETY_AROUSAL_WEIGHT,
    ANXIETY_CLARITY_WEIGHT,
    ANXIETY_EI_SCALE,
    ANXIETY_GABA_WEIGHT,
    ANXIETY_OFFSET,
    ANXIETY_PAIN_WEIGHT,
    ANXIETY_WARMTH_WEIGHT,
    AROUSAL_ADENOSINE_WEIGHT,
    AROUSAL_CORTISOL_WEIGHT,
    AROUSAL_EI_BALANCE_SCALE,
    AROUSAL_GABA_WEIGHT,
    AROUSAL_MELATONIN_DRAG_FACTOR,
    AROUSAL_NOREPI_WEIGHT,
    AROUSAL_OFFSET,
    BOREDOM_AROUSAL_WEIGHT,
    BOREDOM_CLARITY_WEIGHT,
    BOREDOM_ENERGY_WEIGHT,
    BOREDOM_HEDONIC_WEIGHT,
    BOREDOM_OFFSET,
    CLARITY_ACH_WEIGHT,
    CLARITY_ADENOSINE_WEIGHT,
    CLARITY_BDNF_WEIGHT,
    CLARITY_CORTISOL_WEIGHT,
    CLARITY_GLUCOSE_WEIGHT,
    CLARITY_MELATONIN_DRAG_FACTOR,
    CLARITY_OFFSET,
    CLARITY_PAIN_WEIGHT,
    DEPRESSION_ALLOSTATIC_WEIGHT,
    DEPRESSION_ENERGY_WEIGHT,
    DEPRESSION_HEDONIC_WEIGHT,
    DEPRESSION_INFLAMMATION_WEIGHT,
    DEPRESSION_OFFSET,
    DEPRESSION_VALENCE_WEIGHT,
    DISTRESS_ENERGY_WEIGHT,
    DISTRESS_HUNGER_WEIGHT,
    DISTRESS_INFLAMMATION_WEIGHT,
    DISTRESS_OFFSET,
    DISTRESS_PAIN_WEIGHT,
    ENERGY_ADENOSINE_WEIGHT,
    ENERGY_GLUCOSE_WEIGHT,
    ENERGY_HUNGER_WEIGHT,
    ENERGY_INFLAMMATION_WEIGHT,
    ENERGY_NOREPI_WEIGHT,
    ENERGY_OFFSET,
    ENERGY_T3_WEIGHT,
    FLOW_ANXIETY_REDUCTION,
    FLOW_AROUSAL_WEIGHT,
    FLOW_CLARITY_WEIGHT,
    FLOW_GABA_WEIGHT,
    FLOW_HEDONIC_WEIGHT,
    HEDONIC_ALLOSTATIC_WEIGHT,
    HEDONIC_ANANDAMIDE_WEIGHT,
    HEDONIC_DOPAMINE_REWARD_WEIGHT,
    HEDONIC_ENDORPHIN_WEIGHT,
    HEDONIC_INFLAMMATION_WEIGHT,
    HEDONIC_OFFSET,
    HEDONIC_SEROTONIN_WEIGHT,
    BIG5_A_ANXIETY_SCALE,
    BIG5_A_WARMTH_SCALE,
    BIG5_C_DEPRESSION_SCALE,
    BIG5_C_ENERGY_SCALE,
    BIG5_E_AROUSAL_OPTIMAL_BASE,
    BIG5_E_AROUSAL_OPTIMAL_SCALE,
    BIG5_E_AROUSAL_SCALE,
    BIG5_E_WARMTH_SCALE,
    BIG5_N_ANXIETY_SCALE,
    BIG5_N_DEPRESSION_SCALE,
    BIG5_N_VALENCE_SCALE,
    BIG5_O_BOREDOM_SCALE,
    BIG5_O_HEDONIC_SCALE,
    LONELINESS_BOND_OXY_THRESHOLD,
    LONELINESS_BOND_WEIGHT,
    LONELINESS_E_BASE,
    LONELINESS_E_SCALE,
    LONELINESS_INFLAMMATION_WEIGHT,
    LONELINESS_ISOLATION_WEIGHT,
    LONELINESS_OFFSET,
    WARMTH_E_BASE,
    WARMTH_E_SCALE,
    MELATONIN_DRAG_MULTIPLIER,
    MELATONIN_DRAG_THRESHOLD,
    NORM_ADENOSINE_SLEEP_PRESSURE_MIN,
    NORM_ADENOSINE_SLEEP_PRESSURE_SCALE,
    NORM_ANANDAMIDE_DIVISOR,
    NORM_BDNF_MIN,
    NORM_BDNF_RANGE,
    NORM_GABA_MIN,
    NORM_GABA_RANGE,
    NORM_HUNGER_MIN,
    NORM_HUNGER_RANGE,
    NORM_T3_MIN,
    NORM_T3_RANGE,
    NORM_VASOPRESSIN_DIVISOR,
    CRAVING_ENDORPHIN_WEIGHT,
    CRAVING_DOPAMINE_WEIGHT,
    CRAVING_OXYTOCIN_WEIGHT,
    CRAVING_SEROTONIN_WEIGHT,
    CRAVING_ENDORPHIN_MAX,
    CRAVING_DOPAMINE_MIN,
    CRAVING_DOPAMINE_MAX,
    CRAVING_OXYTOCIN_MAX,
    CRAVING_SEROTONIN_MIN,
    CRAVING_SEROTONIN_MAX,
    CRAVING_SENSITIVITY,
    HEDONIC_SETPOINT_BIOLOGICAL_FLOOR,
    VALENCE_ALLOSTATIC_WEIGHT,
    VALENCE_BDNF_WEIGHT,
    VALENCE_CORTISOL_WEIGHT,
    VALENCE_DOPAMINE_COGNITIVE_WEIGHT,
    VALENCE_OFFSET,
    VALENCE_SEROTONIN_WEIGHT,
    VALENCE_T3_WEIGHT,
    WARMTH_CORTISOL_WEIGHT,
    WARMTH_OFFSET,
    WARMTH_OXYTOCIN_WEIGHT,
    WARMTH_PAIN_WEIGHT,
    WARMTH_SEROTONIN_WEIGHT,
    WARMTH_VASOPRESSIN_WEIGHT,
    HOSTILITY_SEROTONIN_WEIGHT,
    HOSTILITY_NOREPI_WEIGHT,
    HOSTILITY_LONELINESS_WEIGHT,
    HOSTILITY_OXYTOCIN_WEIGHT,
    HOSTILITY_OFFSET,
    BIG5_N_HOSTILITY_SCALE,
    HOSTILITY_RELATIONSHIP_TENSION_WEIGHT,
)


_big5_cache: dict[str, float] = {"E": 0.5, "A": 0.5, "O": 0.5, "N": 0.5, "C": 0.5}
_big5_cache_ts: float = 0.0


def _big5() -> dict[str, float]:
    """Return all Big5 traits as 0.0–1.0. Cached for 60s to avoid hot-path disk reads."""
    global _big5_cache, _big5_cache_ts
    import time as _time
    now = _time.time()
    if now - _big5_cache_ts > 60.0:
        try:
            from src.config.config import load_config
            b = load_config().get("big5", {})
            _big5_cache = {
                "E": float(b.get("extraversion",      50)) / 100.0,
                "A": float(b.get("agreeableness",     50)) / 100.0,
                "O": float(b.get("openness",          50)) / 100.0,
                "N": float(b.get("neuroticism",       50)) / 100.0,
                "C": float(b.get("conscientiousness", 50)) / 100.0,
            }
            _big5_cache_ts = now
        except Exception:
            pass
    return _big5_cache


def _p(trait: float, scale: float) -> float:
    """Personality adjustment: (trait - 0.5) * 2 * scale. Zero at average, ±scale at extremes."""
    return (trait - 0.5) * 2.0 * scale


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
    gaba_n     = min(100.0, max(0.0, (gaba     - NORM_GABA_MIN)  / NORM_GABA_RANGE))
    ei         = (glutamate - gaba) / max(gaba, NORM_GABA_MIN)     # signed E/I ratio
    t3_n       = min(100.0, max(0.0, (t3       - NORM_T3_MIN)    / NORM_T3_RANGE))
    bdnf_n     = min(100.0, max(0.0, (bdnf     - NORM_BDNF_MIN)  / NORM_BDNF_RANGE))
    hunger_n   = min(100.0, max(0.0, (ghrelin  - NORM_HUNGER_MIN) / NORM_HUNGER_RANGE))
    adenosine_n = min(100.0, max(0.0,
        (adenosine - NORM_ADENOSINE_SLEEP_PRESSURE_MIN) / NORM_ADENOSINE_SLEEP_PRESSURE_SCALE))

    # --- Receptor sensitivity adjustments ---
    d1_sens     = s.receptor_sensitivity.get("dopamine",  {}).get("D1",    1.0)
    d2_sens     = s.receptor_sensitivity.get("dopamine",  {}).get("D2",    1.0)
    ht1a_sens   = s.receptor_sensitivity.get("serotonin", {}).get("5HT1A", 1.0)
    gaba_a_sens = s.receptor_sensitivity.get("gaba",      {}).get("GABA_A",1.0)

    # SSRI reuptake block: effective serotonin level multiplied
    from src.engine.neuro.substances import get_effective_reuptake_mults
    reuptake_mults = get_effective_reuptake_mults(s)
    serotonin_mult = reuptake_mults.get("serotonin", 1.0)
    # 5HT1A autoreceptors: downregulation → less self-inhibition → more release
    effective_serotonin = _n("serotonin", s) * serotonin_mult * (2.0 - ht1a_sens)
    effective_serotonin = _clamp(effective_serotonin)

    # Old substance tolerance scalar — kept for backward compat during transition
    tol_d = s.tolerance.get("dopamine", 0.0)

    effective_dopamine_reward    = _n("dopamine", s) * d2_sens * (1.0 - tol_d)
    effective_dopamine_cognitive = _n("dopamine", s) * d1_sens * (1.0 - tol_d)
    effective_gaba               = gaba_n * gaba_a_sens

    # Vasopressin and anandamide (normalized)
    vasopressin_n = min(100.0, s.neuroendocrine.get("vasopressin", 2.0) / NORM_VASOPRESSIN_DIVISOR)
    anandamide_n  = min(100.0, s.body.get("anandamide", 1.5)            / NORM_ANANDAMIDE_DIVISOR)

    melatonin_drag = max(0.0, _n("melatonin", s) - MELATONIN_DRAG_THRESHOLD) * MELATONIN_DRAG_MULTIPLIER

    # --- Big5 personality baseline adjustments ---
    # Each trait shifts the floor/ceiling of relevant second/third-order values.
    # Formula: _p(trait, scale) = (trait - 0.5) * 2 * scale → zero at average, ±scale at extremes.
    b5 = _big5()
    E, A, O, N, C = b5["E"], b5["A"], b5["O"], b5["N"], b5["C"]

    # --- Second-order values ---

    # ENERGY: glucose drives ATP; norepinephrine mobilizes; T3 (metabolism) sustains.
    # Conscientiousness raises the floor — purposeful people sustain energy better at rest.
    energy = _clamp(
        ENERGY_OFFSET
        + _p(C, BIG5_C_ENERGY_SCALE)
        + (_n("glucose", s)        * ENERGY_GLUCOSE_WEIGHT)
        + (_n("norepinephrine", s) * ENERGY_NOREPI_WEIGHT)
        + (t3_n                    * ENERGY_T3_WEIGHT)
        - (adenosine_n             * ENERGY_ADENOSINE_WEIGHT)
        - (hunger_n                * ENERGY_HUNGER_WEIGHT)
        - melatonin_drag
        - (infl                    * ENERGY_INFLAMMATION_WEIGHT)
    )

    # COGNITIVE CLARITY: ACh (attention/encoding), glucose (fuel), BDNF (neuroplasticity).
    cognitive_clarity = _clamp(
        CLARITY_OFFSET
        + (_n("acetylcholine", s) * CLARITY_ACH_WEIGHT)
        + (_n("glucose", s)       * CLARITY_GLUCOSE_WEIGHT)
        + (bdnf_n                 * CLARITY_BDNF_WEIGHT)
        - (adenosine_n            * CLARITY_ADENOSINE_WEIGHT)
        - (_n("cortisol", s)      * CLARITY_CORTISOL_WEIGHT)
        - (pain_int               * CLARITY_PAIN_WEIGHT)
        - melatonin_drag          * CLARITY_MELATONIN_DRAG_FACTOR
    )

    # HEDONIC TONE: reward (D2), endorphins, serotonin, anandamide.
    # Openness raises the floor — curious people find more things rewarding.
    # Extraversion is NOT wired here: introverts aren't less happy, just differently stimulated.
    # Blunted by inflammation and allostatic load.
    hedonic_tone = _clamp(
        HEDONIC_OFFSET
        + _p(O, BIG5_O_HEDONIC_SCALE)
        + (effective_dopamine_reward * HEDONIC_DOPAMINE_REWARD_WEIGHT)
        + (_n("endorphins", s)       * HEDONIC_ENDORPHIN_WEIGHT)
        + (effective_serotonin       * HEDONIC_SEROTONIN_WEIGHT)
        + (anandamide_n              * HEDONIC_ANANDAMIDE_WEIGHT)
        - (infl                      * HEDONIC_INFLAMMATION_WEIGHT)
        - (al                        * HEDONIC_ALLOSTATIC_WEIGHT)
    )

    # SOCIAL WARMTH: oxytocin (bonding), serotonin (security), vasopressin (pair-bond).
    # Extraversion and agreeableness both raise the baseline.
    # SPEC-28: Extraversion also amplifies the ceiling via warmth_amp.
    warmth_amp = WARMTH_E_BASE + E * WARMTH_E_SCALE
    social_warmth = _clamp(
        _clamp(
            WARMTH_OFFSET
            + _p(E, BIG5_E_WARMTH_SCALE)
            + _p(A, BIG5_A_WARMTH_SCALE)
            + (_n("oxytocin", s)   * WARMTH_OXYTOCIN_WEIGHT)
            + (effective_serotonin * WARMTH_SEROTONIN_WEIGHT)
            + (vasopressin_n       * WARMTH_VASOPRESSIN_WEIGHT)
            - (_n("cortisol", s)   * WARMTH_CORTISOL_WEIGHT)
            - (pain_int            * WARMTH_PAIN_WEIGHT)
        ) * warmth_amp
    )

    # AROUSAL: norepinephrine (locus coeruleus), cortisol (HPA), E/I balance.
    # Extraversion raises the floor — extraverts are more activated at rest.
    # Calmed by GABA and adenosine; melatonin drags it down.
    arousal = _clamp(
        AROUSAL_OFFSET
        + _p(E, BIG5_E_AROUSAL_SCALE)
        + (_n("norepinephrine", s) * AROUSAL_NOREPI_WEIGHT)
        + (_n("cortisol", s)       * AROUSAL_CORTISOL_WEIGHT)
        + (max(0.0, ei)            * AROUSAL_EI_BALANCE_SCALE)
        - (effective_gaba          * AROUSAL_GABA_WEIGHT)
        - (adenosine_n             * AROUSAL_ADENOSINE_WEIGHT)
        - melatonin_drag           * AROUSAL_MELATONIN_DRAG_FACTOR
    )

    # MOOD VALENCE: serotonin (positive baseline), dopamine (motivation/agency),
    # T3 (metabolic mood support), BDNF (neuroplasticity = capacity for wellbeing).
    # Neuroticism applies a negative bias. Cortisol and allostatic load shift it negative.
    mood_valence = _clamp(
        VALENCE_OFFSET
        - _p(N, BIG5_N_VALENCE_SCALE)
        + (effective_serotonin          * VALENCE_SEROTONIN_WEIGHT)
        + (effective_dopamine_cognitive * VALENCE_DOPAMINE_COGNITIVE_WEIGHT)
        + (t3_n                         * VALENCE_T3_WEIGHT)
        + (bdnf_n                       * VALENCE_BDNF_WEIGHT)
        - (_n("cortisol", s)            * VALENCE_CORTISOL_WEIGHT)
        - (al                           * VALENCE_ALLOSTATIC_WEIGHT)
    )

    # Pain awareness: raw pain amplified by arousal (hypervigilance)
    pain_awareness = _clamp(pain_int * (1.0 + arousal * 0.003))

    # --- Third-order emotional states ---

    # ANXIETY: Neuroticism raises baseline; agreeableness (trust) lowers it.
    anxiety = _clamp(
        _p(N, BIG5_N_ANXIETY_SCALE)
        - _p(A, BIG5_A_ANXIETY_SCALE)
        + (arousal              * ANXIETY_AROUSAL_WEIGHT)
        + (100 - cognitive_clarity) * ANXIETY_CLARITY_WEIGHT
        + (100 - social_warmth)     * ANXIETY_WARMTH_WEIGHT
        + (pain_awareness     * ANXIETY_PAIN_WEIGHT)
        + (max(0.0, ei)       * ANXIETY_EI_SCALE)
        - (effective_gaba     * ANXIETY_GABA_WEIGHT)
        - ANXIETY_OFFSET
    )

    # DEPRESSION: Neuroticism raises susceptibility; conscientiousness adds resilience.
    depression = _clamp(
        _p(N, BIG5_N_DEPRESSION_SCALE)
        - _p(C, BIG5_C_DEPRESSION_SCALE)
        + (100 - mood_valence)  * DEPRESSION_VALENCE_WEIGHT
        + (100 - hedonic_tone)  * DEPRESSION_HEDONIC_WEIGHT
        + (100 - energy)        * DEPRESSION_ENERGY_WEIGHT
        + (infl                 * DEPRESSION_INFLAMMATION_WEIGHT)
        + (al                   * DEPRESSION_ALLOSTATIC_WEIGHT)
        - DEPRESSION_OFFSET
    )

    # BOREDOM: driven by arousal deficit from optimal, not absolute low arousal.
    # Introverts have a low optimal (~25); extraverts need high arousal (~60) to feel engaged.
    # Openness raises the threshold further — curious people are harder to bore at any arousal level.
    optimal_arousal = BIG5_E_AROUSAL_OPTIMAL_BASE + E * BIG5_E_AROUSAL_OPTIMAL_SCALE
    arousal_deficit = max(0.0, optimal_arousal - arousal)   # understimulation relative to need
    boredom = _clamp(
        (arousal_deficit        * BOREDOM_AROUSAL_WEIGHT)
        + (100 - hedonic_tone)  * BOREDOM_HEDONIC_WEIGHT
        + (100 - energy)        * BOREDOM_ENERGY_WEIGHT
        + (100 - cognitive_clarity) * BOREDOM_CLARITY_WEIGHT
        - BOREDOM_OFFSET
        - _p(O, BIG5_O_BOREDOM_SCALE)
    )

    # SPEC-28: Loneliness decoupled from social_warmth.
    # Driven by isolation_pressure (persistent accumulator), bond deficit (oxytocin vs threshold),
    # and inflammation (sickness → withdrawal). Extraversion amplifies felt loneliness.
    isolation_pressure = s.body.get("isolation_pressure", 0.0)
    bond_deficit = max(0.0, 1.0 - (_n("oxytocin", s) / LONELINESS_BOND_OXY_THRESHOLD))
    extroversion_amp = LONELINESS_E_BASE + E * LONELINESS_E_SCALE
    loneliness = _clamp(
        _clamp(
            (isolation_pressure    * LONELINESS_ISOLATION_WEIGHT)
            + (bond_deficit * 100  * LONELINESS_BOND_WEIGHT)
            + (infl                * LONELINESS_INFLAMMATION_WEIGHT)
            - LONELINESS_OFFSET
        ) * extroversion_amp
    )

    flow = _clamp(
        (cognitive_clarity * FLOW_CLARITY_WEIGHT)
        + (hedonic_tone    * FLOW_HEDONIC_WEIGHT)
        + (arousal         * FLOW_AROUSAL_WEIGHT)
        + (effective_gaba  * FLOW_GABA_WEIGHT)   # relaxed alertness enables flow
        - anxiety          * FLOW_ANXIETY_REDUCTION
    )

    # Physical distress: pain + inflammation + hunger + fatigue
    physical_distress = _clamp(
        (pain_awareness * DISTRESS_PAIN_WEIGHT)
        + (infl         * DISTRESS_INFLAMMATION_WEIGHT)
        + (hunger_n     * DISTRESS_HUNGER_WEIGHT)
        + (100 - energy) * DISTRESS_ENERGY_WEIGHT
        - DISTRESS_OFFSET
    )

    # SPEC-34: craving — delta between hedonic setpoint and current reward reality
    _endorphin_norm = min(100.0, max(0.0,
        s.chemicals.get("endorphins", 12.0) / CRAVING_ENDORPHIN_MAX * 100.0))
    _dopamine_norm  = min(100.0, max(0.0,
        (s.chemicals.get("dopamine", 80.0) - CRAVING_DOPAMINE_MIN) /
        (CRAVING_DOPAMINE_MAX - CRAVING_DOPAMINE_MIN) * 100.0))
    _oxytocin_norm  = min(100.0, max(0.0,
        s.chemicals.get("oxytocin", 4.0) / CRAVING_OXYTOCIN_MAX * 100.0))
    _serotonin_norm = min(100.0, max(0.0,
        (s.chemicals.get("serotonin", 22.0) - CRAVING_SEROTONIN_MIN) /
        (CRAVING_SEROTONIN_MAX - CRAVING_SEROTONIN_MIN) * 100.0))
    _reward_reality = (
        _endorphin_norm * CRAVING_ENDORPHIN_WEIGHT
        + _dopamine_norm * CRAVING_DOPAMINE_WEIGHT
        + _oxytocin_norm * CRAVING_OXYTOCIN_WEIGHT
        + _serotonin_norm * CRAVING_SEROTONIN_WEIGHT
    )
    _hedonic_setpoint = s.body.get("hedonic_setpoint", HEDONIC_SETPOINT_BIOLOGICAL_FLOOR)
    craving = _clamp(max(0.0, _hedonic_setpoint - _reward_reality) * CRAVING_SENSITIVITY)

    # SPEC-31: social hostility — amygdala hyperreactivity from serotonin depletion + norepi elevation.
    # Near-zero at normal chemistry; rises meaningfully at Stage 3+ isolation.
    # Neuroscience: serotonin inhibits amygdala. Depleted serotonin + elevated norepi =
    # hyperreactive threat response. Low oxytocin removes prosocial buffering.
    # SPEC-33: relationship tension (net) adds a baseline hostility term — pre-existing
    # resentment makes social_hostility spike faster during isolation.
    _effective_sero_norm = _clamp(effective_serotonin)  # already 0-100
    try:
        from src.config.config import RELATIONSHIP_DIR as _REL_DIR
        from src.brain.hippocampus.hippocampus import _get_net_relationship_dimensions
        import os as _os
        _tensions = []
        if _os.path.exists(_REL_DIR):
            for _fn in _os.listdir(_REL_DIR):
                if _fn.endswith(".md"):
                    _dims = _get_net_relationship_dimensions(_fn[:-3])
                    _tensions.append(max(0.0, float(_dims.get("tension", 0.0))))
        _rel_tension = sum(_tensions) / len(_tensions) if _tensions else 0.0
    except Exception:
        _rel_tension = 0.0
    social_hostility = _clamp(
        (100 - _effective_sero_norm) * HOSTILITY_SEROTONIN_WEIGHT
        + _n("norepinephrine", s)    * HOSTILITY_NOREPI_WEIGHT
        + loneliness                 * HOSTILITY_LONELINESS_WEIGHT
        - _n("oxytocin", s)          * HOSTILITY_OXYTOCIN_WEIGHT
        + _rel_tension               * HOSTILITY_RELATIONSHIP_TENSION_WEIGHT * 50.0
        - HOSTILITY_OFFSET
    ) * (1.0 + N * BIG5_N_HOSTILITY_SCALE)
    social_hostility = _clamp(social_hostility)

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
            "craving":           round(craving, 1),
            "social_hostility":  round(social_hostility, 1),
        },
    }
