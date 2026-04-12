"""Endocrine system — thyroid (TSH/T4/T3), sex hormones (estradiol/progesterone/testosterone),
growth hormone, DHEA, prolactin, vasopressin.
Full implementation for SPEC-22.
"""
from __future__ import annotations

import math

from src.sim.bio.state import BiologicalState
from src.sim.chem.units import clamp_chemical
from src.sim.events import EventBus


# ---------------------------------------------------------------------------
# Thyroid axis
# ---------------------------------------------------------------------------

def _advance_thyroid(s: BiologicalState, sim_hours: float) -> BiologicalState:
    """
    Simplified TRH → TSH → T4 → T3 cascade.
    Chronic high cortisol suppresses TSH (stress-induced subclinical hypothyroidism).
    Leptin < 5 (starvation) reduces T3 via adaptive thermogenesis.
    """
    cortisol = s.chemicals.get("cortisol", 250.0)
    leptin   = s.neuroendocrine.get("leptin", 15.0)

    # TSH (approach_rate 0.05/hr — very slow pituitary response)
    tsh_target = 2.0 - max(0.0, cortisol - 500.0) * 0.002
    if leptin < 5.0:
        tsh_target *= 0.7   # starvation blunts thyroid axis
    tsh_target = max(0.1, tsh_target)
    tsh = s.neuroendocrine.get("tsh", 2.0)
    s.neuroendocrine["tsh"] = tsh + (tsh_target - tsh) * min(1.0, 0.05 * sim_hours)

    # T4 driven by TSH (half-life ~7 days → approach_rate 0.02/hr)
    t4_target = max(1.0, min(20.0, s.neuroendocrine["tsh"] * 4.0))
    t4 = s.neuroendocrine.get("t4", 8.0)
    s.neuroendocrine["t4"] = t4 + (t4_target - t4) * min(1.0, 0.02 * sim_hours)

    # T3 converted peripherally from T4 (half-life ~1 day → approach_rate 0.08/hr)
    t3_target = max(20.0, min(400.0, s.neuroendocrine["t4"] * 15.0))
    t3 = s.neuroendocrine.get("t3", 120.0)
    s.neuroendocrine["t3"] = t3 + (t3_target - t3) * min(1.0, 0.08 * sim_hours)

    return s


# ---------------------------------------------------------------------------
# Sex hormones + menstrual cycle
# ---------------------------------------------------------------------------

def _advance_cycle(s: BiologicalState, sim_hours: float) -> BiologicalState:
    """
    Advance menstrual cycle day (1–28). 1 sim-hour = 1/24 day.
    Computes phase-appropriate estradiol and progesterone targets and
    approaches them at physiologically appropriate rates.
    """
    day_advance = sim_hours / 24.0
    new_day     = (s.cycle_day - 1 + day_advance) % 28 + 1
    s.cycle_day = new_day
    day = s.cycle_day

    if day <= 5:
        est_target  = 30.0 + day * 4.0          # menstrual: low rising from 30
        prog_target = 0.3
    elif day <= 13:
        est_target  = 50.0 + (day - 5) * 25.0   # follicular: rising to ~250
        prog_target = 0.5
    elif day <= 14:
        est_target  = 350.0                       # ovulation peak
        prog_target = 0.8
    elif day <= 23:
        est_target  = 350.0 - (day - 14) * 28.0  # early luteal: falling post-ovulation
        prog_target = 1.0 + (day - 14) * 1.5     # rising to ~16 ng/mL
    else:
        est_target  = 50.0                         # late luteal / PMS phase
        prog_target = max(0.3, 16.0 - (day - 23) * 2.5)   # falling

    est  = s.neuroendocrine.get("estradiol", 100.0)
    prog = s.neuroendocrine.get("progesterone", 0.5)
    s.neuroendocrine["estradiol"]    = est  + (est_target  - est)  * min(1.0, 0.08 * sim_hours)
    s.neuroendocrine["progesterone"] = prog + (prog_target - prog) * min(1.0, 0.06 * sim_hours)

    return s


