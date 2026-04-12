"""Circadian system — adenosine two-process model.
Full adenosine implementation for SPEC-21. Orexin/SCN/temperature deferred to SPEC-24."""
from __future__ import annotations

from src.sim.bio.state import BiologicalState
from src.sim.events import EventBus


def _advance_adenosine(s: BiologicalState, sim_hours: float) -> BiologicalState:
    """
    Update body["adenosine"] based on sleep/wake state.

    During waking: adenosine builds as a byproduct of neural ATP consumption.
      Base rate: 3.0 nmol/L/hr; stress (high cortisol) accelerates accumulation.
    During sleep: glymphatic clearance removes adenosine at ~20 nmol/L/hr.
      Floor at 15.0 nmol/L — complete clearance does not occur.

    sleep_pressure (0-100 AU) is derived from this value:
        SP = (adenosine - 20) / 0.6
    """
    a = s.body["adenosine"]

    if s.sleeping:
        # Glymphatic system clears adenosine during NREM/SWS
        a = max(15.0, a - 20.0 * sim_hours)
    else:
        # Neural activity accumulates adenosine; cortisol stress accelerates it
        base_rate   = 3.0
        stress_bonus = max(0.0, s.chemicals.get("cortisol", 250.0) - 400.0) * 0.004
        base_rate   += stress_bonus
        a = min(100.0, a + base_rate * sim_hours)

    s.body["adenosine"] = a
    return s


def advance_circadian(s: BiologicalState, sim_hours: float,
                       hour_of_day: float, event_bus: EventBus) -> BiologicalState:
    """Entry point called by engine. Advances adenosine; other circadian elements deferred."""
    s = _advance_adenosine(s, sim_hours)
    return s


def advance_sleep(s: BiologicalState, sim_hours: float, now: float,
                   hour_of_day: float, cfg: dict, event_bus: EventBus) -> BiologicalState:
    """Stub — sleep/wake state transitions remain in engine.py until SPEC-24."""
    return s
