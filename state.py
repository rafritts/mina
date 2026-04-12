"""
Compatibility shim — core logic forwarded to src.sim.*

Existing callers (encoder.py, decoder.py, cortex.py, heartbeat.py, tests) import
from this module unchanged. load_state() and save_state() are defined here (not
re-exported) so that pytest monkeypatching of state._STATE_FILE works correctly.
"""
import json
import os

from src.sim.bio.state import BiologicalState, apply_deltas, log_state
from src.sim.engine import advance
from src.sim.psych.derived import derived
from src.sim.bio.defaults import CHEMICAL_DEFAULTS as _CHEMICAL_DEFAULTS

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_STATE_FILE = os.path.join(_PROJECT_ROOT, "run", "state.json")


def load_state() -> BiologicalState:
    """Load BiologicalState from _STATE_FILE. Migrates v1/v2 states automatically."""
    try:
        with open(_STATE_FILE) as f:
            data = json.load(f)
        migrated = data.get("schema_version", 1) < 3
        s = BiologicalState.from_dict(data)
        if migrated:
            save_state(s)
        return s
    except (FileNotFoundError, json.JSONDecodeError):
        return BiologicalState()


def save_state(s: BiologicalState) -> None:
    """Persist BiologicalState to _STATE_FILE."""
    os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
    with open(_STATE_FILE, "w") as f:
        json.dump(s.to_dict(), f, indent=2)


def load_and_advance() -> BiologicalState:
    """Load state, apply time-based decay, save, return."""
    s = load_state()
    s = advance(s)
    save_state(s)
    return s


__all__ = [
    "BiologicalState",
    "advance",
    "load_state",
    "save_state",
    "load_and_advance",
    "derived",
    "apply_deltas",
    "log_state",
    "_CHEMICAL_DEFAULTS",
    "_STATE_FILE",
]
