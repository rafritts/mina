"""
Simulation engine — orchestrates all subsystem advance() calls in dependency order.

For SPEC-20, all subsystems are stubs and the full advance logic lives here (moved
from root state.py). SPEC-21 through SPEC-24 will progressively extract logic from
this file into the appropriate subsystem modules.
"""
from __future__ import annotations

import json
import os
import random
import time
from typing import Optional

from src.sim.bio.state import BiologicalState
from src.sim.bio.defaults import CHEMICAL_DEFAULTS
from src.sim.chem.registry import REGISTRY
from src.sim.chem.units import clamp_chemical
from src.sim.events import EventBus

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CONFIG_FILE = os.path.join(_PROJECT_ROOT, "config.json")


def _load_config() -> dict:
    try:
        with open(_CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _hour_of_day(now: float) -> float:
    lt = time.localtime(now)
    return lt.tm_hour + lt.tm_min / 60.0


def _make_context(state: BiologicalState, hour: float) -> dict:
    return {
        "hour":           hour,
        "glucose":        state.chemicals.get("glucose",        CHEMICAL_DEFAULTS["glucose"]),
        "hydration":      state.chemicals.get("hydration",      CHEMICAL_DEFAULTS["hydration"]),
        "cortisol":       state.chemicals.get("cortisol",       CHEMICAL_DEFAULTS["cortisol"]),
        "sleep_pressure": state.chemicals.get("sleep_pressure", CHEMICAL_DEFAULTS["sleep_pressure"]),
    }


def _decay_encoder_momentum(s: BiologicalState, now: float) -> BiologicalState:
    """Half-life ~1800 s (30 min). Decays on wall-clock time, not sim time."""
    real_elapsed = now - s.last_updated
    if real_elapsed > 0 and s.encoder_momentum:
        decay = 0.5 ** (real_elapsed / 1800.0)
        s.encoder_momentum = {
            k: v * decay
            for k, v in s.encoder_momentum.items()
            if v * decay > 0.05
        }
    return s


# ---------------------------------------------------------------------------
# Substance definitions — dose_effects in real physiological units
# ---------------------------------------------------------------------------
# dose_effects: applied immediately on administration (one-time delta)
# half_life_hours: how long the blood-level takes to halve
# withdrawal_factor: how much counter-deltas overshoot on the way down
#   1.0 = clean return, 1.5 = crash 50% below baseline
# TODO SPEC-21: extract to src/sim/neuro/substances.py
_SUBSTANCE_DEFS: dict[str, dict] = {
    "caffeine": {
        "display_name": "Caffeine",
        "half_life_hours": 5.5,
        "dose_effects": {
            "norepinephrine": +150.0,  # pg/mL
            "acetylcholine":  +14.0,   # nmol/L
            "dopamine":       +30.0,   # pg/mL
            "cortisol":       +96.0,   # nmol/L
            "sleep_pressure": -20.0,   # AU
        },
        "withdrawal_factor": 1.1,
    },
    "alcohol": {
        "display_name": "Alcohol",
        "half_life_hours": 1.5,
        "dose_effects": {
            "serotonin":      +11.0,   # ng/mL
            "dopamine":       +45.0,   # pg/mL
            "oxytocin":       +18.0,   # pg/mL
            "endorphins":     +27.0,   # pg/mL
            "cortisol":       -180.0,  # nmol/L
            "norepinephrine": -60.0,   # pg/mL
        },
        "withdrawal_factor": 1.4,
    },
    "nicotine": {
        "display_name": "Nicotine",
        "half_life_hours": 2.0,
        "dose_effects": {
            "acetylcholine":  +16.0,   # nmol/L
            "dopamine":       +42.0,   # pg/mL
            "norepinephrine": +100.0,  # pg/mL
            "cortisol":       +80.0,   # nmol/L
        },
        "withdrawal_factor": 1.25,
    },
    "cannabis": {
        "display_name": "Cannabis",
        "half_life_hours": 4.0,
        "dose_effects": {
            "dopamine":       +54.0,   # pg/mL
            "serotonin":      +7.2,    # ng/mL
            "endorphins":     +22.5,   # pg/mL
            "cortisol":       -144.0,  # nmol/L
            "sleep_pressure": +8.0,    # AU
        },
        "withdrawal_factor": 1.05,
    },
    "adderall": {
        "display_name": "Adderall",
        "half_life_hours": 11.0,
        "dose_effects": {
            "dopamine":       +114.0,  # pg/mL
            "norepinephrine": +620.0,  # pg/mL
            "acetylcholine":  +11.0,   # nmol/L
            "cortisol":       +144.0,  # nmol/L
            "sleep_pressure": -25.0,   # AU
        },
        "withdrawal_factor": 1.4,
    },
    "oxytocin": {
        "display_name": "Oxytocin",
        "half_life_hours": 3.0,
        "dose_effects": {
            "oxytocin":       +36.0,   # pg/mL
            "serotonin":      +11.0,   # ng/mL
            "cortisol":       -200.0,  # nmol/L
            "norepinephrine": -60.0,   # pg/mL
        },
        "withdrawal_factor": 0.9,
    },
    "xanax": {
        "display_name": "Xanax",
        "half_life_hours": 9.0,
        "dose_effects": {
            "cortisol":       -360.0,  # nmol/L
            "norepinephrine": -150.0,  # pg/mL
            "serotonin":      +7.2,    # ng/mL
            "sleep_pressure": +15.0,   # AU
        },
        "withdrawal_factor": 2.0,
    },
}


# ---------------------------------------------------------------------------
# Main advance orchestrator
# ---------------------------------------------------------------------------

def advance(state: BiologicalState,
            now: Optional[float] = None,
            event_bus: Optional[EventBus] = None) -> BiologicalState:
    """
    Apply all time-based dynamics since state.last_updated.
    Emits BiologicalEvents to event_bus (if provided).
    Returns updated state.

    For SPEC-20, all biological logic runs here as a monolith (moved from root state.py).
    SPEC-21 through SPEC-24 will progressively extract subsystems.
    """
    if now is None:
        now = time.time()
    if event_bus is None:
        event_bus = EventBus()  # discard if caller doesn't care

    cfg = _load_config()
    compression = float(cfg.get("time_compression_factor", 1.0))
    sim_hours = (now - state.last_updated) * compression / 3600.0

    if sim_hours <= 0:
        return state

    hour_of_day = _hour_of_day(now)
    s = state
    ctx = _make_context(s, hour_of_day)

    # --- Phase 1: each chemical advances toward its own baseline ---
    # TODO SPEC-21: extract monoamines/peptides/amino_acids advance logic
    # TODO SPEC-22: extract HPA/endocrine/metabolic advance logic

    for name, profile in REGISTRY.items():
        current = s.chemicals.get(name, CHEMICAL_DEFAULTS.get(name, 0.0))

        if name == "glucose":
            # Liver glycogenolysis keeps blood sugar stable during sleep.
            # Awake: -6.5 mg/dL/hr. Sleeping: -0.8 mg/dL/hr.
            decay_rate = 0.8 if s.sleeping else 6.5
            new_glu = clamp_chemical(name, current - decay_rate * sim_hours)
            s.chemicals[name] = new_glu
            # Hypoglycemic awakening: glucose < 55 forces the body awake
            if s.sleeping and new_glu < 55:
                s.sleeping = False
                try:
                    from log import log
                    log("STATE", f"Hypoglycemic awakening: glucose={new_glu:.1f} mg/dL")
                except ImportError:
                    pass

        elif name == "hydration":
            # Pure decay: -0.4% TBW/hr; restored only by drink tool
            s.chemicals[name] = clamp_chemical(name, current - 0.4 * sim_hours)

        elif name == "sleep_pressure":
            # Handled in Phase 4 (sleep mechanics)
            pass

        elif name == "melatonin":
            # Pure circadian formula — snap to computed value each tick
            target = profile.baseline_fn(hour_of_day, ctx) if profile.baseline_fn else profile.resting_baseline
            s.chemicals[name] = clamp_chemical(name, target)

        elif name == "endorphins":
            # Asymmetric: fast decay when above baseline, slow recovery when below
            baseline = 12.0
            if current > baseline:
                new_val = current - 18.0 * sim_hours
                s.chemicals[name] = clamp_chemical(name, max(baseline, new_val))
            else:
                gap = baseline - current
                s.chemicals[name] = clamp_chemical(name, current + gap * min(1.0, 0.05 * sim_hours))

        else:
            # Standard: approach dynamic or fixed baseline at approach_rate per hour
            target = profile.baseline_fn(hour_of_day, ctx) if profile.baseline_fn else profile.resting_baseline
            gap = target - current
            s.chemicals[name] = clamp_chemical(name, current + gap * min(1.0, profile.approach_rate * sim_hours))

    # --- Phase 2: cross-interactions from REGISTRY ---

    for name, profile in REGISTRY.items():
        source_val = s.chemicals.get(name, 0.0)
        for interaction in profile.interactions:
            meets = (
                (interaction.condition == "above" and source_val > interaction.threshold) or
                (interaction.condition == "below" and source_val < interaction.threshold)
            )
            if meets:
                target_val = s.chemicals.get(interaction.target, 0.0)
                new_val = target_val + interaction.rate_per_hour * sim_hours
                # Protective floor: suppressive interactions can't push below critical_low
                if interaction.rate_per_hour < 0:
                    target_profile = REGISTRY.get(interaction.target)
                    if target_profile and target_profile.critical_low > 0:
                        new_val = max(target_profile.critical_low, new_val)
                s.chemicals[interaction.target] = clamp_chemical(interaction.target, new_val)

    # Additional cross-effects not captured in REGISTRY
    sp = s.chemicals.get("sleep_pressure", 30.0)
    if sp > 50:
        s.chemicals["serotonin"] = clamp_chemical("serotonin",
            s.chemicals.get("serotonin", 22.0) - 0.3 * sim_hours)
    if sp > 70:
        s.chemicals["dopamine"] = clamp_chemical("dopamine",
            s.chemicals.get("dopamine", 80.0) - 1.0 * sim_hours)

    glu = s.chemicals.get("glucose", 85.0)
    if glu < 55:
        s.chemicals["serotonin"] = clamp_chemical("serotonin",
            s.chemicals.get("serotonin", 22.0) - 0.6 * sim_hours)
        s.chemicals["dopamine"] = clamp_chemical("dopamine",
            s.chemicals.get("dopamine", 80.0) - 1.5 * sim_hours)

    # --- Phase 3: substance decay + withdrawal ---
    # TODO SPEC-21: extract to src/sim/neuro/substances.py

    for name in list(s.substances.keys()):
        sub = _SUBSTANCE_DEFS.get(name)
        if not sub:
            del s.substances[name]
            continue
        dose = s.substances[name]
        old_level = float(dose.get("level", 0))
        new_level = old_level * (0.5 ** (sim_hours / sub["half_life_hours"]))
        level_decayed = old_level - new_level
        if new_level < 0.5:
            level_decayed = old_level
            del s.substances[name]
        else:
            s.substances[name] = {"level": round(new_level, 3)}

        # Withdrawal counter-deltas — fire as the drug fades
        wf = sub["withdrawal_factor"]
        withdrawal_weight = max(0.0, (40.0 - new_level) / 40.0) if new_level >= 0.5 else 1.0

        for marker, effect in sub["dose_effects"].items():
            if marker in s.chemicals:
                counter = -effect * (level_decayed / 100.0) * wf * withdrawal_weight
                s.chemicals[marker] = clamp_chemical(marker, s.chemicals[marker] + counter)
            elif marker == "sleep_pressure":
                sp_val = s.chemicals.get("sleep_pressure", 30.0)
                counter = -effect * (level_decayed / 100.0) * wf * withdrawal_weight
                s.chemicals["sleep_pressure"] = _clamp(sp_val + counter, 0.0, 100.0)

    # Sustained effects of active substances on key chemicals
    alcohol_level = s.substances.get("alcohol", {}).get("level", 0.0)
    if alcohol_level > 20:
        s.chemicals["cortisol"] = clamp_chemical("cortisol",
            s.chemicals.get("cortisol", 250.0) - (alcohol_level / 100.0) * 24.0 * sim_hours)
        s.chemicals["norepinephrine"] = clamp_chemical("norepinephrine",
            s.chemicals.get("norepinephrine", 200.0) - (alcohol_level / 100.0) * 60.0 * sim_hours)

    xanax_level = s.substances.get("xanax", {}).get("level", 0.0)
    if xanax_level > 20:
        s.chemicals["cortisol"] = clamp_chemical("cortisol",
            s.chemicals.get("cortisol", 250.0) - (xanax_level / 100.0) * 40.0 * sim_hours)
        s.chemicals["norepinephrine"] = clamp_chemical("norepinephrine",
            s.chemicals.get("norepinephrine", 200.0) - (xanax_level / 100.0) * 90.0 * sim_hours)

    oxy_level = s.substances.get("oxytocin", {}).get("level", 0.0)
    if oxy_level > 20:
        s.chemicals["cortisol"] = clamp_chemical("cortisol",
            s.chemicals.get("cortisol", 250.0) - (oxy_level / 100.0) * 24.0 * sim_hours)

    add_level = s.substances.get("adderall", {}).get("level", 0.0)
    if add_level > 20:
        s.chemicals["dopamine"] = clamp_chemical("dopamine",
            s.chemicals.get("dopamine", 80.0) + (add_level / 100.0) * 6.0 * sim_hours)
        s.chemicals["norepinephrine"] = clamp_chemical("norepinephrine",
            s.chemicals.get("norepinephrine", 200.0) + (add_level / 100.0) * 39.0 * sim_hours)

    # --- Encoder momentum decay ---
    s = _decay_encoder_momentum(s, now)

    # --- Tolerance decay ---
    for substance in list(s.tolerance.keys()):
        s.tolerance[substance] = max(0.0, s.tolerance[substance] - 0.01 * sim_hours)
        if s.tolerance[substance] == 0.0:
            del s.tolerance[substance]

    # --- Phase 4: sleep/wake mechanics ---
    # TODO SPEC-21/SPEC-24: extract to physio/circadian.py

    sleep_p = s.chemicals.get("sleep_pressure", 30.0)
    if s.sleeping:
        sleep_p = _clamp(sleep_p - 24.0 * sim_hours, 0.0, 100.0)
        s.chemicals["sleep_pressure"] = sleep_p

        scheduled_wake = s.sleep_expected_wake and now >= s.sleep_expected_wake
        pressure_depleted = sleep_p <= 0
        if scheduled_wake or pressure_depleted:
            s.sleeping = False
            s.sleep_start = None
            s.sleep_expected_wake = None
            # Morning cortisol surge
            ctx_wake = _make_context(s, hour_of_day)
            baseline_cort = (REGISTRY["cortisol"].baseline_fn(hour_of_day, ctx_wake)
                             if REGISTRY["cortisol"].baseline_fn else 250.0)
            s.chemicals["cortisol"] = clamp_chemical("cortisol",
                baseline_cort + random.uniform(40, 120))
            s.chemicals["melatonin"] = clamp_chemical("melatonin",
                REGISTRY["melatonin"].baseline_fn(hour_of_day, ctx_wake)
                if REGISTRY["melatonin"].baseline_fn else 5.0)
            s.chemicals["endorphins"] = clamp_chemical("endorphins",
                s.chemicals.get("endorphins", 12.0) + random.uniform(3, 12))
    else:
        s.chemicals["sleep_pressure"] = _clamp(sleep_p + 1.8 * sim_hours, 0.0, 100.0)

    # --- Auto-sleep onset ---
    if not s.sleeping and s.chemicals.get("melatonin", 0.0) >= 195.0:
        sleep_start_hour = float(cfg.get("sleep_window_start", 4))
        sleep_end_hour   = float(cfg.get("sleep_window_end", 8))
        in_window = sleep_start_hour <= hour_of_day < sleep_end_hour
        if in_window:
            s.sleeping = True
            s.sleep_start = now
            lt = time.localtime(now)
            wake = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                                int(sleep_end_hour), int((sleep_end_hour % 1) * 60), 0,
                                lt.tm_wday, lt.tm_yday, lt.tm_isdst))
            if wake <= now:
                wake += 86400
            s.sleep_expected_wake = wake
            try:
                from log import log
                log("SLEEP", f"Auto-onset at {time.strftime('%H:%M')} "
                    f"(melatonin={s.chemicals.get('melatonin', 0):.0f} pg/mL) — wake at "
                    f"{time.strftime('%H:%M', time.localtime(wake))}")
            except ImportError:
                pass

    s.last_updated = now
    return s
