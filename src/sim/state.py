"""
ChemicalState — the sim's internal representation of neurochemical levels.

Each chemical tracks tonic (slow background), phasic (transient event spike),
setpoint (adapted baseline), and receptor sensitivity separately.
The decoder combines tonic + phasic into a single normalized felt level.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field


@dataclass
class ChemicalLevel:
    tonic: float             # nM — slow background level
    setpoint: float          # nM — adapted baseline (drifts with chronic exposure)
    phasic: float = 0.0      # nM — transient spike from events, decays fast
    sensitivity: float = 1.0 # receptor gain multiplier (Class 4 dynamics)


@dataclass
class ChemicalState:
    levels: dict[str, ChemicalLevel] = field(default_factory=dict)
    last_updated: float = field(default_factory=time.time)
    # Previous tick's normalized values — used by decoder to compute rate
    prev_normalized: dict[str, float] = field(default_factory=dict)
    # Sleep / consciousness (SPEC-62 DEFECT-2). Binary for now; SPEC-61 may extend.
    sleeping: bool = False
    sleep_elapsed_s: float = 0.0

    # ── Serialization ──────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "levels": {
                name: {
                    "tonic":       lvl.tonic,
                    "setpoint":    lvl.setpoint,
                    "phasic":      lvl.phasic,
                    "sensitivity": lvl.sensitivity,
                }
                for name, lvl in self.levels.items()
            },
            "last_updated": self.last_updated,
            "prev_normalized": self.prev_normalized,
            "sleeping": self.sleeping,
            "sleep_elapsed_s": self.sleep_elapsed_s,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ChemicalState:
        levels = {
            name: ChemicalLevel(
                tonic=       float(v.get("tonic",       0.0)),
                setpoint=    float(v.get("setpoint",    0.0)),
                phasic=      float(v.get("phasic",      0.0)),
                sensitivity= float(v.get("sensitivity", 1.0)),
            )
            for name, v in d.get("levels", {}).items()
        }
        return cls(
            levels=          levels,
            last_updated=    float(d.get("last_updated", time.time())),
            prev_normalized= {k: float(v) for k, v in d.get("prev_normalized", {}).items()},
            sleeping=        bool(d.get("sleeping", False)),
            sleep_elapsed_s= float(d.get("sleep_elapsed_s", 0.0)),
        )

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> ChemicalState:
        with open(path) as f:
            return cls.from_dict(json.load(f))
