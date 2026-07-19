"""
Observer — per-tick structured observation of the simulation.

After every tick, the Observer snapshots chemical state, computes deltas vs the
previous tick, detects notable events (spikes, crashes, threshold crossings), and
appends a structured record to run/obs.jsonl.

Event types:
  spike             — normalized rose > SPIKE_THRESHOLD in one tick
  crash             — normalized fell > CRASH_THRESHOLD in one tick
  threshold_crossed — normalized crossed a major boundary (3, 5, 7, 9 on 0-10 scale)
  floor_hit         — normalized at or below FLOOR_WARN (chemical near zero)
  ceiling_hit       — normalized at or above CEILING_WARN (chemical near max)

Severity (for spikes/crashes):
  minor        — delta 1.0–2.0
  moderate     — delta 2.0–4.0
  significant  — delta > 4.0
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from src.config.config import RUN_DIR
from .params import CHEMICAL_PARAMS
from .state import ChemicalState

_OBS_FILE       = Path(RUN_DIR) / "obs.jsonl"
_MAX_LINES      = 8_640   # 24h at 10s ticks
_THRESHOLDS     = [3.0, 5.0, 7.0, 9.0]
_SPIKE_THRESH   = 1.0     # normalized units per tick
_CRASH_THRESH   = 1.0
_FLOOR_WARN     = 0.5     # normalized (out of 10)
_CEILING_WARN   = 9.5


class Observer:
    def __init__(self) -> None:
        self._prev: dict[str, float] = {}   # name → normalized 0-10

    def observe(self, state: ChemicalState, dt: float, sleeping: bool) -> dict:
        """Snapshot state, detect events, append to obs.jsonl. Call after tick()."""
        curr = self._compute_norm(state)
        events = self._detect(curr)
        chemicals = self._build_chem_dict(state, curr)

        obs = {
            "ts":        time.time(),
            "dt":        round(dt, 1),
            "sleeping":  sleeping,
            "chemicals": chemicals,
            "events":    events,
        }

        self._prev = curr
        _append(obs)
        return obs

    # ── internals ──────────────────────────────────────────────────────────────

    def _compute_norm(self, state: ChemicalState) -> dict[str, float]:
        result: dict[str, float] = {}
        for name, lvl in state.levels.items():
            p = CHEMICAL_PARAMS.get(name)
            if not p or p["class"] == 4:
                continue
            nm = p["normalization_max"]
            result[name] = round((lvl.tonic + lvl.phasic) / nm * 10.0, 3)
        return result

    def _detect(self, curr: dict[str, float]) -> list[dict]:
        events: list[dict] = []
        for name, norm in curr.items():
            prev = self._prev.get(name)
            if prev is None:
                continue
            delta = norm - prev

            # Spike / crash
            if delta >= _SPIKE_THRESH:
                events.append({
                    "type":     "spike",
                    "chemical": name,
                    "delta":    round(delta, 3),
                    "norm":     norm,
                    "severity": _severity(delta),
                })
            elif delta <= -_CRASH_THRESH:
                events.append({
                    "type":     "crash",
                    "chemical": name,
                    "delta":    round(delta, 3),
                    "norm":     norm,
                    "severity": _severity(abs(delta)),
                })

            # Threshold crossings
            for t in _THRESHOLDS:
                if prev < t <= norm:
                    events.append({
                        "type":      "threshold_crossed",
                        "chemical":  name,
                        "threshold": t,
                        "direction": "rising",
                        "norm":      norm,
                    })
                elif prev >= t > norm:
                    events.append({
                        "type":      "threshold_crossed",
                        "chemical":  name,
                        "threshold": t,
                        "direction": "falling",
                        "norm":      norm,
                    })

            # Floor / ceiling warnings
            if norm <= _FLOOR_WARN and (prev is None or prev > _FLOOR_WARN):
                events.append({"type": "floor_hit", "chemical": name, "norm": norm})
            if norm >= _CEILING_WARN and (prev is None or prev < _CEILING_WARN):
                events.append({"type": "ceiling_hit", "chemical": name, "norm": norm})

        return events

    def _build_chem_dict(self, state: ChemicalState, curr: dict[str, float]) -> dict:
        out: dict[str, dict] = {}
        for name, norm in curr.items():
            lvl = state.levels.get(name)
            if not lvl:
                continue
            p = CHEMICAL_PARAMS.get(name)
            if not p:
                continue
            nm = p["normalization_max"]
            setpt_norm = round(lvl.setpoint / nm * 10.0, 3)
            out[name] = {
                "norm":    norm,
                "delta":   round(norm - self._prev.get(name, norm), 3),
                "setpt":   setpt_norm,
                "gap":     round(norm - setpt_norm, 3),
            }
        return out


def _severity(delta: float) -> str:
    if delta >= 4.0:
        return "significant"
    if delta >= 2.0:
        return "moderate"
    return "minor"


# ── file I/O ──────────────────────────────────────────────────────────────────

def _append(obs: dict) -> None:
    _OBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_OBS_FILE, "a") as f:
        f.write(json.dumps(obs) + "\n")

    # Trim periodically (every ~5 minutes worth of ticks)
    if int(obs["ts"]) % 300 < 10:
        try:
            lines = _OBS_FILE.read_text().splitlines()
            if len(lines) > _MAX_LINES:
                _OBS_FILE.write_text("\n".join(lines[-_MAX_LINES:]) + "\n")
        except Exception:
            pass


def read_obs(limit: int = 200, hours: float | None = None) -> list[dict]:
    cutoff = time.time() - hours * 3600 if hours else None
    try:
        lines = _OBS_FILE.read_text().splitlines()
    except FileNotFoundError:
        return []

    result = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            obs = json.loads(line)
            if cutoff and obs.get("ts", 0) < cutoff:
                continue
            result.append(obs)
        except json.JSONDecodeError:
            pass
    return result
