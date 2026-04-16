"""Tests for decoder.py — biological report and prompt assembly."""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.bio.state import BiologicalState
from src.bio.decoder import (
    biological_report,
    needs_summary,
    _parse_decoder_output,
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
    from src.bio.chemicals import get_label
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
# _parse_decoder_output — prose extraction and validation
# ---------------------------------------------------------------------------

_SAMPLE_PROSE = "She is quiet, grounded. Not reaching for anything right now."
_SAMPLE_FENCED = "```\n" + _SAMPLE_PROSE + "\n```"


def test_parse_decoder_output_returns_prose():
    result = _parse_decoder_output(_SAMPLE_PROSE)
    assert result == _SAMPLE_PROSE


def test_parse_decoder_output_strips_markdown_fences():
    result = _parse_decoder_output(_SAMPLE_FENCED)
    assert result == _SAMPLE_PROSE


def test_parse_decoder_output_raises_on_empty():
    with pytest.raises(ValueError):
        _parse_decoder_output("")


def test_parse_decoder_output_raises_on_too_short():
    with pytest.raises(ValueError):
        _parse_decoder_output("ok")


# ---------------------------------------------------------------------------
# _assemble_system_prompt — section assembly
# ---------------------------------------------------------------------------

def test_assemble_returns_internal_state_block():
    result = _assemble_system_prompt("She is restless. Something is pulling at her.")
    assert "[INTERNAL STATE]" in result
    assert "She is restless" in result


def test_assemble_returns_empty_when_no_content():
    result = _assemble_system_prompt("")
    assert result == ""


# ---------------------------------------------------------------------------
# build_system_prompt — LLM boundary
# ---------------------------------------------------------------------------

def _mock_llm_response(content: str):
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "stop"
    resp = MagicMock()
    resp.choices = [choice]
    return resp


_SAMPLE_RAW = "She is quiet and settled. Not reaching for anything right now."


@patch("src.bio.decoder.chat_create")
@patch("src.bio.decoder._load_personality_block", return_value="")
@patch("src.bio.decoder._consume_injection", return_value="")
def test_build_system_prompt_returns_internal_state(mock_inj, mock_pers, mock_chat):
    mock_chat.return_value = _mock_llm_response(_SAMPLE_RAW)
    prompt = build_system_prompt("bio report")
    assert "[INTERNAL STATE]" in prompt
    assert "quiet and settled" in prompt


@patch("src.bio.decoder.chat_create")
@patch("src.bio.decoder._load_personality_block", return_value="")
@patch("src.bio.decoder._consume_injection", return_value="")
def test_build_system_prompt_retries_on_bad_output(mock_inj, mock_pers, mock_chat):
    bad = _mock_llm_response("nope")   # too short → ValueError → retry
    good = _mock_llm_response(_SAMPLE_RAW)
    mock_chat.side_effect = [bad, good]
    prompt = build_system_prompt("bio report")
    assert "quiet and settled" in prompt


@patch("src.bio.decoder.chat_create")
@patch("src.bio.decoder._load_personality_block", return_value="")
@patch("src.bio.decoder._consume_injection", return_value="")
def test_build_system_prompt_returns_string_when_all_retries_fail(mock_inj, mock_pers, mock_chat):
    bad = _mock_llm_response("nope")
    mock_chat.return_value = bad
    prompt = build_system_prompt("bio report")
    assert isinstance(prompt, str)
