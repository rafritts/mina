"""
SPEC-62 correctness tests — circadian ratchet, sleep persistence,
decoder circadian gap, baseline social_warmth.

Pure deterministic sims — no LLM, no network.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading

import pytest

from src.sim.params import CHEMICAL_PARAMS, CIRCADIAN
from src.sim.state import ChemicalState, ChemicalLevel
from src.sim.tick import (
    build_initial_state,
    tick,
    _circadian_offset,
    biased_natural_setpoint,
)
from src.sim.decoder import decode
from src.sim.sim import Sim
from src.gateway.server import _compute_derived


BIG5 = {
    "openness": 72.0,
    "conscientiousness": 55.0,
    "extraversion": 48.0,
    "agreeableness": 68.0,
    "neuroticism": 65.0,
}


# ── DEFECT-1: circadian setpoint ratchet ─────────────────────────────────────


def test_multiday_circadian_does_not_ratchet_setpoints(monkeypatch):
    """5 simulated days of clock cycling must not walk mel/cort setpoints."""
    state = build_initial_state(BIG5)
    mel0 = state.levels["melatonin"].setpoint
    cort0 = state.levels["cortisol"].setpoint
    da0 = state.levels["dopamine"].setpoint

    hour = [0.0]

    def fake_hour(_now: float) -> float:
        return hour[0]

    monkeypatch.setattr("src.sim.tick._hour_of_day", fake_hour)

    steps = int(5 * 24 * 3600 / 10)
    for _ in range(steps):
        tick(state, 10.0, sleeping=False)
        hour[0] = (hour[0] + 10.0 / 3600.0) % 24.0

    mel = state.levels["melatonin"].setpoint
    cort = state.levels["cortisol"].setpoint
    da = state.levels["dopamine"].setpoint

    mel_tol = max(2.0, 0.15 * mel0)
    cort_tol = max(2.0, 0.15 * cort0)
    assert abs(mel - mel0) <= mel_tol, f"mel setpoint ratcheted: {mel0:.2f} → {mel:.2f}"
    assert abs(cort - cort0) <= cort_tol, f"cort setpoint ratcheted: {cort0:.2f} → {cort:.2f}"
    natural_da = CHEMICAL_PARAMS["dopamine"]["tonic_setpoint"]
    assert da >= natural_da * 0.65, f"DA setpoint collapsed: {da:.3f}"
    assert da >= da0 * 0.65


def test_circadian_tonic_still_swings(monkeypatch):
    """Rhythm preserved: night mel tonic above setpoint; day mel low."""
    state = build_initial_state(BIG5)

    monkeypatch.setattr("src.sim.tick._hour_of_day", lambda _n: 2.0)
    for _ in range(2000):
        tick(state, 10.0, sleeping=False)
    mel_night = state.levels["melatonin"].tonic
    mel_sp_night = state.levels["melatonin"].setpoint
    assert mel_night > mel_sp_night + 10.0, (
        f"night mel should peak above setpoint: tonic={mel_night:.1f} sp={mel_sp_night:.1f}"
    )

    monkeypatch.setattr("src.sim.tick._hour_of_day", lambda _n: 14.0)
    for _ in range(2000):
        tick(state, 10.0, sleeping=False)
    mel_day = state.levels["melatonin"].tonic
    mel_sp_day = state.levels["melatonin"].setpoint
    # Day trough: offset ≈ −amplitude; tonic near floor, not above setpoint
    assert mel_day <= mel_sp_day + 1.0, (
        f"day mel should be at/below setpoint: tonic={mel_day:.1f} sp={mel_sp_day:.1f}"
    )
    assert mel_night > mel_day + 20.0, "night→day swing missing"


def test_repair_circadian_setpoint_scars():
    """Production-like ratcheted mel/cort setpoints reset on Sim load."""
    state = build_initial_state(BIG5)
    state.levels["melatonin"].setpoint = 42.0
    state.levels["melatonin"].tonic = 42.0
    state.levels["cortisol"].setpoint = 362.0
    state.levels["cortisol"].tonic = 362.0
    # DA stays healthy — must not be mass-reset
    da_sp = state.levels["dopamine"].setpoint

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "sim_state.json")
        state.save(path)
        import src.sim.sim as sim_mod
        import src.config.config as cfg

        old = cfg.SIM_STATE_FILE
        try:
            cfg.SIM_STATE_FILE = path
            sim_mod.SIM_STATE_FILE = path
            s = Sim()
            mel_nat = biased_natural_setpoint("melatonin", BIG5)
            cort_nat = biased_natural_setpoint("cortisol", BIG5)
            assert abs(s._state.levels["melatonin"].setpoint - mel_nat) < 0.01
            assert abs(s._state.levels["cortisol"].setpoint - cort_nat) < 0.01
            assert abs(s._state.levels["dopamine"].setpoint - da_sp) < 0.01
        finally:
            cfg.SIM_STATE_FILE = old
            sim_mod.SIM_STATE_FILE = old


# ── DEFECT-2: sleep persistence ──────────────────────────────────────────────


def test_sleep_roundtrip_save_load():
    state = build_initial_state(BIG5)
    state.sleeping = True
    state.sleep_elapsed_s = 3600.0

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "sim_state.json")
        state.save(path)
        loaded = ChemicalState.load(path)
        assert loaded.sleeping is True
        assert loaded.sleep_elapsed_s == 3600.0


def test_sleep_defaults_on_legacy_file():
    """Old sim_state.json without sleep keys loads as awake."""
    state = build_initial_state(BIG5)
    d = state.to_dict()
    del d["sleeping"]
    del d["sleep_elapsed_s"]
    loaded = ChemicalState.from_dict(d)
    assert loaded.sleeping is False
    assert loaded.sleep_elapsed_s == 0.0


def test_sim_init_restores_sleep():
    state = build_initial_state(BIG5)
    state.sleeping = True
    state.sleep_elapsed_s = 1800.0

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "sim_state.json")
        state.save(path)
        import src.sim.sim as sim_mod
        import src.config.config as cfg

        old = cfg.SIM_STATE_FILE
        try:
            cfg.SIM_STATE_FILE = path
            sim_mod.SIM_STATE_FILE = path
            s = Sim()
            assert s.is_sleeping() is True
            assert s._sleep_elapsed_s == 1800.0
            assert s._state.sleeping is True
        finally:
            cfg.SIM_STATE_FILE = old
            sim_mod.SIM_STATE_FILE = old


def test_set_sleeping_writes_through_to_state():
    sim = Sim.__new__(Sim)
    sim._state = build_initial_state(BIG5)
    sim._big5 = dict(BIG5)
    sim._lock = threading.Lock()
    sim._sleeping = False
    sim._sleep_elapsed_s = 0.0
    sim._stop_event = threading.Event()
    sim._thread = None
    sim._observer = None

    sim.set_sleeping(True)
    assert sim._state.sleeping is True
    assert sim._state.sleep_elapsed_s == 0.0
    sim.set_sleeping(False)
    assert sim._state.sleeping is False


# ── DEFECT-3: decoder gap vs circadian target ────────────────────────────────


def test_evening_cortisol_gap_near_zero_when_on_trough(monkeypatch):
    """On-clock evening cortisol must not report a large negative gap."""
    state = build_initial_state(BIG5)
    hour = 20.0
    monkeypatch.setattr("src.sim.decoder._hour_of_day", lambda _n: hour)
    monkeypatch.setattr("src.sim.tick._hour_of_day", lambda _n: hour)

    lvl = state.levels["cortisol"]
    offset = _circadian_offset("cortisol", hour)
    lvl.tonic = max(0.0, lvl.setpoint + offset)
    lvl.phasic = 0.0

    out = decode(state)
    gap = out["cortisol"]["gap"]
    assert abs(gap) <= 1, f"on-trough cort gap should be ~0, got {gap}"


def test_cortisol_true_stress_still_positive_gap(monkeypatch):
    state = build_initial_state(BIG5)
    hour = 20.0
    monkeypatch.setattr("src.sim.decoder._hour_of_day", lambda _n: hour)

    lvl = state.levels["cortisol"]
    offset = _circadian_offset("cortisol", hour)
    # Well above circadian target
    lvl.tonic = lvl.setpoint + offset + 400.0
    lvl.phasic = 0.0

    out = decode(state)
    gap = out["cortisol"]["gap"]
    assert gap >= 2, f"true stress should show positive gap, got {gap}"


# ── DEFECT-4: social_warmth vs absolute OT ───────────────────────────────────


def test_baseline_social_warmth_not_floor():
    state = build_initial_state(BIG5)
    levels = {
        name: {
            "tonic": lvl.tonic,
            "phasic": lvl.phasic,
            "setpoint": lvl.setpoint,
            "sensitivity": lvl.sensitivity,
        }
        for name, lvl in state.levels.items()
    }
    second, _third = _compute_derived(levels)
    warmth = second["social_warmth"]
    assert 35.0 <= warmth <= 65.0, f"baseline social_warmth crushed or inflated: {warmth}"


def test_elevated_ot_raises_social_warmth():
    state = build_initial_state(BIG5)
    # Elevate OT well above setpoint
    ot = state.levels["oxytocin"]
    ot.tonic = ot.setpoint
    ot.phasic = CHEMICAL_PARAMS["oxytocin"]["normalization_max"] * 0.3

    levels = {
        name: {
            "tonic": lvl.tonic,
            "phasic": lvl.phasic,
            "setpoint": lvl.setpoint,
            "sensitivity": lvl.sensitivity,
        }
        for name, lvl in state.levels.items()
    }
    second, _ = _compute_derived(levels)
    # Baseline around mid-40s–50s; elevated OT should push higher
    assert second["social_warmth"] > 50.0
