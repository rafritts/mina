"""
Tick — continuous chemical dynamics run every 10 seconds.

Handles:
  - Phasic decay (exponential half-life per chemical)
  - Tonic approach to setpoint (gap closure)
  - Setpoint adaptation (slow drift from chronic exposure)
  - Class 2 accumulation from sustained Class 1 elevation
  - HPA cascade (CRH drives cortisol rise)
  - Opponent processes (continuous drag when one chemical is elevated)
  - Circadian offsets for time-of-day baseline shifts
  - Sleep pressure (adenosine accumulation/clearance)

The tick is state-in, state-out. The Sim class owns the lock and threading.
"""
from __future__ import annotations

import math
import time

from .state import ChemicalState, ChemicalLevel
from .params import (
    CHEMICAL_PARAMS,
    OPPONENT_PROCESSES,
    CLASS2_ACCUMULATION,
    HPA,
    CIRCADIAN,
)


def _normalized(level: ChemicalLevel, params: dict) -> float:
    """Compute 0-10 normalized value (tonic + phasic) / normalization_max * 10."""
    combined = level.tonic + level.phasic
    raw = combined / params["normalization_max"] * 10.0
    return max(0.0, raw)


def _hour_of_day(now: float) -> float:
    lt = time.localtime(now)
    return lt.tm_hour + lt.tm_min / 60.0


def _circadian_offset(chemical: str, hour: float) -> float:
    """Sinusoidal circadian offset in nM. Zero if not circadian-driven."""
    c = CIRCADIAN.get(chemical)
    if not c:
        return 0.0
    peak = c["peak_hour"]
    amp  = c["amplitude_nM"]
    phase = 2 * math.pi * (hour - peak) / 24.0
    return amp * math.cos(phase)


