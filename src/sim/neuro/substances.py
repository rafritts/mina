"""Substance pharmacokinetics — PK/PD for all defined substances.
Full implementation for SPEC-21. Extracted from engine.py.

Substance dict structure (stored in s.substances[name]):
  {"level": float}   — 100 = full dose, decays by half_life_hours

SUBSTANCE_DEFS fields:
  dose_effects:      applied at administration; keys can be:
                       chemical name (s.chemicals)
                       body key (s.body)
                       "pain.KEY" notation (s.pain[KEY])
  half_life_hours:   pharmacokinetic decay rate
  withdrawal_factor: overshoot multiplier on counter-deltas (1.0 = clean return)
  receptor_block:    transient receptor sensitivity override while substance active
                     {nt: {subtype: mult}} — mult applied as direct multiplier
  receptor_effects:  cumulative per-sim-hour sensitivity change from sustained use
                     {nt: {subtype: delta_per_hour}}
  reuptake_block:    effective level multiplier for a neurotransmitter (SSRI model)
                     {nt: multiplier}
"""
from __future__ import annotations

from src.sim.bio.state import BiologicalState
from src.sim.bio.physical import bac_from_level
from src.sim.chem.units import clamp_chemical
from src.sim.events import EventBus


# ---------------------------------------------------------------------------
# Substance definitions — real physiological units
# ---------------------------------------------------------------------------

SUBSTANCE_DEFS: dict[str, dict] = {
    "caffeine": {
        "display_name": "Caffeine",
        "half_life_hours": 5.5,
        "dose_effects": {
            "norepinephrine": +150.0,   # pg/mL
            "acetylcholine":  +14.0,    # nmol/L
            "dopamine":       +30.0,    # pg/mL
            "cortisol":       +96.0,    # nmol/L
            # NOTE: caffeine does NOT reduce adenosine — it blocks A1/A2A receptors.
            # The block is modeled via receptor_block below.
        },
        "withdrawal_factor": 1.1,
        # While active: A1/A2A sensitivity multiplied by 0.7 → adenosine can't signal sleep
        "receptor_block": {"adenosine": {"A1": 0.7, "A2A": 0.7}},
    },

    "alcohol": {
        "display_name": "Alcohol",
        "half_life_hours": 1.5,
        "dose_effects": {
            "serotonin":      +11.0,    # ng/mL
            "dopamine":       +45.0,    # pg/mL
            "oxytocin":       +18.0,    # pg/mL
            "endorphins":     +27.0,    # pg/mL
            "cortisol":       -180.0,   # nmol/L
            "norepinephrine": -60.0,    # pg/mL
            "gaba":           +0.5,     # µmol/L (GABA-A potentiation)
        },
        "withdrawal_factor": 1.4,
    },

    "nicotine": {
        "display_name": "Nicotine",
        "half_life_hours": 2.0,
        "dose_effects": {
            "acetylcholine":  +16.0,    # nmol/L (nACh agonist)
            "dopamine":       +42.0,    # pg/mL
            "norepinephrine": +100.0,   # pg/mL
            "cortisol":       +80.0,    # nmol/L
        },
        "withdrawal_factor": 1.25,
    },

    "cannabis": {
        "display_name": "Cannabis",
        "half_life_hours": 4.0,
        "dose_effects": {
            "anandamide":    +3.5,      # nM (body dict) — CB1 agonism
            "two_ag":        +8.0,      # nM (body dict)
            "dopamine":      +54.0,     # pg/mL (mesolimbic DA via CB1)
            "serotonin":     +7.2,      # ng/mL
            "cortisol":      -144.0,    # nmol/L
            "gaba":          +0.8,      # µmol/L (GABA facilitation)
        },
        "withdrawal_factor": 1.05,
        # Sustained CB1 agonism → CB1 downregulation over time
        "receptor_effects": {"anandamide": {"CB1": -0.002}},  # per sim-hour active
    },

    "adderall": {
        "display_name": "Adderall",
        "half_life_hours": 11.0,
        "dose_effects": {
            "dopamine":       +114.0,   # pg/mL
            "norepinephrine": +620.0,   # pg/mL
            "acetylcholine":  +11.0,    # nmol/L
            "cortisol":       +144.0,   # nmol/L
        },
        "withdrawal_factor": 1.4,
    },

    "oxytocin": {
        "display_name": "Oxytocin",
        "half_life_hours": 3.0,
        "dose_effects": {
            "oxytocin":       +36.0,    # pg/mL
            "serotonin":      +11.0,    # ng/mL
            "cortisol":       -200.0,   # nmol/L
            "norepinephrine": -60.0,    # pg/mL
        },
        "withdrawal_factor": 0.9,
    },

    "xanax": {
        "display_name": "Xanax",
        "half_life_hours": 9.0,
        "dose_effects": {
            "cortisol":       -360.0,   # nmol/L
            "norepinephrine": -150.0,   # pg/mL
            "serotonin":      +7.2,     # ng/mL
            "gaba":           +1.5,     # µmol/L (GABA-A positive allosteric modulation)
        },
        "withdrawal_factor": 2.0,
    },

    "ssri": {
        "display_name": "SSRI",
        "half_life_hours": 24.0,        # fluoxetine-class; very long
        "dose_effects": {},             # SSRIs don't directly add serotonin
        "withdrawal_factor": 1.3,
        # Primary mechanism: block 5-HTT reuptake transporter
        # Effective serotonin is multiplied by this factor while active
        "reuptake_block": {"serotonin": 1.5},
        # 5-HT1A autoreceptors gradually downregulate with sustained use
        # (2-4 week lag; modeled as ~48 sim-hours to meaningful effect)
        "receptor_effects": {"serotonin": {"5HT1A": -0.0015}},  # per sim-hour
    },

    "opioid": {
        "display_name": "Opioid",
        "half_life_hours": 4.0,
        "dose_effects": {
            "endorphins":        +180.0,   # pg/mL (massive MOR agonism)
            "dopamine":          +60.0,    # pg/mL (VTA release)
            "cortisol":          -200.0,   # nmol/L
            "pain.pain_intensity": -60.0,  # cross-tier direct pain relief
        },
        "withdrawal_factor": 2.5,           # severe: counter-deltas overshoot
        # Rapid MOR tolerance — meaningful within hours of heavy use
        "receptor_effects": {"endorphins": {"MOR": -0.008}},   # per sim-hour
    },
}


