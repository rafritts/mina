"""Personality drift — Big 5 trait modulation driven by allostatic load.
Full implementation for SPEC-24.

High allostatic load slowly shifts Big 5 traits — primarily neuroticism rises
and conscientiousness/agreeableness fall. Changes are reversible but slow,
mirroring real-world studies on chronic stress and personality.

The drift dict is returned but NOT written to personality.json by this module.
Writing only occurs when drift exceeds threshold AND allostatic load has been
elevated for ≥24 sim-hours — preventing noise commits from short stress events.
"""
from __future__ import annotations

from src.sim.bio.state import BiologicalState


def apply_personality_drift(s: BiologicalState, personality: dict,
                              sim_hours: float) -> dict:
    """
    Compute personality drift from allostatic load.

    Returns an updated personality dict (does NOT write to personality.json).
    Caller is responsible for persisting if drift exceeds threshold.

    Drift is:
    - Active above al = 60.0 (chronic severe stress territory)
    - Reversible: below al = 15.0, traits slowly recover toward original if
      '_original' snapshot is present in the personality dict

    Literature basis: van den Berg et al. (2014), Sutin et al. (2010) — chronic
    life stress reliably increases neuroticism and reduces conscientiousness.
    """
    al = s.neuroplasticity.get("allostatic_load", 0.0)
    p  = dict(personality)   # don't mutate in place

    if al > 60.0:
        # Chronic severe stress effects (literature-supported):
        # Neuroticism rises (increased emotional reactivity, anxiety sensitivity)
        # Conscientiousness falls (reduced self-regulation under resource depletion)
        # Agreeableness falls (reduced prosocial behavior under chronic threat)
        drift_rate = (al - 60.0) * 0.0001 * sim_hours   # very slow: days to weeks
        p["neuroticism"]       = min(100.0, p.get("neuroticism",       65.0) + drift_rate)
        p["conscientiousness"] = max(  0.0, p.get("conscientiousness", 70.0) - drift_rate * 0.5)
        p["agreeableness"]     = max(  0.0, p.get("agreeableness",     75.0) - drift_rate * 0.3)

    elif al < 15.0 and personality.get("_original"):
        # Recovery: slowly restore toward original personality baseline
        original = personality["_original"]
        for trait in ["neuroticism", "conscientiousness", "agreeableness"]:
            current = p.get(trait, 50.0)
            orig    = original.get(trait, 50.0)
            if abs(current - orig) > 0.1:
                # Very slow recovery — trauma lingers longer than it builds
                p[trait] = current + (orig - current) * min(1.0, 0.00005 * sim_hours)

    return p
