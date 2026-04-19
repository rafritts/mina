"""Tests for state.py — biological simulation math."""
import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.brain.brainstem.state import (
    BiologicalState,
    apply_deltas,
    advance,
    load_state,
    _CHEMICAL_DEFAULTS,
)


def make_state(**chem_overrides) -> BiologicalState:
    s = BiologicalState()
    s.chemicals.update(chem_overrides)
    return s


def test_apply_deltas_clamps_to_critical_high():
    # apply_deltas uses critical_high (the absolute physiological ceiling),
    # not hard_ceiling (the encoder saturation threshold).
    from src.brain.brainstem.chemicals import REGISTRY
    critical_high = REGISTRY["dopamine"].critical_high
    state = make_state(dopamine=critical_high - 5)
    result = apply_deltas(state, {"dopamine": 100.0})
    assert result.dopamine <= critical_high


def test_apply_deltas_negative_delta_floors_at_zero():
    state = make_state(cortisol=10.0)
    result = apply_deltas(state, {"cortisol": -100.0})
    assert result.cortisol >= 0.0


def test_advance_decays_cortisol_toward_baseline_over_time():
    state = make_state(cortisol=900.0)
    state.last_updated = time.time() - 3600  # 1 hour ago
    result = advance(state)
    assert result.cortisol < 900.0


def test_advance_builds_sleep_pressure_while_awake():
    state = make_state(sleep_pressure=20.0)
    state.sleeping = False
    state.last_updated = time.time() - 3600
    result = advance(state)
    assert result.sleep_pressure > 20.0


def test_advance_reduces_sleep_pressure_while_sleeping():
    state = make_state(sleep_pressure=80.0)
    state.sleeping = True
    state.last_updated = time.time() - 3600
    result = advance(state)
    assert result.sleep_pressure < 80.0


def test_state_roundtrip_serialize_deserialize(tmp_path):
    state = BiologicalState()
    state.chemicals["cortisol"] = 350.0
    state.chemicals["dopamine"] = 95.0
    state.sleeping = True

    data = state.to_dict()
    loaded = BiologicalState.from_dict(data)
    assert loaded.cortisol == 350.0
    assert loaded.dopamine == 95.0
    assert loaded.sleeping is True


def test_load_state_returns_defaults_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("src.brain.brainstem.state._STATE_FILE", str(tmp_path / "nonexistent.json"))
    state = load_state()
    assert isinstance(state, BiologicalState)
    assert state.cortisol == _CHEMICAL_DEFAULTS["cortisol"]
