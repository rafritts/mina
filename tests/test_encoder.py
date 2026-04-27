"""Tests for encoder.py — saturation, personality scaling, and LLM boundary."""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.brain.brainstem.state import BiologicalState
from src.brain.amygdala.stimulus_encoder import (
    _apply_saturation,
    _apply_personality_scaling,
    _personality_multipliers,
    encode_stimulus,
    encode_response,
    evaluate_activity_deltas,
)


def make_state(**chem_overrides) -> BiologicalState:
    s = BiologicalState()
    s.chemicals.update(chem_overrides)
    return s


# ---------------------------------------------------------------------------
# Saturation
# ---------------------------------------------------------------------------

def test_saturation_drops_delta_to_zero_above_hard_ceiling():
    from src.engine.chem.registry import REGISTRY
    hard = REGISTRY["dopamine"].hard_ceiling
    state = make_state(dopamine=hard)
    result = _apply_saturation({"dopamine": 50.0}, state)
    assert result.get("dopamine", 0.0) == 0.0


def test_saturation_scales_quadratically_in_soft_to_hard_zone():
    from src.engine.chem.registry import REGISTRY
    soft = REGISTRY["dopamine"].soft_ceiling
    hard = REGISTRY["dopamine"].hard_ceiling
    midpoint = soft + (hard - soft) * 0.5
    state = make_state(dopamine=midpoint)
    # At the midpoint, quadratic scale = (1 - 0.5)^2 = 0.25
    result = _apply_saturation({"dopamine": 100.0}, state)
    # Should be ~25% of original, capped at remaining headroom
    scaled = result.get("dopamine", 0.0)
    assert 0 < scaled < 50.0  # well below linear scaling


def test_saturation_passes_delta_unchanged_below_soft_ceiling():
    from src.engine.chem.registry import REGISTRY
    soft = REGISTRY["dopamine"].soft_ceiling
    state = make_state(dopamine=soft * 0.5)  # well below soft
    result = _apply_saturation({"dopamine": 20.0}, state)
    assert result["dopamine"] == 20.0


def test_saturation_does_not_touch_negative_deltas():
    state = BiologicalState()
    result = _apply_saturation({"cortisol": -50.0}, state)
    assert result["cortisol"] == -50.0


# ---------------------------------------------------------------------------
# Personality scaling
# ---------------------------------------------------------------------------

def test_personality_scaling_amplifies_cortisol_spike_at_high_neuroticism():
    personality = {"big5": {"neuroticism": 90, "extraversion": 50, "agreeableness": 50,
                            "conscientiousness": 50, "openness": 50}}
    result = _apply_personality_scaling({"cortisol": 100.0}, personality)
    # High N should amplify positive cortisol spike (n_factor = 0.8 + 0.9*0.6 = 1.34)
    assert result["cortisol"] > 100.0


def test_personality_scaling_dampens_cortisol_recovery_at_high_neuroticism():
    personality = {"big5": {"neuroticism": 90, "extraversion": 50, "agreeableness": 50,
                            "conscientiousness": 50, "openness": 50}}
    result = _apply_personality_scaling({"cortisol": -50.0}, personality)
    # High N inverts the factor for negative cortisol (recovery is slower)
    assert abs(result["cortisol"]) < 50.0


def test_personality_scaling_identity_when_no_personality_loaded():
    result = _apply_personality_scaling({"dopamine": 20.0, "cortisol": -10.0}, {})
    assert result == {"dopamine": 20.0, "cortisol": -10.0}


# ---------------------------------------------------------------------------
# LLM boundary — SPEC-29: neurotransmitters go to secretion queue, not return dict
# ---------------------------------------------------------------------------

