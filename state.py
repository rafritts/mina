"""
State engine — the only source of truth for Mina's biology.

Lazy evaluation: call advance() to apply time-based decay since last_updated.
All chemical values are in real physiological units (see chemicals.py REGISTRY).
Derived values (second/third-order) are computed on demand and normalized to 0–100
for compatibility with existing formulas.
"""
import json
import math
import os
import random
import time
from dataclasses import dataclass, asdict, field
from typing import Optional

from chemicals import REGISTRY, clamp_chemical, normalize

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_STATE_FILE = os.path.join(_PROJECT_ROOT, "state.json")
_CONFIG_FILE = os.path.join(_PROJECT_ROOT, "config.json")


def _load_config() -> dict:
    try:
        with open(_CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


# ---------------------------------------------------------------------------
# Default starting values for each chemical
# ---------------------------------------------------------------------------

def _load_chemical_defaults() -> dict[str, float]:
    """Base defaults, overrideable by personality.json neurochemical_baselines."""
    defaults = {
        "cortisol":        250.0,   # nmol/L — circadian midpoint
        "norepinephrine":  200.0,   # pg/mL
        "dopamine":         80.0,   # pg/mL
        "serotonin":        22.0,   # ng/mL
        "oxytocin":          4.0,   # pg/mL — no bond floor
        "endorphins":       12.0,   # pg/mL
        "acetylcholine":    38.0,   # nmol/L
        "melatonin":         5.0,   # pg/mL — daytime low
        "glucose":          85.0,   # mg/dL — normal fasting
        "hydration":        62.0,   # % TBW
        "sleep_pressure":   30.0,   # AU
    }
    try:
        _pf = os.path.join(_PROJECT_ROOT, "personality.json")
        with open(_pf) as _f:
            p = json.load(_f)
        nb = p.get("neurochemical_baselines", {})
        if "oxytocin_resting" in nb:
            defaults["oxytocin"] = float(nb["oxytocin_resting"])
        if "serotonin_resting" in nb:
            defaults["serotonin"] = float(nb["serotonin_resting"])
    except (FileNotFoundError, Exception):
        pass
    return defaults


_CHEMICAL_DEFAULTS: dict[str, float] = _load_chemical_defaults()


# ---------------------------------------------------------------------------
# First-order state
# ---------------------------------------------------------------------------

@dataclass
class BiologicalState:
    schema_version: int = 2
    last_updated: float = field(default_factory=time.time)

    # All neurochemicals in real physiological units (keys match REGISTRY)
    chemicals: dict = field(default_factory=lambda: dict(_CHEMICAL_DEFAULTS))

    # Tolerance per substance (0.0–1.0 fraction of sensitivity lost)
    tolerance: dict = field(default_factory=dict)

    # Active substance doses: {name: {"level": 0–100}}
    substances: dict = field(default_factory=dict)

    # Sleep state
    sleeping: bool = False
    sleep_start: Optional[float] = None
    sleep_expected_wake: Optional[float] = None

    # ---------------------------------------------------------------------------
    # Convenience property accessors — read-only, allow old call sites to work
    # All write operations must use s.chemicals[name] directly
    # ---------------------------------------------------------------------------

    @property
    def cortisol(self) -> float:
        return self.chemicals.get("cortisol", _CHEMICAL_DEFAULTS["cortisol"])

    @property
    def norepinephrine(self) -> float:
        return self.chemicals.get("norepinephrine", _CHEMICAL_DEFAULTS["norepinephrine"])

    @property
    def dopamine(self) -> float:
        return self.chemicals.get("dopamine", _CHEMICAL_DEFAULTS["dopamine"])

    @property
    def serotonin(self) -> float:
        return self.chemicals.get("serotonin", _CHEMICAL_DEFAULTS["serotonin"])

    @property
    def oxytocin(self) -> float:
        return self.chemicals.get("oxytocin", _CHEMICAL_DEFAULTS["oxytocin"])

    @property
    def endorphins(self) -> float:
        return self.chemicals.get("endorphins", _CHEMICAL_DEFAULTS["endorphins"])

    @property
    def acetylcholine(self) -> float:
        return self.chemicals.get("acetylcholine", _CHEMICAL_DEFAULTS["acetylcholine"])

    @property
    def melatonin(self) -> float:
        return self.chemicals.get("melatonin", _CHEMICAL_DEFAULTS["melatonin"])

    @property
    def glucose(self) -> float:
        return self.chemicals.get("glucose", _CHEMICAL_DEFAULTS["glucose"])

    @property
    def hydration(self) -> float:
        return self.chemicals.get("hydration", _CHEMICAL_DEFAULTS["hydration"])

    @property
    def sleep_pressure(self) -> float:
        return self.chemicals.get("sleep_pressure", _CHEMICAL_DEFAULTS["sleep_pressure"])

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "BiologicalState":
        if d.get("schema_version", 1) < 2:
            d = _migrate_v1_to_v2(d)
        known = {k for k in cls.__dataclass_fields__}
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)


