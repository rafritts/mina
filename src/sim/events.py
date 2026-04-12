"""
EventBus — mechanism by which the simulation communicates with the rest of the system.

The EventBus is populated during advance() and consumed by callers after each tick.
Events enable memory triggers, behavioral responses, and personality drift without
requiring callers to poll state directly.

Usage:
    bus = EventBus()
    new_state = advance(state, event_bus=bus)
    for event in bus.drain():
        handle_event(event)
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

EventType = Literal["spike", "crash", "threshold_crossed", "sustained_extreme", "state_entered"]
System = Literal["neuro", "endocrine", "immune", "pain", "psych", "sleep", "metabolic"]
Severity = Literal["minor", "moderate", "significant", "major"]


@dataclass
class BiologicalEvent:
    event_type: EventType
    system: System
    chemical: str          # e.g. "cortisol", "il6", "pain_intensity"
    value: float           # current value in natural units
    delta: float           # change this tick (positive = increase)
    unit: str              # e.g. "nmol/L", "pg/mL", "AU"
    label: str             # current label e.g. "ACUTE STRESS"
    label_crossed: bool    # True if this tick crossed a label boundary
    severity: Severity
    significance: float    # 0.0–1.0 computed score for memory trigger decisions
    timestamp: float


class EventBus:
    """Collects events during advance(). Consumed by callers via drain()."""

    def __init__(self) -> None:
        self._events: list[BiologicalEvent] = []

    def emit(self, event: BiologicalEvent) -> None:
        self._events.append(event)

    def drain(self) -> list[BiologicalEvent]:
        events, self._events = self._events, []
        return events

    @property
    def has_events(self) -> bool:
        return bool(self._events)


def compute_significance(chemical: str, delta: float, value: float,
                          label_crossed: bool, display_range: float) -> float:
    """
    Score 0.0–1.0 for memory trigger decisions.

    Factors:
    - delta as fraction of display range (big swings = significant)
    - label boundary crossing (always at least 0.3)
    - absolute value at extremes (sustained extremes = significant)
    """
    frac = abs(delta) / max(1.0, display_range)
    score = min(1.0, frac * 2.0)   # 50% of display range → significance 1.0
    if label_crossed:
        score = max(score, 0.3)
    # Bonus for extreme values
    from src.sim.chem.units import get_label
    label, _ = get_label(chemical, value)
    if label in ("MAXED", "FLOODED", "ACUTE STRESS", "EXHAUSTED", "HYPOGLYCEMIC", "CRASHED"):
        score = max(score, 0.6)
    return round(score, 3)


# Memory trigger thresholds (used by hippocampus integration in SPEC-24)
SIGNIFICANCE_RAG_CANDIDATE = 0.25    # episodic: "something happened"
SIGNIFICANCE_RAG_STRONG    = 0.60    # strong candidate
SIGNIFICANCE_KAG_CANDIDATE = 0.80    # semantic: "this changes who I am"
SIGNIFICANCE_MULTI_EVENT   = 0.40    # 3+ simultaneous events above this → definitely save
