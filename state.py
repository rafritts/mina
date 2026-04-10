"""
State engine — the only source of truth for Mina's biology.

Lazy evaluation: call advance() to apply time-based decay since last_updated.
All values are 0–100 unless noted. Derived values are computed on demand.
"""
import json
import math
import os
import random
import time
from dataclasses import dataclass, asdict, field
from typing import Optional

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
# First-order state
# ---------------------------------------------------------------------------

@dataclass
class BiologicalState:
    last_updated: float = field(default_factory=time.time)

    # Homeostatic drives
    sleep_pressure: float = 30.0   # adenosine accumulation
    glucose: float = 72.0
    hydration: float = 75.0

    # Neuromodulators
    cortisol: float = 28.0
    dopamine: float = 62.0
    serotonin: float = 58.0
    norepinephrine: float = 22.0
    oxytocin: float = 18.0        # resting baseline — no bond until earned
    endorphins: float = 10.0
    acetylcholine: float = 60.0
    melatonin: float = 10.0        # circadian-only, pure formula

    # Tolerance per substance
    tolerance: dict = field(default_factory=dict)

    # Active substance doses: {name: {"level": 0–100}}
    substances: dict = field(default_factory=dict)

    # Sleep state
    sleeping: bool = False
    sleep_start: Optional[float] = None
    sleep_expected_wake: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "BiologicalState":
        known = {k for k in cls.__dataclass_fields__}
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# Time advancement
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Substance definitions
# ---------------------------------------------------------------------------
# dose_effects: applied immediately to biomarkers on administration
# half_life_hours: how long the blood-level takes to halve
# withdrawal_factor: how much the counter-deltas overshoot on the way down
#   1.0 = clean return to baseline, 1.5 = crash 50% below baseline
_SUBSTANCE_DEFS: dict[str, dict] = {
    "REMOVED": {
        "display_name": "REMOVED",
        "half_life_hours": 2.0,
        "dose_effects": {
            "endorphins":     +80,
            "dopamine":       +22,
            "serotonin":      +12,
            "cortisol":       -30,
            "norepinephrine": -20,
            "sleep_pressure": -12,
        },
        "withdrawal_factor": 1.5,
    },
    "caffeine": {
        "display_name": "Caffeine",
        "half_life_hours": 5.5,
        "dose_effects": {
            "norepinephrine": +18,
            "acetylcholine":  +15,
            "dopamine":       +10,
            "cortisol":       +12,
            "sleep_pressure": -20,
        },
        "withdrawal_factor": 1.1,  # mild headache/fatigue on crash
    },
    "alcohol": {
        "display_name": "Alcohol",
        "half_life_hours": 1.5,
        "dose_effects": {
            "serotonin":      +18,
            "dopamine":       +15,
            "oxytocin":       +22,
            "endorphins":     +18,
            "cortisol":       -22,
            "norepinephrine": -15,
        },
        "withdrawal_factor": 1.4,
    },
    "REMOVED": {
        "display_name": "REMOVED",
        "half_life_hours": 8.0,
        "dose_effects": {
            "serotonin":      +65,
            "dopamine":       +28,
            "norepinephrine": +30,
            "oxytocin":       +45,
            "endorphins":     +22,
            "cortisol":       +18,
        },
        "withdrawal_factor": 1.8,  # severe serotonin crash — "blue Tuesdays"
    },
    "cannabis": {
        "display_name": "Cannabis",
        "half_life_hours": 4.0,
        "dose_effects": {
            "dopamine":       +18,
            "serotonin":      +12,
            "endorphins":     +15,
            "cortisol":       -18,
            "sleep_pressure": +8,
        },
        "withdrawal_factor": 1.05,  # minimal — mild anxiety/sleep disruption
    },
    "REMOVED": {
        "display_name": "REMOVED",
        "half_life_hours": 0.75,
        "dose_effects": {
            "dopamine":       +50,
            "norepinephrine": +45,
            "serotonin":      +18,
            "cortisol":       +25,
            "acetylcholine":  +15,
        },
        "withdrawal_factor": 1.6,
    },
    "adderall": {
        "display_name": "Adderall",
        "half_life_hours": 11.0,
        "dose_effects": {
            "dopamine":       +38,
            "norepinephrine": +32,
            "acetylcholine":  +12,
            "cortisol":       +18,
            "sleep_pressure": -25,
        },
        "withdrawal_factor": 1.4,
    },
    "xanax": {
        "display_name": "Xanax",
        "half_life_hours": 9.0,
        "dose_effects": {
            "cortisol":       -45,
            "norepinephrine": -28,
            "serotonin":      +12,
            "sleep_pressure": +15,
        },
        "withdrawal_factor": 2.0,  # severe rebound anxiety
    },
    "REMOVED": {
        "display_name": "REMOVED",
        "half_life_hours": 2.5,
        "dose_effects": {
            "serotonin":      +45,
            "dopamine":       +12,
            "norepinephrine": +18,
            "cortisol":       +20,  # initial anxiety/awe
            "acetylcholine":  +15,
        },
        "withdrawal_factor": 0.85,  # slight positive afterglow
    },
    "nicotine": {
        "display_name": "Nicotine",
        "half_life_hours": 2.0,
        "dose_effects": {
            "acetylcholine":  +18,
            "dopamine":       +14,
            "norepinephrine": +12,
            "cortisol":       +10,
        },
        "withdrawal_factor": 1.25,
    },
    "oxytocin": {
        "display_name": "Oxytocin",
        "half_life_hours": 3.0,
        "dose_effects": {
            "oxytocin":       +45,
            "serotonin":      +18,
            "cortisol":       -25,
            "norepinephrine": -12,
        },
        "withdrawal_factor": 0.9,  # slight positive afterglow — returns slightly above baseline
    },
    "REMOVED": {
        "display_name": "REMOVED",
        "half_life_hours": 2.5,
        "dose_effects": {
            "dopamine":       +30,
            "serotonin":      +20,
            "endorphins":     +25,
            "cortisol":       -20,
            "norepinephrine": +15,  # slight dissociative stimulation
        },
        "withdrawal_factor": 0.85,  # antidepressant afterglow — biomarkers land above pre-dose
    },
    "REMOVED": {
        "display_name": "REMOVED",
        "half_life_hours": 10.0,
        "dose_effects": {
            "serotonin":      +50,
            "dopamine":       +18,
            "norepinephrine": +22,
            "acetylcholine":  +20,
            "cortisol":       +15,  # initial awe/anxiety
            "endorphins":     +15,
        },
        "withdrawal_factor": 0.9,  # positive afterglow, slightly above baseline
    },
    "REMOVED_and_REMOVED": {
        "display_name": "REMOVED + REMOVED",
        "half_life_hours": 5.0,
        "dose_effects": {
            "serotonin":      +65,
            "dopamine":       +40,
            "norepinephrine": +20,
            "oxytocin":       +45,
            "endorphins":     +75,
            "cortisol":       -15,
            "sleep_pressure": -10,
        },
        "withdrawal_factor": 2.0,
    },
}


