"""GABA and glutamate dynamics — excitatory/inhibitory balance.
Full implementation for SPEC-21."""
from __future__ import annotations

from src.engine.bio.state import BiologicalState
from src.engine.bio.defaults import CHEMICAL_DEFAULTS
from src.engine.chem.registry import REGISTRY
from src.engine.chem.units import clamp_chemical
from src.engine.events import EventBus


def advance_amino_acids(s: BiologicalState, sim_hours: float,
                         event_bus: EventBus) -> BiologicalState:
    """
    Advance GABA and glutamate dynamics.

    Both chemicals approach a dynamic baseline that depends on cortisol, sleep
    state, and each other's current level (E/I reciprocal balance). Glutamate
    also drives cross-tier effects at high levels (excitotoxicity).
    """
    gaba_profile = REGISTRY["gaba"]
    glu_profile  = REGISTRY["glutamate"]

    gaba = s.chemicals.get("gaba", CHEMICAL_DEFAULTS.get("gaba", 3.0))
    glu  = s.chemicals.get("glutamate", CHEMICAL_DEFAULTS.get("glutamate", 4.0))

    # Context for baseline functions — uses current (pre-tick) values
    ctx = {
        "cortisol":  s.chemicals.get("cortisol", 250.0),
        "sleeping":  s.sleeping,
        "glutamate": glu,
        "gaba":      gaba,
    }

    # GABA: approach dynamic baseline
    gaba_target = gaba_profile.baseline_fn(0.0, ctx)  # hour unused by GABA fn
    gaba_gap    = gaba_target - gaba
    new_gaba    = gaba + gaba_gap * min(1.0, gaba_profile.approach_rate * sim_hours)
    new_gaba    = clamp_chemical("gaba", new_gaba)
    s.chemicals["gaba"] = new_gaba

    # Update context with fresh GABA so glutamate baseline sees the new value
    ctx["gaba"] = new_gaba

    # Glutamate: approach dynamic baseline
    glu_target = glu_profile.baseline_fn(0.0, ctx)
    glu_gap    = glu_target - glu
    new_glu    = glu + glu_gap * min(1.0, glu_profile.approach_rate * sim_hours)
    new_glu    = clamp_chemical("glutamate", new_glu)
    s.chemicals["glutamate"] = new_glu

    # --- Glutamate cross-tier effects ---

    if new_glu > 10.0:
        # Excitotoxicity: neuroinflammation and core temperature rise
        s.immune["il6"]      = min(200.0, s.immune.get("il6", 3.0) + 0.5 * sim_hours)
        s.body["core_temp"]  = min(42.0,  s.body.get("core_temp", 37.0) + 0.01 * sim_hours)

    if new_glu > 8.0:
        # NMDA activation → synaptic potentiation (LTP-like)
        s.neuroplasticity["synaptic_potentiation"] = min(
            100.0,
            s.neuroplasticity.get("synaptic_potentiation", 50.0) + 0.3 * sim_hours,
        )

    return s
