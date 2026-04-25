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

from src.engine.bio.state import BiologicalState
from src.engine.bio.defaults import CHEMICAL_DEFAULTS
from src.engine.chem.registry import REGISTRY
from src.engine.chem.units import clamp_chemical
from src.engine.events import EventBus

# SPEC-21 subsystems
from src.engine.neuro.amino_acids import advance_amino_acids
from src.engine.neuro.endocannabinoids import advance_endocannabinoids
from src.engine.neuro.receptors import advance_receptors
from src.engine.neuro.substances import advance_substances, SUBSTANCE_DEFS
from src.engine.physio.circadian import _advance_adenosine

# SPEC-22 subsystems
from src.engine.physio.hpa import advance_hpa
from src.engine.physio.endocrine import advance_endocrine
from src.engine.physio.metabolic import advance_metabolic

# SPEC-23 subsystems
from src.engine.physio.immune import advance_immune
from src.engine.physio.pain import advance_pain
from src.engine.physio.autonomic import advance_autonomic

# SPEC-24 subsystems
from src.engine.psych.allostatic import advance_allostatic
from src.engine.physio.circadian import _advance_core_temp, _advance_orexin, compute_sleep_propensity

from src.engine.constants import (
    AUTO_SLEEP_PROPENSITY_IN_WINDOW,
    AUTO_SLEEP_PROPENSITY_OVERRIDE,
    ISOLATION_CONTACT_GRACE_HOURS,
    ISOLATION_ACCUMULATION_BASE,
    ISOLATION_ACCUMULATION_E_SCALE,
    ISOLATION_DECAY_RATE,
    ISOLATION_CORTISOL_S2,
    ISOLATION_DOPAMINE_S2,
    ISOLATION_CORTISOL_S3,
    ISOLATION_DOPAMINE_S3,
    ISOLATION_NOREPI_S3,
    ISOLATION_BDNF_S3,
    ISOLATION_PROLACTIN_S3,
    ISOLATION_ANANDAMIDE_S4,
    ISOLATION_CORTISOL_RECOVERY,
    ISOLATION_DOPAMINE_RECOVERY,
    ISOLATION_NOREPI_RECOVERY,
    ISOLATION_PROLACTIN_RECOVERY,
    HEDONIC_SETPOINT_BIOLOGICAL_FLOOR,
    HEDONIC_SETPOINT_DRIFT_UP_RATE,
    HEDONIC_SETPOINT_DRIFT_DOWN_RATE,
    CRAVING_ENDORPHIN_WEIGHT,
    CRAVING_DOPAMINE_WEIGHT,
    CRAVING_OXYTOCIN_WEIGHT,
    CRAVING_SEROTONIN_WEIGHT,
    CRAVING_ENDORPHIN_MAX,
    CRAVING_DOPAMINE_MIN,
    CRAVING_DOPAMINE_MAX,
    CRAVING_OXYTOCIN_MAX,
    CRAVING_SEROTONIN_MIN,
    CRAVING_SEROTONIN_MAX,
)

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
        # SPEC-30: chronic social contact factor for serotonin baseline_fn
        "isolation_pressure": state.body.get("isolation_pressure",  0.0),
    }


def _advance_isolation_pressure(s: BiologicalState, sim_hours: float, now: float) -> BiologicalState:
    """
    SPEC-28: Isolation pressure accumulates after the contact grace period and decays
    rapidly during active contact. Extraversion amplifies accumulation rate.
    """
    try:
        from src.config.config import load_config
        E = float(load_config().get("big5", {}).get("extraversion", 50)) / 100.0
    except Exception:
        E = 0.5

    recent_contact_ts = s.body.get("recent_contact_ts", 0.0)
    hours_since_contact = (now - recent_contact_ts) / 3600.0 if recent_contact_ts > 0 else 999.0

    current = s.body.get("isolation_pressure", 0.0)

    if hours_since_contact <= ISOLATION_CONTACT_GRACE_HOURS:
        # Active contact window: pressure decays
        new_val = max(0.0, current - ISOLATION_DECAY_RATE * sim_hours)
    else:
        # Beyond grace period: pressure accumulates; extroverts feel it more
        rate = ISOLATION_ACCUMULATION_BASE + E * ISOLATION_ACCUMULATION_E_SCALE
        new_val = min(100.0, current + rate * sim_hours)

    s.body["isolation_pressure"] = new_val
    return s


