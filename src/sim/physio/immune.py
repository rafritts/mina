"""Immune system — cytokines, inflammation index, sickness behavior cascade.
Stub for SPEC-20. Full implementation in SPEC-23."""
from __future__ import annotations
from src.sim.bio.state import BiologicalState
from src.sim.events import EventBus


def advance_immune(s: BiologicalState, sim_hours: float, event_bus: EventBus) -> BiologicalState:
    """Stub — returns state unchanged. Implemented in SPEC-23."""
    return s
