"""
Decoder — deterministic snapshot of ChemicalState into pillar-legible JSON.

Output schema per chemical:
  normalized  — current level (tonic + phasic) on 0-10 scale, whole number
  setpoint    — adapted baseline on 0-10 scale, whole number
  gap         — normalized - setpoint, signed whole number
  rate        — change in normalized since last tick, signed whole number

Core chemicals always present: DA, 5-HT, NE, epinephrine, cortisol, oxytocin.
Conditional chemicals: shown only when |gap| >= threshold (default 2).
Sleep-axis chemicals (melatonin / adenosine / orexin) need a larger gap so
mild evening circadian drift does not read as "sleepy."

Noise floor: |raw gap| < 1.0 and |raw rate| < 1.0 round to 0. Integer
rounding alone used to invent ±1 swings from 0.5–0.9 drift — pillars treated
those as real mood moves.
"""
from __future__ import annotations

import time

from .state import ChemicalState
from .params import CHEMICAL_PARAMS
from .tick import _circadian_offset, _hour_of_day

_CORE = frozenset({"dopamine", "serotonin", "norepinephrine", "epinephrine", "cortisol", "oxytocin"})
_GAP_THRESHOLD = 2  # default |gap| for most conditional chemicals

# Sub-unit drift on the 0–10 scale is measurement/rounding noise, not a swing.
_GAP_NOISE_FLOOR = 1.0
_RATE_NOISE_FLOOR = 1.0

# Sleep / circadian axis: only surface when the shift is hard to ignore.
# Mild nocturnal melatonin (+1–2) is normal evening chemistry, not sleepiness.
# Adenosine only matters near real sleep pressure (enter threshold ~8).
_SLEEP_AXIS_GAP_THRESHOLD: dict[str, int] = {
    "melatonin": 4,
    "adenosine": 4,
    "orexin": 3,
}


def _gap_threshold(name: str) -> int:
    return _SLEEP_AXIS_GAP_THRESHOLD.get(name, _GAP_THRESHOLD)


def _quantize_delta(raw: float, floor: float) -> int:
    """Round a signed delta; force 0 when |raw| is under the noise floor."""
    if abs(raw) < floor:
        return 0
    return int(round(raw))


def decode(state: ChemicalState) -> dict[str, dict[str, int]]:
    """
    Snapshot current ChemicalState into decoder output.
    Updates state.prev_normalized as a side effect (for rate tracking).
    """
    output: dict[str, dict[str, int]] = {}
    # Wall clock — same source as tick Phase 2. Admin advance without a virtual
    # sim clock still uses wall hour for circadian (SPEC-62 follow-up).
    hour = _hour_of_day(time.time())

    for name, lvl in state.levels.items():
        p = CHEMICAL_PARAMS.get(name)
        if not p:
            continue

        # Grades D (class 4 scaffolds) are not emitted in decoder output
        if p["class"] == 4:
            continue

        norm_max = p["normalization_max"]
        combined = lvl.tonic + lvl.phasic
        norm_raw = max(0.0, combined / norm_max * 10.0)
        setpoint_raw = max(0.0, lvl.setpoint / norm_max * 10.0)
        # Gap vs circadian target for clock chems so on-rhythm trough/peak
        # is not reported as off-baseline (SPEC-62 DEFECT-3). Non-circadian
        # chemicals get offset 0 → same as gap vs setpoint.
        target_nM = lvl.setpoint + _circadian_offset(name, hour)
        target_raw = max(0.0, target_nM / norm_max * 10.0)

        normalized = int(round(norm_raw))
        setpoint = int(round(setpoint_raw))
        # Gap from raw levels so 1.4 vs 2.2 does not become a fake −1 after
        # independent rounding of each side.
        gap = _quantize_delta(norm_raw - target_raw, _GAP_NOISE_FLOOR)

        prev = state.prev_normalized.get(name, norm_raw)
        rate = _quantize_delta(norm_raw - prev, _RATE_NOISE_FLOOR)

        is_core = name in _CORE
        if not is_core and abs(gap) < _gap_threshold(name):
            continue

        output[name] = {
            "normalized": normalized,
            "setpoint":   setpoint,
            "gap":        gap,
            "rate":       rate,
        }

    # Update prev_normalized for next tick's rate calculation (store raw 0–10)
    for name, lvl in state.levels.items():
        p = CHEMICAL_PARAMS.get(name)
        if not p or p["class"] == 4:
            continue
        norm_max = p["normalization_max"]
        combined = lvl.tonic + lvl.phasic
        state.prev_normalized[name] = max(0.0, combined / norm_max * 10.0)

    return output


def format_decoder_output(decoded: dict[str, dict[str, int]]) -> str:
    """Format decoder output as a readable block for LLM prompts."""
    if not decoded:
        return "(no significant chemical activity)"
    lines = []
    for name, vals in sorted(decoded.items()):
        n = vals["normalized"]
        s = vals["setpoint"]
        g = vals["gap"]
        r = vals["rate"]
        gap_str  = f"+{g}" if g >= 0 else str(g)
        rate_str = f"+{r}" if r >= 0 else str(r)
        lines.append(
            f"  {name:<18} normalized={n:>2}  setpoint={s:>2}  gap={gap_str:>3}  rate={rate_str:>3}"
        )
    return "\n".join(lines)
