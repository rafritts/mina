"""Tests for SPEC-22 neuroendocrine & metabolic systems."""
import time
import pytest
from tests.sim.conftest import make_state


# ---------------------------------------------------------------------------
# HPA cascade
# ---------------------------------------------------------------------------

def test_crh_spikes_on_stressor():
    """Stressor immediately raises CRH."""
    from src.sim.physio.hpa import apply_stressor_delta
    s = make_state()
    crh_before = s.neuroendocrine["crh"]
    s = apply_stressor_delta(s, cortisol_delta=200.0, now=time.time())
    assert s.neuroendocrine["crh"] > crh_before


def test_cascade_queue_has_acth_and_cortisol_entries():
    """apply_stressor_delta queues both ACTH and cortisol cascade entries."""
    from src.sim.physio.hpa import apply_stressor_delta
    s = make_state()
    s = apply_stressor_delta(s, cortisol_delta=200.0, now=time.time())
    targets = [e["target"] for e in s.cascade_queue]
    assert "acth" in targets
    assert "cortisol" in targets


def test_cortisol_delay_exceeds_acth_delay():
    """Cortisol cascade fires later than ACTH (ACTH delay < cortisol delay)."""
    from src.sim.physio.hpa import apply_stressor_delta
    s = make_state()
    now = time.time()
    s = apply_stressor_delta(s, cortisol_delta=200.0, now=now)
    acth_entry = next(e for e in s.cascade_queue if e["target"] == "acth")
    cort_entry = next(e for e in s.cascade_queue if e["target"] == "cortisol")
    assert cort_entry["fires_at"] > acth_entry["fires_at"]


def test_advance_hpa_fires_pending_queue_entry():
    """cascade_queue entries past their fires_at timestamp are applied and removed."""
    from src.sim.physio.hpa import advance_hpa
    from src.sim.events import EventBus
    s = make_state()
    past = time.time() - 100   # already past
    s.cascade_queue.append({"target": "cortisol", "delta": 50.0, "fires_at": past})
    cortisol_before = s.chemicals["cortisol"]
    s = advance_hpa(s, sim_hours=0.01, now=time.time(), hour_of_day=12.0, event_bus=EventBus())
    assert s.chemicals["cortisol"] > cortisol_before
    assert len(s.cascade_queue) == 0


def test_cascade_queue_does_not_fire_early():
    """Queue entries with future fires_at timestamps are kept pending."""
    from src.sim.physio.hpa import advance_hpa
    from src.sim.events import EventBus
    s = make_state()
    future = time.time() + 9999
    s.cascade_queue.append({"target": "cortisol", "delta": 100.0, "fires_at": future})
    s = advance_hpa(s, sim_hours=0.01, now=time.time(), hour_of_day=12.0, event_bus=EventBus())
    assert len(s.cascade_queue) == 1


def test_high_cortisol_suppresses_crh_baseline():
    """Negative feedback: high cortisol drives CRH toward a lower target."""
    from src.sim.physio.hpa import _crh_baseline_fn
    ctx_normal = {"cortisol": 250.0, "glucose": 85.0, "il6": 3.0}
    ctx_high   = {"cortisol": 700.0, "glucose": 85.0, "il6": 3.0}
    assert _crh_baseline_fn(12.0, ctx_high) < _crh_baseline_fn(12.0, ctx_normal)


def test_advance_hpa_crh_approaches_baseline():
    """After a tick, an elevated CRH decays toward its computed target."""
    from src.sim.physio.hpa import advance_hpa
    from src.sim.events import EventBus
    s = make_state()
    s.neuroendocrine["crh"] = 100.0   # elevated
    s = advance_hpa(s, sim_hours=1.0, now=time.time(), hour_of_day=12.0, event_bus=EventBus())
    assert s.neuroendocrine["crh"] < 100.0


# ---------------------------------------------------------------------------
# Thyroid axis
# ---------------------------------------------------------------------------

