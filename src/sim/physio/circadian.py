"""Circadian system — adenosine two-process model, orexin, core body temperature.
Full two-process implementation for SPEC-24.

Borbély two-process model:
  Process S (homeostatic): adenosine — builds during waking, cleared during sleep
  Process C (circadian):   melatonin (promotes sleep) vs orexin (promotes wake)

Together they determine sleep propensity. Neither alone is sufficient.
"""
from __future__ import annotations

import math
import time

from src.sim.bio.state import BiologicalState
from src.sim.events import EventBus


# ---------------------------------------------------------------------------
# Process S: adenosine (homeostatic sleep pressure)
# ---------------------------------------------------------------------------

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
        base_rate    = 3.0
        stress_bonus = max(0.0, s.chemicals.get("cortisol", 250.0) - 400.0) * 0.004
        base_rate   += stress_bonus
        a = min(100.0, a + base_rate * sim_hours)

    s.body["adenosine"] = a
    return s


# ---------------------------------------------------------------------------
# Process C: orexin (circadian wake-promotion)
# ---------------------------------------------------------------------------

def _orexin_baseline_fn(hour: float, ctx: dict) -> float:
    """
    Orexin peaks ~3pm as wake-promoting drive; lowest at ~3am.
    Absent or very low orexin = narcoleptic-like state (irresistible sleep).

    Adenosine and orexin mutually inhibit (lateral hypothalamus ↔ VLPO).
    High cortisol (stress) transiently supports orexin (stress = stay awake).
    """
    # Circadian cosine: peak at 15:00 (3pm), trough at 03:00
    base = 200.0 + 150.0 * math.cos((hour - 15.0) * math.pi / 12.0)
    # Adenosine opposes orexin (mutual inhibition with sleep-active VLPO neurons)
    adenosine = ctx.get("adenosine", 25.0)
    base -= max(0.0, adenosine - 40.0) * 2.0
    # Cortisol supports orexin (stress-induced hyperarousal)
    base += max(0.0, ctx.get("cortisol", 250.0) - 400.0) * 0.1
    return max(30.0, base)


def _advance_orexin(s: BiologicalState, sim_hours: float,
                    hour_of_day: float) -> BiologicalState:
    """Advance orexin toward its circadian baseline (approach_rate 0.5/hr — responsive)."""
    ctx = {
        "adenosine": s.body.get("adenosine", 25.0),
        "cortisol":  s.chemicals.get("cortisol", 250.0),
    }
    target  = _orexin_baseline_fn(hour_of_day, ctx)
    current = s.neuroendocrine.get("orexin", 300.0)
    s.neuroendocrine["orexin"] = max(20.0, current + (target - current) * min(1.0, 0.5 * sim_hours))
    return s


# ---------------------------------------------------------------------------
# Sleep propensity (two-process composite)
# ---------------------------------------------------------------------------

def compute_sleep_propensity(s: BiologicalState) -> float:
    """
    Sleep propensity: 0 (fully awake) → 100 (irresistible sleep).

    Process S: adenosine buildup (homeostatic pressure)
    Process C: melatonin (promotes sleep) vs orexin (promotes wake)

    The two processes together explain why:
    - You stay alert at 7pm despite 16 waking hours (orexin fighting adenosine)
    - You crash after 2am (orexin falls, adenosine wins)
    - Naps partially refresh (adenosine partially cleared, circadian clock unchanged)
    """
    adenosine = s.body.get("adenosine",                     25.0)
    melatonin = s.chemicals.get("melatonin",                 5.0)
    orexin    = s.neuroendocrine.get("orexin",             300.0)

    # Process S: 0 propensity at adenosine 20, 100 propensity at adenosine 90
    s_process = min(100.0, max(0.0, (adenosine - 20.0) / 0.70))

    # Process C: melatonin drives sleep, orexin drives waking
    melatonin_drive = (melatonin / 220.0) * 100.0
    orexin_wake     = (orexin    / 400.0) * 100.0
    c_process = max(0.0, melatonin_drive - orexin_wake * 0.6)

    # Weighted composite: homeostatic pressure dominates
    propensity = s_process * 0.6 + c_process * 0.4
    return min(100.0, max(0.0, round(propensity, 1)))


# ---------------------------------------------------------------------------
# Core body temperature
# ---------------------------------------------------------------------------

def _advance_core_temp(s: BiologicalState, sim_hours: float,
                        hour_of_day: float) -> BiologicalState:
    """
    Core body temperature: circadian-driven, 36.3–37.2°C.
    Nadir ~4–6am (promotes sleep onset), peak ~6–8pm (promotes alertness).
    Fever: elevated by IL-6 and IL-1β (pyrogens via PGE2 in the hypothalamus).
    """
    # Circadian component: nadir at 4am, peak at 16pm
    circadian_temp = 36.75 + 0.4 * math.sin((hour_of_day - 4.0) * math.pi / 12.0)

    # Fever component (cytokine-driven)
    il1b = s.immune.get("il1b", 2.0)
    il6  = s.immune.get("il6",  3.0)
    fever_delta = 0.0
    if il1b > 10.0 or il6 > 20.0:
        fever_delta = max(0.0, il6 - 20.0) * 0.02 + max(0.0, il1b - 10.0) * 0.03
        fever_delta = min(4.0, fever_delta)   # max fever +4°C

    target = circadian_temp + fever_delta

    # During sleep: heat dissipation drops core temp ~0.3°C below circadian
    if s.sleeping:
        target -= 0.3

    current = s.body.get("core_temp", 37.0)
    # Fast approach (0.3/hr) — temperature responds within ~3 hours
    s.body["core_temp"] = round(current + (target - current) * min(1.0, 0.3 * sim_hours), 2)
    return s


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def advance_circadian(s: BiologicalState, sim_hours: float,
                       hour_of_day: float, event_bus: EventBus) -> BiologicalState:
    """Entry point called by engine. Advances adenosine; other circadian elements deferred."""
    s = _advance_adenosine(s, sim_hours)
    return s


def advance_sleep(s: BiologicalState, sim_hours: float, now: float,
                   hour_of_day: float, cfg: dict, event_bus: EventBus) -> BiologicalState:
    """Stub — sleep/wake state transitions remain in engine.py until SPEC-24."""
    return s