def tick(state: ChemicalState, dt: float, sleeping: bool = False) -> ChemicalState:
    """
    Advance all chemical dynamics by dt seconds.
    Returns the updated state (mutates in place and returns self).
    """
    now  = time.time()
    hour = _hour_of_day(now)

    levels = state.levels
    params = CHEMICAL_PARAMS

    # Build a snapshot of current normalized values for Class 2 accumulation
    norm_snapshot: dict[str, float] = {}
    for name, lvl in levels.items():
        p = params.get(name)
        if p:
            norm_snapshot[name] = _normalized(lvl, p)

    # ── Phase 1: phasic decay ────────────────────────────────────────────────
    for name, lvl in levels.items():
        p = params.get(name)
        if not p or lvl.phasic == 0.0:
            continue
        hl = p["phasic_half_life_s"]
        # Sleep clears phasic faster for monoamines (CNS quiets during NREM)
        if sleeping and p["class"] == 1:
            hl *= 0.5
        decay = 0.5 ** (dt / hl)
        lvl.phasic *= decay

    # ── Phase 2: tonic approach to setpoint ──────────────────────────────────
    for name, lvl in levels.items():
        p = params.get(name)
        if not p:
            continue
        rate = p["tonic_decay_rate"]
        target = lvl.setpoint + _circadian_offset(name, hour)
        gap = target - lvl.tonic
        lvl.tonic += gap * min(1.0, rate * dt / 10.0)  # rate is per-tick (10s)

    # ── Phase 3: setpoint adaptation (slow drift from chronic exposure) ───────
    for name, lvl in levels.items():
        p = params.get(name)
        if not p:
            continue
        adapt_rate = p["setpoint_adapt_rate"]
        # Setpoint drifts toward the current tonic level (habituation)
        gap = lvl.tonic - lvl.setpoint
        lvl.setpoint += gap * min(1.0, adapt_rate * dt / 10.0)

    # ── Phase 4: Class 2 accumulation from sustained Class 1 elevation ───────
    for target_chem, spec in CLASS2_ACCUMULATION.items():
        lvl = levels.get(target_chem)
        p   = params.get(target_chem)
        if not lvl or not p:
            continue

        weighted = sum(
            spec["drivers"].get(src, 0.0) * norm_snapshot.get(src, 0.0)
            for src in spec["drivers"]
        )
        if weighted > spec["threshold"]:
            excess = weighted - spec["threshold"]
            accumulation = spec["rate_nM_per_tick"] * excess * (dt / 10.0)
            lvl.phasic += accumulation

    # ── Phase 5: HPA cascade ─────────────────────────────────────────────────
    # CRH accumulates when NE is elevated above threshold (threat axis proxy)
    ne_norm = norm_snapshot.get("norepinephrine", 0.0)
    epi_norm = norm_snapshot.get("epinephrine", 0.0)
    crh_lvl = levels.get("crh")
    if crh_lvl and (ne_norm + 0.5 * epi_norm) > HPA["crh_driver_threshold_nM"]:
        # NE sustained above threshold → CRH accumulation
        crh_lvl.phasic += HPA["crh_accumulation_nM_per_s"] * dt
    # CRH natural decay (already handled by Phase 1 phasic decay above)

    # Cortisol rises from sustained CRH (slow, 30-min lag modeled as low rate)
    crh_normalized = _normalized(crh_lvl, params["crh"]) if crh_lvl else 0.0
    cortisol_lvl = levels.get("cortisol")
    if cortisol_lvl and crh_normalized > HPA["cortisol_driver_threshold_normalized"]:
        cortisol_lvl.phasic += HPA["cortisol_rise_nM_per_s"] * dt

    # ── Phase 6: Opponent processes ───────────────────────────────────────────
    for src_name, threshold, tgt_name, drag_nM in OPPONENT_PROCESSES:
        src_norm = norm_snapshot.get(src_name, 0.0)
        if src_norm < threshold:
            continue
        tgt_lvl = levels.get(tgt_name)
        if not tgt_lvl:
            continue
        # Drag on phasic first, then tonic if phasic is depleted
        drag = drag_nM * (dt / 10.0) * (src_norm - threshold)
        if tgt_lvl.phasic >= drag:
            tgt_lvl.phasic -= drag
        else:
            remaining = drag - tgt_lvl.phasic
            tgt_lvl.phasic = 0.0
            tgt_lvl.tonic = max(0.0, tgt_lvl.tonic - remaining)

    # ── Phase 7: Adenosine sleep pressure ─────────────────────────────────────
    adenosine_lvl = levels.get("adenosine")
    if adenosine_lvl:
        if sleeping:
            # Clears ~2× faster during sleep (glymphatic clearance)
            hl = params["adenosine"]["phasic_half_life_s"] / 2.0
            adenosine_lvl.tonic *= 0.5 ** (dt / hl)
        else:
            # Accumulates with wakefulness (rate: approach from setpoint is handled above,
            # but we add a small wakefulness-driven accumulation on phasic)
            adenosine_lvl.phasic += 0.5 * (dt / 10.0)  # slow accumulation per tick

    # ── Phase 8: Floor enforcement (nothing goes negative) ────────────────────
    for lvl in levels.values():
        lvl.tonic   = max(0.0, lvl.tonic)
        lvl.phasic  = max(0.0, lvl.phasic)
        lvl.setpoint = max(0.0, lvl.setpoint)

    state.last_updated = now
    return state


def build_initial_state(big5: dict[str, float]) -> ChemicalState:
    """
    Initialize ChemicalState from CHEMICAL_PARAMS, applying Big 5 setpoint biases.
    Called once at startup if no persisted state exists.
    """
    from .params import BIG5_SETPOINT_BIAS

    levels: dict[str, ChemicalLevel] = {}

    for name, p in CHEMICAL_PARAMS.items():
        base = p["tonic_setpoint"]
        levels[name] = ChemicalLevel(
            tonic=base,
            setpoint=base,
            phasic=0.0,
            sensitivity=1.0,
        )

    # Apply Big 5 setpoint biases
    for trait, biases in BIG5_SETPOINT_BIAS.items():
        trait_val = big5.get(trait, 50.0)
        trait_frac = (trait_val - 50.0) / 50.0  # centered at 0, range -1 to +1
        for chem, scale in biases.items():
            lvl = levels.get(chem)
            if lvl:
                delta = lvl.setpoint * scale * trait_frac
                lvl.setpoint += delta
                lvl.tonic    += delta

    return ChemicalState(
        levels=levels,
        last_updated=time.time(),
        prev_normalized={},
    )
