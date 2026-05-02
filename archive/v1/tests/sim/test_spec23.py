"""
SPEC-23 tests: immune system, pain system, and autonomic nervous system.

Covers:
  - Cytokine dynamics and inflammation index
  - Sickness behavior cascade (cytokines → first-order chemicals)
  - Substance P and PGE2 baseline functions
  - Central sensitization build and decay
  - Gate control theory (endorphins / anandamide / GABA)
  - Pain → systemic chemistry effects
  - Vagal tone and HRV derivation
  - Engine integration: SPEC-23 subsystems hooked in advance()
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tests.sim.conftest import make_state
from src.engine.events import EventBus
from src.engine.physio.immune import (
    advance_immune,
    compute_inflammation_index,
)
from src.engine.physio.pain import (
    advance_pain,
    compute_pain_intensity,
    _apply_pain_effects,
    _substance_p_baseline_fn,
    _pge2_baseline_fn,
    _advance_central_sensitization,
)
from src.engine.physio.autonomic import advance_autonomic, compute_vagal_tone


# ===========================================================================
# Helpers
# ===========================================================================

def bus() -> EventBus:
    return EventBus()


# ===========================================================================
# I. Inflammation index
# ===========================================================================

def test_inflammation_index_healthy_state():
    """Default immune values → index near zero."""
    immune = {"il1b": 2.0, "il6": 3.0, "tnf_alpha": 3.0, "crp": 0.5, "il10": 10.0}
    assert compute_inflammation_index(immune) < 5.0


def test_inflammation_index_reflects_cytokines():
    """High IL-1β + IL-6 → elevated index (formula gives ~38 with these inputs)."""
    immune = {"il1b": 30.0, "il6": 60.0, "tnf_alpha": 3.0, "crp": 0.5, "il10": 10.0}
    assert compute_inflammation_index(immune) > 35.0


def test_il10_dampens_inflammation_index():
    """Higher IL-10 (anti-inflammatory) → lower index for same pro-inflammatory load."""
    base = {"il1b": 20.0, "il6": 40.0, "tnf_alpha": 15.0, "crp": 5.0}
    low_il10  = {**base, "il10":  5.0}
    high_il10 = {**base, "il10": 40.0}
    assert compute_inflammation_index(high_il10) < compute_inflammation_index(low_il10)


def test_inflammation_index_clamped_0_100():
    """Index is always in [0, 100]."""
    extreme = {"il1b": 200.0, "il6": 200.0, "tnf_alpha": 200.0, "crp": 200.0, "il10": 5.0}
    assert compute_inflammation_index(extreme) == 100.0
    healthy = {"il1b": 2.0, "il6": 3.0, "tnf_alpha": 3.0, "crp": 0.5, "il10": 50.0}
    assert compute_inflammation_index(healthy) >= 0.0


# ===========================================================================
# II. Cytokine dynamics
# ===========================================================================

def test_sleep_deprivation_raises_il1b():
    """High adenosine (sleep debt) → IL-1β baseline rises → IL-1β increases."""
    s = make_state()
    s.body["adenosine"] = 80.0   # exhausted
    s = advance_immune(s, sim_hours=2.0, event_bus=bus())
    assert s.immune["il1b"] > 2.0


def test_chronic_cortisol_raises_il1b():
    """Cortisol > 600 → immune dysregulation → IL-1β elevated."""
    s = make_state(cortisol=750.0)
    s.immune["il1b"] = 2.0
    s = advance_immune(s, sim_hours=3.0, event_bus=bus())
    assert s.immune["il1b"] > 2.0


def test_high_pain_raises_il1b():
    """Sustained pain > 40 → IL-1β rises."""
    s = make_state()
    s.pain["pain_intensity"] = 70.0
    s = advance_immune(s, sim_hours=2.0, event_bus=bus())
    assert s.immune["il1b"] > 2.5


def test_il6_rises_with_elevated_il1b():
    """IL-1β cascade: elevated IL-1β → higher IL-6 baseline → IL-6 increases."""
    s = make_state()
    s.immune["il1b"] = 20.0
    s.immune["il6"]  =  3.0
    s = advance_immune(s, sim_hours=4.0, event_bus=bus())
    assert s.immune["il6"] > 5.0


def test_crp_lags_behind_il6():
    """CRP approach rate is 0.04/hr — barely moves in 0.1 hr."""
    s = make_state()
    s.immune["il6"]  = 80.0   # would drive CRP to ~22
    s.immune["crp"]  =  0.5
    s_after = advance_immune(s, sim_hours=0.1, event_bus=bus())
    # Very slow: CRP should move < 0.1 in 0.1 hr
    assert abs(s_after.immune["crp"] - 0.5) < 0.1


def test_il10_rises_counter_to_il6():
    """IL-10 baseline is driven up by elevated IL-6 (counter-regulation)."""
    s = make_state()
    s.immune["il6"]  = 60.0
    s.immune["il10"] = 10.0
    s = advance_immune(s, sim_hours=3.0, event_bus=bus())
    assert s.immune["il10"] > 12.0


# ===========================================================================
# III. Sickness behavior cascade
# ===========================================================================

def test_sickness_behavior_suppresses_serotonin():
    """Elevated IL-1β (>8) → serotonin drainage.
    Use a short tick so IL-1β doesn't fully decay before sickness behavior fires.
    """
    s = make_state()
    s.immune["il1b"] = 20.0
    initial_serotonin = s.chemicals["serotonin"]
    s = advance_immune(s, sim_hours=0.5, event_bus=bus())
    assert s.chemicals["serotonin"] < initial_serotonin


def test_sickness_behavior_suppresses_dopamine():
    """Elevated IL-6 (>15) → dopamine drainage."""
    s = make_state()
    s.immune["il6"] = 30.0
    s.immune["inflammation_index"] = 50.0   # needed for oxytocin threshold too
    initial_dopamine = s.chemicals["dopamine"]
    s = advance_immune(s, sim_hours=2.0, event_bus=bus())
    assert s.chemicals["dopamine"] < initial_dopamine


def test_tnfa_elevates_cortisol():
    """TNF-α > 12 → cortisol boost (HPA activation via TNF receptors)."""
    s = make_state(cortisol=250.0)
    s.immune["tnf_alpha"] = 25.0
    initial_cortisol = s.chemicals["cortisol"]
    s = advance_immune(s, sim_hours=1.0, event_bus=bus())
    assert s.chemicals["cortisol"] > initial_cortisol


def test_high_inflammation_builds_adenosine():
    """Inflammation index > 40 → hypersomnia drive → adenosine increases.
    Use a tiny tick so markers barely decay and the recomputed index stays > 40.
    """
    s = make_state()
    s.immune["il1b"]      = 30.0
    s.immune["il6"]       = 60.0
    s.immune["tnf_alpha"] = 20.0
    s.immune["crp"]       = 10.0
    s.immune["il10"]      =  5.0   # low IL-10 (no counter-regulation) → index stays high
    initial_adenosine = s.body["adenosine"]
    s = advance_immune(s, sim_hours=0.01, event_bus=bus())
    assert s.body["adenosine"] > initial_adenosine


def test_sickness_behavior_reduces_oxytocin():
    """Inflammation index > 50 → oxytocin reduction (social withdrawal).
    Use higher markers so recomputed index > 50 and a tiny tick to prevent decay.
    """
    s = make_state()
    s.immune["il1b"]      = 40.0
    s.immune["il6"]       = 80.0
    s.immune["tnf_alpha"] = 20.0
    s.immune["crp"]       = 10.0
    s.immune["il10"]      =  5.0   # low counter-regulation → index ~61
    initial_oxytocin = s.chemicals["oxytocin"]
    s = advance_immune(s, sim_hours=0.01, event_bus=bus())
    assert s.chemicals["oxytocin"] < initial_oxytocin


# ===========================================================================
# IV. Substance P and PGE2 baseline functions
# ===========================================================================

def test_substance_p_baseline_fn_rises_with_il1b():
    """IL-1β sensitizes nociceptors → higher Substance P baseline."""
    ctx_low  = {"il1b":  2.0, "pge2": 80.0, "endorphins": 12.0, "cortisol": 250.0}
    ctx_high = {"il1b": 30.0, "pge2": 80.0, "endorphins": 12.0, "cortisol": 250.0}
    assert _substance_p_baseline_fn(0.0, ctx_high) > _substance_p_baseline_fn(0.0, ctx_low)


def test_substance_p_baseline_fn_reduced_by_endorphins():
    """High endorphins (opioid gate control) → lower Substance P baseline."""
    ctx_low  = {"il1b": 5.0, "pge2": 80.0, "endorphins": 12.0, "cortisol": 250.0}
    ctx_high = {"il1b": 5.0, "pge2": 80.0, "endorphins": 80.0, "cortisol": 250.0}
    assert _substance_p_baseline_fn(0.0, ctx_high) < _substance_p_baseline_fn(0.0, ctx_low)


def test_pge2_baseline_fn_driven_by_inflammation():
    """IL-1β + TNF-α (COX-2 induction) → higher PGE2 baseline."""
    ctx_low  = {"il1b":  2.0, "tnf_alpha":  3.0, "pge2":  80.0}
    ctx_high = {"il1b": 30.0, "tnf_alpha": 20.0, "pge2":  80.0}
    assert _pge2_baseline_fn(0.0, ctx_high) > _pge2_baseline_fn(0.0, ctx_low)


def test_pge2_self_amplification():
    """PGE2 >200 → COX-2 upregulation → higher target."""
    ctx_low  = {"il1b": 2.0, "tnf_alpha": 3.0, "pge2":  80.0}
    ctx_high = {"il1b": 2.0, "tnf_alpha": 3.0, "pge2": 400.0}
    assert _pge2_baseline_fn(0.0, ctx_high) > _pge2_baseline_fn(0.0, ctx_low)


# ===========================================================================
# V. Gate control theory
# ===========================================================================

def test_endorphins_close_pain_gate():
    """High endorphins → reduced computed pain intensity."""
    s = make_state()
    s.pain["substance_p"] = 200.0
    s.chemicals["endorphins"] = 12.0   # baseline — no gate effect
    pain_low = compute_pain_intensity(s)

    s.chemicals["endorphins"] = 80.0   # strong opioid gate
    pain_high = compute_pain_intensity(s)

    assert pain_high < pain_low


def test_anandamide_closes_pain_gate():
    """High anandamide (CB1 activation) → reduced pain intensity."""
    s = make_state()
    s.pain["substance_p"] = 150.0
    s.body["anandamide"] = 1.5   # baseline
    pain_low = compute_pain_intensity(s)

    s.body["anandamide"] = 8.0   # elevated endocannabinoid
    pain_high = compute_pain_intensity(s)

    assert pain_high < pain_low


def test_gaba_closes_pain_gate():
    """High GABA (spinal inhibitory) → reduced pain intensity."""
    s = make_state()
    s.pain["substance_p"] = 150.0
    s.chemicals["gaba"] = 3.0   # baseline
    pain_low = compute_pain_intensity(s)

    s.chemicals["gaba"] = 12.0
    pain_high = compute_pain_intensity(s)

    assert pain_high < pain_low


def test_cortisol_amplifies_pain_attention():
    """High cortisol (hypervigilance) → increased perceived pain."""
    s = make_state()
    s.pain["substance_p"] = 150.0
    s.chemicals["cortisol"] = 300.0
    pain_low = compute_pain_intensity(s)

    s.chemicals["cortisol"] = 800.0   # stress hypervigilance
    pain_high = compute_pain_intensity(s)

    assert pain_high > pain_low


# ===========================================================================
# VI. Central sensitization
# ===========================================================================

def test_central_sensitization_amplifies_pain():
    """Central sensitization → same substance_p → more pain."""
    s = make_state()
    s.pain["substance_p"] = 120.0
    s.pain["central_sensitization"] = 0.0
    pain_no_cs = compute_pain_intensity(s)

    s.pain["central_sensitization"] = 60.0
    pain_with_cs = compute_pain_intensity(s)

    assert pain_with_cs > pain_no_cs


def test_central_sensitization_builds_with_sustained_pain():
    """Pain >40 and substance_p >80 → CS accumulates."""
    s = make_state()
    s.pain["pain_intensity"]         = 70.0
    s.pain["substance_p"]            = 120.0
    s.pain["central_sensitization"]  =  0.0
    s = _advance_central_sensitization(s, sim_hours=2.0)
    assert s.pain["central_sensitization"] > 0.0


def test_central_sensitization_decays_without_pain():
    """No pain → CS decays slowly."""
    s = make_state()
    s.pain["pain_intensity"]        = 0.0
    s.pain["substance_p"]           = 30.0
    s.pain["central_sensitization"] = 20.0
    s = _advance_central_sensitization(s, sim_hours=5.0)
    assert s.pain["central_sensitization"] < 20.0


def test_pge2_amplifies_pain_above_200():
    """PGE2 >200 → peripheral sensitization multiplier → more pain."""
    s = make_state()
    s.pain["substance_p"] = 100.0
    s.pain["pge2"]        =  80.0   # no amplification
    pain_low = compute_pain_intensity(s)

    s.pain["pge2"] = 600.0   # strong peripheral sensitization
    pain_high = compute_pain_intensity(s)

    assert pain_high > pain_low


# ===========================================================================
# VII. Pain → systemic chemistry effects
# ===========================================================================

def test_pain_causes_cortisol_spike():
    """Pain >20 → cortisol elevation (HPA response)."""
    s = make_state(cortisol=250.0)
    s.pain["pain_intensity"] = 60.0
    initial = s.chemicals["cortisol"]
    s = _apply_pain_effects(s, sim_hours=1.0)
    assert s.chemicals["cortisol"] > initial


def test_pain_causes_norepinephrine_spike():
    """Pain >20 → norepinephrine elevation (sympathetic arousal)."""
    s = make_state()
    s.pain["pain_intensity"] = 60.0
    initial = s.chemicals["norepinephrine"]
    s = _apply_pain_effects(s, sim_hours=1.0)
    assert s.chemicals["norepinephrine"] > initial


def test_pain_triggers_endorphin_release():
    """Pain >20 → endorphin release (endogenous opioid response)."""
    s = make_state()
    s.chemicals["endorphins"]  = 12.0
    s.pain["pain_intensity"]   = 60.0
    s = _apply_pain_effects(s, sim_hours=1.0)
    assert s.chemicals["endorphins"] > 12.0


def test_severe_pain_disrupts_sleep():
    """Pain >50 → adenosine buildup (sleep disruption)."""
    s = make_state()
    initial_adenosine = s.body["adenosine"]
    s.pain["pain_intensity"] = 70.0
    s = _apply_pain_effects(s, sim_hours=2.0)
    assert s.body["adenosine"] > initial_adenosine


def test_severe_pain_suppresses_dopamine():
    """Pain >50 → dopamine drain (chronic pain → anhedonia)."""
    s = make_state()
    initial_dopamine = s.chemicals["dopamine"]
    s.pain["pain_intensity"] = 70.0
    s = _apply_pain_effects(s, sim_hours=2.0)
    assert s.chemicals["dopamine"] < initial_dopamine


# ===========================================================================
# VIII. Vagal tone and HRV
# ===========================================================================

def test_vagal_tone_high_with_calm_state():
    """Low cortisol, low pain, high GABA → vagal tone > 55."""
    s = make_state(cortisol=200.0)
    s.pain["pain_intensity"] = 0.0
    s.chemicals["gaba"]      = 8.0
    assert compute_vagal_tone(s) > 55.0


def test_vagal_tone_low_with_stress():
    """High cortisol + high pain → vagal tone well below midpoint."""
    s = make_state(cortisol=700.0)
    s.pain["pain_intensity"] = 70.0
    assert compute_vagal_tone(s) < 30.0


def test_oxytocin_raises_vagal_tone():
    """High oxytocin (social safety) → higher vagal tone."""
    s = make_state()
    s.chemicals["oxytocin"] = 4.0
    low_tone = compute_vagal_tone(s)

    s.chemicals["oxytocin"] = 60.0
    high_tone = compute_vagal_tone(s)

    assert high_tone > low_tone


def test_vagal_tone_clamped_0_100():
    """Vagal tone is always in [0, 100]."""
    s = make_state(cortisol=2000.0)
    s.pain["pain_intensity"] = 100.0
    assert 0.0 <= compute_vagal_tone(s) <= 100.0

    s2 = make_state(cortisol=50.0)
    s2.chemicals["oxytocin"] = 200.0
    s2.chemicals["gaba"]     = 50.0
    assert 0.0 <= compute_vagal_tone(s2) <= 100.0


def test_hrv_derived_from_vagal_tone():
    """advance_autonomic stores hrv_rmssd = 10 + vagal_tone * 0.7."""
    s = make_state()
    s = advance_autonomic(s, sim_hours=1.0, event_bus=bus())
    expected = round(10.0 + s.body["vagal_tone"] * 0.70, 1)
    assert s.body["hrv_rmssd"] == expected


def test_advance_autonomic_stores_vagal_tone():
    """advance_autonomic writes vagal_tone into body dict."""
    s = make_state()
    assert "vagal_tone" not in s.body
    s = advance_autonomic(s, sim_hours=1.0, event_bus=bus())
    assert "vagal_tone" in s.body


# ===========================================================================
# IX. Engine integration
# ===========================================================================

def test_engine_advance_with_spec23_subsystems():
    """engine.advance() runs without error with SPEC-23 hooks in place."""
    from src.engine.engine import advance
    import time
    s = make_state()
    now = time.time()
    s.last_updated = now - 300   # 5 minutes ago
    s2 = advance(s, now=now, event_bus=bus())
    # State was updated and pain/immune/autonomic fields exist
    assert s2.last_updated == now
    assert "inflammation_index" in s2.immune
    assert "pain_intensity" in s2.pain
    assert "vagal_tone" in s2.body


def test_high_il1b_suppresses_serotonin_through_engine():
    """With elevated IL-1β, engine.advance() produces lower serotonin."""
    from src.engine.engine import advance
    import time
    now = time.time()

    s_normal = make_state()
    s_normal.last_updated = now - 3600
    s_normal = advance(s_normal, now=now, event_bus=bus())

    s_sick = make_state()
    s_sick.last_updated = now - 3600
    s_sick.immune["il1b"] = 30.0
    s_sick = advance(s_sick, now=now, event_bus=bus())

    assert s_sick.chemicals["serotonin"] < s_normal.chemicals["serotonin"]
