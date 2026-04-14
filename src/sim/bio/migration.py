"""
Schema migration converters.

v1 → v2: convert 0-100 normalized scale to real physiological units.
v2 → v3: add neuroendocrine, immune, pain, body, neuroplasticity tiers.
"""
from __future__ import annotations

import time


def _migrate_v1_to_v2(old: dict) -> dict:
    """Convert 0-100 scale state.json to real physiological units (schema_version 2)."""
    from src.sim.chem.units import clamp_chemical

    factors = {
        "cortisol":        lambda v: v * 8.0,
        "norepinephrine":  lambda v: 50.0 + v * 19.5,
        "dopamine":        lambda v: v * 3.0,
        "serotonin":       lambda v: v * 0.6,
        "oxytocin":        lambda v: v * 0.8,
        "endorphins":      lambda v: v * 1.5,
        "acetylcholine":   lambda v: v * 0.9,
        "melatonin":       lambda v: v * 2.2,
        "glucose":         lambda v: 40.0 + v * 1.6,
        "hydration":       lambda v: 48.0 + v * 0.22,
        "sleep_pressure":  lambda v: float(v),   # AU unchanged
    }

    from src.sim.bio.defaults import CHEMICAL_DEFAULTS

    chemicals = {}
    for name, fn in factors.items():
        raw_val = old.get(name)
        if raw_val is not None:
            chemicals[name] = clamp_chemical(name, fn(float(raw_val)))
        else:
            chemicals[name] = CHEMICAL_DEFAULTS.get(name, 0.0)

    try:
        from log import log
        log("MIGRATION", "Converted state from v1 (0-100 scale) to v2 (real physiological units).")
    except ImportError:
        pass

    return {
        "schema_version": 2,
        "last_updated":   old.get("last_updated", time.time()),
        "chemicals":      chemicals,
        "tolerance":      old.get("tolerance", {}),
        "substances":     old.get("substances", {}),
        "sleeping":       old.get("sleeping", False),
        "sleep_start":    old.get("sleep_start", None),
        "sleep_expected_wake": old.get("sleep_expected_wake", None),
    }


def migrate_v2_to_v3(old: dict) -> dict:
    """
    Add v3 tiers with defaults. Existing chemicals dict is untouched.
    sleep_pressure AU carried forward as adenosine proxy in body tier.
    """
    from src.sim.bio.defaults import (
        neuroendocrine_defaults, immune_defaults, pain_defaults,
        body_defaults, neuroplasticity_defaults,
    )

    old_sp = old.get("chemicals", {}).get("sleep_pressure", 30.0)

    result = dict(old)
    result["schema_version"] = 3

    if "neuroendocrine" not in result:
        result["neuroendocrine"] = neuroendocrine_defaults()

    if "immune" not in result:
        result["immune"] = immune_defaults()

    if "pain" not in result:
        result["pain"] = pain_defaults()

    if "body" not in result:
        result["body"] = body_defaults(sleep_pressure_au=old_sp)
    elif "bac" not in result["body"]:
        result["body"]["bac"] = 0.0

    if "neuroplasticity" not in result:
        result["neuroplasticity"] = neuroplasticity_defaults()

    if "receptor_sensitivity" not in result:
        result["receptor_sensitivity"] = {}

    if "cascade_queue" not in result:
        result["cascade_queue"] = []

    if "context_queue" not in result:
        result["context_queue"] = []

    if "cycle_day" not in result:
        result["cycle_day"] = 1

    return result


def migrate_v3_to_v4(old: dict) -> dict:
    """
    SPEC-29: add stimulus_window, sensitization, secretion_queue.
    Rename encoder_momentum → habituation (retained but unused in v4+).
    """
    result = dict(old)
    result["schema_version"] = 4

    # Rename encoder_momentum → habituation
    if "encoder_momentum" in result and "habituation" not in result:
        result["habituation"] = result.pop("encoder_momentum")
    elif "habituation" not in result:
        result["habituation"] = {}

    if "stimulus_window" not in result:
        result["stimulus_window"] = []

    if "sensitization" not in result:
        result["sensitization"] = {}

    if "secretion_queue" not in result:
        result["secretion_queue"] = []

    try:
        from log import log
        log("MIGRATION", "Migrated state from v3 to v4 (SPEC-29: stimulus window, sensitization, secretion queue).")
    except ImportError:
        pass

    return result
