"""HPA axis — stressor → CRH → ACTH → cortisol cascade with delay queue.
Stub for SPEC-20. Full implementation in SPEC-22."""
from __future__ import annotations
from src.sim.bio.state import BiologicalState
from src.sim.events import EventBus


def advance_hpa(s: BiologicalState, sim_hours: float, now: float,
                hour_of_day: float, event_bus: EventBus) -> BiologicalState:
    """Stub — returns state unchanged. Implemented in SPEC-22."""
    return s
