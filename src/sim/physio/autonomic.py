"""Autonomic nervous system — vagal tone (PNS/SNS balance), derived HRV.
Full implementation for SPEC-23.

We track a single vagal_tone value (0–100) representing parasympathetic dominance
rather than modelling individual neurons. High vagal tone = rest-and-digest.
"""
from __future__ import annotations

from src.sim.bio.state import BiologicalState
from src.sim.events import EventBus


def compute_vagal_tone(s: BiologicalState) -> float:
    """
    Vagal tone (PNS dominance), 0–100.
    High → calm, social, restorative.
    Low  → stressed, defended, fight-or-flight.
    """
    cortisol  = s.chemicals.get("cortisol",       250.0)
    norepi    = s.chemicals.get("norepinephrine",  200.0)
    oxytocin  = s.chemicals.get("oxytocin",          4.0)
    gaba      = s.chemicals.get("gaba",               3.0)
    pain_int  = s.pain.get("pain_intensity",          0.0)
    adenosine = s.body.get("adenosine",              25.0)

    tone = 55.0   # balanced midpoint

    # SNS suppressors (each pushes toward fight-or-flight)
    tone -= max(0, cortisol  - 300.0) * 0.04
    tone -= max(0, norepi    - 250.0) * 0.02
    tone -= pain_int * 0.25
    tone -= max(0, adenosine - 50.0) * 0.3   # severe fatigue → ANS dysregulation

    # PNS promoters (each pushes toward rest-and-digest)
    tone += max(0, oxytocin - 4.0) * 0.5    # social safety signal
    tone += max(0, gaba     - 2.0) * 3.0    # GABAergic tone is PNS-coupled

    return min(100.0, max(0.0, round(tone, 1)))


def advance_autonomic(s: BiologicalState, sim_hours: float, event_bus: EventBus) -> BiologicalState:
    """
    Recompute and store vagal tone and derived HRV each tick.
    These are derived values — no dynamics, just a clean recomputation from current state.
    HRV (RMSSD): vagal_tone 0 → ~10 ms; vagal_tone 100 → ~80 ms.
    """
    tone = compute_vagal_tone(s)
    s.body["vagal_tone"]  = tone
    s.body["hrv_rmssd"]   = round(10.0 + tone * 0.70, 1)
    return s