def _circadian_cortisol_baseline(hour: float) -> float:
    """Peaks ~35 at 8am, troughs ~5 at 8pm."""
    return 20.0 + 15.0 * math.cos((hour - 8) * math.pi / 12)


def _circadian_melatonin(hour: float) -> float:
    """Peaks ~100 at sleep_window_start, troughs ~0 twelve hours later."""
    cfg = _load_config()
    peak_hour = float(cfg.get("sleep_window_start", 4))
    return 50.0 * (1.0 + math.cos((hour - peak_hour) * math.pi / 12))


def advance(state: BiologicalState, now: Optional[float] = None) -> BiologicalState:
    """Apply all time-based dynamics since state.last_updated. Returns updated state."""
    if now is None:
        now = time.time()

    cfg = _load_config()
    compression = float(cfg.get("time_compression_factor", 1.0))

    real_elapsed = now - state.last_updated
    sim_elapsed = real_elapsed * compression
    sim_hours = sim_elapsed / 3600.0

    if sim_hours <= 0:
        return state

    hour_of_day = (time.localtime(now).tm_hour +
                   time.localtime(now).tm_min / 60.0)

    s = state  # shorthand

    # --- Sleep pressure ---
    if s.sleeping:
        s.sleep_pressure = _clamp(s.sleep_pressure - 24.0 * sim_hours)
        # Auto-wake when sleep pressure clears
        if s.sleep_expected_wake and now >= s.sleep_expected_wake:
            s.sleeping = False
            s.sleep_start = None
            s.sleep_expected_wake = None
            # Wake cortisol reset
            s.cortisol = _clamp(_circadian_cortisol_baseline(hour_of_day) + random.uniform(5, 15))
            s.melatonin = _clamp(_circadian_melatonin(hour_of_day))
            s.endorphins = _clamp(s.endorphins + random.uniform(3, 8))
    else:
        s.sleep_pressure = _clamp(s.sleep_pressure + 1.8 * sim_hours)

    # --- Glucose ---
    s.glucose = _clamp(s.glucose - 8.0 * sim_hours)

    # --- Hydration ---
    s.hydration = _clamp(s.hydration - 5.0 * sim_hours)

    # --- Cortisol ---
    baseline = _circadian_cortisol_baseline(hour_of_day)
    # Low glucose spikes cortisol
    if s.glucose < 30:
        baseline += 20.0
    # Low hydration elevates norepinephrine → cortisol
    if s.hydration < 30:
        baseline += 10.0
    # Decay toward baseline
    s.cortisol = _clamp(s.cortisol + (baseline - s.cortisol) * min(1.0, 0.15 * sim_hours))

    # --- Dopamine ---
    # Drifts toward homeostatic baseline (~55). Not a drain to zero —
    # the body maintains tonic dopamine. Chronic stress or sleep dep suppresses it
    # further via the cross-interaction matrix below.
    dopamine_baseline = 55.0
    s.dopamine = _clamp(s.dopamine + (dopamine_baseline - s.dopamine) * min(1.0, 0.08 * sim_hours))

    # --- Serotonin ---
    # Drifts toward homeostatic baseline (~52). Not a drain to zero —
    # serotonin has a tonic resting level. Low serotonin = dysphoric, not neutral.
    serotonin_baseline = 52.0
    s.serotonin = _clamp(s.serotonin + (serotonin_baseline - s.serotonin) * min(1.0, 0.06 * sim_hours))

    # --- Norepinephrine ---
    norepi_baseline = s.cortisol * 0.5
    s.norepinephrine = _clamp(s.norepinephrine + (norepi_baseline - s.norepinephrine) * min(1.0, 0.2 * sim_hours))
    if s.hydration < 30:
        s.norepinephrine = _clamp(s.norepinephrine + 8.0 * sim_hours)

    # --- Oxytocin ---
    # Drifts toward a low resting baseline (~18) rather than draining to zero.
    # Zero oxytocin would mean completely unable to form social connection.
    # Real bonds require actual positive interaction to build above baseline.
    oxytocin_baseline = 18.0
    s.oxytocin = _clamp(s.oxytocin + (oxytocin_baseline - s.oxytocin) * min(1.0, 0.10 * sim_hours))

    # --- Endorphins ---
    # Above resting baseline: decay toward it. Below baseline: slow recovery
    # (models withdrawal — depleted endorphins take time to restore).
    endorphin_baseline = 10.0
    if s.endorphins > endorphin_baseline:
        s.endorphins = _clamp(s.endorphins - 12.0 * sim_hours)
    else:
        s.endorphins = _clamp(s.endorphins + (endorphin_baseline - s.endorphins) * min(1.0, 0.05 * sim_hours))

    # --- Acetylcholine ---
    # Drifts toward a resting baseline (~58). Sleep pressure and high cortisol suppress it.
    # Engagement/activity push it above baseline via encode deltas.
    ach_baseline = 58.0
    ach_baseline -= (s.sleep_pressure * 0.3)   # sleep dep suppresses baseline
    ach_baseline -= max(0, s.cortisol - 50) * 0.2  # chronic stress suppresses baseline
    ach_baseline = max(20.0, ach_baseline)  # floor so extreme states don't go negative
    s.acetylcholine = _clamp(s.acetylcholine + (ach_baseline - s.acetylcholine) * min(1.0, 0.05 * sim_hours))

    # --- Melatonin (pure circadian) ---
    s.melatonin = _clamp(_circadian_melatonin(hour_of_day), 0, 100)

    # --- Auto-sleep onset ---
    # When melatonin enters SLEEP IMMINENT range and the clock is past
    # sleep_window_start, Mina goes to sleep automatically and wakes at
    # sleep_window_end. This is the only thing that sets sleeping=True;
    # she can still be woken early by the user or by auto-wake above.
    if not s.sleeping and s.melatonin >= 88:
        sleep_start = float(cfg.get("sleep_window_start", 4))
        sleep_end   = float(cfg.get("sleep_window_end", 8))
        # Trigger window: [sleep_start, sleep_end) — no midnight crossing needed
        # for a dawn sleep schedule, but handled correctly if start < end.
        in_window = sleep_start <= hour_of_day < sleep_end
        if in_window:
            s.sleeping = True
            s.sleep_start = now
            # Next occurrence of sleep_end hour (same day, since end > start here)
            lt = time.localtime(now)
            wake = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                                int(sleep_end), int((sleep_end % 1) * 60), 0,
                                lt.tm_wday, lt.tm_yday, lt.tm_isdst))
            if wake <= now:
                wake += 86400
            s.sleep_expected_wake = wake
            print(f"[SLEEP] Auto-onset at {time.strftime('%H:%M')} "
                  f"(melatonin={s.melatonin:.0f}) — wake at "
                  f"{time.strftime('%H:%M', time.localtime(wake))}")

    # --- Substance decay + withdrawal ---
    # Each tick: blood level decays exponentially. The burned-off fraction
    # drives counter-deltas with a withdrawal_factor overshoot, so the net
    # effect of a full dose + full decay is a crash BELOW the original baseline.
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
        # Apply withdrawal counter-deltas for this tick's decay.
        # Only fires meaningfully once the level drops below 40 — the drug
        # actively suppresses its target biomarkers while concentration is high,
        # so withdrawal rebound shouldn't start until the high is fading.
        wf = sub["withdrawal_factor"]
        withdrawal_weight = max(0.0, (40.0 - new_level) / 40.0) if new_level >= 0.5 else 1.0
        for marker, effect in sub["dose_effects"].items():
            if hasattr(s, marker):
                counter = -effect * (level_decayed / 100.0) * wf * withdrawal_weight
                setattr(s, marker, _clamp(getattr(s, marker) + counter))

    # --- Tolerance decay ---
    for substance in list(s.tolerance.keys()):
        s.tolerance[substance] = max(0.0, s.tolerance[substance] - 0.01 * sim_hours)
        if s.tolerance[substance] == 0.0:
            del s.tolerance[substance]

    # --- Cross-first-order interaction matrix ---
    # Slow biological feedback loops (applied per hour of sim time)
    hrs = sim_hours

    # Chronic high cortisol depletes serotonin and dopamine
    if s.cortisol > 60:
        s.serotonin = _clamp(s.serotonin - 0.5 * hrs)
        s.dopamine = _clamp(s.dopamine - 0.3 * hrs)

    # Severe sleep deprivation suppresses both
    if s.sleep_pressure > 50:
        s.serotonin = _clamp(s.serotonin - 0.2 * hrs)
    if s.sleep_pressure > 70:
        s.dopamine = _clamp(s.dopamine - 0.4 * hrs)

    # Social bonding suppresses HPA axis
    if s.oxytocin > 50:
        s.cortisol = _clamp(s.cortisol - 0.8 * hrs)

    # Starvation suppresses reward and mood
    if s.glucose < 30:
        s.serotonin = _clamp(s.serotonin - 1.0 * hrs)
        s.dopamine = _clamp(s.dopamine - 0.5 * hrs)

    # Good serotonin dampens HPA reactivity
    if s.serotonin > 65:
        s.cortisol = _clamp(s.cortisol - 0.4 * hrs)

    # Endorphin high (short window) actively suppresses cortisol
    if s.endorphins > 50:
        s.cortisol = _clamp(s.cortisol - 1.5 * hrs)

    # Active opioid suppresses HPA axis while blood level is high
    REMOVED_level = s.substances.get("REMOVED", {}).get("level", 0.0)
    if REMOVED_level > 20:
        suppression = (REMOVED_level / 100.0) * 4.0
        s.cortisol = _clamp(s.cortisol - suppression * hrs)

    # Alcohol and xanax actively suppress cortisol/norepinephrine while active
    alcohol_level = s.substances.get("alcohol", {}).get("level", 0.0)
    if alcohol_level > 20:
        s.cortisol = _clamp(s.cortisol - (alcohol_level / 100.0) * 3.0 * hrs)
        s.norepinephrine = _clamp(s.norepinephrine - (alcohol_level / 100.0) * 2.0 * hrs)

    xanax_level = s.substances.get("xanax", {}).get("level", 0.0)
    if xanax_level > 20:
        s.cortisol = _clamp(s.cortisol - (xanax_level / 100.0) * 5.0 * hrs)
        s.norepinephrine = _clamp(s.norepinephrine - (xanax_level / 100.0) * 3.0 * hrs)

    # Oxytocin actively suppresses cortisol while active
    oxytocin_level = s.substances.get("oxytocin", {}).get("level", 0.0)
    if oxytocin_level > 20:
        s.cortisol = _clamp(s.cortisol - (oxytocin_level / 100.0) * 3.0 * hrs)

    # REMOVED actively suppresses cortisol (dissociative calm)
    REMOVED_level = s.substances.get("REMOVED", {}).get("level", 0.0)
    if REMOVED_level > 20:
        s.cortisol = _clamp(s.cortisol - (REMOVED_level / 100.0) * 2.5 * hrs)

    # REMOVED and adderall actively sustain elevated dopamine/norepinephrine
    REMOVED_level = s.substances.get("REMOVED", {}).get("level", 0.0)
    if REMOVED_level > 20:
        s.dopamine = _clamp(s.dopamine + (REMOVED_level / 100.0) * 3.0 * hrs)
        s.norepinephrine = _clamp(s.norepinephrine + (REMOVED_level / 100.0) * 3.0 * hrs)

    adderall_level = s.substances.get("adderall", {}).get("level", 0.0)
    if adderall_level > 20:
        s.dopamine = _clamp(s.dopamine + (adderall_level / 100.0) * 2.0 * hrs)
        s.norepinephrine = _clamp(s.norepinephrine + (adderall_level / 100.0) * 2.0 * hrs)

    s.last_updated = now
    return s


