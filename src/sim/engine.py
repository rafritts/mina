"""
Simulation engine — orchestrates all subsystem advance() calls in dependency order.

SPEC-20: monolithic logic migrated from root state.py.
SPEC-21: amino_acids, endocannabinoids, receptors, substances extracted to subsystems.
         Adenosine (sleep_pressure) migrated to body tier via circadian.py.
SPEC-22+: HPA/endocrine/metabolic/immune/pain extraction.
SPEC-24: allostatic load, BDNF, orexin, core temp; two-process sleep onset.
"""
from __future__ import annotations

import json
import os
import random
import time
from typing import Optional

from src.sim.bio.state import BiologicalState
from src.sim.bio.defaults import CHEMICAL_DEFAULTS
from src.sim.chem.registry import REGISTRY
from src.sim.chem.units import clamp_chemical
from src.sim.events import EventBus

# SPEC-21 subsystems
from src.sim.neuro.amino_acids import advance_amino_acids
from src.sim.neuro.endocannabinoids import advance_endocannabinoids
from src.sim.neuro.receptors import advance_receptors
from src.sim.neuro.substances import advance_substances, SUBSTANCE_DEFS
from src.sim.physio.circadian import _advance_adenosine

# SPEC-22 subsystems
from src.sim.physio.hpa import advance_hpa
from src.sim.physio.endocrine import advance_endocrine
from src.sim.physio.metabolic import advance_metabolic

# SPEC-23 subsystems
from src.sim.physio.immune import advance_immune
from src.sim.physio.pain import advance_pain
from src.sim.physio.autonomic import advance_autonomic

# SPEC-24 subsystems
from src.sim.psych.allostatic import advance_allostatic
from src.sim.physio.circadian import _advance_core_temp, _advance_orexin, compute_sleep_propensity

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CONFIG_FILE = os.path.join(_PROJECT_ROOT, "config.json")


