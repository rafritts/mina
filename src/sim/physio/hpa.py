"""HPA axis — CRH → ACTH → cortisol cascade with delay queue.
Full implementation for SPEC-22.

Cortisol itself lives in s.chemicals and is advanced via the REGISTRY loop in Phase 1;
the baseline_fn there now reads ACTH from ctx. This module manages CRH, ACTH, and
the cascade queue for event-driven stressor latency.
"""
from __future__ import annotations

import math

from src.sim.bio.state import BiologicalState
from src.sim.chem.units import clamp_chemical
from src.sim.events import EventBus


def _make_hpa_ctx(s: BiologicalState, hour: float) -> dict:
    return {
        "hour":     hour,
        "glucose":  s.chemicals.get("glucose", 85.0),
        "cortisol": s.chemicals.get("cortisol", 250.0),
        "il6":      s.immune.get("il6", 3.0),
        "crh":      s.neuroendocrine.get("crh", 30.0),
    }


def _crh_baseline_fn(hour: float, ctx: dict) -> float:
    """CRH circadian: peaks with cortisol awakening response (~8am). Negative cortisol feedback."""
    base = 15.0 + 20.0 * math.cos((hour - 8) * math.pi / 12)
    # Negative feedback: high cortisol suppresses hypothalamic CRH release
    base -= max(0.0, ctx.get("cortisol", 250.0) - 400.0) * 0.015
    # Hypoglycemia activates HPA
    if ctx.get("glucose", 85.0) < 60.0:
        base += 15.0
    # IL-6 (sickness signal) activates HPA
    base += max(0.0, ctx.get("il6", 3.0) - 10.0) * 1.5
    return max(5.0, base)


def _acth_baseline_fn(hour: float, ctx: dict) -> float:
    """ACTH follows CRH with fast coupling; cortisol provides negative feedback."""
    crh = ctx.get("crh", 30.0)
    base = crh * 0.85   # ACTH tracks ~85% of CRH signal
    base -= max(0.0, ctx.get("cortisol", 250.0) - 400.0) * 0.02
    return max(3.0, base)


def advance_hpa(s: BiologicalState, sim_hours: float, now: float,
                hour_of_day: float, event_bus: EventBus) -> BiologicalState:
    """
    Advance the HPA axis: CRH and ACTH dynamics + cascade queue processing.

    Phase 1 (REGISTRY loop) advances cortisol itself using the ACTH-driven
    baseline_fn — so advance_hpa must run before Phase 1 to keep ACTH current.
    """
    ctx = _make_hpa_ctx(s, hour_of_day)

    # 1. CRH (fast: half-life ~15 min → approach_rate 2.8/hr)
    crh = s.neuroendocrine.get("crh", 30.0)
    crh_target = _crh_baseline_fn(hour_of_day, ctx)
    s.neuroendocrine["crh"] = crh + (crh_target - crh) * min(1.0, 2.8 * sim_hours)

    # 2. ACTH (fast: half-life ~30 min → approach_rate 1.2/hr)
    # Use updated CRH so ACTH tracks intra-tick CRH movement
    ctx["crh"] = s.neuroendocrine["crh"]
    acth = s.neuroendocrine.get("acth", 25.0)
    acth_target = _acth_baseline_fn(hour_of_day, ctx)
    s.neuroendocrine["acth"] = acth + (acth_target - acth) * min(1.0, 1.2 * sim_hours)

    # 3. Process cascade queue — fire any entries whose wall-clock time has passed
    still_pending = []
    for entry in s.cascade_queue:
        if now >= entry["fires_at"]:
            target = entry["target"]
            delta  = entry["delta"]
            if target in s.chemicals:
                s.chemicals[target] = clamp_chemical(
                    target, s.chemicals.get(target, 0.0) + delta
                )
            elif target in s.neuroendocrine:
                s.neuroendocrine[target] = max(
                    0.0, s.neuroendocrine.get(target, 0.0) + delta
                )
        else:
            still_pending.append(entry)
    s.cascade_queue = still_pending

    return s


def apply_stressor_delta(s: BiologicalState, cortisol_delta: float,
                          now: float) -> BiologicalState:
    """
    Route a stressor through the HPA cascade with physiological delays.

    CRH spikes immediately (hypothalamic response).
    ACTH follows in ~10 real minutes (pituitary).
    Cortisol follows in ~30 real minutes (10 min pituitary + 20 min adrenal).

    Use this for event-driven stressors (emotional triggers, social conflict, pain).
    Direct pharmacological cortisol deltas should still write to s.chemicals["cortisol"].
    """
    # CRH: immediate hypothalamic response
    s.neuroendocrine["crh"] = min(
        200.0, s.neuroendocrine.get("crh", 30.0) + cortisol_delta * 0.12
    )

    # ACTH: queued ~10 real minutes later (pituitary)
    s.cascade_queue.append({
        "target":   "acth",
        "delta":    cortisol_delta * 0.08,
        "fires_at": now + 600,
    })

    # Cortisol: queued ~30 real minutes later (cascade dampens raw delta)
    s.cascade_queue.append({
        "target":   "cortisol",
        "delta":    cortisol_delta * 0.6,
        "fires_at": now + 1800,
    })

    return s