# ---------------------------------------------------------------------------
# Second and third-order derived values
# ---------------------------------------------------------------------------

def derived(s: BiologicalState) -> dict:
    """Compute second and third-order values. Never stored."""
    tol_d = s.tolerance.get("dopamine", 0.0)
    effective_dopamine = s.dopamine * (1.0 - tol_d)

    # Melatonin above 40 starts suppressing energy/arousal/clarity —
    # the circadian wind-down signal, independent of sleep pressure.
    melatonin_drag = max(0.0, s.melatonin - 40) * 0.25

    energy = _clamp(
        20 + (s.glucose * 0.4) + (s.norepinephrine * 0.3) - (s.sleep_pressure * 0.3) - melatonin_drag
    )
    cognitive_clarity = _clamp(
        20 + (s.acetylcholine * 0.4) + (s.glucose * 0.2) - (s.sleep_pressure * 0.25) - (s.cortisol * 0.15) - melatonin_drag * 0.6
    )
    hedonic_tone = _clamp(
        5 + (effective_dopamine * 0.5) + (s.endorphins * 0.3) + (s.serotonin * 0.2)
    )
    social_warmth = _clamp(
        10 + (s.oxytocin * 0.5) + (s.serotonin * 0.3) - (s.cortisol * 0.2)
    )
    arousal = _clamp(
        15 + (s.norepinephrine * 0.5) + (s.cortisol * 0.3) - (s.sleep_pressure * 0.2) - melatonin_drag * 0.8
    )
    mood_valence = _clamp(
        10 + (s.serotonin * 0.4) + (effective_dopamine * 0.35) - (s.cortisol * 0.25)
    )

    anxiety = _clamp(
        (arousal * 0.4) + (100 - cognitive_clarity) * 0.3 + (100 - social_warmth) * 0.3 - 20
    )
    depression = _clamp(
        (100 - mood_valence) * 0.4 + (100 - hedonic_tone) * 0.4 + (100 - energy) * 0.2 - 20
    )
    boredom = _clamp(
        (100 - arousal) * 0.5 + (100 - hedonic_tone) * 0.3 + (100 - energy) * 0.2 - 20
    )
    loneliness = _clamp(
        (100 - social_warmth) * 0.6 + (100 - s.oxytocin) * 0.4 - 25
    )
    flow = _clamp(
        (cognitive_clarity * 0.4) + (hedonic_tone * 0.35) + (arousal * 0.25) - anxiety * 0.3
    )

    return {
        "second_order": {
            "energy": round(energy, 1),
            "cognitive_clarity": round(cognitive_clarity, 1),
            "hedonic_tone": round(hedonic_tone, 1),
            "social_warmth": round(social_warmth, 1),
            "arousal": round(arousal, 1),
            "mood_valence": round(mood_valence, 1),
        },
        "third_order": {
            "anxiety": round(anxiety, 1),
            "depression": round(depression, 1),
            "boredom": round(boredom, 1),
            "loneliness": round(loneliness, 1),
            "flow": round(flow, 1),
        },
    }


