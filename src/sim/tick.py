"""
Tick — continuous chemical dynamics run every 10 seconds.

Handles:
  - Phasic decay (exponential half-life per chemical)
  - Tonic approach to setpoint (gap closure)
  - Setpoint adaptation (slow drift; asymmetric — resists downward ratchets)
  - Class 2 accumulation from sustained Class 1 elevation (hard-capped)
  - HPA cascade (CRH drives cortisol rise)
  - Opponent processes (phasic-first; tonic floored)
  - Circadian offsets for time-of-day baseline shifts
  - Sleep pressure (adenosine accumulation/clearance in the correct compartment)

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
    ADENOSINE_ACCUM_PER_TICK,
    SETPOINT_DOWN_SCALE,
    OPPONENT_TONIC_FLOOR_FRAC,
    SETPOINT_FLOOR_FRAC,
    CHEMICAL_TOTAL_CAP_MULT,
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


def _cap_total(lvl: ChemicalLevel, p: dict) -> None:
    """Hard-cap tonic+phasic at normalization_max * CHEMICAL_TOTAL_CAP_MULT."""
    max_total = p["normalization_max"] * CHEMICAL_TOTAL_CAP_MULT
    excess = (lvl.tonic + lvl.phasic) - max_total
    if excess <= 0:
        return
    # Drain phasic first, then tonic down to a homeostatic floor
    if lvl.phasic >= excess:
        lvl.phasic -= excess
    else:
        excess -= lvl.phasic
        lvl.phasic = 0.0
        floor = p["tonic_setpoint"] * OPPONENT_TONIC_FLOOR_FRAC
        lvl.tonic = max(floor, lvl.tonic - excess)


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
    # Adenosine wake-pressure is handled exclusively in Phase 7 — do not apply
    # generic reuptake decay to it while awake (that made accumulation and decay
    # cancel, so sleep threshold was never reached at realistic rates).
    for name, lvl in levels.items():
        p = params.get(name)
        if not p or lvl.phasic == 0.0:
            continue
        if name == "adenosine":
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

    # ── Phase 3: setpoint adaptation (asymmetric) ────────────────────────────
    # Upward: full rate (chronic high exposure raises baseline).
    # Downward: SETPOINT_DOWN_SCALE × rate — prevents opponent drag / acute
    # dips from permanently erasing setpoints (the death-spiral ratchet).
    for name, lvl in levels.items():
        p = params.get(name)
        if not p:
            continue
        adapt_rate = p["setpoint_adapt_rate"]
        gap = lvl.tonic - lvl.setpoint
        if gap < 0:
            adapt_rate *= SETPOINT_DOWN_SCALE
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
            _cap_total(lvl, p)

    # ── Phase 5: HPA cascade ─────────────────────────────────────────────────
    # CRH accumulates when NE is elevated above threshold (threat axis proxy)
    ne_norm = norm_snapshot.get("norepinephrine", 0.0)
    epi_norm = norm_snapshot.get("epinephrine", 0.0)
    crh_lvl = levels.get("crh")
    crh_threshold = HPA.get(
        "crh_driver_threshold_normalized",
        HPA.get("crh_driver_threshold_nM", 6.0),  # legacy key fallback
    )
    if crh_lvl and (ne_norm + 0.5 * epi_norm) > crh_threshold:
        crh_lvl.phasic += HPA["crh_accumulation_nM_per_s"] * dt
        _cap_total(crh_lvl, params["crh"])

    # Cortisol rises from sustained CRH (slow, 30-min lag modeled as low rate)
    crh_normalized = _normalized(crh_lvl, params["crh"]) if crh_lvl else 0.0
    cortisol_lvl = levels.get("cortisol")
    if cortisol_lvl and crh_normalized > HPA["cortisol_driver_threshold_normalized"]:
        cortisol_lvl.phasic += HPA["cortisol_rise_nM_per_s"] * dt
        _cap_total(cortisol_lvl, params["cortisol"])

    # ── Phase 6: Opponent processes ───────────────────────────────────────────
    # Phasic-first; tonic only down to OPPONENT_TONIC_FLOOR_FRAC of natural base.
    for src_name, threshold, tgt_name, drag_nM in OPPONENT_PROCESSES:
        src_norm = min(10.0, norm_snapshot.get(src_name, 0.0))
        if src_norm < threshold:
            continue
        tgt_lvl = levels.get(tgt_name)
        if not tgt_lvl:
            continue
        p_tgt = params.get(tgt_name)
        tonic_floor = (
            p_tgt["tonic_setpoint"] * OPPONENT_TONIC_FLOOR_FRAC if p_tgt else 0.0
        )
        drag = drag_nM * (dt / 10.0) * (src_norm - threshold)
        if tgt_lvl.phasic >= drag:
            tgt_lvl.phasic -= drag
        else:
            remaining = drag - tgt_lvl.phasic
            tgt_lvl.phasic = 0.0
            tgt_lvl.tonic = max(tonic_floor, tgt_lvl.tonic - remaining)

    # ── Phase 7: Adenosine sleep pressure ─────────────────────────────────────
    # Accumulation goes into *phasic* (the wake reservoir). Sleep clears phasic
    # fast (glymphatic), not tonic (tonic is the resting floor ~100 nM).
    adenosine_lvl = levels.get("adenosine")
    if adenosine_lvl:
        ade_p = params["adenosine"]
        if sleeping:
            # Clear the wake-pressure reservoir (phasic) with ~1h half-life
            sleep_hl = 3600.0
            adenosine_lvl.phasic *= 0.5 ** (dt / sleep_hl)
            # Mild tonic settle toward setpoint while asleep
            gap = ade_p["tonic_setpoint"] - adenosine_lvl.tonic
            adenosine_lvl.tonic += gap * min(1.0, 0.02 * dt / 10.0)
        else:
            adenosine_lvl.phasic += ADENOSINE_ACCUM_PER_TICK * (dt / 10.0)
            _cap_total(adenosine_lvl, ade_p)

    # ── Phase 8: Floors, caps, non-negativity ─────────────────────────────────
    for name, lvl in levels.items():
        p = params.get(name)
        if p:
            min_setpoint = p["tonic_setpoint"] * SETPOINT_FLOOR_FRAC
            lvl.setpoint = max(min_setpoint, lvl.setpoint)
            _cap_total(lvl, p)
        lvl.tonic    = max(0.0, lvl.tonic)
        lvl.phasic   = max(0.0, lvl.phasic)
        # Sensitivity stays in a sane band (receptor gain)
        lvl.sensitivity = max(0.3, min(1.5, lvl.sensitivity))

    # ── Phase 9: Slow receptor sensitivity (Class 4 dynamics, light) ──────────
    # High chronic level → mild desensitization; low → mild upregulation.
    # Very slow — hours/days scale. Keeps a brake that was previously dead code.
    for name, lvl in levels.items():
        p = params.get(name)
        if not p or p["class"] == 4:
            continue
        norm = _normalized(lvl, p)
        # Target sensitivity: 1.0 at setpoint-ish (~3–5), lower when chronically high
        target_sens = 1.0
        if norm > 6.0:
            target_sens = 0.85
        elif norm < 2.0:
            target_sens = 1.15
        lvl.sensitivity += (target_sens - lvl.sensitivity) * min(1.0, 0.0003 * dt / 10.0)

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


def chemical_norm(state: ChemicalState, name: str) -> float:
    """0–10 normalized level for a chemical (helper for auto-sleep etc.)."""
    lvl = state.levels.get(name)
    p = CHEMICAL_PARAMS.get(name)
    if not lvl or not p:
        return 0.0
    return _normalized(lvl, p)
