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
    _parse_decoder_json,
    _assemble_system_prompt,
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
# _parse_decoder_json — JSON extraction and validation
# ---------------------------------------------------------------------------

_SAMPLE_JSON = '{"how_you_are": "Grounded. Not reaching."}'
_SAMPLE_JSON_FENCED = '```json\n' + _SAMPLE_JSON + '\n```'


def test_parse_decoder_json_extracts_all_fields():
    data = _parse_decoder_json(_SAMPLE_JSON)
    assert data["how_you_are"] == "Grounded. Not reaching."


def test_parse_decoder_json_strips_markdown_fences():
    data = _parse_decoder_json(_SAMPLE_JSON_FENCED)
    assert data["how_you_are"] == "Grounded. Not reaching."


def test_parse_decoder_json_raises_on_missing_keys():
    import pytest
    with pytest.raises((ValueError, KeyError)):
        _parse_decoder_json('{"something_else": "Direct."}')


def test_parse_decoder_json_raises_on_invalid_json():
    import pytest
    with pytest.raises(Exception):
        _parse_decoder_json("not json at all")


# ---------------------------------------------------------------------------
# _assemble_system_prompt — section assembly
# ---------------------------------------------------------------------------

def test_assemble_includes_present_sections():
    sections = {"how_you_are": "Grounded."}
    result = _assemble_system_prompt(sections)
    assert "## How you're feeling right now" in result
    assert "Grounded." in result
    assert "emotional snapshot" in result


def test_assemble_returns_empty_when_no_content():
    sections = {"how_you_are": None}
    result = _assemble_system_prompt(sections)
    assert result == ""


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


_SAMPLE_RAW = '{"how_you_are": "Quiet. Not reaching."}'


@patch("decoder.get_client")
@patch("decoder._load_personality_block", return_value="")
@patch("decoder._consume_injection", return_value="")
@patch("hippocampus.read_identity", return_value="")
def test_build_system_prompt_returns_emotional_snapshot(
    mock_identity, mock_inj, mock_pers, mock_client
):
    mock_client.return_value.chat.completions.create.return_value = _mock_llm_response(_SAMPLE_RAW)
    prompt = build_system_prompt("bio report")
    assert "emotional snapshot" in prompt


@patch("decoder.get_client")
@patch("decoder._load_personality_block", return_value="")
@patch("decoder._consume_injection", return_value="")
@patch("hippocampus.read_identity", return_value="")
def test_build_system_prompt_includes_dynamic_sections(
    mock_identity, mock_inj, mock_pers, mock_client
):
    mock_client.return_value.chat.completions.create.return_value = _mock_llm_response(_SAMPLE_RAW)
    prompt = build_system_prompt("bio report")
    assert "Quiet. Not reaching." in prompt
    assert "emotional snapshot" in prompt


@patch("decoder.get_client")
@patch("decoder._load_personality_block", return_value="")
@patch("decoder._consume_injection", return_value="")
@patch("hippocampus.read_identity", return_value="")
def test_build_system_prompt_retries_on_bad_json(
    mock_identity, mock_inj, mock_pers, mock_client
):
    bad = _mock_llm_response("not json")
    good = _mock_llm_response(_SAMPLE_RAW)
    mock_client.return_value.chat.completions.create.side_effect = [bad, good]
    prompt = build_system_prompt("bio report")
    assert "Quiet. Not reaching." in prompt


@patch("decoder.get_client")
@patch("decoder._load_personality_block", return_value="")
@patch("decoder._consume_injection", return_value="")
@patch("hippocampus.read_identity", return_value="")
def test_build_system_prompt_returns_string_when_all_retries_fail(
    mock_identity, mock_inj, mock_pers, mock_client
):
    bad = _mock_llm_response("not json")
    mock_client.return_value.chat.completions.create.return_value = bad
    prompt = build_system_prompt("bio report")
    assert isinstance(prompt, str)