def _advance_testosterone(s: BiologicalState, sim_hours: float) -> BiologicalState:
    """Testosterone at female baseline (~40 ng/dL). Very slow homeostatic return."""
    test = s.neuroendocrine.get("testosterone", 40.0)
    s.neuroendocrine["testosterone"] = test + (40.0 - test) * min(1.0, 0.01 * sim_hours)
    return s


# ---------------------------------------------------------------------------
# Other hormones
# ---------------------------------------------------------------------------

def _advance_growth_hormone(s: BiologicalState, sim_hours: float) -> BiologicalState:
    """
    GH is pulsatile. Main pulse occurs in first 2 hours of sleep.
    BDNF effects from GH are implemented in SPEC-24 (advance_neuroplasticity).
    """
    import time as _time
    gh = s.neuroendocrine.get("growth_hormone", 1.0)

    if s.sleeping and s.sleep_start is not None:
        sleep_elapsed = _time.time() - s.sleep_start
        sleep_hours   = sleep_elapsed / 3600.0
        target = 8.0 if sleep_hours < 2.0 else 0.5   # initial pulse then drops
    else:
        target = 0.5   # daytime low

    s.neuroendocrine["growth_hormone"] = gh + (target - gh) * min(1.0, 0.4 * sim_hours)
    return s


def _advance_dhea(s: BiologicalState, sim_hours: float, hour_of_day: float) -> BiologicalState:
    """DHEA inversely tracks cortisol over the long term — buffer against adrenal exhaustion."""
    cortisol = s.chemicals.get("cortisol", 250.0)
    base = 150.0
    if cortisol > 500.0:
        base -= (cortisol - 500.0) * 0.1
    base += 30.0 * math.cos((hour_of_day - 9) * math.pi / 12)
    base = max(20.0, base)

    dhea = s.neuroendocrine.get("dhea", 150.0)
    # Very slow (approach_rate 0.02/hr) — reflects long-term adrenal state
    s.neuroendocrine["dhea"] = dhea + (base - dhea) * min(1.0, 0.02 * sim_hours)
    return s


def _advance_prolactin(s: BiologicalState, sim_hours: float) -> BiologicalState:
    """Prolactin — peaks during sleep and social reward. Suppressed by dopamine."""
    oxytocin = s.chemicals.get("oxytocin", 4.0)
    dopamine = s.chemicals.get("dopamine", 80.0)
    base = 8.0
    if s.sleeping:
        base += 15.0
    base += max(0.0, oxytocin - 30.0) * 0.3
    base -= max(0.0, dopamine - 100.0) * 0.05
    base = max(2.0, base)

    prolactin = s.neuroendocrine.get("prolactin", 8.0)
    s.neuroendocrine["prolactin"] = prolactin + (base - prolactin) * min(1.0, 0.15 * sim_hours)
    return s


def _advance_vasopressin(s: BiologicalState, sim_hours: float) -> BiologicalState:
    """Vasopressin (ADH) — water conservation + social bonding complement to oxytocin."""
    hydration = s.chemicals.get("hydration", 62.0)
    oxytocin  = s.chemicals.get("oxytocin", 4.0)
    base = 2.0
    if hydration < 58.0:
        base += (58.0 - hydration) * 0.3   # dehydration strongly activates ADH
    base += max(0.0, oxytocin - 20.0) * 0.05
    base = max(0.5, base)

    vp = s.neuroendocrine.get("vasopressin", 2.0)
    s.neuroendocrine["vasopressin"] = vp + (base - vp) * min(1.0, 0.25 * sim_hours)
    return s


# ---------------------------------------------------------------------------
# Cross-effects: neuroendocrine → first-order chemicals
# ---------------------------------------------------------------------------