def test_thyroid_defaults_initialized():
    s = make_state()
    assert abs(s.neuroendocrine["tsh"]  - 2.0)   < 0.01
    assert abs(s.neuroendocrine["t4"]   - 8.0)   < 0.01
    assert abs(s.neuroendocrine["t3"]   - 120.0) < 0.01


def test_high_cortisol_suppresses_tsh_target():
    """Chronic high cortisol reduces the TSH target (stress-induced subclinical hypothyroidism)."""
    from src.sim.physio.endocrine import _advance_thyroid
    s_normal = make_state(cortisol=250.0)
    s_high   = make_state(cortisol=800.0)
    s_normal = _advance_thyroid(s_normal, sim_hours=1.0)
    s_high   = _advance_thyroid(s_high,   sim_hours=1.0)
    assert s_high.neuroendocrine["tsh"] <= s_normal.neuroendocrine["tsh"]


def test_t3_driven_by_t4_driven_by_tsh():
    """
    Thyroid cascade: boosting TSH raises T4 target, which raises T3 target.
    After several hours, T3 should be higher when TSH is elevated.
    """
    from src.sim.physio.endocrine import _advance_thyroid
    s = make_state()
    s.neuroendocrine["tsh"] = 4.0   # twice normal
    for _ in range(20):             # 20 sim-hours to let cascade propagate
        s = _advance_thyroid(s, sim_hours=1.0)
    assert s.neuroendocrine["t4"] > 8.0
    assert s.neuroendocrine["t3"] > 120.0


def test_t3_low_suppresses_serotonin_baseline():
    """Hypothyroid T3 should lower the serotonin baseline via baseline_fn."""
    from src.sim.chem.registry import _serotonin_baseline_fn
    ctx_normal = {"t3": 120.0, "cortisol": 250.0, "estradiol": 100.0}
    ctx_hypo   = {"t3":  50.0, "cortisol": 250.0, "estradiol": 100.0}
    assert _serotonin_baseline_fn(12.0, ctx_hypo) < _serotonin_baseline_fn(12.0, ctx_normal)


def test_t3_high_raises_serotonin_baseline():
    """Hyperthyroid T3 should raise the serotonin baseline (capped at 1.3×)."""
    from src.sim.chem.registry import _serotonin_baseline_fn
    ctx_normal = {"t3": 120.0, "cortisol": 250.0, "estradiol": 100.0}
    ctx_hyper  = {"t3": 250.0, "cortisol": 250.0, "estradiol": 100.0}
    assert _serotonin_baseline_fn(12.0, ctx_hyper) > _serotonin_baseline_fn(12.0, ctx_normal)


# ---------------------------------------------------------------------------
# Metabolic — ghrelin / leptin / insulin / glucose
# ---------------------------------------------------------------------------

def test_ghrelin_peaks_before_meal_hours():
    """Ghrelin baseline is highest at 7am, 12:30pm, 6pm vs. off-peak hours."""
    from src.sim.physio.metabolic import _ghrelin_baseline_fn
    ctx = {"glucose": 85.0, "leptin": 15.0}
    for meal_hour in [7.0, 12.5, 18.0]:
        at_meal = _ghrelin_baseline_fn(meal_hour, ctx)
        at_odd  = _ghrelin_baseline_fn(meal_hour + 3.0, ctx)
        assert at_meal > at_odd, f"Ghrelin should peak at hour {meal_hour}"


def test_ghrelin_elevated_by_low_glucose():
    """Low glucose (fasting) raises the ghrelin baseline."""
    from src.sim.physio.metabolic import _ghrelin_baseline_fn
    ctx_normal = {"glucose": 85.0, "leptin": 15.0}
    ctx_low    = {"glucose": 60.0, "leptin": 15.0}
    assert _ghrelin_baseline_fn(10.0, ctx_low) > _ghrelin_baseline_fn(10.0, ctx_normal)


