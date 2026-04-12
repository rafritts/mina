"""GABA and glutamate dynamics — E/I balance.
Stub for SPEC-20. Full implementation in SPEC-21."""
from __future__ import annotations
from src.sim.bio.state import BiologicalState
from src.sim.events import EventBus


def advance_amino_acids(s: BiologicalState, sim_hours: float, event_bus: EventBus) -> BiologicalState:
    """Stub — returns state unchanged. Implemented in SPEC-21."""
    return s
