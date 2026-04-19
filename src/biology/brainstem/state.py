"""
Compatibility shim — core logic forwarded to src.sim.*

Existing callers (encoder.py, decoder.py, cortex.py, heartbeat.py, tests) import
from this module unchanged. load_state() and save_state() are defined here (not
re-exported) so that pytest monkeypatching of state._STATE_FILE works correctly.
"""
import json
import os
import threading

from src.sim.bio.state import BiologicalState, apply_deltas, log_state
from src.sim.engine import advance
from src.sim.psych.derived import derived
from src.sim.bio.defaults import CHEMICAL_DEFAULTS as _CHEMICAL_DEFAULTS

from src.config.config import STATE_FILE as _STATE_FILE


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
    """Persist BiologicalState to _STATE_FILE using an atomic write.

    Writing directly to the target file risks partial reads if another thread
    calls load_state() mid-write (json.JSONDecodeError → BiologicalState()
    defaults, silently resetting 9+ hours of state). Writing to a temp file
    and os.replace() is atomic on POSIX — readers always see a complete file.
    """
    os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
    tmp = _STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s.to_dict(), f, indent=2)
    os.replace(tmp, _STATE_FILE)


# Prevents concurrent load/advance/save collisions between the background sim
# loop and conversation turns or freetime cycles.
_ADVANCE_LOCK = threading.Lock()


def load_and_advance() -> BiologicalState:
    """Load state, apply time-based decay, save, return."""
    with _ADVANCE_LOCK:
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
