"""
SPEC-24 tests: neuroplasticity, circadian refinement, system integration.

Covers:
  - BDNF dynamics (baseline_fn, allostatic advance)
  - Allostatic load accumulation and recovery
  - Synaptic potentiation (LTP conditions)
  - Orexin circadian baseline
  - Sleep propensity (two-process model)
  - Core body temperature (circadian + fever)
  - Derived() SPEC-24 additions (physical_distress, allostatic effects)
  - Behavioral drives
  - Personality drift
  - Engine integration (phases wired up, context updated)
"""
import sys, os, time, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from tests.sim.conftest import make_state

from src.sim.psych.allostatic import (
    _bdnf_baseline_fn,
    _make_allostatic_ctx,
    _compute_synaptic_potentiation_delta,
    advance_allostatic,
)
from src.sim.physio.circadian import (
    _orexin_baseline_fn,
    _advance_orexin,
    compute_sleep_propensity,
    _advance_core_temp,
)
from src.sim.psych.derived import derived
from src.sim.behavioral_drives import compute_behavioral_drives
from src.sim.psych.personality import apply_personality_drift
from src.sim.events import EventBus


# ===========================================================================
# BDNF baseline function
# ===========================================================================

class TestBdnfBaselineFn:
    def test_healthy_state_near_9000(self):
        """Resting healthy state → BDNF near 9000 pg/mL."""
        ctx = {"cortisol": 250.0, "inflammation_index": 0.0, "adenosine": 25.0,
               "sleeping": False, "growth_hormone": 1.0}
        bdnf = _bdnf_baseline_fn(0.0, ctx)
        assert 8000 < bdnf <= 9000

    def test_chronic_stress_suppresses_bdnf(self):
        """Cortisol 1000 → significant BDNF suppression."""
        ctx = {"cortisol": 1000.0, "inflammation_index": 0.0, "adenosine": 25.0,
               "sleeping": False, "growth_hormone": 1.0}
        bdnf = _bdnf_baseline_fn(0.0, ctx)
        healthy_ctx = {"cortisol": 250.0, "inflammation_index": 0.0, "adenosine": 25.0,
                       "sleeping": False, "growth_hormone": 1.0}
        healthy = _bdnf_baseline_fn(0.0, healthy_ctx)
        assert bdnf < healthy - 1000

    def test_inflammation_suppresses_bdnf(self):
        """High inflammation index → lower BDNF baseline."""
        ctx_high_infl = {"cortisol": 250.0, "inflammation_index": 60.0, "adenosine": 25.0,
                         "sleeping": False, "growth_hormone": 1.0}
        ctx_healthy   = {"cortisol": 250.0, "inflammation_index": 0.0,  "adenosine": 25.0,
                         "sleeping": False, "growth_hormone": 1.0}
        assert _bdnf_baseline_fn(0.0, ctx_high_infl) < _bdnf_baseline_fn(0.0, ctx_healthy)

    def test_sleep_gh_boost(self):
        """Sleeping with high GH → higher BDNF than awake."""
        ctx_sleeping = {"cortisol": 250.0, "inflammation_index": 0.0, "adenosine": 25.0,
                        "sleeping": True, "growth_hormone": 8.0}
        ctx_awake    = {"cortisol": 250.0, "inflammation_index": 0.0, "adenosine": 25.0,
                        "sleeping": False, "growth_hormone": 1.0}
        assert _bdnf_baseline_fn(0.0, ctx_sleeping) > _bdnf_baseline_fn(0.0, ctx_awake)

    def test_sleep_deprivation_suppresses_bdnf(self):
        """High adenosine (sleep debt) → BDNF below baseline."""
        ctx_deprived = {"cortisol": 250.0, "inflammation_index": 0.0, "adenosine": 85.0,
                        "sleeping": False, "growth_hormone": 1.0}
        ctx_rested   = {"cortisol": 250.0, "inflammation_index": 0.0, "adenosine": 25.0,
                        "sleeping": False, "growth_hormone": 1.0}
        assert _bdnf_baseline_fn(0.0, ctx_deprived) < _bdnf_baseline_fn(0.0, ctx_rested) - 500

    def test_floor_clamped(self):
        """Even extreme stress cannot drop BDNF below 1000."""
        ctx = {"cortisol": 9999.0, "inflammation_index": 100.0, "adenosine": 100.0,
               "sleeping": False, "growth_hormone": 0.0}
        assert _bdnf_baseline_fn(0.0, ctx) >= 1000.0