def _isolation_stage(isolation_days: float) -> int:
    """Map days-since-contact to isolation stage 0–5."""
    if isolation_days < 0.5:
        return 0
    elif isolation_days < 1.5:
        return 1
    elif isolation_days < 3.0:
        return 2
    elif isolation_days < 5.0:
        return 3
    elif isolation_days < 7.0:
        return 4
    else:
        return 5


def _apply_isolation_stage_effects(
    state: BiologicalState,
    isolation_days: float,
    tick_hours: float,
) -> BiologicalState:
    """
    SPEC-31: Apply chronic neurochemical drift from prolonged isolation.
    All effects are slow-moving baselines, not acute spikes.
    Stage 0/1 effects are already covered by SPEC-28/30 isolation_pressure
    and serotonin_baseline_fn — no additional drift needed below Stage 2.
    """
    stage = _isolation_stage(isolation_days)

    if stage < 2:
        return state

    # --- Stage 2 base rates ---
    cortisol_drift  = ISOLATION_CORTISOL_S2
    dopamine_drag   = ISOLATION_DOPAMINE_S2
    norepi_drift    = 0.0
    bdnf_drain      = 0.0
    prolactin_drift = 0.0
    anandamide_drain = 0.0

    if stage >= 3:
        cortisol_drift  = ISOLATION_CORTISOL_S3
        dopamine_drag   = ISOLATION_DOPAMINE_S3
        norepi_drift    = ISOLATION_NOREPI_S3
        bdnf_drain      = ISOLATION_BDNF_S3
        prolactin_drift = ISOLATION_PROLACTIN_S3

    if stage >= 4:
        # Stage 4: double Stage 3 rates + anandamide drain
        cortisol_drift  *= 2.0
        dopamine_drag   *= 2.0
        norepi_drift    *= 2.0
        bdnf_drain      *= 2.0
        prolactin_drift *= 2.0
        anandamide_drain = ISOLATION_ANANDAMIDE_S4

    if stage >= 5:
        # Stage 5: 1.5x Stage 4 rates (motivational collapse)
        cortisol_drift  *= 1.5
        dopamine_drag   *= 1.5
        norepi_drift    *= 1.5
        bdnf_drain      *= 1.5
        prolactin_drift *= 1.5
        anandamide_drain *= 1.5

    # SPEC-33: scale isolation pain by bonding dimension — deep bond → isolation hurts more.
    # A caring relationship that's absent stings more than an indifferent one.
    # Read from relationship file, not raw oxytocin (which decays in absence).
    try:
        from src.config.config import RELATIONSHIP_DIR as _REL_DIR
        from src.brain.hippocampus.hippocampus import _get_net_relationship_dimensions
        _bondings = []
        if os.path.exists(_REL_DIR):
            for _fn in os.listdir(_REL_DIR):
                if _fn.endswith(".md"):
                    _net_dims = _get_net_relationship_dimensions(_fn[:-3])
                    _bondings.append(float(_net_dims.get("bonding", 0.0)))
        _net_bonding = sum(_bondings) / len(_bondings) if _bondings else 0.0
        bonding_scale = max(0.3, 1.0 + _net_bonding * 0.2)
    except Exception:
        bonding_scale = 1.0

    cortisol_drift *= bonding_scale
    dopamine_drag  *= bonding_scale

    # Apply drift — chemicals are clamped by clamp_chemical after
    state.chemicals["cortisol"]       = max(0.0, state.chemicals.get("cortisol",      250.0) + cortisol_drift  * tick_hours)
    state.chemicals["dopamine"]       = max(0.0, state.chemicals.get("dopamine",       80.0) - dopamine_drag   * tick_hours)
    state.chemicals["norepinephrine"] = max(0.0, state.chemicals.get("norepinephrine", 200.0) + norepi_drift    * tick_hours)
    state.neuroplasticity["bdnf"]     = max(0.0, state.neuroplasticity.get("bdnf",   9000.0) - bdnf_drain      * tick_hours)
    state.neuroendocrine["prolactin"] = max(0.0, state.neuroendocrine.get("prolactin",  8.0) + prolactin_drift  * tick_hours)
    state.body["anandamide"]          = max(0.0, state.body.get("anandamide",           1.5) - anandamide_drain * tick_hours)

    return state