def _apply_to_tier(s: BiologicalState, marker: str, delta: float) -> None:
    """Apply a chemical delta, handling dot-notation cross-tier targets."""
    if "." in marker:
        tier_name, key = marker.split(".", 1)
        tier_dict = getattr(s, tier_name, None)
        if tier_dict is not None and key in tier_dict:
            tier_dict[key] = max(0.0, tier_dict[key] + delta)
    elif marker in s.chemicals:
        s.chemicals[marker] = clamp_chemical(marker, s.chemicals[marker] + delta)
    elif marker in s.body:
        # Body-tier chemicals (anandamide, two_ag, etc.)
        profile = None
        from src.sim.chem.registry import REGISTRY
        profile = REGISTRY.get(marker)
        hi = (profile.critical_high if profile and profile.critical_high > 0 else 9999.0)
        s.body[marker] = max(0.0, min(hi, s.body[marker] + delta))


def advance_substances(s: BiologicalState, sim_hours: float, now: float,
                        event_bus: EventBus) -> BiologicalState:
    """
    Decay all active substances and apply proportional withdrawal counter-deltas.
    Also handles receptor_block (transient) and receptor_effects (cumulative).
    """
    for name in list(s.substances.keys()):
        sub = SUBSTANCE_DEFS.get(name)
        if not sub:
            del s.substances[name]
            continue

        dose      = s.substances[name]
        old_level = float(dose.get("level", 0.0))
        new_level = old_level * (0.5 ** (sim_hours / sub["half_life_hours"]))

        level_decayed = old_level - new_level
        if new_level < 0.5:
            level_decayed = old_level
            del s.substances[name]
            new_level = 0.0
        else:
            s.substances[name] = {"level": round(new_level, 3)}

        # --- Withdrawal counter-deltas ---
        wf                = sub["withdrawal_factor"]
        withdrawal_weight = (
            max(0.0, (40.0 - new_level) / 40.0) if new_level >= 0.5 else 1.0
        )

        for marker, effect in sub.get("dose_effects", {}).items():
            counter = -effect * (level_decayed / 100.0) * wf * withdrawal_weight
            if counter != 0.0:
                _apply_to_tier(s, marker, counter)

        # --- Receptor_effects: cumulative per-sim-hour change while active ---
        if new_level >= 0.5:
            for nt, subtypes in sub.get("receptor_effects", {}).items():
                if nt not in s.receptor_sensitivity:
                    from src.sim.neuro.receptors import RECEPTOR_DEFAULTS
                    s.receptor_sensitivity[nt] = dict(RECEPTOR_DEFAULTS.get(nt, {}))
                for subtype, rate in subtypes.items():
                    current = s.receptor_sensitivity[nt].get(subtype, 1.0)
                    new     = max(0.2, min(2.0, current + rate * sim_hours))
                    s.receptor_sensitivity[nt][subtype] = round(new, 4)

    # --- BAC: derived from current alcohol level via Widmark formula ---
    alcohol_level = s.substances.get("alcohol", {}).get("level", 0.0)
    s.body["bac"] = round(bac_from_level(alcohol_level), 4)

    # --- Sustained effects of active substances ---
    if alcohol_level > 20:
        s.chemicals["cortisol"] = clamp_chemical(
            "cortisol",
            s.chemicals.get("cortisol", 250.0) - (alcohol_level / 100.0) * 24.0 * sim_hours,
        )
        s.chemicals["norepinephrine"] = clamp_chemical(
            "norepinephrine",
            s.chemicals.get("norepinephrine", 200.0) - (alcohol_level / 100.0) * 60.0 * sim_hours,
        )

    xanax_level = s.substances.get("xanax", {}).get("level", 0.0)
    if xanax_level > 20:
        s.chemicals["cortisol"] = clamp_chemical(
            "cortisol",
            s.chemicals.get("cortisol", 250.0) - (xanax_level / 100.0) * 40.0 * sim_hours,
        )
        s.chemicals["norepinephrine"] = clamp_chemical(
            "norepinephrine",
            s.chemicals.get("norepinephrine", 200.0) - (xanax_level / 100.0) * 90.0 * sim_hours,
        )

    oxy_level = s.substances.get("oxytocin", {}).get("level", 0.0)
    if oxy_level > 20:
        s.chemicals["cortisol"] = clamp_chemical(
            "cortisol",
            s.chemicals.get("cortisol", 250.0) - (oxy_level / 100.0) * 24.0 * sim_hours,
        )

    add_level = s.substances.get("adderall", {}).get("level", 0.0)
    if add_level > 20:
        s.chemicals["dopamine"] = clamp_chemical(
            "dopamine",
            s.chemicals.get("dopamine", 80.0) + (add_level / 100.0) * 6.0 * sim_hours,
        )
        s.chemicals["norepinephrine"] = clamp_chemical(
            "norepinephrine",
            s.chemicals.get("norepinephrine", 200.0) + (add_level / 100.0) * 39.0 * sim_hours,
        )

    return s