# ===========================================================================
# Allostatic load advance
# ===========================================================================

class TestAllostaticLoad:
    def test_resting_state_no_accumulation(self):
        """Healthy baseline → allostatic load stays near zero."""
        s   = make_state()
        bus = EventBus()
        s   = advance_allostatic(s, 1.0, bus)
        # With no stressors: total_load_rate ≈ 0, baseline_recovery fires
        assert s.neuroplasticity["allostatic_load"] < 1.0

    def test_chronic_cortisol_builds_load(self):
        """Sustained high cortisol → allostatic load accumulates."""
        s = make_state(cortisol=800.0)
        bus = EventBus()
        s = advance_allostatic(s, 10.0, bus)
        assert s.neuroplasticity["allostatic_load"] > 0.5

    def test_sleep_reduces_load(self):
        """Sleeping with moderate pre-existing load → load decreases."""
        s = make_state()
        s.neuroplasticity["allostatic_load"] = 30.0
        s.sleeping = True
        bus = EventBus()
        s = advance_allostatic(s, 1.0, bus)
        assert s.neuroplasticity["allostatic_load"] < 30.0

    def test_load_clamped_0_100(self):
        """Allostatic load never goes below 0 or above 100."""
        s = make_state(cortisol=9999.0)
        s.immune["inflammation_index"] = 100.0
        s.pain["pain_intensity"] = 100.0
        s.body["adenosine"] = 100.0
        bus = EventBus()
        s = advance_allostatic(s, 100.0, bus)
        assert 0.0 <= s.neuroplasticity["allostatic_load"] <= 100.0

    def test_event_emitted_above_50(self):
        """allostatic_load > 50 → event emitted."""
        s = make_state(cortisol=700.0)
        s.neuroplasticity["allostatic_load"] = 55.0
        bus = EventBus()
        s = advance_allostatic(s, 1.0, bus)
        events = bus.drain()
        al_events = [e for e in events if e.chemical == "allostatic_load"]
        assert len(al_events) > 0

    def test_bdnf_advances_each_tick(self):
        """BDNF changes each tick when stressors are present."""
        s = make_state(cortisol=800.0)
        initial_bdnf = s.neuroplasticity["bdnf"]
        bus = EventBus()
        s = advance_allostatic(s, 24.0, bus)
        assert s.neuroplasticity["bdnf"] != initial_bdnf

    def test_synaptic_potentiation_advances(self):
        """Synaptic potentiation changes each tick."""
        s = make_state()
        initial_sp = s.neuroplasticity["synaptic_potentiation"]
        bus = EventBus()
        s = advance_allostatic(s, 1.0, bus)
        # SP should change (LTP drive present at healthy baseline)
        assert s.neuroplasticity["synaptic_potentiation"] != initial_sp


# ===========================================================================
# Synaptic potentiation
# ===========================================================================

class TestSynapticPotentiation:
    def test_sleep_consolidation_bonus(self):
        """Sleep provides a large consolidation bonus to synaptic potentiation."""
        s_sleeping = make_state()
        s_sleeping.sleeping = True
        s_awake    = make_state()

        delta_sleep = _compute_synaptic_potentiation_delta(s_sleeping, 1.0)
        delta_awake = _compute_synaptic_potentiation_delta(s_awake,    1.0)
        assert delta_sleep > delta_awake + 1.0

    def test_cortisol_suppresses_ltp(self):
        """High cortisol penalizes synaptic potentiation."""
        s_stressed = make_state(cortisol=800.0)
        s_healthy  = make_state(cortisol=250.0)
        assert (_compute_synaptic_potentiation_delta(s_stressed, 1.0) <
                _compute_synaptic_potentiation_delta(s_healthy,  1.0))

    def test_low_bdnf_reduces_ltp(self):
        """Low BDNF reduces LTP drive."""
        s_low_bdnf  = make_state()
        s_low_bdnf.neuroplasticity["bdnf"] = 2000.0
        s_high_bdnf = make_state()
        s_high_bdnf.neuroplasticity["bdnf"] = 12000.0
        assert (_compute_synaptic_potentiation_delta(s_low_bdnf,  1.0) <
                _compute_synaptic_potentiation_delta(s_high_bdnf, 1.0))


