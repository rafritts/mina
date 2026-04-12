"""Allostatic load — cumulative biological stress burden accumulation and decay.
Stub for SPEC-20. Full implementation in SPEC-24."""
from __future__ import annotations
from src.sim.bio.state import BiologicalState
from src.sim.events import EventBus


def advance_allostatic(s: BiologicalState, sim_hours: float, event_bus: EventBus) -> BiologicalState:
    """Stub — returns state unchanged. Implemented in SPEC-24."""
    return s