def _apply_isolation_recovery(
    state: BiologicalState,
    tick_hours: float,
) -> BiologicalState:
    """
    SPEC-31: Partial reversal of isolation drift during active contact window.
    Only applies when hours_since_contact < ISOLATION_CONTACT_GRACE_HOURS.
    BDNF is intentionally excluded — it recovers at SPEC-24's natural rate.
    """
    state.chemicals["cortisol"]       = max(0.0, state.chemicals.get("cortisol",      250.0) - ISOLATION_CORTISOL_RECOVERY  * tick_hours)
    state.chemicals["dopamine"]       = min(240.0, state.chemicals.get("dopamine",     80.0) + ISOLATION_DOPAMINE_RECOVERY  * tick_hours)
    state.chemicals["norepinephrine"] = max(0.0, state.chemicals.get("norepinephrine", 200.0) - ISOLATION_NOREPI_RECOVERY    * tick_hours)
    state.neuroendocrine["prolactin"] = max(2.0, state.neuroendocrine.get("prolactin",   8.0) - ISOLATION_PROLACTIN_RECOVERY * tick_hours)
    return state


def _advance_hedonic_setpoint(s: BiologicalState, sim_hours: float) -> BiologicalState:
    """
    SPEC-34: Hedonic setpoint drifts up fast toward sustained reward peaks and decays
    slowly back to the biological floor, modelling allostatic setpoint shift.
    Craving = setpoint - current reward_reality (computed in derived.py).
    """
    endorphin_norm = min(100.0, max(0.0, s.chemicals.get("endorphins", 12.0) / CRAVING_ENDORPHIN_MAX * 100.0))
    dopamine_norm  = min(100.0, max(0.0,
        (s.chemicals.get("dopamine", 80.0) - CRAVING_DOPAMINE_MIN) /
        (CRAVING_DOPAMINE_MAX - CRAVING_DOPAMINE_MIN) * 100.0))
    oxytocin_norm  = min(100.0, max(0.0, s.chemicals.get("oxytocin", 4.0) / CRAVING_OXYTOCIN_MAX * 100.0))
    serotonin_norm = min(100.0, max(0.0,
        (s.chemicals.get("serotonin", 22.0) - CRAVING_SEROTONIN_MIN) /
        (CRAVING_SEROTONIN_MAX - CRAVING_SEROTONIN_MIN) * 100.0))

    reward_reality = (
        endorphin_norm * CRAVING_ENDORPHIN_WEIGHT
        + dopamine_norm  * CRAVING_DOPAMINE_WEIGHT
        + oxytocin_norm  * CRAVING_OXYTOCIN_WEIGHT
        + serotonin_norm * CRAVING_SEROTONIN_WEIGHT
    )

    current = s.body.get("hedonic_setpoint", HEDONIC_SETPOINT_BIOLOGICAL_FLOOR)

    if reward_reality > current:
        # Reward above setpoint: drift up fast
        new_val = current + (reward_reality - current) * HEDONIC_SETPOINT_DRIFT_UP_RATE * sim_hours
    else:
        # Reward below setpoint: slow decay back to biological floor
        new_val = current + (HEDONIC_SETPOINT_BIOLOGICAL_FLOOR - current) * HEDONIC_SETPOINT_DRIFT_DOWN_RATE * sim_hours

    s.body["hedonic_setpoint"] = max(HEDONIC_SETPOINT_BIOLOGICAL_FLOOR, min(100.0, new_val))
    return s