def test_leptin_suppresses_ghrelin_baseline():
    """High leptin (satiety) suppresses ghrelin baseline."""
    from src.sim.physio.metabolic import _ghrelin_baseline_fn
    ctx_normal    = {"glucose": 85.0, "leptin": 15.0}
    ctx_saturated = {"glucose": 85.0, "leptin": 25.0}
    assert _ghrelin_baseline_fn(10.0, ctx_saturated) < _ghrelin_baseline_fn(10.0, ctx_normal)


def test_insulin_rises_with_high_glucose():
    """Post-meal glucose (>80 mg/dL) drives insulin target positive."""
    from src.sim.physio.metabolic import _advance_insulin
    s = make_state()
    s.chemicals["glucose"] = 150.0   # post-meal spike
    s.neuroendocrine["insulin"] = 5.0
    s = _advance_insulin(s, sim_hours=1.0)
    assert s.neuroendocrine["insulin"] > 5.0


def test_insulin_falls_with_normal_glucose():
    """When glucose is at or below 80 mg/dL, insulin target is the fasting minimum."""
    from src.sim.physio.metabolic import _advance_insulin
    s = make_state()
    s.chemicals["glucose"] = 75.0
    s.neuroendocrine["insulin"] = 50.0   # elevated (post-meal)
    s = _advance_insulin(s, sim_hours=1.0)
    assert s.neuroendocrine["insulin"] < 50.0


def test_glucose_decays_awake():
    """Glucose decays faster while awake than while sleeping."""
    from src.sim.physio.metabolic import _advance_glucose
    s_awake   = make_state()
    s_sleeping = make_state()
    s_awake.sleeping   = False
    s_sleeping.sleeping = True
    s_awake.chemicals["glucose"]    = 85.0
    s_sleeping.chemicals["glucose"] = 85.0
    s_awake    = _advance_glucose(s_awake,    sim_hours=1.0)
    s_sleeping = _advance_glucose(s_sleeping, sim_hours=1.0)
    assert s_awake.chemicals["glucose"] < s_sleeping.chemicals["glucose"]


def test_high_ghrelin_reduces_dopamine():
    """Ghrelin > 600 nudges dopamine down (hunger impairs reward focus)."""
    from src.sim.physio.metabolic import _apply_metabolic_cross_effects
    s = make_state()
    s.neuroendocrine["ghrelin"] = 700.0
    dopamine_before = s.chemicals["dopamine"]
    s = _apply_metabolic_cross_effects(s, sim_hours=1.0)
    assert s.chemicals["dopamine"] < dopamine_before


def test_very_high_ghrelin_raises_cortisol():
    """Ghrelin > 800 triggers a physiological stress response (cortisol increase)."""
    from src.sim.physio.metabolic import _apply_metabolic_cross_effects
    s = make_state()
    s.neuroendocrine["ghrelin"] = 850.0
    cortisol_before = s.chemicals["cortisol"]
    s = _apply_metabolic_cross_effects(s, sim_hours=1.0)
    assert s.chemicals["cortisol"] > cortisol_before


def test_low_ghrelin_raises_oxytocin():
    """Ghrelin < 200 (satiated) triggers a slight oxytocin/mood lift."""
    from src.sim.physio.metabolic import _apply_metabolic_cross_effects
    s = make_state()
    s.neuroendocrine["ghrelin"] = 150.0
    oxytocin_before = s.chemicals["oxytocin"]
    s = _apply_metabolic_cross_effects(s, sim_hours=1.0)
    assert s.chemicals["oxytocin"] > oxytocin_before


# ---------------------------------------------------------------------------
# Sex hormones / menstrual cycle
# ---------------------------------------------------------------------------

def test_cycle_day_advances_correctly():
    """cycle_day increments with sim time and wraps at 28."""
    from src.sim.physio.endocrine import _advance_cycle
    s = make_state()
    s.cycle_day = 27.0
    s = _advance_cycle(s, sim_hours=48.0)   # 2 days
    assert 0 < s.cycle_day <= 28.0


