"""
Regression tests for sim death-spiral fixes.

These are pure deterministic sims — no LLM, no network.
"""
from __future__ import annotations

import pytest

from src.sim.params import CHEMICAL_PARAMS, EVENT_GAIN
from src.sim.tick import build_initial_state, tick, chemical_norm
from src.sim.chemistry import apply_chemistry
from src.sim.sim import Sim


BIG5 = {
    "openness": 72.0,
    "conscientiousness": 55.0,
    "extraversion": 48.0,
    "agreeableness": 68.0,
    "neuroticism": 65.0,
}

WARM_ENC = {
    "salience": 7,
    "threat": 0,
    "social_threat": 0,
    "reward": 7,
    "bonding": 8,
    "arousal": 5,
    "aversion": 0,
    "novelty": 4,
    "loss": 0,
    "romance": 0,
    "shame": 0,
    "directed_at_mina": True,
    "register_shift": False,
    "expected_magnitude": 0,
    "channel": "dialogue",
}


def _norm(state, name: str) -> float:
    return chemical_norm(state, name)


def test_event_gain_keeps_single_turn_sub_physiological():
    state = build_initial_state(BIG5)
    apply_chemistry(WARM_ENC, state, BIG5, relationship_modifier=1.0)
    da = state.levels["dopamine"]
    da_norm_delta = da.phasic / CHEMICAL_PARAMS["dopamine"]["normalization_max"] * 10.0
    # Architecture target: chatbot ceiling ~5–6 total; one turn should be ~0.5–1.5
    assert da_norm_delta < 2.0, f"DA spike too hot: {da_norm_delta:.2f} norm units"
    assert da_norm_delta > 0.2, f"DA spike too cold: {da_norm_delta:.2f}"
    assert EVENT_GAIN < 0.5


def test_oxytocin_capped_under_sustained_warm_class1():
    state = build_initial_state(BIG5)
    for _ in range(120):  # ~1h of warm messages every 30s
        apply_chemistry(WARM_ENC, state, BIG5, 1.0)
        for _ in range(3):
            tick(state, 10.0, sleeping=False)
    ot = state.levels["oxytocin"]
    ot_norm = (ot.tonic + ot.phasic) / CHEMICAL_PARAMS["oxytocin"]["normalization_max"] * 10
    assert ot_norm <= 10.5, f"OT runaway: norm={ot_norm:.1f}"


def test_16h_awake_does_not_floor_monoamine_setpoints():
    state = build_initial_state(BIG5)
    da0 = state.levels["dopamine"].setpoint
    ne0 = state.levels["norepinephrine"].setpoint
    for _ in range(int(16 * 3600 / 10)):
        tick(state, 10.0, sleeping=False)
    da = state.levels["dopamine"]
    ne = state.levels["norepinephrine"]
    # Must stay well above the old 25% death floor
    assert da.setpoint >= da0 * 0.65, f"DA setpoint collapsed: {da.setpoint:.3f} vs base {da0:.3f}"
    assert ne.setpoint >= ne0 * 0.65, f"NE setpoint collapsed: {ne.setpoint:.3f} vs base {ne0:.3f}"
    assert da.tonic >= CHEMICAL_PARAMS["dopamine"]["tonic_setpoint"] * 0.65
    assert ne.tonic >= CHEMICAL_PARAMS["norepinephrine"]["tonic_setpoint"] * 0.65


def test_sleep_clears_adenosine_phasic_reservoir():
    state = build_initial_state(BIG5)
    # Force high sleep pressure in the phasic (wake) reservoir
    state.levels["adenosine"].phasic = 400.0
    state.levels["adenosine"].tonic = 100.0
    before = state.levels["adenosine"].tonic + state.levels["adenosine"].phasic
    for _ in range(int(6 * 3600 / 10)):
        tick(state, 10.0, sleeping=True)
    after = state.levels["adenosine"].tonic + state.levels["adenosine"].phasic
    assert after < before * 0.5, f"Sleep did not clear ADE: {before:.0f} → {after:.0f}"
    assert _norm(state, "adenosine") < 4.0


def test_auto_sleep_cycle_recovers():
    """Advance many hours: sim should sleep when ADE high and wake recovered."""
    sim = Sim.__new__(Sim)
    sim._state = build_initial_state(BIG5)
    sim._big5 = dict(BIG5)
    sim._lock = __import__("threading").Lock()
    sim._sleeping = False
    sim._sleep_elapsed_s = 0.0
    sim._stop_event = __import__("threading").Event()
    sim._thread = None
    sim._observer = None  # unused in advance path we call

    # Step ticks with auto-sleep (same as advance)
    from src.sim.sim import _TICK_INTERVAL_S
    hours = 30
    steps = int(hours * 3600 / _TICK_INTERVAL_S)
    slept = False
    woke = False
    for _ in range(steps):
        was = sim._sleeping
        sim._maybe_toggle_sleep_locked(_TICK_INTERVAL_S)
        if not was and sim._sleeping:
            slept = True
        tick(sim._state, _TICK_INTERVAL_S, sleeping=sim._sleeping)
        if was and not sim._sleeping:
            woke = True

    assert slept, "Never entered auto-sleep in 30h"
    assert woke, "Never woke from auto-sleep in 30h"
    # After a full cycle, monoamine setpoints should not be at the old 25% floor
    da_sp = sim._state.levels["dopamine"].setpoint
    natural = CHEMICAL_PARAMS["dopamine"]["tonic_setpoint"]
    assert da_sp >= natural * 0.65, f"DA setpoint after sleep cycle: {da_sp}"


def test_repair_lifts_old_floor_scars():
    """Persisted death-spiral state should be repaired on Sim init."""
    from src.sim.state import ChemicalState, ChemicalLevel
    import tempfile, os, json

    # Build a scarred state like production had
    state = build_initial_state(BIG5)
    state.levels["dopamine"].tonic = 2.0
    state.levels["dopamine"].setpoint = 2.0
    state.levels["norepinephrine"].tonic = 0.75
    state.levels["norepinephrine"].setpoint = 0.75
    state.levels["adenosine"].phasic = 400.0

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "sim_state.json")
        state.save(path)
        # Patch SIM_STATE_FILE
        import src.sim.sim as sim_mod
        import src.config.config as cfg
        old = cfg.SIM_STATE_FILE
        try:
            cfg.SIM_STATE_FILE = path
            sim_mod.SIM_STATE_FILE = path
            s = Sim()
            da = s._state.levels["dopamine"]
            assert da.setpoint >= CHEMICAL_PARAMS["dopamine"]["tonic_setpoint"] * 0.9
            assert da.tonic >= CHEMICAL_PARAMS["dopamine"]["tonic_setpoint"] * 0.65
        finally:
            cfg.SIM_STATE_FILE = old
            sim_mod.SIM_STATE_FILE = old
