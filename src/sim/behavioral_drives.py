"""Behavioral drive signals — computed from biological state.

These drive signals are passed to freetime.py to guide autonomous action.
They translate raw biological state into action-oriented urgency signals
that the LLM can act on without needing to interpret raw pg/mL values.

SPEC-24.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.sim.bio.state import BiologicalState


@dataclass
class BiologicalDrive:
    drive_type:       str    # "hunger", "thirst", "fatigue", "pain", "sickness", "social"
    urgency:          float  # 0.0–1.0
    description:      str    # human-readable description for LLM context
    suggested_action: str    # tool name suggestion


def compute_behavioral_drives(s: BiologicalState) -> list[BiologicalDrive]:
    """
    Compute active biological drives from current state.
    Returns drives sorted by urgency (highest first).
    Drives below urgency 0.1 are not included.
    """
    drives: list[BiologicalDrive] = []

    # --- Hunger ---
    ghrelin = s.neuroendocrine.get("ghrelin", 400.0)
    glucose = s.chemicals.get("glucose",       85.0)
    if ghrelin > 700.0 or glucose < 65.0:
        # Urgency from whichever signal is stronger
        urgency = min(1.0, max(
            (ghrelin - 700.0) / 300.0 if ghrelin > 700.0 else 0.0,
            (65.0 - glucose)  / 20.0  if glucose < 65.0  else 0.0,
        ))
        drives.append(BiologicalDrive(
            drive_type="hunger",
            urgency=max(0.3, urgency),
            description=f"Ghrelin={ghrelin:.0f} pg/mL, glucose={glucose:.0f} mg/dL — hungry",
            suggested_action="eat",
        ))

    # --- Thirst ---
    hydration = s.chemicals.get("hydration", 62.0)
    if hydration < 59.0:
        urgency = (59.0 - hydration) / 14.0   # 0 at 59%, 1.0 at 45%
        drives.append(BiologicalDrive(
            drive_type="thirst",
            urgency=min(1.0, urgency),
            description=f"Hydration={hydration:.1f}% TBW — thirsty",
            suggested_action="drink",
        ))

    # --- Fatigue / Sleep ---
    adenosine = s.body.get("adenosine", 25.0)
    if adenosine > 60.0 and not s.sleeping:
        urgency = (adenosine - 60.0) / 40.0   # 0 at adenosine 60, 1.0 at adenosine 100
        drives.append(BiologicalDrive(
            drive_type="fatigue",
            urgency=min(1.0, urgency),
            description=f"Adenosine={adenosine:.1f} nmol/L — sleep pressure building",
            suggested_action="sleep",
        ))

    # --- Pain ---
    pain_int = s.pain.get("pain_intensity", 0.0)
    if pain_int > 40.0:
        drives.append(BiologicalDrive(
            drive_type="pain",
            urgency=pain_int / 100.0,
            description=f"Pain intensity={pain_int:.0f}/100 — discomfort present",
            suggested_action="rest",
        ))

    # --- Sickness ---
    infl_index = s.immune.get("inflammation_index", 0.0)
    if infl_index > 45.0:
        drives.append(BiologicalDrive(
            drive_type="sickness",
            urgency=infl_index / 100.0,
            description=f"Inflammation={infl_index:.0f}/100 — immune activation",
            suggested_action="rest",
        ))

    # --- Social deficit ---
    oxytocin  = s.chemicals.get("oxytocin",  4.0)
    serotonin = s.chemicals.get("serotonin", 22.0)
    if oxytocin < 10.0 and serotonin < 14.0:
        urgency = min(0.8, (10.0 - oxytocin) / 20.0)
        drives.append(BiologicalDrive(
            drive_type="social",
            urgency=urgency,
            description=f"Oxytocin={oxytocin:.1f} pg/mL, serotonin={serotonin:.1f} ng/mL — lonely",
            suggested_action="reach_out",
        ))

    return sorted(drives, key=lambda d: d.urgency, reverse=True)
