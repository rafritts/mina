"""Receptor sensitivity tracking — up/downregulation.
Full implementation for SPEC-21.

Receptor sensitivity bounds: [0.2, 2.0]. 1.0 = normal.
  < 1.0 = downregulated (tolerance: sustained over-stimulation)
  > 1.0 = upregulated (sensitization: sustained under-stimulation)

This is a slow system — meaningful change takes many sim-hours (days real-time).
"""
from __future__ import annotations

from src.engine.bio.state import BiologicalState
from src.engine.chem.registry import REGISTRY

# Default receptor subtypes per neurotransmitter
RECEPTOR_DEFAULTS: dict[str, dict[str, float]] = {
    "dopamine":       {"D1": 1.0, "D2": 1.0, "D3": 1.0},
    "serotonin":      {"5HT1A": 1.0, "5HT2A": 1.0, "5HT3": 1.0},
    "norepinephrine": {"alpha1": 1.0, "alpha2": 1.0, "beta1": 1.0},
    "gaba":           {"GABA_A": 1.0, "GABA_B": 1.0},
    "glutamate":      {"NMDA": 1.0, "AMPA": 1.0},
    "adenosine":      {"A1": 1.0, "A2A": 1.0},
    "endorphins":     {"MOR": 1.0},     # mu-opioid receptor
    "anandamide":     {"CB1": 1.0, "CB2": 1.0},
    "acetylcholine":  {"M1": 1.0, "nACh": 1.0},
    "oxytocin":       {"OTR": 1.0},
}

# Thresholds for chemicals not in REGISTRY (stored in body tier)
_BODY_RECEPTOR_THRESHOLDS: dict[str, dict[str, float]] = {
    "adenosine": {
        "soft_ceiling": 60.0,   # nmol/L — elevated, drives downregulation
        "resting_low":  20.0,   # nmol/L — depleted, drives upregulation
    },
    "anandamide": {
        "soft_ceiling": 5.0,    # nM
        "resting_low":  0.5,    # nM
    },
}

_DOWN_RATE = 0.0004   # per sim-hour above soft_ceiling (tolerance; days-scale)
_UP_RATE   = 0.0002   # per sim-hour below resting_low (sensitization; weeks-scale)
_RESTORE   = 0.001    # per sim-hour gap toward 1.0 (homeostatic reset)
_BOUNDS    = (0.2, 2.0)


def advance_receptors(s: BiologicalState, sim_hours: float) -> BiologicalState:
    """
    Update receptor sensitivity for each tracked chemical.
    Very slow — intended to model days-to-weeks scale tolerance/sensitization.
    """
    if s.receptor_sensitivity is None:
        s.receptor_sensitivity = {}

    for chem_name, subtypes in RECEPTOR_DEFAULTS.items():
        # OTR trajectory is owned by consolidate_relationship(), not chemical homeostasis
        if chem_name == "oxytocin":
            continue

        # Get current level and relevant thresholds
        if chem_name in s.chemicals:
            level = s.chemicals[chem_name]
            profile = REGISTRY.get(chem_name)
            if not profile:
                continue
            soft_ceiling = profile.soft_ceiling
            resting_low  = profile.resting_low

        elif chem_name in _BODY_RECEPTOR_THRESHOLDS:
            # Body-tier chemical (adenosine, anandamide)
            body_key = chem_name
            level = s.body.get(body_key, 1.0)
            thresholds   = _BODY_RECEPTOR_THRESHOLDS[chem_name]
            soft_ceiling = thresholds.get("soft_ceiling")
            resting_low  = thresholds.get("resting_low", 0.0)

        else:
            continue

        # Initialize receptor sensitivity for this chemical if missing
        if chem_name not in s.receptor_sensitivity:
            s.receptor_sensitivity[chem_name] = dict(subtypes)

        for receptor_type in subtypes:
            current = s.receptor_sensitivity[chem_name].get(receptor_type, 1.0)

            if soft_ceiling and level > soft_ceiling:
                # Sustained elevation → downregulation (tolerance)
                delta = -_DOWN_RATE * sim_hours
            elif resting_low and level < resting_low:
                # Sustained depletion → upregulation (sensitization)
                delta = +_UP_RATE * sim_hours
            else:
                # Homeostatic reset toward 1.0
                gap   = 1.0 - current
                delta = gap * _RESTORE * sim_hours

            new = max(_BOUNDS[0], min(_BOUNDS[1], current + delta))
            s.receptor_sensitivity[chem_name][receptor_type] = round(new, 4)

    return s
