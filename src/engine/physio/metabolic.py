"""Metabolic system — ghrelin, leptin, insulin, glucose.
Full implementation for SPEC-22.

Glucose is managed here (removed from Phase 1 REGISTRY loop in SPEC-22).
"""
from __future__ import annotations

import math

from src.engine.bio.state import BiologicalState
from src.engine.chem.units import clamp_chemical
from src.engine.events import EventBus


# ---------------------------------------------------------------------------
# Baseline functions (importable for tests)
# ---------------------------------------------------------------------------

def _ghrelin_baseline_fn(hour: float, ctx: dict) -> float:
    """
    Ghrelin follows a diurnal pattern — three meal-anticipation peaks.
    Rises with fasting (low glucose). Suppressed by high leptin (satiety).
    """
    base = 250.0
    for meal_hour in [7.0, 12.5, 18.0]:
        proximity = abs(hour - meal_hour)
        base += 150.0 * math.exp(-proximity * proximity / 2.0)   # Gaussian peaks
    if ctx.get("glucose", 85.0) < 70.0:
        base += (70.0 - ctx["glucose"]) * 5.0
    if ctx.get("leptin", 15.0) > 20.0:
        base *= 0.6   # satiety signal suppresses hunger
    return min(1000.0, base)


def _leptin_baseline_fn(hour: float, ctx: dict) -> float:
    """Leptin peaks at ~2am, lowest in morning. Falls with fasting/low glucose."""
    base = 12.0 + 6.0 * math.cos((hour - 2) * math.pi / 12)
    if ctx.get("glucose", 85.0) < 70.0:
        base *= 0.7
    return max(2.0, base)


# ---------------------------------------------------------------------------
# Advance functions
# ---------------------------------------------------------------------------

def _advance_insulin(s: BiologicalState, sim_hours: float) -> BiologicalState:
    """
    Insulin rises proportionally with glucose above 80 mg/dL (post-meal response).
    Falls to fasting baseline (~3 µIU/mL) as glucose normalises.
    """
    glucose = s.chemicals.get("glucose", 85.0)
    if glucose > 80.0:
        insulin_target = max(3.0, (glucose - 80.0) * 1.2)
    else:
        insulin_target = 3.0

    insulin = s.neuroendocrine.get("insulin", 5.0)
    s.neuroendocrine["insulin"] = insulin + (insulin_target - insulin) * min(1.0, 0.5 * sim_hours)
    return s


def _advance_glucose(s: BiologicalState, sim_hours: float) -> BiologicalState:
    """
    Glucose decay with insulin-mediated clearance.
    Replaces the glucose special-case in engine Phase 1 (SPEC-22).

    Sleep/awake fasting: -0.8 mg/dL/hr (hepatic glucose production largely offsets uptake)
    High insulin: additional insulin-mediated clearance
    Hypoglycaemic awakening: glucose < 55 forces the body awake.
    """
    glucose = s.chemicals.get("glucose", 85.0)
    decay_rate = 0.8 if s.sleeping else 0.8

    # Post-meal insulin accelerates glucose clearance
    insulin = s.neuroendocrine.get("insulin", 5.0)
    if insulin > 40.0:
        decay_rate += (insulin - 40.0) * 0.08

    new_glu = clamp_chemical("glucose", glucose - decay_rate * sim_hours)
    s.chemicals["glucose"] = new_glu

    # Hypoglycaemic awakening
    if s.sleeping and new_glu < 55.0:
        s.sleeping = False
        try:
            from log import log
            log("STATE", f"Hypoglycaemic awakening: glucose={new_glu:.1f} mg/dL")
        except ImportError:
            pass

    return s


