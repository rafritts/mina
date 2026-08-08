"""
SPEC-63 Phase 3 — display labels tell the truth about the sim.

Baseline chips must not look like a psychiatric emergency; OT resting ≠ NO BOND;
adenosine bands align with auto-sleep thresholds.
"""
from __future__ import annotations

from src.sim.labels import label_for, annotate_chemical
from src.sim.params import CHEMICAL_PARAMS
from src.sim.tick import build_initial_state
from src.gateway.server import _build_state
from src.sim.sim import Sim
import threading


BIG5 = {
    "openness": 72.0,
    "conscientiousness": 55.0,
    "extraversion": 48.0,
    "agreeableness": 68.0,
    "neuroticism": 65.0,
}


def _fresh_sim() -> Sim:
    sim = Sim.__new__(Sim)
    sim._state = build_initial_state(BIG5)
    sim._big5 = dict(BIG5)
    sim._lock = threading.Lock()
    sim._sleeping = False
    sim._sleep_elapsed_s = 0.0
    sim._stop_event = threading.Event()
    sim._thread = None
    sim._observer = None
    return sim


# ── Acceptance A: factory baseline ───────────────────────────────────────────


def test_baseline_labels_not_crashed():
    state = build_initial_state(BIG5)
    for name in ("dopamine", "serotonin", "norepinephrine", "oxytocin", "endorphins", "epinephrine"):
        lvl = state.levels[name]
        lab = label_for(name, lvl.tonic + lvl.phasic, lvl.setpoint)
        assert lab["name"] not in {
            "ANHEDONIC",
            "NO DRIVE",
            "DYSPHORIC",
            "SEVERELY LOW",
            "SEDATED",
            "NO BOND",
            "DISTANT",
            "DEPLETED",
        }, f"{name} baseline chip wrong: {lab['name']}"
        assert lab["color"] in {"success", "neutral", "info"}, (
            f"{name} should not be red at baseline: {lab}"
        )


def test_baseline_ot_is_resting():
    state = build_initial_state(BIG5)
    lvl = state.levels["oxytocin"]
    lab = label_for("oxytocin", lvl.tonic + lvl.phasic, lvl.setpoint)
    assert lab["name"] == "RESTING"
    assert lab["color"] == "success"


def test_baseline_da_is_baseline():
    state = build_initial_state(BIG5)
    lvl = state.levels["dopamine"]
    lab = label_for("dopamine", lvl.tonic + lvl.phasic, lvl.setpoint)
    assert lab["name"] == "BASELINE"


def test_gateway_state_emits_label_fields():
    sim = _fresh_sim()
    dto = _build_state(sim)
    da = dto["chemicals"]["dopamine"]
    ot = dto["chemicals"]["oxytocin"]
    assert da["label"] == "BASELINE"
    assert "gap" in da and abs(da["gap"]) < 1.0
    assert "normalized_10" in da
    assert "setpoint" in da
    assert ot["label"] == "RESTING"
    assert ot["label"] not in {"NO BOND", "DISTANT"}
    assert ot["unit"] == "nM"


# ── Acceptance B: gap sensitivity ────────────────────────────────────────────


def test_low_da_shows_anhedonic_family():
    p = CHEMICAL_PARAMS["dopamine"]
    # Well below natural setpoint with clear negative gap
    lab = label_for("dopamine", value_nM=1.0, setpoint_nM=p["tonic_setpoint"])
    assert lab["name"] in {"ANHEDONIC", "NO DRIVE", "LOW SEEKING"}
    assert lab["color"] in {"error", "warning"}


def test_elevated_ot_shows_surge_family():
    p = CHEMICAL_PARAMS["oxytocin"]
    # Strong elevation above setpoint
    lab = label_for("oxytocin", value_nM=0.12, setpoint_nM=p["tonic_setpoint"])
    assert lab["name"] in {"WARMING", "CONNECTED", "DEEP SURGE", "SATURATED"}
    assert lab["name"] != "RESTING"
    assert lab["name"] not in {"NO BOND", "DISTANT"}


# ── Acceptance C: adenosine vs sleep thresholds ──────────────────────────────


def test_adenosine_wake_threshold_not_exhausted():
    # norm ≈ 3 → combined = 0.3 * 500 = 150
    lab = label_for("adenosine", value_nM=150.0, setpoint_nM=100.0)
    assert lab["name"] in {"ALERT", "WELL RESTED", "BUILDING"}
    assert lab["name"] != "EXHAUSTED"


def test_adenosine_enter_threshold_is_sleep_onset():
    # SLEEP_ENTER = 8.0 → combined = 0.8 * 500 = 400
    lab = label_for("adenosine", value_nM=400.0, setpoint_nM=100.0)
    assert lab["name"] in {"SLEEP ONSET", "EXHAUSTED", "TIRED"}
    # Must not be mid-ALERT
    assert lab["name"] not in {"WELL RESTED", "ALERT"}


def test_adenosine_exhausted_past_enter():
    lab = label_for("adenosine", value_nM=480.0, setpoint_nM=100.0)
    assert lab["name"] == "EXHAUSTED"


# ── annotate + ranges ────────────────────────────────────────────────────────


def test_annotate_includes_norm_max_for_sliders():
    ann = annotate_chemical("dopamine", tonic=8.0, phasic=0.0, setpoint=8.0)
    assert ann["norm_max"] == CHEMICAL_PARAMS["dopamine"]["normalization_max"]
    assert ann["normalized_10"] == 4.0  # 8/20*10
    assert abs(ann["gap"]) < 0.05


def test_cortisol_on_track_is_normal(monkeypatch):
    """On circadian trough, gap≈0 → NORMAL not DEPLETED."""
    monkeypatch.setattr("src.sim.labels._hour_of_day", lambda _n: 20.0)
    from src.sim.tick import _circadian_offset

    sp = 250.0
    offset = _circadian_offset("cortisol", 20.0)
    value = max(0.0, sp + offset)
    lab = label_for("cortisol", value, sp, hour=20.0)
    assert lab["name"] == "NORMAL"
