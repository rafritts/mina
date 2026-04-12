"""Allostatic load, BDNF, and synaptic potentiation — neuroplasticity tier.
Full implementation for SPEC-24.

Allostatic load is the cumulative biological cost of chronic stress.
BDNF (Brain-Derived Neurotrophic Factor) mediates stress-induced depression
via suppression of serotonin and dopamine system effectiveness.
Synaptic potentiation tracks the brain's current LTP-readiness (memory formation capacity).
"""
from __future__ import annotations

import time

from src.sim.bio.state import BiologicalState
from src.sim.constants import (
    ALLOSTATIC_ADENOSINE_LOAD_THRESHOLD,
    ALLOSTATIC_ADENOSINE_LOAD_RATE,
    ALLOSTATIC_BASELINE_RECOVERY_RATE,
    ALLOSTATIC_BOND_RECOVERY_THRESHOLD,
    ALLOSTATIC_BOND_RECOVERY_RATE,
    ALLOSTATIC_CORTISOL_LOAD_THRESHOLD,
    ALLOSTATIC_CORTISOL_LOAD_RATE,
    ALLOSTATIC_EVENT_THRESHOLD,
    ALLOSTATIC_IMMUNE_LOAD_RATE,
    ALLOSTATIC_PAIN_LOAD_RATE,
    ALLOSTATIC_SLEEP_RECOVERY_RATE,
    BDNF_ADENOSINE_SUPPRESS_THRESHOLD,
    BDNF_ADENOSINE_SUPPRESS_RATE,
    BDNF_APPROACH_RATE,
    BDNF_CORTISOL_SUPPRESS_THRESHOLD,
    BDNF_CORTISOL_SUPPRESS_RATE,
    BDNF_GH_BOOST_RATE,
    BDNF_INFLAMMATION_SUPPRESS_RATE,
)
from src.sim.events import BiologicalEvent, EventBus


# ---------------------------------------------------------------------------
# BDNF baseline
# ---------------------------------------------------------------------------

def _bdnf_baseline_fn(hour: float, ctx: dict) -> float:
    """
    BDNF is suppressed by chronic stress, inflammation, sleep deprivation.
    Increased by: sleep (GH-mediated synthesis), social bonding, exercise.
    """
    base = 9000.0

    # Cortisol suppresses BDNF synthesis (primary mechanism of stress-induced depression)
    if ctx.get("cortisol", 250.0) > BDNF_CORTISOL_SUPPRESS_THRESHOLD:
        base -= (ctx["cortisol"] - BDNF_CORTISOL_SUPPRESS_THRESHOLD) * BDNF_CORTISOL_SUPPRESS_RATE

    # Inflammation suppresses BDNF
    base -= ctx.get("inflammation_index", 0.0) * BDNF_INFLAMMATION_SUPPRESS_RATE

    # Sleep deprivation suppresses BDNF
    adenosine = ctx.get("adenosine", 25.0)
    if adenosine > BDNF_ADENOSINE_SUPPRESS_THRESHOLD:
        base -= (adenosine - BDNF_ADENOSINE_SUPPRESS_THRESHOLD) * BDNF_ADENOSINE_SUPPRESS_RATE

    # GH during sleep boosts BDNF synthesis
    if ctx.get("sleeping", False):
        gh = ctx.get("growth_hormone", 1.0)
        base += gh * BDNF_GH_BOOST_RATE

    return max(1000.0, min(20000.0, base))


def _make_allostatic_ctx(s: BiologicalState) -> dict:
    """Build context dict for BDNF baseline_fn."""
    return {
        "cortisol":           s.chemicals.get("cortisol", 250.0),
        "inflammation_index": s.immune.get("inflammation_index", 0.0),
        "adenosine":          s.body.get("adenosine", 25.0),
        "sleeping":           s.sleeping,
        "growth_hormone":     s.neuroendocrine.get("growth_hormone", 1.0),
    }


# ---------------------------------------------------------------------------
# Synaptic potentiation
# ---------------------------------------------------------------------------

