"""
Bio snapshot history — rolling chemical snapshots for trajectory analysis.
"""
import json
import os
import time

from src.brain.brainstem.state import BiologicalState, _CHEMICAL_DEFAULTS
from src.config.config import RUN_DIR

_BIO_SNAPSHOT_FILE = os.path.join(RUN_DIR, "bio_snapshots.jsonl")
_BIO_SNAPSHOT_MAX  = 10

_SNAPSHOT_CHEMS = [
    "cortisol", "norepinephrine", "epinephrine", "dopamine",
    "serotonin", "oxytocin", "endorphins", "acetylcholine",
    "gaba", "melatonin", "anandamide", "glucose", "hydration",
]


def _snapshot_chems(state: BiologicalState) -> dict[str, float]:
    result = {}
    for name in _SNAPSHOT_CHEMS:
        if name == "anandamide":
            result[name] = state.body.get("anandamide", 1.5)
        else:
            result[name] = state.chemicals.get(name, _CHEMICAL_DEFAULTS.get(name, 0.0))
    return result


def save_bio_snapshot(state: BiologicalState) -> None:
    entry = {"ts": time.time(), "chems": _snapshot_chems(state)}
    os.makedirs(os.path.dirname(_BIO_SNAPSHOT_FILE), exist_ok=True)
    with open(_BIO_SNAPSHOT_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    try:
        lines = open(_BIO_SNAPSHOT_FILE).read().splitlines()
        if len(lines) > _BIO_SNAPSHOT_MAX:
            with open(_BIO_SNAPSHOT_FILE, "w") as f:
                f.write("\n".join(lines[-_BIO_SNAPSHOT_MAX:]) + "\n")
    except Exception:
        pass


def load_bio_snapshots(n: int = 3) -> list[dict]:
    try:
        lines = open(_BIO_SNAPSHOT_FILE).read().splitlines()
        entries = []
        for line in lines[-n:]:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return entries
    except FileNotFoundError:
        return []
