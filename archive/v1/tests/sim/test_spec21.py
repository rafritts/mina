"""Tests for SPEC-21 neurotransmitter dynamics."""
import time
import pytest
from tests.sim.conftest import make_state


# ---------------------------------------------------------------------------
# Adenosine / sleep_pressure migration
# ---------------------------------------------------------------------------

def test_sleep_pressure_derives_from_body_adenosine():
    s = make_state()
    # Default adenosine = 38.0 nmol/L → SP = (38-20)/0.6 = 30.0 AU
    assert abs(s.sleep_pressure - 30.0) < 0.1


def test_sleep_pressure_at_minimum_adenosine():
    s = make_state()
    s.body["adenosine"] = 15.0  # floor after sleep
    sp = s.sleep_pressure
    assert sp == 0.0  # (15-20)/0.6 → clamped to 0


def test_sleep_pressure_at_high_adenosine():
    s = make_state()
    s.body["adenosine"] = 80.0  # exhausted
    sp = s.sleep_pressure
    assert abs(sp - 100.0) < 0.1


def test_apply_deltas_sleep_pressure_updates_adenosine():
    from src.engine.bio.state import apply_deltas
    s = make_state()
    initial_a = s.body["adenosine"]
    s = apply_deltas(s, {"sleep_pressure": +10.0})
    # +10 AU → +6 nmol/L adenosine
    assert abs(s.body["adenosine"] - (initial_a + 6.0)) < 0.01


def test_advance_adenosine_builds_while_awake():
    from src.engine.physio.circadian import _advance_adenosine
    s = make_state()
    s.sleeping = False
    s.body["adenosine"] = 30.0
    s = _advance_adenosine(s, 1.0)   # 1 sim-hour
    assert s.body["adenosine"] > 30.0


def test_advance_adenosine_clears_during_sleep():
    from src.engine.physio.circadian import _advance_adenosine
    s = make_state()
    s.sleeping = True
    s.body["adenosine"] = 70.0
    s = _advance_adenosine(s, 1.0)   # 1 sim-hour
    assert s.body["adenosine"] < 70.0


def test_advance_adenosine_floor_at_15():
    from src.engine.physio.circadian import _advance_adenosine
    s = make_state()
    s.sleeping = True
    s.body["adenosine"] = 16.0
    s = _advance_adenosine(s, 10.0)  # long sleep
    assert s.body["adenosine"] >= 15.0


# ---------------------------------------------------------------------------
# GABA and Glutamate dynamics
# ---------------------------------------------------------------------------

def test_gaba_present_in_fresh_state():
    s = make_state()
    assert "gaba" in s.chemicals
    assert abs(s.chemicals["gaba"] - 3.0) < 0.01


def test_glutamate_present_in_fresh_state():
    s = make_state()
    assert "glutamate" in s.chemicals
    assert abs(s.chemicals["glutamate"] - 4.0) < 0.01


def test_advance_amino_acids_approaches_baseline():
    from src.engine.neuro.amino_acids import advance_amino_acids
    from src.engine.events import EventBus
    s = make_state()
    s.chemicals["gaba"] = 0.9    # depleted
    s.chemicals["glutamate"] = 12.0  # elevated
    s = advance_amino_acids(s, 2.0, EventBus())
    assert s.chemicals["gaba"] > 0.9
    assert s.chemicals["glutamate"] < 12.0


def test_high_cortisol_suppresses_gaba_baseline():
    from src.engine.neuro.amino_acids import advance_amino_acids
    from src.engine.events import EventBus
    s_low  = make_state(cortisol=200.0)
    s_high = make_state(cortisol=800.0)
    # Force both to same GABA starting point
    s_low.chemicals["gaba"]  = 3.0
    s_high.chemicals["gaba"] = 3.0
    s_low  = advance_amino_acids(s_low,  1.0, EventBus())
    s_high = advance_amino_acids(s_high, 1.0, EventBus())
    assert s_high.chemicals["gaba"] <= s_low.chemicals["gaba"]


def test_excitotoxic_glutamate_raises_il6():
    from src.engine.neuro.amino_acids import advance_amino_acids
    from src.engine.events import EventBus
    s = make_state()
    s.chemicals["glutamate"] = 12.0   # above excitotoxic threshold (10)
    il6_before = s.immune["il6"]
    s = advance_amino_acids(s, 1.0, EventBus())
    assert s.immune["il6"] > il6_before


