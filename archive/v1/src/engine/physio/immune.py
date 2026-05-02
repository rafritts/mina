"""Immune system — cytokines, inflammation index, sickness behavior cascade.
Full implementation for SPEC-23.
"""
from __future__ import annotations

import time

from src.engine.bio.state import BiologicalState
from src.engine.chem.units import clamp_chemical
from src.engine.events import BiologicalEvent, EventBus


# ---------------------------------------------------------------------------
# Inflammation index (exported for tests)
# ---------------------------------------------------------------------------

def compute_inflammation_index(immune: dict) -> float:
    """
    Composite 0–100 AU from all pro-inflammatory markers.
    CRP is a slower integrator (chronic inflammation more than acute).
    """
    il1b = immune.get("il1b",      2.0)
    il6  = immune.get("il6",       3.0)
    tnfa = immune.get("tnf_alpha", 3.0)
    crp  = immune.get("crp",       0.5)
    il10 = immune.get("il10",     10.0)   # anti-inflammatory

    # Scale each marker 0→100 over its activated range
    il1b_n = min(100.0, max(0.0, (il1b - 2.0) / 0.48))   # 2→50 pg/mL
    il6_n  = min(100.0, max(0.0, (il6  - 3.0) / 0.97))   # 3→100 pg/mL
    tnfa_n = min(100.0, max(0.0, (tnfa - 3.0) / 0.97))
    crp_n  = min(100.0, max(0.0, (crp  - 1.0) / 0.99))   # 1→100 mg/L

    # IL-10 dampens the index (counter-regulation)
    il10_factor = max(0.4, 1.0 - (il10 - 10.0) * 0.015)

    index = (il1b_n * 0.30 + il6_n * 0.35 + tnfa_n * 0.25 + crp_n * 0.10) * il10_factor
    return round(min(100.0, max(0.0, index)), 2)


# ---------------------------------------------------------------------------
# Sickness behavior cascade
# ---------------------------------------------------------------------------

def _apply_sickness_behavior(s: BiologicalState, sim_hours: float) -> None:
    """
    Cytokine-driven suppression of first-order chemicals.
    Adaptive: body conserves energy for immune function.
    """
    il1b = s.immune.get("il1b",      2.0)
    il6  = s.immune.get("il6",       3.0)
    tnfa = s.immune.get("tnf_alpha", 3.0)

    # IL-1β → serotonin suppression via IDO enzyme pathway
    # (tryptophan diverted from 5-HT synthesis toward neurotoxic kynurenine)
    if il1b > 8.0:
        drain = (il1b - 8.0) * 0.04 * sim_hours
        s.chemicals["serotonin"] = clamp_chemical("serotonin",
            s.chemicals.get("serotonin", 22.0) - drain)

    # IL-6 → dopamine suppression (mesolimbic DA pathway → anhedonia)
    if il6 > 15.0:
        drain = (il6 - 15.0) * 0.08 * sim_hours
        s.chemicals["dopamine"] = clamp_chemical("dopamine",
            s.chemicals.get("dopamine", 80.0) - drain)

    # TNF-α → cortisol elevation (HPA activation via TNF receptors)
    if tnfa > 12.0:
        boost = (tnfa - 12.0) * 0.3 * sim_hours
        s.chemicals["cortisol"] = clamp_chemical("cortisol",
            s.chemicals.get("cortisol", 250.0) + boost)

    # High inflammation → adenosine buildup (hypersomnia drive)
    infl_index = s.immune.get("inflammation_index", 0.0)
    if infl_index > 40.0:
        s.body["adenosine"] = min(100.0,
            s.body.get("adenosine", 25.0) + (infl_index - 40.0) * 0.015 * sim_hours)

    # Social withdrawal: oxytocin reduction (active sick individuals withdraw)
    if infl_index > 50.0:
        drain = (infl_index - 50.0) * 0.02 * sim_hours
        s.chemicals["oxytocin"] = clamp_chemical("oxytocin",
            s.chemicals.get("oxytocin", 4.0) - drain)


