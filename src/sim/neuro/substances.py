"""Substance pharmacokinetics — PK/PD for all defined substances.
Stub for SPEC-20. Substance logic lives in engine.py until extracted in SPEC-21."""
from __future__ import annotations
from src.sim.bio.state import BiologicalState
from src.sim.events import EventBus


def advance_substances(s: BiologicalState, sim_hours: float, now: float,
                        event_bus: EventBus) -> BiologicalState:
    """Stub — returns state unchanged. Substance PK handled in engine.py for SPEC-20."""
    return s