def test_normal_glutamate_does_not_raise_il6():
    from src.engine.neuro.amino_acids import advance_amino_acids
    from src.engine.events import EventBus
    s = make_state()
    s.chemicals["glutamate"] = 5.0   # normal
    il6_before = s.immune["il6"]
    s = advance_amino_acids(s, 1.0, EventBus())
    assert s.immune["il6"] == il6_before


# ---------------------------------------------------------------------------
# E/I balance
# ---------------------------------------------------------------------------

def test_ei_balance_at_defaults():
    from src.engine.psych.derived import ei_balance
    s = make_state()
    ei = ei_balance(s)
    # Default: glu=4.0, gaba=3.0 → slight excitatory lean
    assert -0.5 < ei < 0.5


def test_ei_balance_is_positive_with_high_glutamate():
    from src.engine.psych.derived import ei_balance
    s = make_state()
    s.chemicals["glutamate"] = 15.0
    s.chemicals["gaba"]      = 2.0
    assert ei_balance(s) > 0.2


def test_ei_balance_is_negative_with_high_gaba():
    from src.engine.psych.derived import ei_balance
    s = make_state()
    s.chemicals["gaba"]      = 8.0
    s.chemicals["glutamate"] = 2.0
    assert ei_balance(s) < -0.2


# ---------------------------------------------------------------------------
# Endocannabinoids
# ---------------------------------------------------------------------------

def test_anandamide_present_in_body_tier():
    s = make_state()
    assert "anandamide" in s.body
    assert abs(s.body["anandamide"] - 1.5) < 0.01


def test_two_ag_present_in_body_tier():
    s = make_state()
    assert "two_ag" in s.body
    assert abs(s.body["two_ag"] - 8.0) < 0.01


def test_high_anandamide_reduces_pain():
    from src.engine.neuro.endocannabinoids import advance_endocannabinoids
    from src.engine.events import EventBus
    s = make_state()
    s.body["anandamide"]   = 5.0    # above 3.0 threshold
    s.pain["pain_intensity"] = 50.0
    s = advance_endocannabinoids(s, 1.0, EventBus())
    assert s.pain["pain_intensity"] < 50.0


def test_high_two_ag_reduces_il6():
    from src.engine.neuro.endocannabinoids import advance_endocannabinoids
    from src.engine.events import EventBus
    s = make_state()
    s.body["two_ag"] = 20.0    # above 15.0 threshold
    s.immune["il6"]  = 10.0
    s = advance_endocannabinoids(s, 1.0, EventBus())
    assert s.immune["il6"] < 10.0


# ---------------------------------------------------------------------------
# Receptor sensitivity
# ---------------------------------------------------------------------------

def test_receptor_sensitivity_initialized_on_advance():
    from src.engine.neuro.receptors import advance_receptors
    s = make_state()
    s.receptor_sensitivity = {}
    s = advance_receptors(s, 1.0)
    assert "dopamine" in s.receptor_sensitivity
    assert "D2" in s.receptor_sensitivity["dopamine"]


def test_high_chemical_causes_downregulation():
    from src.engine.neuro.receptors import advance_receptors
    s = make_state()
    # Dopamine far above soft_ceiling (180 pg/mL)
    s.chemicals["dopamine"] = 250.0
    s.receptor_sensitivity = {"dopamine": {"D1": 1.0, "D2": 1.0, "D3": 1.0}}
    s = advance_receptors(s, 100.0)  # 100 sim-hours
    assert s.receptor_sensitivity["dopamine"]["D2"] < 1.0


def test_low_chemical_causes_upregulation():
    from src.engine.neuro.receptors import advance_receptors
    s = make_state()
    # Dopamine far below resting_low (40 pg/mL)
    s.chemicals["dopamine"] = 5.0
    s.receptor_sensitivity = {"dopamine": {"D1": 1.0, "D2": 1.0, "D3": 1.0}}
    s = advance_receptors(s, 100.0)
    assert s.receptor_sensitivity["dopamine"]["D2"] > 1.0


def test_receptor_sensitivity_bounded():
    from src.engine.neuro.receptors import advance_receptors
    s = make_state()
    # Massively elevated dopamine for very long time
    s.chemicals["dopamine"] = 999.0
    s.receptor_sensitivity = {"dopamine": {"D1": 1.0, "D2": 1.0, "D3": 1.0}}
    s = advance_receptors(s, 100000.0)
    assert s.receptor_sensitivity["dopamine"]["D2"] >= 0.2