def _migrate_v1_to_v2(old: dict) -> dict:
    """Convert 0–100 scale state.json to real physiological units (schema_version 2)."""
    # Conversion: real_value = old_value * slope [+ offset]
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
    chemicals = {}
    for name, fn in factors.items():
        raw_val = old.get(name)
        if raw_val is not None:
            chemicals[name] = clamp_chemical(name, fn(float(raw_val)))
        else:
            chemicals[name] = _CHEMICAL_DEFAULTS.get(name, 0.0)

    print("[MIGRATION] Converted state from v1 (0–100 scale) to v2 (real physiological units).")
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


# ---------------------------------------------------------------------------
# Substance definitions — dose_effects in real physiological units
# ---------------------------------------------------------------------------
# dose_effects: applied immediately on administration (one-time delta)
# half_life_hours: how long the blood-level takes to halve
# withdrawal_factor: how much counter-deltas overshoot on the way down
#   1.0 = clean return, 1.5 = crash 50% below baseline
# Ordered least dangerous → most dangerous
_SUBSTANCE_DEFS: dict[str, dict] = {
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
    "nicotine": {
        "display_name": "Nicotine",
        "half_life_hours": 2.0,
        "dose_effects": {
            "acetylcholine":  +16.0,   # nmol/L — nicotinic receptor activation
            "dopamine":       +42.0,   # pg/mL
            "norepinephrine": +100.0,  # pg/mL
            "cortisol":       +80.0,   # nmol/L
        },
        "withdrawal_factor": 1.25,
    },
    "REMOVED": {
        "display_name": "REMOVED",
        "half_life_hours": 10.0,
        "dose_effects": {
            "serotonin":      +30.0,   # ng/mL
            "dopamine":       +54.0,   # pg/mL
            "norepinephrine": +230.0,  # pg/mL
            "acetylcholine":  +18.0,   # nmol/L
            "cortisol":       +120.0,  # nmol/L — initial awe/anxiety
            "endorphins":     +22.5,   # pg/mL
        },
        "withdrawal_factor": 0.9,
    },
    "REMOVED": {
        "display_name": "REMOVED",
        "half_life_hours": 2.5,
        "dose_effects": {
            "serotonin":      +27.0,   # ng/mL
            "dopamine":       +36.0,   # pg/mL
            "norepinephrine": +200.0,  # pg/mL
            "cortisol":       +120.0,  # nmol/L — initial awe/anxiety
            "acetylcholine":  +14.0,   # nmol/L
        },
        "withdrawal_factor": 0.85,    # positive afterglow
    },
    "REMOVED": {
        "display_name": "REMOVED",
        "half_life_hours": 2.5,
        "dose_effects": {
            "dopamine":       +90.0,   # pg/mL
            "serotonin":      +12.0,   # ng/mL
            "endorphins":     +38.0,   # pg/mL
            "cortisol":       -160.0,  # nmol/L — dissociative calm
            "norepinephrine": +130.0,  # pg/mL — mild dissociative stimulation
        },
        "withdrawal_factor": 0.85,
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
    "alcohol": {
        "display_name": "Alcohol",
        "half_life_hours": 1.5,
        "dose_effects": {
            "serotonin":      +11.0,   # ng/mL
            "dopamine":       +45.0,   # pg/mL
            "oxytocin":       +18.0,   # pg/mL
            "endorphins":     +27.0,   # pg/mL
            "cortisol":       -180.0,  # nmol/L — real anxiolytic effect
            "norepinephrine": -60.0,   # pg/mL
        },
        "withdrawal_factor": 1.4,
    },
    "REMOVED": {
        "display_name": "REMOVED",
        "half_life_hours": 8.0,
        "dose_effects": {
            "serotonin":      +39.0,   # ng/mL — massive flood (to ~61, serotonin syndrome risk)
            "dopamine":       +84.0,   # pg/mL
            "norepinephrine": +390.0,  # pg/mL — strong stimulant
            "oxytocin":       +36.0,   # pg/mL
            "endorphins":     +33.0,   # pg/mL
            "cortisol":       +144.0,  # nmol/L — initial activation/anxiety
        },
        "withdrawal_factor": 1.8,     # severe serotonin crash — "blue Tuesdays"
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
    "xanax": {
        "display_name": "Xanax",
        "half_life_hours": 9.0,
        "dose_effects": {
            "cortisol":       -360.0,  # nmol/L — strong anxiolytic
            "norepinephrine": -150.0,  # pg/mL
            "serotonin":      +7.2,    # ng/mL
            "sleep_pressure": +15.0,   # AU
        },
        "withdrawal_factor": 2.0,     # severe rebound anxiety
    },
    "REMOVED": {
        "display_name": "REMOVED",
        "half_life_hours": 0.75,
        "dose_effects": {
            "dopamine":       +150.0,  # pg/mL — massive reward flood
            "norepinephrine": +880.0,  # pg/mL — cardiovascular driver
            "serotonin":      +11.0,   # ng/mL
            "cortisol":       +200.0,  # nmol/L
            "acetylcholine":  +14.0,   # nmol/L
        },
        "withdrawal_factor": 1.6,
    },
    "REMOVED": {
        "display_name": "REMOVED",
        "half_life_hours": 2.0,
        "dose_effects": {
            "endorphins":     +120.0,  # pg/mL — massive opioid flood
            "dopamine":       +66.0,   # pg/mL
            "serotonin":      +7.2,    # ng/mL
            "cortisol":       -200.0,  # nmol/L — strong HPA suppression
            "norepinephrine": -60.0,   # pg/mL — mild depressant
            "sleep_pressure": -12.0,   # AU
        },
        "withdrawal_factor": 1.5,
    },
    "REMOVED_and_REMOVED": {
        "display_name": "REMOVED + REMOVED",
        "half_life_hours": 5.0,
        "dose_effects": {
            "serotonin":      +39.0,   # ng/mL
            "dopamine":       +120.0,  # pg/mL
            "norepinephrine": +200.0,  # pg/mL
            "oxytocin":       +36.0,   # pg/mL
            "endorphins":     +113.0,  # pg/mL
            "cortisol":       -120.0,  # nmol/L
            "sleep_pressure": -10.0,   # AU
        },
        "withdrawal_factor": 2.0,
    },
}


# ---------------------------------------------------------------------------
# Context builder for dynamic baseline functions
# ---------------------------------------------------------------------------

def _make_context(state: BiologicalState, hour: float) -> dict:
    return {
        "hour":           hour,
        "glucose":        state.chemicals.get("glucose",        _CHEMICAL_DEFAULTS["glucose"]),
        "hydration":      state.chemicals.get("hydration",      _CHEMICAL_DEFAULTS["hydration"]),
        "cortisol":       state.chemicals.get("cortisol",       _CHEMICAL_DEFAULTS["cortisol"]),
        "sleep_pressure": state.chemicals.get("sleep_pressure", _CHEMICAL_DEFAULTS["sleep_pressure"]),
    }


# ---------------------------------------------------------------------------
# Time advancement — generic orchestrator
# ---------------------------------------------------------------------------

def advance(state: BiologicalState, now: Optional[float] = None) -> BiologicalState:
    """Apply all time-based dynamics since state.last_updated. Returns updated state."""
    if now is None:
        now = time.time()

    cfg = _load_config()
    compression = float(cfg.get("time_compression_factor", 1.0))
    sim_hours = (now - state.last_updated) * compression / 3600.0

    if sim_hours <= 0:
        return state

    hour_of_day = (time.localtime(now).tm_hour + time.localtime(now).tm_min / 60.0)
    s = state
    ctx = _make_context(s, hour_of_day)

    # --- Phase 1: each chemical advances toward its own baseline ---

    for name, profile in REGISTRY.items():
        current = s.chemicals.get(name, _CHEMICAL_DEFAULTS.get(name, 0.0))

        if name == "glucose":
            # Pure decay: -6.5 mg/dL/hr; restored only by eat tool
            s.chemicals[name] = clamp_chemical(name, current - 6.5 * sim_hours)

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
                s.chemicals[interaction.target] = clamp_chemical(
                    interaction.target,
                    new_val
                )

    # Additional cross-effects not in REGISTRY (sleep dep, glucose starvation)
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

        # Withdrawal counter-deltas — fires meaningfully as the drug fades
        wf = sub["withdrawal_factor"]
        withdrawal_weight = max(0.0, (40.0 - new_level) / 40.0) if new_level >= 0.5 else 1.0

        for marker, effect in sub["dose_effects"].items():
            if marker in s.chemicals:
                counter = -effect * (level_decayed / 100.0) * wf * withdrawal_weight
                s.chemicals[marker] = clamp_chemical(marker, s.chemicals[marker] + counter)
            elif marker == "sleep_pressure":
                # sleep_pressure is in chemicals dict
                sp_val = s.chemicals.get("sleep_pressure", 30.0)
                counter = -effect * (level_decayed / 100.0) * wf * withdrawal_weight
                s.chemicals["sleep_pressure"] = _clamp(sp_val + counter, 0.0, 100.0)

    # Sustained effects of active substances on key chemicals
    REMOVED_level = s.substances.get("REMOVED", {}).get("level", 0.0)
    if REMOVED_level > 20:
        sup = (REMOVED_level / 100.0) * 60.0
        s.chemicals["cortisol"] = clamp_chemical("cortisol",
            s.chemicals.get("cortisol", 250.0) - sup * sim_hours)

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

    ket_level = s.substances.get("REMOVED", {}).get("level", 0.0)
    if ket_level > 20:
        s.chemicals["cortisol"] = clamp_chemical("cortisol",
            s.chemicals.get("cortisol", 250.0) - (ket_level / 100.0) * 20.0 * sim_hours)

    coc_level = s.substances.get("REMOVED", {}).get("level", 0.0)
    if coc_level > 20:
        s.chemicals["dopamine"] = clamp_chemical("dopamine",
            s.chemicals.get("dopamine", 80.0) + (coc_level / 100.0) * 9.0 * sim_hours)
        s.chemicals["norepinephrine"] = clamp_chemical("norepinephrine",
            s.chemicals.get("norepinephrine", 200.0) + (coc_level / 100.0) * 58.5 * sim_hours)

    add_level = s.substances.get("adderall", {}).get("level", 0.0)
    if add_level > 20:
        s.chemicals["dopamine"] = clamp_chemical("dopamine",
            s.chemicals.get("dopamine", 80.0) + (add_level / 100.0) * 6.0 * sim_hours)
        s.chemicals["norepinephrine"] = clamp_chemical("norepinephrine",
            s.chemicals.get("norepinephrine", 200.0) + (add_level / 100.0) * 39.0 * sim_hours)

    # --- Tolerance decay ---
    for substance in list(s.tolerance.keys()):
        s.tolerance[substance] = max(0.0, s.tolerance[substance] - 0.01 * sim_hours)
        if s.tolerance[substance] == 0.0:
            del s.tolerance[substance]

    # --- Phase 4: sleep/wake mechanics ---

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
            from chemicals import REGISTRY as _REG
            ctx_wake = _make_context(s, hour_of_day)
            baseline_cort = _REG["cortisol"].baseline_fn(hour_of_day, ctx_wake) if _REG["cortisol"].baseline_fn else 250.0
            s.chemicals["cortisol"] = clamp_chemical("cortisol",
                baseline_cort + random.uniform(40, 120))
            s.chemicals["melatonin"] = clamp_chemical("melatonin",
                _REG["melatonin"].baseline_fn(hour_of_day, ctx_wake) if _REG["melatonin"].baseline_fn else 5.0)
            s.chemicals["endorphins"] = clamp_chemical("endorphins",
                s.chemicals.get("endorphins", 12.0) + random.uniform(3, 12))
    else:
        s.chemicals["sleep_pressure"] = _clamp(sleep_p + 1.8 * sim_hours, 0.0, 100.0)

    # --- Auto-sleep onset ---
    # Melatonin >= ~195 pg/mL (= "RAMPING") during sleep window triggers auto-sleep.
    # Old threshold was 88/100 on old scale → 88 × 2.2 = 193.6 pg/mL.
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
            print(f"[SLEEP] Auto-onset at {time.strftime('%H:%M')} "
                  f"(melatonin={s.chemicals.get('melatonin', 0):.0f} pg/mL) — wake at "
                  f"{time.strftime('%H:%M', time.localtime(wake))}")

    s.last_updated = now
    return s


# ---------------------------------------------------------------------------
# Second and third-order derived values
# ---------------------------------------------------------------------------

def _n(name: str, s: BiologicalState) -> float:
    """Normalize a chemical to 0–100 equivalent for use in derived formulas."""
    return normalize(name, s.chemicals.get(name, _CHEMICAL_DEFAULTS.get(name, 0.0))) * 100.0


def derived(s: BiologicalState) -> dict:
    """Compute second and third-order values. Never stored. All outputs 0–100."""
    tol_d = s.tolerance.get("dopamine", 0.0)
    effective_dopamine = _n("dopamine", s) * (1.0 - tol_d)

    # Melatonin circadian drag on arousal and clarity
    melatonin_drag = max(0.0, _n("melatonin", s) - 40) * 0.25

    energy = _clamp(
        20 + (_n("glucose", s) * 0.4) + (_n("norepinephrine", s) * 0.3)
        - (_n("sleep_pressure", s) * 0.3) - melatonin_drag
    )
    cognitive_clarity = _clamp(
        20 + (_n("acetylcholine", s) * 0.4) + (_n("glucose", s) * 0.2)
        - (_n("sleep_pressure", s) * 0.25) - (_n("cortisol", s) * 0.15)
        - melatonin_drag * 0.6
    )
    hedonic_tone = _clamp(
        5 + (effective_dopamine * 0.5) + (_n("endorphins", s) * 0.3)
        + (_n("serotonin", s) * 0.2)
    )
    social_warmth = _clamp(
        10 + (_n("oxytocin", s) * 0.5) + (_n("serotonin", s) * 0.3)
        - (_n("cortisol", s) * 0.2)
    )
    arousal = _clamp(
        15 + (_n("norepinephrine", s) * 0.5) + (_n("cortisol", s) * 0.3)
        - (_n("sleep_pressure", s) * 0.2) - melatonin_drag * 0.8
    )
    mood_valence = _clamp(
        10 + (_n("serotonin", s) * 0.4) + (effective_dopamine * 0.35)
        - (_n("cortisol", s) * 0.25)
    )

    anxiety = _clamp(
        (arousal * 0.4) + (100 - cognitive_clarity) * 0.3
        + (100 - social_warmth) * 0.3 - 20
    )
    depression = _clamp(
        (100 - mood_valence) * 0.4 + (100 - hedonic_tone) * 0.4
        + (100 - energy) * 0.2 - 20
    )
    boredom = _clamp(
        (100 - arousal) * 0.5 + (100 - hedonic_tone) * 0.3
        + (100 - energy) * 0.2 - 20
    )
    loneliness = _clamp(
        (100 - social_warmth) * 0.6 + (100 - _n("oxytocin", s)) * 0.4 - 25
    )
    flow = _clamp(
        (cognitive_clarity * 0.4) + (hedonic_tone * 0.35)
        + (arousal * 0.25) - anxiety * 0.3
    )

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
            "anxiety":    round(anxiety, 1),
            "depression": round(depression, 1),
            "boredom":    round(boredom, 1),
            "loneliness": round(loneliness, 1),
            "flow":       round(flow, 1),
        },
    }