def _mock_llm_response(content: str):
    """Build a mock response matching OpenAI chat completion structure."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@patch("src.brain.amygdala.stimulus_encoder._get_embedding", return_value=None)  # skip Ollama in tests
@patch("src.brain.amygdala.stimulus_encoder.chat_create")
@patch("src.brain.amygdala.stimulus_encoder._load_personality", return_value={})
def test_encode_stimulus_queues_neurotransmitter_deltas(mock_personality, mock_chat, mock_embed):
    """Neurotransmitter deltas go to state.secretion_queue, not the return dict."""
    mock_chat.return_value = _mock_llm_response(
        '{"no_external_deltas": false, "reasoning": "test", "event_override": false, "dopamine": 15.0}'
    )
    from src.application.infra import token_stats
    state = BiologicalState()
    result = encode_stimulus(state, "hello world")
    # dopamine is a secretion-queue chemical — should NOT be in immediate return
    assert "dopamine" not in result
    # should be in the secretion queue instead
    queued_chems = [e["chemical"] for e in state.secretion_queue]
    assert "dopamine" in queued_chems


@patch("src.brain.amygdala.stimulus_encoder._get_embedding", return_value=None)
@patch("src.brain.amygdala.stimulus_encoder.chat_create")
@patch("src.brain.amygdala.stimulus_encoder._load_personality", return_value={})
def test_encode_stimulus_skips_apply_on_no_external_deltas(mock_personality, mock_chat, mock_embed):
    mock_chat.return_value = _mock_llm_response(
        '{"no_external_deltas": true, "reasoning": "nothing happened"}'
    )
    state = BiologicalState()
    result = encode_stimulus(state, "just sitting here")
    assert result == {}
    assert state.secretion_queue == []


@patch("src.brain.amygdala.stimulus_encoder._get_embedding", return_value=None)
@patch("src.brain.amygdala.stimulus_encoder.chat_create")
@patch("src.brain.amygdala.stimulus_encoder._load_personality", return_value={})
def test_encode_stimulus_returns_empty_on_llm_error(mock_personality, mock_chat, mock_embed):
    mock_chat.side_effect = Exception("API down")
    state = BiologicalState()
    result = encode_stimulus(state, "test message")
    assert result == {}  # must not crash


@patch("src.brain.amygdala.stimulus_encoder._get_embedding", return_value=None)
@patch("src.brain.amygdala.stimulus_encoder.chat_create")
@patch("src.brain.amygdala.stimulus_encoder._load_personality", return_value={})
def test_encode_response_queues_oxytocin(mock_personality, mock_chat, mock_embed):
    mock_chat.return_value = _mock_llm_response(
        '{"no_external_deltas": false, "reasoning": "spoke warmly", "event_override": false, "oxytocin": 3.0}'
    )
    state = BiologicalState()
    result = encode_response(state, "I really appreciate you being here.")
    queued_chems = [e["chemical"] for e in state.secretion_queue]
    assert "oxytocin" in queued_chems


@patch("src.brain.amygdala.stimulus_encoder._get_embedding", return_value=None)
@patch("src.brain.amygdala.stimulus_encoder.chat_create")
@patch("src.brain.amygdala.stimulus_encoder._load_personality", return_value={})
def test_evaluate_activity_deltas_passes_activity_and_description_to_llm(mock_personality, mock_chat, mock_embed):
    call_args_list = []
    def capture(*args, **kwargs):
        call_args_list.append(kwargs.get("messages", args[0] if args else []))
        return _mock_llm_response('{"no_external_deltas": false, "reasoning": "ate", "event_override": false, "glucose": 30.0}')
    mock_chat.side_effect = capture
    state = BiologicalState()
    result = evaluate_activity_deltas(state, "eat scrambled eggs", "Ate quickly, was hungry.")
    # Verify the call was made and activity content was in the prompt
    assert len(call_args_list) > 0
    prompt_text = str(call_args_list[0])
    assert "scrambled eggs" in prompt_text
    # glucose is a metabolic chemical — applied immediately, not queued
    assert "glucose" in result


@patch("src.brain.amygdala.stimulus_encoder._get_embedding", return_value=None)
@patch("src.brain.amygdala.stimulus_encoder.chat_create")
@patch("src.brain.amygdala.stimulus_encoder._load_personality", return_value={})
def test_event_override_bypasses_queue(mock_personality, mock_chat, mock_embed):
    """EVENT_OVERRIDE deltas are returned immediately, not queued."""
    mock_chat.return_value = _mock_llm_response(
        '{"no_external_deltas": false, "reasoning": "peak resolution", "event_override": true, '
        '"dopamine": -120.0, "norepinephrine": -80.0}'
    )
    state = BiologicalState()
    result = evaluate_activity_deltas(state, "intense physical exertion", "Peak resolution resolution.")
    # EVENT_OVERRIDE: returned directly for immediate application
    assert "dopamine" in result
    assert result["dopamine"] == pytest.approx(-120.0, rel=0.01)
    assert state.secretion_queue == []