def _compute_synaptic_potentiation_delta(s: BiologicalState, sim_hours: float) -> float:
    """
    Synaptic potentiation rises when LTP conditions are met:
      - Sufficient ACh (attentional signal enables hippocampal encoding)
      - Glutamate in sweet spot (NMDA activation — too low = no LTP, too high = excitotoxic)
      - Sufficient dopamine (reward gating enables LTP)
      - Sufficient BDNF (permits structural synaptic changes)

    Falls under:
      - Sleep deprivation (consolidated memory requires sleep)
      - Chronic cortisol (stress impairs LTP at hippocampal NMDA receptors)

    Sleep provides a strong consolidation bonus (off-line replay + SWS waves).
    """
    ach      = s.chemicals.get("acetylcholine", 38.0)
    glu      = s.chemicals.get("glutamate",      4.0)
    da       = s.chemicals.get("dopamine",       80.0)
    bdnf     = s.neuroplasticity.get("bdnf",   9000.0)
    cortisol = s.chemicals.get("cortisol",      250.0)
    adenosine= s.body.get("adenosine",           25.0)

    ach_factor  = min(1.5, ach  / 38.0)
    glu_factor  = 1.0 if 3.0 < glu < 8.0 else 0.5   # NMDA sweet spot
    da_factor   = min(1.5, da   / 80.0)
    bdnf_factor = min(1.5, bdnf / 9000.0)

    cortisol_penalty = max(0, cortisol  - 400.0) * 0.001
    sleep_penalty    = max(0, adenosine -  55.0) * 0.03

    ltp_drive = (ach_factor * glu_factor * da_factor * bdnf_factor) * 0.5
    ltp_cost  = cortisol_penalty + sleep_penalty

    # Sleep consolidation fires strongly during SWS — offline replay
    consolidation_bonus = 2.0 if s.sleeping else 0.0

    return (ltp_drive - ltp_cost + consolidation_bonus) * sim_hours


# ---------------------------------------------------------------------------
# Main advance function
# ---------------------------------------------------------------------------

def advance_allostatic(s: BiologicalState, sim_hours: float,
                        event_bus: EventBus) -> BiologicalState:
    """
    Advance allostatic load, BDNF, and synaptic potentiation each tick.

    Must run after immune and pain subsystems so inflammation_index and
    pain_intensity are current when computing stressor contributions.
    """
    al         = s.neuroplasticity.get("allostatic_load",     0.0)
    cortisol   = s.chemicals.get("cortisol",                250.0)
    adenosine  = s.body.get("adenosine",                     25.0)
    infl_index = s.immune.get("inflammation_index",           0.0)
    pain_int   = s.pain.get("pain_intensity",                 0.0)
    oxytocin   = s.chemicals.get("oxytocin",                  4.0)

    # --- Allostatic load accumulation ---

    cortisol_load = max(0.0, cortisol  - ALLOSTATIC_CORTISOL_LOAD_THRESHOLD) * ALLOSTATIC_CORTISOL_LOAD_RATE
    sleep_load    = max(0.0, adenosine - ALLOSTATIC_ADENOSINE_LOAD_THRESHOLD) * ALLOSTATIC_ADENOSINE_LOAD_RATE
    immune_load   = infl_index * ALLOSTATIC_IMMUNE_LOAD_RATE
    pain_load     = pain_int   * ALLOSTATIC_PAIN_LOAD_RATE
    total_load_rate = cortisol_load + sleep_load + immune_load + pain_load

    # Recovery contributions (reduce load)
    sleep_recovery    = ALLOSTATIC_SLEEP_RECOVERY_RATE * sim_hours if s.sleeping else 0.0
    bond_recovery     = (max(0.0, oxytocin - ALLOSTATIC_BOND_RECOVERY_THRESHOLD)
                         * ALLOSTATIC_BOND_RECOVERY_RATE * sim_hours)
    baseline_recovery = ALLOSTATIC_BASELINE_RECOVERY_RATE * sim_hours if total_load_rate < 0.01 else 0.0
    total_recovery    = sleep_recovery + bond_recovery + baseline_recovery

    al = max(0.0, min(100.0, al + total_load_rate * sim_hours - total_recovery))
    s.neuroplasticity["allostatic_load"] = round(al, 3)

    # --- BDNF advance (very slow — days/weeks in reality → 0.01/hr) ---
    bdnf = s.neuroplasticity.get("bdnf", 9000.0)
    ctx = _make_allostatic_ctx(s)
    bdnf_target = _bdnf_baseline_fn(0.0, ctx)
    s.neuroplasticity["bdnf"] = round(
        max(500.0, bdnf + (bdnf_target - bdnf) * min(1.0, BDNF_APPROACH_RATE * sim_hours)), 1
    )

    # --- Synaptic potentiation ---
    sp = s.neuroplasticity.get("synaptic_potentiation", 50.0)
    sp_delta = _compute_synaptic_potentiation_delta(s, sim_hours)
    s.neuroplasticity["synaptic_potentiation"] = round(
        min(100.0, max(0.0, sp + sp_delta)), 3
    )

    # --- Emit events for significant allostatic load ---
    if al > ALLOSTATIC_EVENT_THRESHOLD:
        event_bus.emit(BiologicalEvent(
            event_type="threshold_crossed",
            system="psych",
            chemical="allostatic_load",
            value=al,
            delta=total_load_rate * sim_hours - total_recovery,
            unit="AU",
            label="HIGH" if al < 70 else "SEVERE",
            label_crossed=True,
            severity="significant" if al > 60 else "moderate",
            significance=al / 100.0,
            timestamp=time.time(),
        ))

    return s