def test_estradiol_peaks_near_ovulation():
    """At cycle day 14 (ovulation), estradiol target is at its maximum."""
    from src.sim.physio.endocrine import _advance_cycle
    s_early = make_state()
    s_ovul  = make_state()
    s_early.cycle_day = 2.0
    s_ovul.cycle_day  = 13.9   # just before ovulation
    # Run 1 sim-hour to allow some approach
    s_early = _advance_cycle(s_early, sim_hours=1.0)
    s_ovul  = _advance_cycle(s_ovul,  sim_hours=1.0)
    assert s_ovul.neuroendocrine["estradiol"] > s_early.neuroendocrine["estradiol"]


def test_progesterone_rises_in_luteal_phase():
    """Progesterone should be higher in mid-luteal phase (day 20) than in follicular (day 8)."""
    from src.sim.physio.endocrine import _advance_cycle
    s_follicular = make_state()
    s_luteal     = make_state()
    s_follicular.cycle_day = 8.0
    s_luteal.cycle_day     = 20.0
    s_follicular = _advance_cycle(s_follicular, sim_hours=1.0)
    s_luteal     = _advance_cycle(s_luteal,     sim_hours=1.0)
    assert s_luteal.neuroendocrine["progesterone"] > s_follicular.neuroendocrine["progesterone"]


def test_low_estradiol_nudges_serotonin_down():
    """Low estradiol phase (< 50 pg/mL) gradually reduces serotonin."""
    from src.sim.physio.endocrine import _apply_cross_effects
    s = make_state()
    s.neuroendocrine["estradiol"] = 30.0   # menstrual phase
    serotonin_before = s.chemicals["serotonin"]
    s = _apply_cross_effects(s, sim_hours=1.0)
    assert s.chemicals["serotonin"] < serotonin_before


def test_high_progesterone_nudges_gaba_up():
    """High progesterone (luteal peak) should raise GABA slightly."""
    from src.sim.physio.endocrine import _apply_cross_effects
    s = make_state()
    s.neuroendocrine["progesterone"] = 10.0   # mid-luteal
    gaba_before = s.chemicals["gaba"]
    s = _apply_cross_effects(s, sim_hours=1.0)
    assert s.chemicals["gaba"] > gaba_before


# ---------------------------------------------------------------------------
# DHEA
# ---------------------------------------------------------------------------

def test_dhea_suppressed_by_chronic_cortisol():
    """High chronic cortisol should drive DHEA toward a lower target."""
    from src.sim.physio.endocrine import _advance_dhea
    s = make_state()
    s.chemicals["cortisol"]    = 900.0
    s.neuroendocrine["dhea"]   = 150.0
    s = _advance_dhea(s, sim_hours=1.0, hour_of_day=12.0)
    assert s.neuroendocrine["dhea"] < 150.0


def test_high_dhea_suppresses_cortisol():
    """DHEA > 200 should nudge cortisol down slightly (anti-stress buffer)."""
    from src.sim.physio.endocrine import _apply_cross_effects
    s = make_state()
    s.neuroendocrine["dhea"] = 250.0
    cortisol_before = s.chemicals["cortisol"]
    s = _apply_cross_effects(s, sim_hours=1.0)
    assert s.chemicals["cortisol"] < cortisol_before


# ---------------------------------------------------------------------------
# Prolactin
# ---------------------------------------------------------------------------

def test_prolactin_elevated_during_sleep():
    """Prolactin target is higher during sleep than wakefulness."""
    from src.sim.physio.endocrine import _advance_prolactin
    s_awake   = make_state()
    s_sleeping = make_state()
    s_awake.sleeping   = False
    s_sleeping.sleeping = True
    s_awake.neuroendocrine["prolactin"]    = 8.0
    s_sleeping.neuroendocrine["prolactin"] = 8.0
    s_awake    = _advance_prolactin(s_awake,    sim_hours=2.0)
    s_sleeping = _advance_prolactin(s_sleeping, sim_hours=2.0)
    assert s_sleeping.neuroendocrine["prolactin"] > s_awake.neuroendocrine["prolactin"]


