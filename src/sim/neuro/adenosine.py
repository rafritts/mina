"""Adenosine dynamics — the real sleep pressure molecule.
Stub for SPEC-20. Full implementation in SPEC-21 (circadian integration)."""
from __future__ import annotations
from src.sim.bio.state import BiologicalState
from src.sim.events import EventBus


def advance_adenosine(s: BiologicalState, sim_hours: float, event_bus: EventBus) -> BiologicalState:
    """Stub — returns state unchanged. Implemented in SPEC-21."""
    return s
