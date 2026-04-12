"""
src.sim — Mina's biological simulation package.

Public API:
  advance(state, now=None, event_bus=None) -> BiologicalState
  load_and_advance() -> BiologicalState
  apply_deltas(state, deltas) -> BiologicalState
  EventBus, BiologicalEvent
"""
from src.sim.bio.state import BiologicalState, apply_deltas, log_state
from src.sim.engine import advance
from src.sim.bio.persistence import load_and_advance
from src.sim.psych.derived import derived
from src.sim.events import EventBus, BiologicalEvent

__all__ = [
    "BiologicalState",
    "advance",
    "apply_deltas",
    "log_state",
    "load_and_advance",
    "derived",
    "EventBus",
    "BiologicalEvent",
]