# ---------------------------------------------------------------------------
# Updated substance pharmacokinetics
# ---------------------------------------------------------------------------

def test_caffeine_no_longer_changes_adenosine():
    """Caffeine doesn't reduce adenosine — it blocks receptors instead."""
    from src.engine.neuro.substances import SUBSTANCE_DEFS
    caffeine_def = SUBSTANCE_DEFS["caffeine"]
    assert "sleep_pressure" not in caffeine_def.get("dose_effects", {})
    assert "adenosine" not in caffeine_def.get("dose_effects", {})
    assert "receptor_block" in caffeine_def


def test_caffeine_receptor_block_reduces_sleep_pressure():
    """Active caffeine should reduce effective sleep_pressure via A1/A2A block."""
    s = make_state()
    s.body["adenosine"]  = 60.0   # significant adenosine buildup
    s.substances["caffeine"] = {"level": 100.0}
    sp_with_caffeine = s.sleep_pressure

    s2 = make_state()
    s2.body["adenosine"] = 60.0
    sp_without_caffeine = s2.sleep_pressure

    assert sp_with_caffeine < sp_without_caffeine


def test_ssri_in_substance_defs():
    from src.engine.neuro.substances import SUBSTANCE_DEFS
    assert "ssri" in SUBSTANCE_DEFS
    ssri = SUBSTANCE_DEFS["ssri"]
    assert "reuptake_block" in ssri
    assert ssri["reuptake_block"]["serotonin"] > 1.0


def test_opioid_in_substance_defs():
    from src.engine.neuro.substances import SUBSTANCE_DEFS
    assert "opioid" in SUBSTANCE_DEFS
    opioid = SUBSTANCE_DEFS["opioid"]
    assert "pain.pain_intensity" in opioid.get("dose_effects", {})


def test_advance_substances_handles_body_tier_markers():
    """Cannabis dose_effects include anandamide/two_ag (body-stored) — withdrawal should update body."""
    from src.engine.neuro.substances import advance_substances
    from src.engine.events import EventBus
    s = make_state()
    # Prime cannabis at low level to trigger significant decay/withdrawal
    s.substances["cannabis"] = {"level": 30.0}
    s.body["anandamide"] = 5.0   # elevated from the dose
    s = advance_substances(s, 2.0, time.time(), EventBus())
    # After decay, anandamide withdrawal counter-delta should have fired
    # (counter-delta is negative, so anandamide decreases)
    assert s.body["anandamide"] <= 5.0


def test_ssri_reuptake_mult_returned():
    from src.engine.neuro.substances import get_effective_reuptake_mults
    s = make_state()
    s.substances["ssri"] = {"level": 100.0}
    mults = get_effective_reuptake_mults(s)
    assert mults.get("serotonin", 1.0) > 1.0


def test_receptor_blocks_returned_for_caffeine():
    from src.engine.neuro.substances import get_receptor_blocks
    s = make_state()
    s.substances["caffeine"] = {"level": 100.0}
    blocks = get_receptor_blocks(s)
    assert blocks.get("adenosine", {}).get("A1", 1.0) < 1.0
    assert blocks.get("adenosine", {}).get("A2A", 1.0) < 1.0


# ---------------------------------------------------------------------------
# Derived values use receptor sensitivity
# ---------------------------------------------------------------------------

def test_derived_uses_d2_sensitivity():
    from src.engine.psych.derived import derived
    s_normal = make_state(dopamine=200.0)
    s_tolerant = make_state(dopamine=200.0)
    s_tolerant.receptor_sensitivity["dopamine"] = {"D1": 0.5, "D2": 0.5, "D3": 0.5}
    d_normal   = derived(s_normal)["second_order"]["hedonic_tone"]
    d_tolerant = derived(s_tolerant)["second_order"]["hedonic_tone"]
    assert d_tolerant < d_normal


def test_high_ei_increases_anxiety():
    from src.engine.psych.derived import derived
    s_balanced  = make_state(glutamate=4.0, gaba=3.0)
    s_excitable = make_state(glutamate=14.0, gaba=1.0)
    anxiety_balanced  = derived(s_balanced)["third_order"]["anxiety"]
    anxiety_excitable = derived(s_excitable)["third_order"]["anxiety"]
    assert anxiety_excitable > anxiety_balanced
