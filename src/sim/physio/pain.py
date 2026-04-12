"""Pain system — Substance P, PGE2, gate control theory, central sensitization.
Full implementation for SPEC-23.
"""
from __future__ import annotations

import time

from src.sim.bio.state import BiologicalState
from src.sim.chem.units import clamp_chemical
from src.sim.events import BiologicalEvent, EventBus


# ---------------------------------------------------------------------------
# Baseline functions (exported for tests)
# ---------------------------------------------------------------------------

def _substance_p_baseline_fn(hour: float, ctx: dict) -> float:
    """
    Substance P baseline: low at rest, sensitized by inflammation.
    Endorphins suppress release (pre-synaptic opioid inhibition = gate control).
    """
    base = 30.0
    base += ctx.get("il1b", 2.0) * 0.8                  # inflammation sensitizes nociceptors
    base += ctx.get("pge2", 80.0) * 0.05                 # peripheral sensitization → lower threshold
    base -= max(0, ctx.get("endorphins", 12.0) - 12.0) * 0.3   # opioid gate
    if ctx.get("cortisol", 250.0) > 500.0:               # chronic stress sensitizes pain pathways
        base += (ctx["cortisol"] - 500.0) * 0.02
    return max(10.0, base)


def _pge2_baseline_fn(hour: float, ctx: dict) -> float:
    """
    PGE2 rises with tissue damage (COX-2 induction by IL-1β and TNF-α).
    Self-amplifying: PGE2 upregulates COX-2.
    NSAIDs block COX → reduce PGE2 → reduce peripheral sensitization.
    """
    base = 80.0
    base += max(0, ctx.get("il1b",      2.0) -  2.0) * 5.0
    base += max(0, ctx.get("tnf_alpha", 3.0) -  3.0) * 4.0
    base += max(0, ctx.get("pge2",     80.0) - 200.0) * 0.1   # self-amplification
    return max(40.0, min(2000.0, base))


# ---------------------------------------------------------------------------
# Central sensitization
# ---------------------------------------------------------------------------

def _advance_central_sensitization(s: BiologicalState, sim_hours: float) -> BiologicalState:
    """
    Central sensitization builds slowly with sustained high pain + substance P.
    Decays very slowly (weeks-months in real life → modeled as 0.05 AU/hr).
    Mechanism: fibromyalgia, chronic migraine, post-injury allodynia.
    """
    cs       = s.pain.get("central_sensitization", 0.0)
    pain_int = s.pain.get("pain_intensity",         0.0)
    sub_p    = s.pain.get("substance_p",           30.0)

    if pain_int > 40.0 and sub_p > 80.0:
        build_rate = (pain_int - 40.0) * 0.02   # very slow build
        cs = min(100.0, cs + build_rate * sim_hours)
    else:
        cs = max(0.0, cs - 0.05 * sim_hours)

    s.pain["central_sensitization"] = round(cs, 3)
    return s


# ---------------------------------------------------------------------------
# Pain intensity computation (exported for tests)
# ---------------------------------------------------------------------------

def compute_pain_intensity(s: BiologicalState) -> float:
    """
    Compute current subjective pain intensity (0–100 AU).

    Gate control theory: spinal inhibitory signals (endorphins, anandamide, GABA)
    reduce transmission from periphery to brain. Attention (cortisol/stress) amplifies.
    """
    sub_p = s.pain.get("substance_p",           30.0)
    pge2  = s.pain.get("pge2",                  80.0)
    cs    = s.pain.get("central_sensitization",  0.0)

    # Raw pain: substance_p 30 → 0 pain; 300 → ~90 pain
    raw_pain = max(0.0, (sub_p - 30.0) / 3.0)

    # Peripheral sensitization multiplier (PGE2 >200 amplifies pain)
    pge2_factor = 1.0 + max(0, pge2 - 200.0) / 1000.0

    # Central sensitization: amplifies signal and adds a baseline floor
    cs_factor = 1.0 + cs * 0.015   # CS 50 → 1.75× amplification
    cs_offset = cs * 0.3           # CS 50 → +15 baseline pain

    raw_pain = raw_pain * pge2_factor * cs_factor + cs_offset

    # Gate control: endorphin + endocannabinoid + GABA inhibition
    endorphins = s.chemicals.get("endorphins", 12.0)
    anandamide = s.body.get("anandamide",        1.5)
    gaba       = s.chemicals.get("gaba",          3.0)

    endorphin_gate = max(0.0, endorphins - 12.0) * 0.5   # above baseline closes gate
    endo_gate      = max(0.0, anandamide -  1.5) * 2.0
    gaba_gate      = max(0.0, gaba       -  2.0) * 1.5
    total_gate     = endorphin_gate + endo_gate + gaba_gate

    gated_pain = max(0.0, raw_pain - total_gate)

    # Attention gate: high cortisol (hypervigilance) amplifies perceived pain
    cortisol = s.chemicals.get("cortisol", 250.0)
    attention_factor = 1.0 + max(0, cortisol - 400.0) * 0.0005

    return min(100.0, round(gated_pain * attention_factor, 2))


