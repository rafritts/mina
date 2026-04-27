"""
src.engine — Mina's biological simulation package.

Public API:
  advance(state, now=None, event_bus=None) -> BiologicalState
  load_and_advance() -> BiologicalState
  apply_deltas(state, deltas) -> BiologicalState
  EventBus, BiologicalEvent
"""
from src.engine.bio.state import BiologicalState, apply_deltas, log_state
from src.engine.engine import advance
from src.engine.psych.derived import derived
from src.engine.events import EventBus, BiologicalEvent

__all__ = [
    "BiologicalState",
    "advance",
    "apply_deltas",
    "log_state",
    "derived",
    "EventBus",
    "BiologicalEvent",
]