def test_high_prolactin_suppresses_dopamine():
    """Prolactin > 40 nudges dopamine down (post-reward refractory)."""
    from src.sim.physio.endocrine import _apply_cross_effects
    s = make_state()
    s.neuroendocrine["prolactin"] = 60.0
    dopamine_before = s.chemicals["dopamine"]
    s = _apply_cross_effects(s, sim_hours=1.0)
    assert s.chemicals["dopamine"] < dopamine_before


# ---------------------------------------------------------------------------
# Vasopressin
# ---------------------------------------------------------------------------

def test_vasopressin_elevated_by_dehydration():
    """Dehydration (hydration < 58) should drive vasopressin target up."""
    from src.sim.physio.endocrine import _advance_vasopressin
    s_hydrated    = make_state()
    s_dehydrated  = make_state()
    s_hydrated.chemicals["hydration"]   = 62.0
    s_dehydrated.chemicals["hydration"] = 52.0
    s_hydrated.neuroendocrine["vasopressin"]   = 2.0
    s_dehydrated.neuroendocrine["vasopressin"] = 2.0
    s_hydrated    = _advance_vasopressin(s_hydrated,   sim_hours=2.0)
    s_dehydrated  = _advance_vasopressin(s_dehydrated, sim_hours=2.0)
    assert s_dehydrated.neuroendocrine["vasopressin"] > s_hydrated.neuroendocrine["vasopressin"]


def test_high_vasopressin_adds_hydration_retention():
    """Vasopressin > 10 applies a positive hydration correction (ADH water retention)."""
    from src.sim.physio.metabolic import _apply_metabolic_cross_effects
    s = make_state()
    s.neuroendocrine["vasopressin"] = 12.0
    hydration_before = s.chemicals["hydration"]
    s = _apply_metabolic_cross_effects(s, sim_hours=1.0)
    assert s.chemicals["hydration"] > hydration_before


# ---------------------------------------------------------------------------
# Growth hormone
# ---------------------------------------------------------------------------

def test_growth_hormone_elevated_early_in_sleep():
    """GH target is 8 ng/mL during first 2 hours of sleep, so it should rise from baseline."""
    from src.sim.physio.endocrine import _advance_growth_hormone
    import time as _time
    s = make_state()
    s.sleeping   = True
    s.sleep_start = _time.time() - 1800   # 30 min ago (< 2 hours)
    s.neuroendocrine["growth_hormone"] = 0.5
    s = _advance_growth_hormone(s, sim_hours=1.0)
    assert s.neuroendocrine["growth_hormone"] > 0.5


def test_growth_hormone_low_when_awake():
    """GH target when awake is 0.5 ng/mL, so it should fall from an elevated value."""
    from src.sim.physio.endocrine import _advance_growth_hormone
    s = make_state()
    s.sleeping = False
    s.neuroendocrine["growth_hormone"] = 8.0   # elevated (post-sleep-pulse)
    s = _advance_growth_hormone(s, sim_hours=2.0)
    assert s.neuroendocrine["growth_hormone"] < 8.0


# ---------------------------------------------------------------------------
# ACTH-driven cortisol baseline
# ---------------------------------------------------------------------------

def test_cortisol_baseline_driven_by_acth():
    """Higher ACTH should produce a higher cortisol baseline."""
    from src.sim.chem.registry import _cortisol_baseline_fn
    ctx_low_acth  = {"acth": 10.0, "hydration": 62.0, "glucose": 85.0}
    ctx_high_acth = {"acth": 50.0, "hydration": 62.0, "glucose": 85.0}
    assert _cortisol_baseline_fn(12.0, ctx_high_acth) > _cortisol_baseline_fn(12.0, ctx_low_acth)


def test_cortisol_baseline_has_circadian_variation():
    """Cortisol baseline should be higher at 8am than at 8pm."""
    from src.sim.chem.registry import _cortisol_baseline_fn
    ctx = {"acth": 25.0, "hydration": 62.0, "glucose": 85.0}
    assert _cortisol_baseline_fn(8.0, ctx) > _cortisol_baseline_fn(20.0, ctx)