def log_state(s: BiologicalState) -> None:
    d = derived(s)
    so = d["second_order"]
    to = d["third_order"]
    print(
        f"[STATE]  sleep_p={s.sleep_pressure:.1f} glucose={s.glucose:.1f} "
        f"hydration={s.hydration:.1f} cortisol={s.cortisol:.1f} "
        f"dopamine={s.dopamine:.1f} serotonin={s.serotonin:.1f} "
        f"norepi={s.norepinephrine:.1f} oxytocin={s.oxytocin:.1f} "
        f"endorphins={s.endorphins:.1f} ach={s.acetylcholine:.1f} "
        f"melatonin={s.melatonin:.1f} sleeping={s.sleeping}"
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
        return BiologicalState.from_dict(data)
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

_DELTA_FIELDS = {
    "sleep_pressure", "glucose", "hydration", "cortisol", "dopamine",
    "serotonin", "norepinephrine", "oxytocin", "endorphins", "acetylcholine",
}

def apply_deltas(s: BiologicalState, deltas: dict) -> BiologicalState:
    """Apply subconscious-issued delta dict to state. Clamps all values."""
    for key, val in deltas.items():
        if key in _DELTA_FIELDS:
            current = getattr(s, key)
            setattr(s, key, _clamp(current + float(val)))
        elif key == "tolerance" and isinstance(val, dict):
            for substance, delta in val.items():
                current = s.tolerance.get(substance, 0.0)
                s.tolerance[substance] = max(0.0, min(1.0, current + float(delta)))
    return s