def _load_config() -> dict:
    try:
        with open(_CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _hour_of_day(now: float) -> float:
    lt = time.localtime(now)
    return lt.tm_hour + lt.tm_min / 60.0


def _make_context(state: BiologicalState, hour: float) -> dict:
    return {
        "hour":           hour,
        "sleeping":       state.sleeping,
        # First-order chemicals
        "glucose":        state.chemicals.get("glucose",        CHEMICAL_DEFAULTS.get("glucose", 85.0)),
        "hydration":      state.chemicals.get("hydration",      CHEMICAL_DEFAULTS.get("hydration", 62.0)),
        "cortisol":       state.chemicals.get("cortisol",       CHEMICAL_DEFAULTS.get("cortisol", 250.0)),
        "dopamine":       state.chemicals.get("dopamine",       CHEMICAL_DEFAULTS.get("dopamine", 80.0)),
        "serotonin":      state.chemicals.get("serotonin",      CHEMICAL_DEFAULTS.get("serotonin", 22.0)),
        "oxytocin":       state.chemicals.get("oxytocin",       CHEMICAL_DEFAULTS.get("oxytocin", 4.0)),
        # sleep_pressure now derives from body["adenosine"] via property
        "sleep_pressure": state.sleep_pressure,
        # SPEC-22: neuroendocrine hormones feed baseline_fns for cortisol, serotonin, etc.
        "acth":         state.neuroendocrine.get("acth",         25.0),
        "crh":          state.neuroendocrine.get("crh",          30.0),
        "t3":           state.neuroendocrine.get("t3",           120.0),
        "t4":           state.neuroendocrine.get("t4",           8.0),
        "tsh":          state.neuroendocrine.get("tsh",          2.0),
        "estradiol":    state.neuroendocrine.get("estradiol",    100.0),
        "progesterone": state.neuroendocrine.get("progesterone", 0.5),
        "dhea":         state.neuroendocrine.get("dhea",         150.0),
        "insulin":      state.neuroendocrine.get("insulin",      5.0),
        "ghrelin":      state.neuroendocrine.get("ghrelin",      400.0),
        "leptin":       state.neuroendocrine.get("leptin",       15.0),
        "vasopressin":  state.neuroendocrine.get("vasopressin",  2.0),
        "prolactin":    state.neuroendocrine.get("prolactin",    8.0),
        # Immune — for HPA-immune axis and BDNF suppression
        "il6":               state.immune.get("il6",               3.0),
        "inflammation_index": state.immune.get("inflammation_index", 0.0),
        # Pain — for 2-AG baseline
        "pain_intensity":    state.pain.get("pain_intensity",       0.0),
        # Neuroplasticity — for serotonin/dopamine baseline modulation
        "bdnf":              state.neuroplasticity.get("bdnf",    9000.0),
        "allostatic_load":   state.neuroplasticity.get("allostatic_load", 0.0),
        # Body — for BDNF, orexin, and ACh baselines
        "adenosine":         state.body.get("adenosine",           25.0),
        "growth_hormone":    state.neuroendocrine.get("growth_hormone", 1.0),
    }


def _decay_encoder_momentum(s: BiologicalState, now: float) -> BiologicalState:
    """Half-life ~1800 s (30 min). Decays on wall-clock time, not sim time."""
    real_elapsed = now - s.last_updated
    if real_elapsed > 0 and s.encoder_momentum:
        decay = 0.5 ** (real_elapsed / 1800.0)
        s.encoder_momentum = {
            k: v * decay
            for k, v in s.encoder_momentum.items()
            if v * decay > 0.05
        }
    return s


# Chemicals that are handled by subsystems (not the Phase 1 REGISTRY loop)
_SUBSYSTEM_MANAGED = frozenset({
    "sleep_pressure",   # → body["adenosine"] via circadian.py
    "gaba",             # → amino_acids.py
    "glutamate",        # → amino_acids.py
    "anandamide",       # → endocannabinoids.py (body-stored)
    "two_ag",           # → endocannabinoids.py (body-stored)
    "glucose",          # → metabolic.py (SPEC-22: insulin-mediated clearance)
})


# ---------------------------------------------------------------------------
# Main advance orchestrator
# ---------------------------------------------------------------------------

def advance(state: BiologicalState,
            now: Optional[float] = None,
            event_bus: Optional[EventBus] = None) -> BiologicalState:
    """
    Apply all time-based dynamics since state.last_updated.
    Emits BiologicalEvents to event_bus (if provided).
    Returns updated state.
    """
    if now is None:
        now = time.time()
    if event_bus is None:
        event_bus = EventBus()  # discard if caller doesn't care

    cfg = _load_config()
    compression = float(cfg.get("time_compression_factor", 1.0))
    sim_hours = (now - state.last_updated) * compression / 3600.0

    if sim_hours <= 0:
        return state

    hour_of_day = _hour_of_day(now)
    s = state
    ctx = _make_context(s, hour_of_day)

    # --- SPEC-21 Phase A: amino acids (GABA/glutamate) ---
    # Must run before Phase 1 so REGISTRY interactions (GABA→cortisol) use fresh values.
    s = advance_amino_acids(s, sim_hours, event_bus)

    # --- SPEC-22 Phase HPA: CRH, ACTH, cascade queue ---
    # Must run before Phase 1 so ACTH is current when cortisol baseline_fn fires.
    s = advance_hpa(s, sim_hours, now, hour_of_day, event_bus)

    # --- SPEC-22 Phase Endocrine: thyroid, sex hormones, GH, DHEA, prolactin, vasopressin ---
    s = advance_endocrine(s, sim_hours, hour_of_day, event_bus)

    # --- SPEC-22 Phase Metabolic: insulin, glucose, ghrelin, leptin ---
    s = advance_metabolic(s, sim_hours, hour_of_day, event_bus)

    # Rebuild context after SPEC-22 subsystems so Phase 1 baseline_fns see current ACTH/T3/etc.
    ctx = _make_context(s, hour_of_day)

    # --- Phase 1: each chemical advances toward its own baseline ---

    for name, profile in REGISTRY.items():
        if name in _SUBSYSTEM_MANAGED:
            continue  # handled by subsystem

        current = s.chemicals.get(name, CHEMICAL_DEFAULTS.get(name, 0.0))

        if name == "hydration":
            # Pure decay: -0.4% TBW/hr; restored only by drink tool
            s.chemicals[name] = clamp_chemical(name, current - 0.4 * sim_hours)

        elif name == "melatonin":
            # Pure circadian formula — snap to computed value each tick
            target = (profile.baseline_fn(hour_of_day, ctx)
                      if profile.baseline_fn else profile.resting_baseline)
            s.chemicals[name] = clamp_chemical(name, target)

        elif name == "endorphins":
            # Asymmetric: fast decay when above baseline, slow recovery when below
            baseline = 12.0
            if current > baseline:
                new_val = current - 18.0 * sim_hours
                s.chemicals[name] = clamp_chemical(name, max(baseline, new_val))
            else:
                gap = baseline - current
                s.chemicals[name] = clamp_chemical(
                    name, current + gap * min(1.0, 0.05 * sim_hours)
                )

        else:
            # Standard: approach dynamic or fixed baseline at approach_rate per hour
            target = (profile.baseline_fn(hour_of_day, ctx)
                      if profile.baseline_fn else profile.resting_baseline)
            gap = target - current
            s.chemicals[name] = clamp_chemical(
                name, current + gap * min(1.0, profile.approach_rate * sim_hours)
            )

    # --- Phase 2: cross-interactions from REGISTRY ---
    # TODO SPEC-22: extend for neuroendocrine tier targets

    for name, profile in REGISTRY.items():
        if name in _SUBSYSTEM_MANAGED and name not in ("gaba", "glutamate"):
            continue  # body-stored; no chemical interactions
        source_val = s.chemicals.get(name, 0.0)
        for interaction in profile.interactions:
            meets = (
                (interaction.condition == "above" and source_val > interaction.threshold) or
                (interaction.condition == "below" and source_val < interaction.threshold)
            )
            if meets:
                target_val = s.chemicals.get(interaction.target, 0.0)
                new_val = target_val + interaction.rate_per_hour * sim_hours
                # Protective floor: suppressive interactions can't push below critical_low
                if interaction.rate_per_hour < 0:
                    target_profile = REGISTRY.get(interaction.target)
                    if target_profile and target_profile.critical_low > 0:
                        new_val = max(target_profile.critical_low, new_val)
                s.chemicals[interaction.target] = clamp_chemical(interaction.target, new_val)

    # Additional cross-effects not captured in REGISTRY
    sp = s.sleep_pressure  # reads from body["adenosine"]
    if sp > 50:
        s.chemicals["serotonin"] = clamp_chemical(
            "serotonin", s.chemicals.get("serotonin", 22.0) - 0.3 * sim_hours
        )
    if sp > 70:
        s.chemicals["dopamine"] = clamp_chemical(
            "dopamine", s.chemicals.get("dopamine", 80.0) - 1.0 * sim_hours
        )

    glu = s.chemicals.get("glucose", 85.0)
    if glu < 55:
        s.chemicals["serotonin"] = clamp_chemical(
            "serotonin", s.chemicals.get("serotonin", 22.0) - 0.6 * sim_hours
        )
        s.chemicals["dopamine"] = clamp_chemical(
            "dopamine", s.chemicals.get("dopamine", 80.0) - 1.5 * sim_hours
        )

    # --- SPEC-23 Phase Immune: cytokines, sickness behavior ---
    # Runs after Phase 1/2 so cortisol and glutamate reflect the current tick.
    s = advance_immune(s, sim_hours, event_bus)

    # --- SPEC-23 Phase Pain: Substance P, PGE2, gate control, central sensitization ---
    # Runs after immune so IL-1β / TNF-α are current; uses last-tick anandamide (one-tick lag).
    s = advance_pain(s, sim_hours, event_bus)

    # --- SPEC-23 Phase Autonomic: vagal tone + HRV (derived, no dynamics) ---
    s = advance_autonomic(s, sim_hours, event_bus)

    # --- SPEC-24 Phase Allostatic: BDNF, allostatic load, synaptic potentiation ---
    # Runs after immune and pain so current-tick inflammation and pain are captured.
    s = advance_allostatic(s, sim_hours, event_bus)

    # --- SPEC-24 Phase Circadian: orexin + core temperature ---
    # Orexin advances toward its circadian baseline (adenosine/cortisol-modulated).
    # Core temp follows circadian curve + fever from current-tick cytokines.
    s = _advance_orexin(s, sim_hours, hour_of_day)
    s = _advance_core_temp(s, sim_hours, hour_of_day)

    # --- SPEC-21 Phase B: endocannabinoids ---
    s = advance_endocannabinoids(s, sim_hours, event_bus)

    # --- SPEC-21 Phase C: receptor sensitivity ---
    s = advance_receptors(s, sim_hours)

    # --- Phase 3: substance decay + withdrawal ---

    s = advance_substances(s, sim_hours, now, event_bus)

    # --- Encoder momentum decay ---
    s = _decay_encoder_momentum(s, now)

    # --- Tolerance decay (legacy scalar — receptor_sensitivity is the new model) ---
    for substance in list(s.tolerance.keys()):
        s.tolerance[substance] = max(0.0, s.tolerance[substance] - 0.01 * sim_hours)
        if s.tolerance[substance] == 0.0:
            del s.tolerance[substance]

    # --- Phase 4: adenosine + sleep/wake mechanics ---

    # Advance adenosine (replaces direct sleep_pressure manipulation)
    s = _advance_adenosine(s, sim_hours)

    sleep_p = s.sleep_pressure  # property reads from body["adenosine"]

    if s.sleeping:
        scheduled_wake   = s.sleep_expected_wake and now >= s.sleep_expected_wake
        pressure_depleted = sleep_p <= 0.0
        if scheduled_wake or pressure_depleted:
            s.sleeping        = False
            s.sleep_start     = None
            s.sleep_expected_wake = None
            # Morning cortisol surge (CAR — cortisol awakening response)
            ctx_wake = _make_context(s, hour_of_day)
            baseline_cort = (REGISTRY["cortisol"].baseline_fn(hour_of_day, ctx_wake)
                             if REGISTRY["cortisol"].baseline_fn else 250.0)
            s.chemicals["cortisol"] = clamp_chemical(
                "cortisol", baseline_cort + random.uniform(40, 120)
            )
            s.chemicals["melatonin"] = clamp_chemical(
                "melatonin",
                REGISTRY["melatonin"].baseline_fn(hour_of_day, ctx_wake)
                if REGISTRY["melatonin"].baseline_fn else 5.0,
            )
            s.chemicals["endorphins"] = clamp_chemical(
                "endorphins",
                s.chemicals.get("endorphins", 12.0) + random.uniform(3, 12),
            )

    # --- Auto-sleep onset (SPEC-24: two-process propensity model) ---
    # Replaces the old melatonin >= 195 threshold with a physiologically grounded
    # sleep propensity score that integrates both Process S (adenosine) and
    # Process C (melatonin vs orexin).
    if not s.sleeping:
        propensity = compute_sleep_propensity(s)
        sleep_start_hour = float(cfg.get("sleep_window_start", 1.0))
        sleep_end_hour   = float(cfg.get("sleep_window_end", 9.0))
        in_window = (sleep_start_hour <= hour_of_day < sleep_end_hour or
                     hour_of_day < sleep_end_hour)

        # In window: 70 is sufficient; any time: 90 overrides (exhaustion collapse)
        threshold = 70.0 if in_window else 90.0

        if propensity >= threshold:
            s.sleeping    = True
            s.sleep_start = now
            lt = time.localtime(now)
            wake = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                                int(sleep_end_hour), int((sleep_end_hour % 1) * 60), 0,
                                lt.tm_wday, lt.tm_yday, lt.tm_isdst))
            if wake <= now:
                wake += 86400
            s.sleep_expected_wake = wake
            try:
                from log import log
                log("SLEEP", f"Auto-onset: propensity={propensity:.1f} "
                    f"(adenosine={s.body['adenosine']:.1f} nmol/L, "
                    f"melatonin={s.chemicals.get('melatonin', 0):.0f} pg/mL, "
                    f"orexin={s.neuroendocrine.get('orexin', 300):.0f} pg/mL) — "
                    f"wake at {time.strftime('%H:%M', time.localtime(wake))}")
            except ImportError:
                pass

    s.last_updated = now
    return s