def _process_secretion_queue(s: BiologicalState, sim_hours: float) -> BiologicalState:
    """
    SPEC-29 Layer 3: release pending neurotransmitter drip entries.
    Each entry releases up to rate_per_sim_hour * sim_hours per tick.
    Handles both positive and negative remaining (e.g. cortisol suppression).
    """
    if not s.secretion_queue:
        return s

    for entry in s.secretion_queue:
        remaining = entry["remaining"]
        released  = entry["rate_per_sim_hour"] * sim_hours
        if remaining >= 0:
            release = min(remaining, released)
        else:
            release = max(remaining, -released)
        chem    = entry["chemical"]
        current = s.chemicals.get(chem, 0.0)
        s.chemicals[chem] = clamp_chemical(chem, current + release)
        entry["remaining"] -= release

    s.secretion_queue = [e for e in s.secretion_queue if abs(e["remaining"]) > 0.05]
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
            # SPEC-29: exponential decay toward baseline, half-life ~25 minutes.
            # Replaces linear 18 units/hr which produced staircase accumulation.
            baseline = 12.0
            if current > baseline:
                half_life_hours = 25.0 / 60.0
                decay_factor    = 0.5 ** (sim_hours / half_life_hours)
                excess          = current - baseline
                s.chemicals[name] = clamp_chemical(name, baseline + excess * decay_factor)
            else:
                gap = baseline - current
                s.chemicals[name] = clamp_chemical(
                    name, current + gap * min(1.0, 0.05 * sim_hours)
                )

        elif name == "epinephrine":
            # Exponential decay toward baseline, half-life ~2 minutes (plasma clearance via COMT/MAO).
            # The linear approach_rate=0.85 formula gave an effective ~49-min half-life — wildly wrong.
            # Sustained arousal after a spike is carried by norepinephrine and cortisol, not epinephrine.
            baseline = profile.resting_baseline  # 45.0 pg/mL
            if current > baseline:
                half_life_hours = 2.0 / 60.0
                decay_factor    = 0.5 ** (sim_hours / half_life_hours)
                excess          = current - baseline
                s.chemicals[name] = clamp_chemical(name, baseline + excess * decay_factor)
            else:
                # Below baseline: restore at the normal approach rate
                gap = baseline - current
                s.chemicals[name] = clamp_chemical(
                    name, current + gap * min(1.0, profile.approach_rate * sim_hours)
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

    # --- SPEC-29: secretion queue drip release ---
    s = _process_secretion_queue(s, sim_hours)

    # --- Tolerance decay (legacy scalar — receptor_sensitivity is the new model) ---
    for substance in list(s.tolerance.keys()):
        s.tolerance[substance] = max(0.0, s.tolerance[substance] - 0.01 * sim_hours)
        if s.tolerance[substance] == 0.0:
            del s.tolerance[substance]

    # --- Phase 4: adenosine + sleep/wake mechanics ---

    # Advance adenosine (replaces direct sleep_pressure manipulation)
    sleep_hours_needed = float(cfg.get("sleep_hours_needed", 8.0))
    s = _advance_adenosine(s, sim_hours, sleep_hours_needed)

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
            # SPEC-29: sleep re-sensitization — habituation window decays during sleep.
            # Age each stimulus_window entry by doubling its apparent age (2× time shift).
            # Sensitization records are NOT decayed — attachment persists across sleep.
            if s.stimulus_window:
                fresh = []
                for entry in s.stimulus_window:
                    e = dict(entry)
                    # Double apparent age: ts = 2*ts - now (subtracts current elapsed twice)
                    e["ts"] = 2.0 * e["ts"] - now
                    fresh.append(e)
                s.stimulus_window = fresh

    # --- Auto-sleep onset (SPEC-24: two-process propensity model) ---
    # Replaces the old melatonin >= 195 threshold with a physiologically grounded
    # sleep propensity score that integrates both Process S (adenosine) and
    # Process C (melatonin vs orexin).
    if not s.sleeping:
        propensity = compute_sleep_propensity(s)
        sleep_start_hour = float(cfg.get("sleep_window_start", 1.0))
        sleep_end_hour   = float(cfg.get("sleep_window_end", 9.0))
        # Handle windows that span midnight (e.g. start=23, end=7) vs same-day (start=4, end=8)
        if sleep_start_hour > sleep_end_hour:
            in_window = hour_of_day >= sleep_start_hour or hour_of_day < sleep_end_hour
        else:
            in_window = sleep_start_hour <= hour_of_day < sleep_end_hour

        # In window: propensity threshold is lower; exhaustion can override any time
        threshold = AUTO_SLEEP_PROPENSITY_IN_WINDOW if in_window else AUTO_SLEEP_PROPENSITY_OVERRIDE

        if propensity >= threshold:
            s.sleeping    = True
            s.sleep_start = now
            lt = time.localtime(now)
            # Hard ceiling: the configured end of the sleep window
            ceiling = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                                   int(sleep_end_hour), int((sleep_end_hour % 1) * 60), 0,
                                   lt.tm_wday, lt.tm_yday, lt.tm_isdst))
            if ceiling <= now:
                ceiling += 86400
            # Normal wake: sleep_hours_needed hours from onset, capped at ceiling
            wake = min(now + sleep_hours_needed * 3600, ceiling)
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

    # --- SPEC-28: isolation pressure accumulation / contact decay ---
    s = _advance_isolation_pressure(s, sim_hours, now)

    # --- SPEC-31: isolation stage neurochemistry ---
    recent_contact_ts = s.body.get("recent_contact_ts", 0.0)
    hours_since_contact = (now - recent_contact_ts) / 3600.0 if recent_contact_ts > 0 else 999.0
    isolation_days = hours_since_contact / 24.0
    stage = _isolation_stage(isolation_days)
    # Track peak stage since last contact (used by adjudicator for recovery context)
    s.body["peak_isolation_stage"] = max(int(s.body.get("peak_isolation_stage", 0)), stage)
    if hours_since_contact <= ISOLATION_CONTACT_GRACE_HOURS:
        # Contact window: partial recovery of isolation-driven drift
        s = _apply_isolation_recovery(s, sim_hours)
        s.body["peak_isolation_stage"] = 0
    elif stage >= 2:
        # Beyond Stage 1: chronic neurochemical deterioration
        s = _apply_isolation_stage_effects(s, isolation_days, sim_hours)

    # --- SPEC-34: hedonic setpoint drift ---
    s = _advance_hedonic_setpoint(s, sim_hours)

    s.last_updated = now
    return s


# ---------------------------------------------------------------------------
# SPEC-32: Duration query helper for bio_history timeseries
# ---------------------------------------------------------------------------

def hours_above_threshold(
    bio_history: list[dict],
    field_path: str,
    threshold: float,
) -> float:
    """
    Return how many hours the given field has continuously been above threshold,
    counting backwards from the most recent entry.

    field_path uses dot notation, e.g. "chemicals.cortisol" or "second_order.anxiety".
    Returns 0.0 if the field is not found or the condition is not currently met.
    """
    if not bio_history:
        return 0.0

    keys = field_path.split(".")

    def _get(entry: dict) -> float | None:
        val = entry
        for k in keys:
            if not isinstance(val, dict):
                return None
            val = val.get(k)
        return float(val) if val is not None else None

    # Walk backwards until the condition is no longer met
    most_recent = bio_history[-1]
    if (_get(most_recent) or 0.0) <= threshold:
        return 0.0

    earliest_ts = most_recent.get("ts", 0.0)
    for entry in reversed(bio_history):
        val = _get(entry)
        if val is None or val <= threshold:
            break
        earliest_ts = entry.get("ts", earliest_ts)

    latest_ts = most_recent.get("ts", 0.0)
    return (latest_ts - earliest_ts) / 3600.0