# ---------------------------------------------------------------------------
# Pain effects on systemic chemistry (exported for tests)
# ---------------------------------------------------------------------------

def _apply_pain_effects(s: BiologicalState, sim_hours: float) -> BiologicalState:
    """Pain's downstream effects: HPA activation, sympathetic arousal, opioid response."""
    pain_int = s.pain.get("pain_intensity", 0.0)

    if pain_int > 20.0:
        # Cortisol: HPA response to pain signal
        s.chemicals["cortisol"] = clamp_chemical("cortisol",
            s.chemicals.get("cortisol", 250.0) + (pain_int - 20.0) * 0.4 * sim_hours)

        # Norepinephrine: sympathetic arousal
        s.chemicals["norepinephrine"] = clamp_chemical("norepinephrine",
            s.chemicals.get("norepinephrine", 200.0) + (pain_int - 20.0) * 0.8 * sim_hours)

        # Endorphins: endogenous opioid response (partially closes the gate)
        s.chemicals["endorphins"] = clamp_chemical("endorphins",
            s.chemicals.get("endorphins", 12.0) + (pain_int - 20.0) * 0.2 * sim_hours)

    if pain_int > 50.0:
        # Moderate-severe pain → sleep disruption (adenosine buildup)
        s.body["adenosine"] = min(100.0,
            s.body.get("adenosine", 25.0) + (pain_int - 50.0) * 0.01 * sim_hours)

        # Chronic pain → anhedonia (dopamine suppression)
        s.chemicals["dopamine"] = clamp_chemical("dopamine",
            s.chemicals.get("dopamine", 80.0) - (pain_int - 50.0) * 0.05 * sim_hours)

    return s


# ---------------------------------------------------------------------------
# Main advance function
# ---------------------------------------------------------------------------

def advance_pain(s: BiologicalState, sim_hours: float, event_bus: EventBus) -> BiologicalState:
    """Advance all pain markers and apply downstream effects."""
    ctx = {
        "il1b":      s.immune.get("il1b",           2.0),
        "tnf_alpha": s.immune.get("tnf_alpha",       3.0),
        "pge2":      s.pain.get("pge2",             80.0),
        "endorphins": s.chemicals.get("endorphins", 12.0),
        "cortisol":   s.chemicals.get("cortisol",  250.0),
    }

    # Advance Substance P toward its inflammation-sensitive baseline
    sub_p        = s.pain.get("substance_p", 30.0)
    sub_p_target = _substance_p_baseline_fn(0.0, ctx)
    s.pain["substance_p"] = max(10.0, sub_p + (sub_p_target - sub_p) * min(1.0, 0.15 * sim_hours))

    # Advance PGE2 toward its inflammation-driven baseline
    pge2        = s.pain.get("pge2", 80.0)
    pge2_target = _pge2_baseline_fn(0.0, ctx)
    s.pain["pge2"] = max(20.0, pge2 + (pge2_target - pge2) * min(1.0, 0.20 * sim_hours))

    # Central sensitization accumulation/decay
    s = _advance_central_sensitization(s, sim_hours)

    # Recompute subjective pain intensity from updated upstream state
    prev_pain = s.pain.get("pain_intensity", 0.0)
    s.pain["pain_intensity"] = compute_pain_intensity(s)

    # Apply pain's downstream effects on systemic chemistry
    s = _apply_pain_effects(s, sim_hours)

    # Emit event when pain is clinically significant
    pain_int = s.pain["pain_intensity"]
    if pain_int > 30.0:
        event_bus.emit(BiologicalEvent(
            event_type="threshold_crossed" if pain_int > 50.0 else "spike",
            system="pain",
            chemical="pain_intensity",
            value=pain_int,
            delta=pain_int - prev_pain,
            unit="AU",
            label="SEVERE" if pain_int > 70.0 else "MODERATE",
            label_crossed=pain_int > 50.0,
            severity="significant" if pain_int > 50.0 else "moderate",
            significance=min(1.0, pain_int / 100.0),
            timestamp=time.time(),
        ))

    return s
