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

def _circadian_cortisol_baseline(hour: float) -> float:
    """Peaks ~35 at 8am, troughs ~5 at 8pm."""
    return 20.0 + 15.0 * math.cos((hour - 8) * math.pi / 12)


def _circadian_melatonin(hour: float) -> float:
    """Peaks ~100 at 2am, troughs ~0 at 2pm."""
    return 50.0 * (1.0 + math.cos((hour - 2) * math.pi / 12))


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
    s.endorphins = _clamp(s.endorphins - 15.0 * sim_hours)

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