def _apply_cross_effects(s: BiologicalState, sim_hours: float) -> BiologicalState:
    """
    Apply neuroendocrine → first-order chemical cross-effects.
    These are gentle per-hour nudges — they establish a directional pull
    rather than snapping values.
    """
    t3           = s.neuroendocrine.get("t3", 120.0)
    estradiol    = s.neuroendocrine.get("estradiol", 100.0)
    prog         = s.neuroendocrine.get("progesterone", 0.5)
    prolactin    = s.neuroendocrine.get("prolactin", 8.0)
    dhea         = s.neuroendocrine.get("dhea", 150.0)
    testosterone = s.neuroendocrine.get("testosterone", 40.0)

    # --- T3 (thyroid) ---
    if t3 < 60.0:
        # Hypothyroid: drag monoamines toward lower levels
        penalty = (60.0 - t3) * 0.01 * sim_hours
        s.chemicals["dopamine"]       = clamp_chemical("dopamine",       s.chemicals.get("dopamine", 80.0)       - penalty * 3.0)
        s.chemicals["serotonin"]      = clamp_chemical("serotonin",      s.chemicals.get("serotonin", 22.0)      - penalty * 2.0)
        s.chemicals["norepinephrine"] = clamp_chemical("norepinephrine", s.chemicals.get("norepinephrine", 200.0) - penalty * 2.0)
    elif t3 > 250.0:
        # Hyperthyroid: amplify arousal
        bonus = (t3 - 250.0) * 0.005 * sim_hours
        s.chemicals["norepinephrine"] = clamp_chemical("norepinephrine", s.chemicals.get("norepinephrine", 200.0) + bonus * 2.0)

    # --- Estradiol → serotonin ---
    if estradiol < 50.0:
        # Low estradiol (menstrual / late luteal) → serotonin deficit
        penalty = (50.0 - estradiol) * 0.005 * sim_hours
        s.chemicals["serotonin"] = clamp_chemical("serotonin", s.chemicals.get("serotonin", 22.0) - penalty)

    # --- Progesterone → GABA (allopregnanolone is a GABA-A positive allosteric modulator) ---
    if prog > 2.0:
        bonus = (prog - 2.0) * 0.01 * sim_hours
        s.chemicals["gaba"] = clamp_chemical("gaba", s.chemicals.get("gaba", 3.0) + bonus)

    # --- Prolactin > 40 → dopamine suppression (post-reward refractory period) ---
    if prolactin > 40.0:
        s.chemicals["dopamine"] = clamp_chemical("dopamine",
            s.chemicals.get("dopamine", 80.0) - 5.0 * sim_hours)

    # --- DHEA cross-effects ---
    if dhea > 200.0:
        # Anti-stress buffer: mild cortisol suppression + serotonin support
        s.chemicals["cortisol"]  = clamp_chemical("cortisol",
            s.chemicals.get("cortisol", 250.0) - 0.5 * sim_hours)
        s.chemicals["serotonin"] = clamp_chemical("serotonin",
            s.chemicals.get("serotonin", 22.0) + 0.1 * sim_hours)
    elif dhea < 50.0:
        # Adrenal exhaustion: reduced stress buffering → mild cortisol elevation
        s.chemicals["cortisol"] = clamp_chemical("cortisol",
            s.chemicals.get("cortisol", 250.0) + 0.3 * sim_hours)

    # --- Low testosterone (<20 ng/dL) → mild dopamine drive reduction ---
    if testosterone < 20.0:
        penalty = (20.0 - testosterone) * 0.3 * 0.01 * sim_hours
        s.chemicals["dopamine"] = clamp_chemical("dopamine",
            s.chemicals.get("dopamine", 80.0) - penalty)

    return s


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def advance_endocrine(s: BiologicalState, sim_hours: float,
                       hour_of_day: float, event_bus: EventBus) -> BiologicalState:
    """
    Advance thyroid, sex hormones, GH, DHEA, prolactin, vasopressin,
    then apply neuroendocrine → first-order chemical cross-effects.
    """
    s = _advance_thyroid(s, sim_hours)
    s = _advance_cycle(s, sim_hours)
    s = _advance_testosterone(s, sim_hours)
    s = _advance_growth_hormone(s, sim_hours)
    s = _advance_dhea(s, sim_hours, hour_of_day)
    s = _advance_prolactin(s, sim_hours)
    s = _advance_vasopressin(s, sim_hours)
    s = _apply_cross_effects(s, sim_hours)
    return s