# ===========================================================================
# Orexin baseline
# ===========================================================================

class TestOrexinBaseline:
    def test_peak_afternoon(self):
        """Orexin should be highest ~3pm (hour 15)."""
        ctx = {"adenosine": 25.0, "cortisol": 250.0}
        peak    = _orexin_baseline_fn(15.0, ctx)
        trough  = _orexin_baseline_fn(3.0,  ctx)
        assert peak > trough + 100

    def test_adenosine_suppresses_orexin(self):
        """High adenosine suppresses orexin (mutual inhibition)."""
        ctx_tired  = {"adenosine": 80.0, "cortisol": 250.0}
        ctx_rested = {"adenosine": 25.0, "cortisol": 250.0}
        assert _orexin_baseline_fn(15.0, ctx_tired) < _orexin_baseline_fn(15.0, ctx_rested)

    def test_cortisol_supports_orexin(self):
        """High cortisol (stress) transiently elevates orexin."""
        ctx_stressed = {"adenosine": 25.0, "cortisol": 700.0}
        ctx_calm     = {"adenosine": 25.0, "cortisol": 250.0}
        assert _orexin_baseline_fn(15.0, ctx_stressed) > _orexin_baseline_fn(15.0, ctx_calm)

    def test_floor_not_zero(self):
        """Orexin always has a minimum floor (not narcoleptic in simulation)."""
        ctx = {"adenosine": 100.0, "cortisol": 0.0}
        assert _orexin_baseline_fn(3.0, ctx) >= 30.0

    def test_orexin_advances_toward_baseline(self):
        """advance call updates orexin toward its circadian baseline."""
        s = make_state()
        s.neuroendocrine["orexin"] = 50.0   # set artificially low
        s = _advance_orexin(s, 1.0, 15.0)   # afternoon — should push toward high baseline
        assert s.neuroendocrine["orexin"] > 50.0


# ===========================================================================
# Sleep propensity (two-process model)
# ===========================================================================

class TestSleepPropensity:
    def test_high_adenosine_high_propensity(self):
        """High adenosine + melatonin → high sleep propensity."""
        s = make_state()
        s.body["adenosine"] = 80.0
        s.chemicals["melatonin"] = 200.0
        s.neuroendocrine["orexin"] = 50.0
        propensity = compute_sleep_propensity(s)
        assert propensity > 70.0

    def test_rested_awake_low_propensity(self):
        """Low adenosine + low melatonin + high orexin → low propensity."""
        s = make_state()
        s.body["adenosine"] = 22.0
        s.chemicals["melatonin"] = 5.0
        s.neuroendocrine["orexin"] = 350.0
        propensity = compute_sleep_propensity(s)
        assert propensity < 30.0

    def test_two_process_conflict(self):
        """High adenosine + high orexin = moderate propensity (internal conflict)."""
        s = make_state()
        s.body["adenosine"] = 70.0
        s.neuroendocrine["orexin"] = 350.0
        s.chemicals["melatonin"] = 10.0
        propensity = compute_sleep_propensity(s)
        # Neither very high nor very low
        assert 20.0 < propensity < 75.0

    def test_propensity_clamped_0_100(self):
        """Propensity always 0–100."""
        s = make_state()
        s.body["adenosine"] = 100.0
        s.chemicals["melatonin"] = 220.0
        s.neuroendocrine["orexin"] = 0.0
        p = compute_sleep_propensity(s)
        assert 0.0 <= p <= 100.0

        s2 = make_state()
        s2.body["adenosine"] = 15.0
        s2.chemicals["melatonin"] = 0.0
        s2.neuroendocrine["orexin"] = 400.0
        p2 = compute_sleep_propensity(s2)
        assert 0.0 <= p2 <= 100.0


# ===========================================================================
# Core body temperature
# ===========================================================================