# ---------------------------------------------------------------------------
# Main advance function
# ---------------------------------------------------------------------------

def advance_immune(s: BiologicalState, sim_hours: float, event_bus: EventBus) -> BiologicalState:
    """
    Advance all immune markers toward their dynamic baselines.
    Must run after Phase 1 so cortisol and glutamate reflect the current tick.
    """
    cortisol  = s.chemicals.get("cortisol",       250.0)
    adenosine = s.body.get("adenosine",             25.0)
    glutamate = s.chemicals.get("glutamate",         4.0)
    pain_int  = s.pain.get("pain_intensity",         0.0)  # last-tick value
    ghrelin   = s.neuroendocrine.get("ghrelin",    400.0)

    # --- Compute dynamic baselines ---

    # IL-1β: rises with sleep deprivation, pain, and chronic stress
    il1b_baseline = 2.0
    if adenosine > 65.0:
        il1b_baseline += (adenosine - 65.0) * 0.08
    if pain_int > 40.0:
        il1b_baseline += (pain_int - 40.0) * 0.1
    if cortisol > 600.0:   # chronic stress → immune dysregulation
        il1b_baseline += (cortisol - 600.0) * 0.005
    il1b_baseline = max(1.0, min(80.0, il1b_baseline))

    # IL-6: rises with IL-1β cascade, severe hunger, excitotoxicity
    il6_baseline = 3.0 + max(0, s.immune.get("il1b", 2.0) - 5.0) * 0.5
    if ghrelin > 700.0:
        il6_baseline += (ghrelin - 700.0) * 0.002
    if glutamate > 10.0:   # excitotoxicity → neuroinflammation
        il6_baseline += (glutamate - 10.0) * 0.5
    il6_baseline = max(1.0, min(120.0, il6_baseline))

    # TNF-α: follows IL-1β cascade
    tnfa_baseline = 3.0 + max(0, s.immune.get("il1b", 2.0) - 5.0) * 0.4
    tnfa_baseline = max(1.0, min(100.0, tnfa_baseline))

    # CRP: lags 12–24 hr behind acute cytokines (liver synthesis)
    crp_target = 0.5 + max(0, s.immune.get("il6", 3.0) - 10.0) * 0.3
    crp_target  = max(0.2, min(200.0, crp_target))

    # IL-10: counter-regulatory — rises in response to inflammation
    il10_baseline = 10.0 + max(0, s.immune.get("il6", 3.0) - 10.0) * 0.8
    il10_baseline = max(5.0, min(80.0, il10_baseline))

    # --- Advance toward baselines ---

    for key, target, rate in [
        ("il1b",      il1b_baseline, 0.30),
        ("il6",       il6_baseline,  0.25),
        ("tnf_alpha", tnfa_baseline, 0.20),
        ("il10",      il10_baseline, 0.35),
    ]:
        current = s.immune.get(key, 3.0)
        s.immune[key] = max(0.5, current + (target - current) * min(1.0, rate * sim_hours))

    # CRP: very slow (approach_rate 0.04/hr ≈ 12–24 hr half-life)
    crp = s.immune.get("crp", 0.5)
    s.immune["crp"] = max(0.1, crp + (crp_target - crp) * min(1.0, 0.04 * sim_hours))

    # Derived inflammation index
    s.immune["inflammation_index"] = compute_inflammation_index(s.immune)

    # Sickness behavior cascade
    _apply_sickness_behavior(s, sim_hours)

    # Emit event when inflammation is elevated
    infl = s.immune["inflammation_index"]
    if infl > 40.0:
        event_bus.emit(BiologicalEvent(
            event_type="threshold_crossed",
            system="immune",
            chemical="inflammation_index",
            value=infl,
            delta=infl,
            unit="AU",
            label="ACTIVE" if infl > 65.0 else "MODERATE",
            label_crossed=True,
            severity="significant" if infl > 65.0 else "moderate",
            significance=min(1.0, infl / 100.0),
            timestamp=time.time(),
        ))

    return s
