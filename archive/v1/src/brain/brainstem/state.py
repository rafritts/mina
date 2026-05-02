"""
Compatibility shim — core logic forwarded to src.engine.*

Existing callers (encoder.py, decoder.py, cortex.py, heartbeat.py, tests) import
from this module unchanged. load_state() and save_state() are defined here (not
re-exported) so that pytest monkeypatching of state._STATE_FILE works correctly.
"""
import fcntl
import json
import os
import threading

from src.engine.bio.state import BiologicalState, apply_deltas, log_state
from src.engine.engine import advance
from src.engine.psych.derived import derived
from src.engine.bio.defaults import CHEMICAL_DEFAULTS as _CHEMICAL_DEFAULTS

from src.config.config import STATE_FILE as _STATE_FILE

_STATE_LOCK_FILE = _STATE_FILE + ".lock"


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


# Within-process lock (thread safety) + cross-process file lock (heartbeat vs dashboard).
_ADVANCE_LOCK = threading.Lock()


class _StateLock:
    """Combined threading + file lock for cross-process load/advance/save safety."""
    def __enter__(self):
        _ADVANCE_LOCK.acquire()
        os.makedirs(os.path.dirname(_STATE_LOCK_FILE), exist_ok=True)
        self._fh = open(_STATE_LOCK_FILE, "w")
        fcntl.flock(self._fh, fcntl.LOCK_EX)
        return self

    def __exit__(self, *_):
        fcntl.flock(self._fh, fcntl.LOCK_UN)
        self._fh.close()
        _ADVANCE_LOCK.release()


def load_and_advance() -> BiologicalState:
    """Load state, apply time-based decay, save, return."""
    with _StateLock():
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
