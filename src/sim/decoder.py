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
"""
from __future__ import annotations

from .state import ChemicalState
from .params import CHEMICAL_PARAMS

_CORE = frozenset({"dopamine", "serotonin", "norepinephrine", "epinephrine", "cortisol", "oxytocin"})
_GAP_THRESHOLD = 2  # default |gap| for most conditional chemicals

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


def decode(state: ChemicalState) -> dict[str, dict[str, int]]:
    """
    Snapshot current ChemicalState into decoder output.
    Updates state.prev_normalized as a side effect (for rate tracking).
    """
    output: dict[str, dict[str, int]] = {}

    for name, lvl in state.levels.items():
        p = CHEMICAL_PARAMS.get(name)
        if not p:
            continue

        # Grades D (class 4 scaffolds) are not emitted in decoder output
        if p["class"] == 4:
            continue

        norm_max = p["normalization_max"]
        combined = lvl.tonic + lvl.phasic
        norm_raw = combined / norm_max * 10.0
        setpoint_raw = lvl.setpoint / norm_max * 10.0

        normalized = round(max(0.0, norm_raw))
        setpoint   = round(max(0.0, setpoint_raw))
        gap        = normalized - setpoint
        rate       = normalized - round(state.prev_normalized.get(name, normalized))

        is_core = name in _CORE
        if not is_core and abs(gap) < _gap_threshold(name):
            continue

        output[name] = {
            "normalized": normalized,
            "setpoint":   setpoint,
            "gap":        gap,
            "rate":       rate,
        }

    # Update prev_normalized for next tick's rate calculation
    for name, lvl in state.levels.items():
        p = CHEMICAL_PARAMS.get(name)
        if not p or p["class"] == 4:
            continue
        norm_max = p["normalization_max"]
        combined = lvl.tonic + lvl.phasic
        state.prev_normalized[name] = combined / norm_max * 10.0

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
