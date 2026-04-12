"""Circadian system — adenosine two-process model, orexin, SCN clock, core body temp.
Stub for SPEC-20. Full implementation in SPEC-21/SPEC-24."""
from __future__ import annotations
from src.sim.bio.state import BiologicalState
from src.sim.events import EventBus


def advance_circadian(s: BiologicalState, sim_hours: float,
                       hour_of_day: float, event_bus: EventBus) -> BiologicalState:
    """Stub — returns state unchanged. Implemented in SPEC-21/SPEC-24."""
    return s


def advance_sleep(s: BiologicalState, sim_hours: float, now: float,
                   hour_of_day: float, cfg: dict, event_bus: EventBus) -> BiologicalState:
    """Stub — returns state unchanged. Sleep logic lives in engine.py for SPEC-20."""
    return s