def _advance_ghrelin(s: BiologicalState, sim_hours: float, hour_of_day: float) -> BiologicalState:
    """Advance ghrelin toward its diurnal + fasting-sensitive baseline."""
    ctx = {
        "glucose": s.chemicals.get("glucose", 85.0),
        "leptin":  s.neuroendocrine.get("leptin", 15.0),
    }
    target  = _ghrelin_baseline_fn(hour_of_day, ctx)
    ghrelin = s.neuroendocrine.get("ghrelin", 400.0)
    # Ghrelin responds within 1–2 hours of meal or fast (approach_rate 0.8/hr)
    s.neuroendocrine["ghrelin"] = ghrelin + (target - ghrelin) * min(1.0, 0.8 * sim_hours)
    return s


def _advance_leptin(s: BiologicalState, sim_hours: float, hour_of_day: float) -> BiologicalState:
    """Advance leptin toward its circadian baseline."""
    ctx = {"glucose": s.chemicals.get("glucose", 85.0)}
    target = _leptin_baseline_fn(hour_of_day, ctx)
    leptin  = s.neuroendocrine.get("leptin", 15.0)
    # Leptin changes slowly — reflects adipose stores (approach_rate 0.05/hr)
    s.neuroendocrine["leptin"] = leptin + (target - leptin) * min(1.0, 0.05 * sim_hours)
    return s


# ---------------------------------------------------------------------------
# Cross-effects: metabolic hormones → first-order chemicals
# ---------------------------------------------------------------------------

def _apply_metabolic_cross_effects(s: BiologicalState, sim_hours: float) -> BiologicalState:
    """Apply metabolic hormone → first-order chemical cross-effects."""
    ghrelin     = s.neuroendocrine.get("ghrelin", 400.0)
    leptin      = s.neuroendocrine.get("leptin", 15.0)
    vasopressin = s.neuroendocrine.get("vasopressin", 2.0)

    # --- Ghrelin behavioral effects ---
    if ghrelin > 600.0:
        # Hunger impairs focus: reward-seeking intensifies, dopamine baseline drops
        s.chemicals["dopamine"] = clamp_chemical("dopamine",
            s.chemicals.get("dopamine", 80.0) - 5.0 * sim_hours)
    if ghrelin > 800.0:
        # Severe hunger is physiologically stressful → cortisol surge
        s.chemicals["cortisol"] = clamp_chemical("cortisol",
            s.chemicals.get("cortisol", 250.0) + 40.0 * sim_hours)
    if ghrelin < 200.0:
        # Satiated — slight social ease and mood lift
        s.chemicals["oxytocin"] = clamp_chemical("oxytocin",
            s.chemicals.get("oxytocin", 4.0) + 1.0 * sim_hours)

    # --- Leptin < 5 (starvation / leptin resistance) → hedonic suppression ---
    if leptin < 5.0:
        s.chemicals["dopamine"]  = clamp_chemical("dopamine",
            s.chemicals.get("dopamine", 80.0) - 2.0 * sim_hours)
        s.chemicals["serotonin"] = clamp_chemical("serotonin",
            s.chemicals.get("serotonin", 22.0) - 0.5 * sim_hours)

    # --- Vasopressin > 10 → ADH water retention (offset hydration decay by 20%) ---
    if vasopressin > 10.0:
        # The Phase 1 hydration decay is 0.4/hr; 20% of that is recovered here
        s.chemicals["hydration"] = clamp_chemical("hydration",
            s.chemicals.get("hydration", 62.0) + 0.08 * sim_hours)

    return s


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def advance_metabolic(s: BiologicalState, sim_hours: float,
                       hour_of_day: float, event_bus: EventBus) -> BiologicalState:
    """
    Advance metabolic hormones and glucose.
    Must run before Phase 1 REGISTRY loop (glucose is no longer in Phase 1).
    """
    s = _advance_insulin(s, sim_hours)
    s = _advance_glucose(s, sim_hours)
    s = _advance_ghrelin(s, sim_hours, hour_of_day)
    s = _advance_leptin(s, sim_hours, hour_of_day)
    s = _apply_metabolic_cross_effects(s, sim_hours)
    return s