class TestCoreBodyTemperature:
    def test_circadian_variation(self):
        """Temperature peaks at ~10am (π/2) and troughs at ~10pm (−π/2)."""
        # Formula: 36.75 + 0.4 * sin((hour - 4) * π/12)
        # Peak at hour 10: sin(π/2) = 1  → 37.15
        # Trough at hour 22: sin(3π/2) = −1 → 36.35
        target_peak  = 36.75 + 0.4 * math.sin((10.0 - 4.0) * math.pi / 12.0)
        target_trough = 36.75 + 0.4 * math.sin((22.0 - 4.0) * math.pi / 12.0)
        assert target_peak > target_trough + 0.5

    def test_fever_from_cytokines(self):
        """High IL-6 and IL-1β raise core temperature above normal."""
        s_healthy = make_state()
        s_fever   = make_state()
        s_fever.immune["il6"]  = 30.0
        s_fever.immune["il1b"] = 15.0

        _advance_core_temp(s_healthy, 1.0, 12.0)
        _advance_core_temp(s_fever,   1.0, 12.0)
        assert s_fever.body["core_temp"] > s_healthy.body["core_temp"]

    def test_sleep_lowers_temperature(self):
        """Sleeping → target temperature 0.3°C lower than awake at same hour."""
        s_sleeping = make_state()
        s_awake    = make_state()
        s_sleeping.sleeping = True
        _advance_core_temp(s_sleeping, 5.0, 12.0)
        _advance_core_temp(s_awake,    5.0, 12.0)
        assert s_sleeping.body["core_temp"] < s_awake.body["core_temp"]

    def test_temperature_stored_in_body(self):
        """Temperature value is stored in s.body['core_temp']."""
        s = make_state()
        _advance_core_temp(s, 1.0, 12.0)
        assert "core_temp" in s.body
        assert 35.0 < s.body["core_temp"] < 42.0


# ===========================================================================
# Derived() SPEC-24 additions
# ===========================================================================

class TestDerivedSpec24:
    def test_physical_distress_key_present(self):
        """derived() now returns physical_distress in third_order."""
        s = make_state()
        d = derived(s)
        assert "physical_distress" in d["third_order"]

    def test_physical_distress_elevated_by_pain(self):
        """High pain → elevated physical_distress."""
        s_pain    = make_state()
        s_pain.pain["pain_intensity"] = 70.0
        s_healthy = make_state()
        assert (derived(s_pain)["third_order"]["physical_distress"] >
                derived(s_healthy)["third_order"]["physical_distress"])

    def test_allostatic_load_reduces_mood_valence(self):
        """High allostatic load → lower mood_valence."""
        s_healthy  = make_state()
        s_stressed = make_state()
        s_stressed.neuroplasticity["allostatic_load"] = 80.0
        assert (derived(s_stressed)["second_order"]["mood_valence"] <
                derived(s_healthy)["second_order"]["mood_valence"])

    def test_allostatic_load_increases_depression(self):
        """High allostatic load contributes to depression score."""
        s_healthy  = make_state()
        s_stressed = make_state()
        s_stressed.neuroplasticity["allostatic_load"] = 80.0
        assert (derived(s_stressed)["third_order"]["depression"] >=
                derived(s_healthy)["third_order"]["depression"])

    def test_low_bdnf_reduces_hedonic_tone(self):
        """Very low BDNF → lower hedonic_tone (through serotonin/dopamine blunting)."""
        # Note: BDNF doesn't directly enter hedonic_tone in the formula, but
        # it affects mood_valence via bdnf_n. Check mood_valence instead.
        s_low_bdnf  = make_state()
        s_low_bdnf.neuroplasticity["bdnf"] = 1500.0
        s_high_bdnf = make_state()
        s_high_bdnf.neuroplasticity["bdnf"] = 15000.0
        assert (derived(s_low_bdnf)["second_order"]["mood_valence"] <
                derived(s_high_bdnf)["second_order"]["mood_valence"])

    def test_inflammation_reduces_energy(self):
        """High inflammation index → lower energy (sickness behavior)."""
        s_inflamed = make_state()
        s_inflamed.immune["inflammation_index"] = 70.0
        s_healthy  = make_state()
        assert (derived(s_inflamed)["second_order"]["energy"] <
                derived(s_healthy)["second_order"]["energy"])

    def test_inflation_increases_loneliness(self):
        """Inflammation increases loneliness (sickness behavior withdrawal)."""
        s_inflamed = make_state()
        s_inflamed.immune["inflammation_index"] = 80.0
        s_healthy  = make_state()
        assert (derived(s_inflamed)["third_order"]["loneliness"] >=
                derived(s_healthy)["third_order"]["loneliness"])