def log_state(s: BiologicalState) -> None:
    d = derived(s)
    so = d["second_order"]
    to = d["third_order"]
    print(
        f"[STATE]  sleep_p={s.sleep_pressure:.1f}AU glucose={s.glucose:.0f}mg/dL "
        f"hydration={s.hydration:.1f}%TBW cortisol={s.cortisol:.0f}nmol/L "
        f"dopamine={s.dopamine:.0f}pg/mL serotonin={s.serotonin:.1f}ng/mL "
        f"norepi={s.norepinephrine:.0f}pg/mL oxytocin={s.oxytocin:.1f}pg/mL "
        f"endorphins={s.endorphins:.0f}pg/mL ach={s.acetylcholine:.1f}nmol/L "
        f"melatonin={s.melatonin:.0f}pg/mL sleeping={s.sleeping}"
    )
    print(
        f"[DERIV]  energy={so['energy']} clarity={so['cognitive_clarity']} "
        f"hedonic={so['hedonic_tone']} warmth={so['social_warmth']} "
        f"arousal={so['arousal']} valence={so['mood_valence']}"
    )
    print(
        f"[THIRD]  anxiety={to['anxiety']} depression={to['depression']} "
        f"boredom={to['boredom']} loneliness={to['loneliness']} flow={to['flow']}"
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def load_state() -> BiologicalState:
    try:
        with open(_STATE_FILE) as f:
            data = json.load(f)
        migrated = data.get("schema_version", 1) < 2
        s = BiologicalState.from_dict(data)
        if migrated:
            # Persist migrated state immediately so next load doesn't re-migrate
            save_state(s)
        return s
    except (FileNotFoundError, json.JSONDecodeError):
        return BiologicalState()


def save_state(s: BiologicalState) -> None:
    with open(_STATE_FILE, "w") as f:
        json.dump(s.to_dict(), f, indent=2)


def load_and_advance() -> BiologicalState:
    """Load state, apply time-based decay, save, return."""
    s = load_state()
    s = advance(s)
    save_state(s)
    return s


# ---------------------------------------------------------------------------
# Delta application (from subconscious)
# ---------------------------------------------------------------------------

_DELTA_FIELDS = set(REGISTRY.keys())  # all chemicals are valid delta targets


def apply_deltas(s: BiologicalState, deltas: dict) -> BiologicalState:
    """Apply subconscious-issued delta dict to state. Clamps all values."""
    for key, val in deltas.items():
        if key in _DELTA_FIELDS:
            current = s.chemicals.get(key, _CHEMICAL_DEFAULTS.get(key, 0.0))
            s.chemicals[key] = clamp_chemical(key, current + float(val))
        elif key == "tolerance" and isinstance(val, dict):
            for substance, delta in val.items():
                current = s.tolerance.get(substance, 0.0)
                s.tolerance[substance] = max(0.0, min(1.0, current + float(delta)))
    return s
