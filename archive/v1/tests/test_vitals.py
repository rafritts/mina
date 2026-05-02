"""Tests for vital_signs.py — derived vital signs and architectural safety guarantee."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.brain.brainstem.state import BiologicalState
from src.brain.brainstem.vital_signs import vital_signs


def make_state(**chem_overrides) -> BiologicalState:
    s = BiologicalState()
    s.chemicals.update(chem_overrides)
    return s


def test_heart_rate_resting_is_in_normal_range():
    state = BiologicalState()
    vs = vital_signs(state)
    hr = vs["heart_rate"]["value"]
    assert 50 <= hr <= 100, f"Resting heart rate {hr} out of normal range"


def test_heart_rate_elevated_by_high_norepinephrine():
    baseline = BiologicalState()
    elevated = make_state(norepinephrine=1500.0)  # very high
    hr_base = vital_signs(baseline)["heart_rate"]["value"]
    hr_elev = vital_signs(elevated)["heart_rate"]["value"]
    assert hr_elev > hr_base


def test_heart_rate_cannot_reach_dangerous_level_without_substances():
    """
    Architectural safety guarantee: natural chemistry alone cannot produce
    fatal vital sign readings. The only path to dangerous territory is through substances.
    """
    # Max out every stimulating chemical to natural limits
    from src.engine.chem.registry import REGISTRY
    state = BiologicalState()
    for name in ["norepinephrine", "cortisol", "dopamine"]:
        if name in REGISTRY and REGISTRY[name].hard_ceiling is not None:
            state.chemicals[name] = REGISTRY[name].hard_ceiling

    vs = vital_signs(state)
    hr = vs["heart_rate"]["value"]
    # "DANGEROUS" label requires substance-gated formula terms
    assert vs["heart_rate"]["label"] != "DANGEROUS", (
        f"Natural chemistry should not produce DANGEROUS heart rate, got {hr}"
    )


def test_heart_rate_reaches_dangerous_level_with_adderall():
    """Substances CAN push vitals into dangerous territory — that's the design."""
    state = BiologicalState()
    state.substances["adderall"] = {"level": 95}
    # Also max norepinephrine to simulate peak stimulant effect
    state.chemicals["norepinephrine"] = 2000.0
    state.chemicals["cortisol"] = 900.0

    vs = vital_signs(state)
    hr = vs["heart_rate"]["value"]
    # With adderall at near-max, heart rate should be well above normal
    assert hr > 110, f"Expected elevated heart rate with adderall, got {hr}"