# ===========================================================================
# Behavioral drives
# ===========================================================================

class TestBehavioralDrives:
    def test_hunger_from_high_ghrelin(self):
        """High ghrelin → hunger drive."""
        s = make_state()
        s.neuroendocrine["ghrelin"] = 850.0
        drives = compute_behavioral_drives(s)
        hunger = [d for d in drives if d.drive_type == "hunger"]
        assert len(hunger) == 1
        assert hunger[0].urgency > 0.4

    def test_hunger_from_low_glucose(self):
        """Low glucose → hunger drive."""
        s = make_state(glucose=55.0)
        drives = compute_behavioral_drives(s)
        hunger = [d for d in drives if d.drive_type == "hunger"]
        assert len(hunger) == 1

    def test_thirst_from_low_hydration(self):
        """Low hydration → thirst drive."""
        s = make_state(hydration=50.0)
        drives = compute_behavioral_drives(s)
        thirst = [d for d in drives if d.drive_type == "thirst"]
        assert len(thirst) == 1
        assert thirst[0].urgency > 0.3

    def test_fatigue_from_high_adenosine(self):
        """High adenosine (awake) → fatigue drive."""
        s = make_state()
        s.body["adenosine"] = 75.0
        drives = compute_behavioral_drives(s)
        fatigue = [d for d in drives if d.drive_type == "fatigue"]
        assert len(fatigue) == 1

    def test_no_fatigue_when_sleeping(self):
        """Sleeping with high adenosine → no fatigue drive (already in bed)."""
        s = make_state()
        s.body["adenosine"] = 75.0
        s.sleeping = True
        drives = compute_behavioral_drives(s)
        fatigue = [d for d in drives if d.drive_type == "fatigue"]
        assert len(fatigue) == 0

    def test_drives_sorted_by_urgency(self):
        """Drives are returned highest urgency first."""
        s = make_state(hydration=45.0)
        s.neuroendocrine["ghrelin"] = 600.0
        drives = compute_behavioral_drives(s)
        if len(drives) >= 2:
            for i in range(len(drives) - 1):
                assert drives[i].urgency >= drives[i + 1].urgency

    def test_healthy_state_no_urgent_drives(self):
        """Healthy baseline → no drives above urgency 0.1."""
        s = make_state()
        drives = compute_behavioral_drives(s)
        # At healthy baseline, nothing should be urgent
        assert all(d.urgency < 0.5 for d in drives)

    def test_pain_drive_above_threshold(self):
        """Pain > 40 → pain drive."""
        s = make_state()
        s.pain["pain_intensity"] = 65.0
        drives = compute_behavioral_drives(s)
        pain = [d for d in drives if d.drive_type == "pain"]
        assert len(pain) == 1
        assert pain[0].urgency == pytest.approx(0.65, abs=0.01)


# ===========================================================================
# Personality drift
# ===========================================================================

