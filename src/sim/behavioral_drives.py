"""Behavioral drive signals — computed from biological state.

These drive signals are passed to freetime.py to guide autonomous action.
They translate raw biological state into action-oriented urgency signals
that the LLM can act on without needing to interpret raw pg/mL values.

SPEC-24.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.sim.bio.state import BiologicalState
from src.sim.constants import (
    DRIVE_FATIGUE_ADENOSINE_THRESHOLD,
    DRIVE_FATIGUE_URGENCY_DIVISOR,
    DRIVE_HUNGER_GHRELIN_THRESHOLD,
    DRIVE_HUNGER_GLUCOSE_THRESHOLD,
    DRIVE_HUNGER_URGENCY_DIVISOR,
    DRIVE_HUNGER_URGENCY_FLOOR,
    DRIVE_PAIN_THRESHOLD,
    DRIVE_SICKNESS_THRESHOLD,
    DRIVE_SOCIAL_OXYTOCIN_THRESHOLD,
    DRIVE_SOCIAL_SEROTONIN_THRESHOLD,
    DRIVE_SOCIAL_URGENCY_DIVISOR,
    DRIVE_THIRST_THRESHOLD,
    DRIVE_THIRST_URGENCY_DIVISOR,
)


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
    if ghrelin > DRIVE_HUNGER_GHRELIN_THRESHOLD or glucose < DRIVE_HUNGER_GLUCOSE_THRESHOLD:
        urgency = min(1.0, max(
            (ghrelin - DRIVE_HUNGER_GHRELIN_THRESHOLD) / DRIVE_HUNGER_URGENCY_DIVISOR
            if ghrelin > DRIVE_HUNGER_GHRELIN_THRESHOLD else 0.0,
            (DRIVE_HUNGER_GLUCOSE_THRESHOLD - glucose) / 20.0
            if glucose < DRIVE_HUNGER_GLUCOSE_THRESHOLD else 0.0,
        ))
        drives.append(BiologicalDrive(
            drive_type="hunger",
            urgency=max(DRIVE_HUNGER_URGENCY_FLOOR, urgency),
            description=f"Ghrelin={ghrelin:.0f} pg/mL, glucose={glucose:.0f} mg/dL — hungry",
            suggested_action="eat",
        ))

    # --- Thirst ---
    hydration = s.chemicals.get("hydration", 62.0)
    if hydration < DRIVE_THIRST_THRESHOLD:
        urgency = (DRIVE_THIRST_THRESHOLD - hydration) / DRIVE_THIRST_URGENCY_DIVISOR
        drives.append(BiologicalDrive(
            drive_type="thirst",
            urgency=min(1.0, urgency),
            description=f"Hydration={hydration:.1f}% TBW — thirsty",
            suggested_action="drink",
        ))

    # --- Fatigue / Sleep ---
    adenosine = s.body.get("adenosine", 25.0)
    if adenosine > DRIVE_FATIGUE_ADENOSINE_THRESHOLD and not s.sleeping:
        urgency = (adenosine - DRIVE_FATIGUE_ADENOSINE_THRESHOLD) / DRIVE_FATIGUE_URGENCY_DIVISOR
        drives.append(BiologicalDrive(
            drive_type="fatigue",
            urgency=min(1.0, urgency),
            description=f"Adenosine={adenosine:.1f} nmol/L — sleep pressure building",
            suggested_action="sleep",
        ))

    # --- Pain ---
    pain_int = s.pain.get("pain_intensity", 0.0)
    if pain_int > DRIVE_PAIN_THRESHOLD:
        drives.append(BiologicalDrive(
            drive_type="pain",
            urgency=pain_int / 100.0,
            description=f"Pain intensity={pain_int:.0f}/100 — discomfort present",
            suggested_action="rest",
        ))

    # --- Sickness ---
    infl_index = s.immune.get("inflammation_index", 0.0)
    if infl_index > DRIVE_SICKNESS_THRESHOLD:
        drives.append(BiologicalDrive(
            drive_type="sickness",
            urgency=infl_index / 100.0,
            description=f"Inflammation={infl_index:.0f}/100 — immune activation",
            suggested_action="rest",
        ))

    # --- Social deficit ---
    oxytocin  = s.chemicals.get("oxytocin",  4.0)
    serotonin = s.chemicals.get("serotonin", 22.0)
    if oxytocin < DRIVE_SOCIAL_OXYTOCIN_THRESHOLD and serotonin < DRIVE_SOCIAL_SEROTONIN_THRESHOLD:
        urgency = min(0.8, (DRIVE_SOCIAL_OXYTOCIN_THRESHOLD - oxytocin) / DRIVE_SOCIAL_URGENCY_DIVISOR)
        drives.append(BiologicalDrive(
            drive_type="social",
            urgency=urgency,
            description=f"Oxytocin={oxytocin:.1f} pg/mL, serotonin={serotonin:.1f} ng/mL — lonely",
            suggested_action="reach_out",
        ))

    return sorted(drives, key=lambda d: d.urgency, reverse=True)
