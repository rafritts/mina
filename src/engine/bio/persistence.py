"""
State persistence — load, save, and load-and-advance helpers.

This module is used internally by the src.engine package. Root state.py re-implements
load_state() / save_state() with its own _STATE_FILE so that pytest monkeypatching
works (monkeypatch targets state._STATE_FILE, which lives in the root shim).
"""
from __future__ import annotations

import json
import os

import pathlib

_PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent.parent
_STATE_FILE = str(_PROJECT_ROOT / "run" / "state.json")


def load_state(state_file: str = _STATE_FILE):
    """Load BiologicalState from JSON. Migrates v1/v2 states automatically."""
    from src.engine.bio.state import BiologicalState
    try:
        with open(state_file) as f:
            data = json.load(f)
        migrated = data.get("schema_version", 1) < 3
        s = BiologicalState.from_dict(data)
        if migrated:
            save_state(s, state_file)
        return s
    except (FileNotFoundError, json.JSONDecodeError):
        return BiologicalState()


def save_state(s, state_file: str = _STATE_FILE) -> None:
    """Persist BiologicalState to JSON."""
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    with open(state_file, "w") as f:
        json.dump(s.to_dict(), f, indent=2)


def load_and_advance(state_file: str = _STATE_FILE):
    """Load state, apply time-based decay, save, return."""
    from src.engine.engine import advance
    s = load_state(state_file)
    s = advance(s)
    save_state(s, state_file)
    return s
