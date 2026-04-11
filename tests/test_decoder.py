"""Tests for decoder.py — biological report and prompt parsing."""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from state import BiologicalState
from decoder import (
    biological_report,
    needs_summary,
    _parse_decoder_output,
    _get_range,
    _CLARITY_RANGES,
    build_system_prompt,
)


def make_state(**chem_overrides) -> BiologicalState:
    s = BiologicalState()
    s.chemicals.update(chem_overrides)
    return s


# ---------------------------------------------------------------------------
# biological_report — pure Python
# ---------------------------------------------------------------------------

def test_biological_report_includes_all_chemicals():
    state = BiologicalState()
    report = biological_report(state)
    for chem in ["Cortisol", "Dopamine", "Serotonin", "Oxytocin", "Norepineph"]:
        assert chem in report


def test_biological_report_labels_cortisol_at_known_ranges():
    from chemicals import get_label
    state = make_state(cortisol=800.0)
    report = biological_report(state)
    label, _ = get_label("cortisol", 800.0)
    assert label in report


def test_biological_report_reflects_sleeping_state():
    state = BiologicalState()
    state.sleeping = True
    report = biological_report(state)
    assert "SLEEPING" in report


# ---------------------------------------------------------------------------
# _parse_decoder_output — XML tag extraction
# ---------------------------------------------------------------------------

def test_parse_decoder_output_extracts_observations_and_prompt():
    raw = """
<observations>
Still thinking about what he said.
</observations>
<system_prompt>
## What's on her mind
Still thinking about what he said.
</system_prompt>
"""
    obs, prompt = _parse_decoder_output(raw)
    assert "Still thinking" in obs
    assert "What's on her mind" in prompt


def test_parse_decoder_output_handles_missing_tags_gracefully():
    raw = "No tags here at all."
    obs, prompt = _parse_decoder_output(raw)
    assert obs == ""
    assert prompt == ""


def test_parse_decoder_output_handles_empty_string():
    obs, prompt = _parse_decoder_output("")
    assert obs == ""
    assert prompt == ""


# ---------------------------------------------------------------------------
# build_system_prompt — LLM boundary
# ---------------------------------------------------------------------------

def _mock_llm_response(content: str):
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


_SAMPLE_RAW = """
<observations>
Nothing in particular. Quiet.
</observations>
<system_prompt>
## What's on her mind
Nothing in particular. Quiet.

## Voice right now
Direct. Not reaching.
</system_prompt>
"""


@patch("decoder.get_client")
@patch("decoder._load_personality_block", return_value="")
@patch("decoder._consume_injection", return_value="")
@patch("decoder._observations")
@patch("hippocampus.read_identity", return_value="")
def test_build_system_prompt_appends_voice_constraints(
    mock_identity, mock_obs, mock_inj, mock_pers, mock_client
):
    mock_client.return_value.chat.completions.create.return_value = _mock_llm_response(_SAMPLE_RAW)
    mock_obs.read.return_value = ""

    prompt = build_system_prompt("bio report", [], "", "")
    assert "No emojis" in prompt


@patch("decoder.get_client")
@patch("decoder._load_personality_block", return_value="")
@patch("decoder._consume_injection", return_value="")
@patch("decoder._observations")
@patch("hippocampus.read_identity", return_value="")
def test_build_system_prompt_writes_observations_as_side_effect(
    mock_identity, mock_obs, mock_inj, mock_pers, mock_client
):
    mock_client.return_value.chat.completions.create.return_value = _mock_llm_response(_SAMPLE_RAW)
    mock_obs.read.return_value = ""

    build_system_prompt("bio report", [], "", "")

    mock_obs.write.assert_called_once()
    written = mock_obs.write.call_args[0][0]
    assert "Nothing in particular" in written


@patch("decoder.get_client")
@patch("decoder._load_personality_block", return_value="")
@patch("decoder._consume_injection", return_value="")
@patch("decoder._observations")
@patch("hippocampus.read_identity", return_value="")
def test_build_system_prompt_returns_fallback_when_llm_returns_empty(
    mock_identity, mock_obs, mock_inj, mock_pers, mock_client
):
    mock_client.return_value.chat.completions.create.return_value = _mock_llm_response("")
    mock_obs.read.return_value = ""
    mock_obs.write = MagicMock()

    prompt = build_system_prompt("bio report", [], "", "")
    assert isinstance(prompt, str)