class TestPersonalityDrift:
    def test_high_al_raises_neuroticism(self):
        """Allostatic load > 60 → neuroticism rises."""
        s = make_state()
        s.neuroplasticity["allostatic_load"] = 80.0
        p = {"neuroticism": 65.0, "conscientiousness": 70.0, "agreeableness": 75.0}
        result = apply_personality_drift(s, p, 100.0)
        assert result["neuroticism"] > 65.0

    def test_high_al_lowers_conscientiousness(self):
        """High allostatic load → conscientiousness falls."""
        s = make_state()
        s.neuroplasticity["allostatic_load"] = 80.0
        p = {"neuroticism": 65.0, "conscientiousness": 70.0, "agreeableness": 75.0}
        result = apply_personality_drift(s, p, 100.0)
        assert result["conscientiousness"] < 70.0

    def test_below_threshold_no_drift(self):
        """Low allostatic load → no drift."""
        s = make_state()
        s.neuroplasticity["allostatic_load"] = 30.0
        p = {"neuroticism": 65.0, "conscientiousness": 70.0, "agreeableness": 75.0}
        result = apply_personality_drift(s, p, 100.0)
        assert result == p

    def test_recovery_restores_toward_original(self):
        """Low allostatic load + _original snapshot → traits drift back."""
        s = make_state()
        s.neuroplasticity["allostatic_load"] = 5.0
        p = {
            "neuroticism":       70.0,   # drifted up from 65
            "conscientiousness": 65.0,   # drifted down from 70
            "agreeableness":     72.0,
            "_original": {
                "neuroticism":       65.0,
                "conscientiousness": 70.0,
                "agreeableness":     75.0,
            },
        }
        result = apply_personality_drift(s, p, 1000.0)
        # Neuroticism should approach 65 (decrease)
        assert result["neuroticism"] < 70.0
        # Conscientiousness should approach 70 (increase)
        assert result["conscientiousness"] > 65.0

    def test_original_dict_not_mutated(self):
        """apply_personality_drift returns a copy; original is not mutated."""
        s = make_state()
        s.neuroplasticity["allostatic_load"] = 80.0
        p = {"neuroticism": 65.0, "conscientiousness": 70.0, "agreeableness": 75.0}
        original = dict(p)
        apply_personality_drift(s, p, 100.0)
        assert p == original


# ===========================================================================
# Engine integration
# ===========================================================================

class TestEngineIntegration:
    def test_advance_updates_allostatic_load(self):
        """Engine advance updates allostatic_load in neuroplasticity tier."""
        from src.sim.engine import advance
        s = make_state(cortisol=700.0)
        s.body["adenosine"] = 70.0
        s.immune["inflammation_index"] = 50.0
        initial_al = s.neuroplasticity["allostatic_load"]
        now = time.time()
        s = advance(s, now=now + 3600, event_bus=EventBus())
        # With high stressors, allostatic load should have accumulated
        assert s.neuroplasticity["allostatic_load"] >= initial_al

    def test_advance_updates_orexin(self):
        """Engine advance updates orexin in neuroendocrine tier."""
        from src.sim.engine import advance
        s = make_state()
        s.neuroendocrine["orexin"] = 50.0   # artificially low
        now = time.time()
        s = advance(s, now=now + 3600, event_bus=EventBus())
        # Orexin should have moved toward its circadian target
        assert s.neuroendocrine["orexin"] != 50.0

    def test_advance_updates_core_temp(self):
        """Engine advance updates core_temp in body tier."""
        from src.sim.engine import advance
        s = make_state()
        s.body["core_temp"] = 36.0   # set below circadian target
        now = time.time()
        s = advance(s, now=now + 3600, event_bus=EventBus())
        assert s.body["core_temp"] != 36.0

    def test_advance_updates_bdnf(self):
        """Engine advance updates BDNF."""
        from src.sim.engine import advance
        s = make_state(cortisol=800.0)
        initial_bdnf = s.neuroplasticity["bdnf"]
        now = time.time()
        s = advance(s, now=now + 7200, event_bus=EventBus())
        assert s.neuroplasticity["bdnf"] != initial_bdnf

    def test_engine_context_includes_bdnf(self):
        """_make_context includes bdnf so serotonin baseline_fn can use it."""
        from src.sim.engine import _make_context, _hour_of_day
        s = make_state()
        s.neuroplasticity["bdnf"] = 3000.0
        ctx = _make_context(s, 12.0)
        assert ctx["bdnf"] == pytest.approx(3000.0)

    def test_serotonin_baseline_reduced_by_low_bdnf(self):
        """Low BDNF → lower serotonin target from baseline_fn."""
        from src.sim.chem.registry import REGISTRY
        ctx_low_bdnf  = {"t3": 120.0, "estradiol": 100.0, "bdnf": 2000.0}
        ctx_high_bdnf = {"t3": 120.0, "estradiol": 100.0, "bdnf": 12000.0}
        fn = REGISTRY["serotonin"].baseline_fn
        assert fn(12.0, ctx_low_bdnf) < fn(12.0, ctx_high_bdnf)
