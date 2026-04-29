"""Endocannabinoid dynamics — anandamide and 2-AG.
Full implementation for SPEC-21.

Both molecules are stored in state.body (not state.chemicals) because they are
lipid-based retrograde messengers with different dynamics from neurotransmitters.
The REGISTRY has profiles for units/labels/saturation only.
"""
from __future__ import annotations

from src.engine.bio.state import BiologicalState
from src.engine.chem.registry import REGISTRY
from src.engine.chem.units import clamp_chemical
from src.engine.events import EventBus


def advance_endocannabinoids(s: BiologicalState, sim_hours: float,
                              event_bus: EventBus) -> BiologicalState:
    """
    Advance anandamide and 2-AG dynamics.

    Values live in state.body. Cross-tier effects modulate pain, cortisol,
    and immune markers via CB1/CB2 receptor signaling.
    """
    ana_profile   = REGISTRY["anandamide"]
    two_ag_profile = REGISTRY["two_ag"]

    ctx = {
        "cortisol":     s.chemicals.get("cortisol", 250.0),
        "oxytocin":     s.chemicals.get("oxytocin", 4.0),
        "pain_intensity": s.pain.get("pain_intensity", 0.0),
    }

    # Snapshot pre-tick levels for effect gating — effects fire based on what
    # the chemical IS (current exposure), then the chemical decays toward baseline.
    ana    = s.body.get("anandamide", 1.5)
    two_ag = s.body.get("two_ag", 8.0)

    # --- Anandamide cross-effects via CB1 (using pre-tick level) ---

    if ana > 3.0:
        # CB1 closes pain gate: retrograde inhibition of Substance P release
        s.pain["pain_intensity"] = max(
            0.0,
            s.pain.get("pain_intensity", 0.0) - 3.0 * sim_hours,
        )

    if ana > 4.0:
        # Stress buffering: CB1 inhibits CRH neurons in hypothalamus
        s.chemicals["cortisol"] = clamp_chemical(
            "cortisol",
            s.chemicals.get("cortisol", 250.0) - 10.0 * sim_hours,
        )

    # --- 2-AG cross-effects via CB2 (pre-tick level) ---

    if two_ag > 15.0:
        # CB2 peripheral immune modulation: anti-inflammatory
        s.immune["il6"]       = max(0.0, s.immune.get("il6", 3.0)       - 0.5 * sim_hours)
        s.immune["tnf_alpha"] = max(0.0, s.immune.get("tnf_alpha", 3.0) - 0.3 * sim_hours)

    # --- Anandamide advance toward baseline (fast FAAH turnover) ---
    ana_target = ana_profile.baseline_fn(0.0, ctx)
    ana_gap    = ana_target - ana
    new_ana    = ana + ana_gap * min(1.0, ana_profile.approach_rate * sim_hours)
    new_ana    = max(ana_profile.critical_low or 0.3, min(ana_profile.critical_high or 15.0, new_ana))
    s.body["anandamide"] = new_ana

    # --- 2-AG advance toward baseline ---
    two_ag_target = two_ag_profile.baseline_fn(0.0, ctx)
    two_ag_gap    = two_ag_target - two_ag
    new_two_ag    = two_ag + two_ag_gap * min(1.0, two_ag_profile.approach_rate * sim_hours)
    new_two_ag    = max(two_ag_profile.critical_low or 2.0, min(two_ag_profile.critical_high or 50.0, new_two_ag))
    s.body["two_ag"] = new_two_ag

    return s