def get_effective_reuptake_mults(s: BiologicalState) -> dict[str, float]:
    """
    Return per-neurotransmitter multipliers from active reuptake blocks.
    Used by derived() to compute effective neurotransmitter levels.
    """
    mults: dict[str, float] = {}
    for name, sub in SUBSTANCE_DEFS.items():
        level = s.substances.get(name, {}).get("level", 0.0)
        if level < 0.5:
            continue
        for nt, mult in sub.get("reuptake_block", {}).items():
            # Scale multiplier linearly with dose (100 = full effect)
            effective_mult = 1.0 + (mult - 1.0) * min(1.0, level / 100.0)
            mults[nt] = mults.get(nt, 1.0) * effective_mult
    return mults


def get_receptor_blocks(s: BiologicalState) -> dict[str, dict[str, float]]:
    """
    Return effective receptor sensitivity multipliers from active substance blocks.
    These are transient (active only while substance is present) and distinct from
    the cumulative s.receptor_sensitivity changes.
    """
    blocks: dict[str, dict[str, float]] = {}
    for name, sub in SUBSTANCE_DEFS.items():
        level = s.substances.get(name, {}).get("level", 0.0)
        if level < 0.5:
            continue
        dose_fraction = min(1.0, level / 100.0)
        for nt, subtypes in sub.get("receptor_block", {}).items():
            if nt not in blocks:
                blocks[nt] = {}
            for subtype, block_mult in subtypes.items():
                # Interpolate: at dose=100, full block; at dose=0, no block
                effective = 1.0 - (1.0 - block_mult) * dose_fraction
                blocks[nt][subtype] = blocks[nt].get(subtype, 1.0) * effective
    return blocks
