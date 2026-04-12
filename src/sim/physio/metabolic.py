"""Metabolic system — glucose, insulin, glucagon, leptin, ghrelin, vasopressin.
Stub for SPEC-20. Full implementation in SPEC-22."""
from __future__ import annotations
from src.sim.bio.state import BiologicalState
from src.sim.events import EventBus


def advance_metabolic(s: BiologicalState, sim_hours: float,
                       hour_of_day: float, event_bus: EventBus) -> BiologicalState:
    """Stub — returns state unchanged. Implemented in SPEC-22."""
    return s
