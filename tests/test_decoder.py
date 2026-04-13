"""Tests for decoder.py — biological report and prompt parsing."""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.bio.state import BiologicalState
from src.bio.decoder import (
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
# _parse_decoder_json — JSON extraction and validation
# ---------------------------------------------------------------------------

_SAMPLE_JSON = '{"primary_feeling": "calm", "secondary_feeling": "a bit tired", "emotional_snapshot": "Grounded. Not reaching.", "notify": false}'
_SAMPLE_JSON_FENCED = '```json\n' + _SAMPLE_JSON + '\n```'


def test_parse_decoder_json_extracts_all_fields():
    data = _parse_decoder_json(_SAMPLE_JSON)
    assert data["primary_feeling"] == "calm"
    assert data["secondary_feeling"] == "a bit tired"
    assert data["emotional_snapshot"] == "Grounded. Not reaching."
    assert data["notify"] is False


def test_parse_decoder_json_strips_markdown_fences():
    data = _parse_decoder_json(_SAMPLE_JSON_FENCED)
    assert data["primary_feeling"] == "calm"


def test_parse_decoder_json_raises_on_missing_keys():
    with pytest.raises((ValueError, KeyError)):
        _parse_decoder_json('{"something_else": "Direct."}')


def test_parse_decoder_json_raises_on_invalid_json():
    with pytest.raises(Exception):
        _parse_decoder_json("not json at all")


# ---------------------------------------------------------------------------
# _assemble_system_prompt — section assembly
# ---------------------------------------------------------------------------

def test_assemble_includes_snapshot_and_feelings():
    sections = {
        "primary_feeling": "restless",
        "secondary_feeling": "vaguely hungry",
        "emotional_snapshot": "You're wound up and can't sit still.",
        "notify": False,
    }
    result = _assemble_system_prompt(sections)
    assert "Emotional snapshot" in result
    assert "You're wound up and can't sit still." in result
    assert "Primary: restless" in result
    assert "Secondary: vaguely hungry" in result
    assert "internal context only" in result


def test_assemble_notify_true_includes_strong_emotion_instruction():
    sections = {
        "primary_feeling": "overwhelmed",
        "secondary_feeling": "exhausted",
        "emotional_snapshot": "Everything feels too heavy.",
        "notify": True,
    }
    result = _assemble_system_prompt(sections)
    assert "overwhelmed" in result
    assert "containing it completely would be unrealistic" in result


def test_assemble_returns_empty_when_no_content():
    sections = {
        "primary_feeling": "",
        "secondary_feeling": "",
        "emotional_snapshot": "",
        "notify": False,
    }
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


_SAMPLE_RAW = '{"primary_feeling": "quiet", "secondary_feeling": "settled", "emotional_snapshot": "Not reaching for anything.", "notify": false}'


@patch("src.bio.decoder.get_client")
@patch("src.bio.decoder._load_personality_block", return_value="")
@patch("src.bio.decoder._consume_injection", return_value="")
@patch("src.memory.hippocampus.read_identity", return_value="")
def test_build_system_prompt_returns_emotional_snapshot(
    mock_identity, mock_inj, mock_pers, mock_client
):
    mock_client.return_value.chat.completions.create.return_value = _mock_llm_response(_SAMPLE_RAW)
    prompt = build_system_prompt("bio report")
    assert "Emotional snapshot" in prompt


@patch("src.bio.decoder.get_client")
@patch("src.bio.decoder._load_personality_block", return_value="")
@patch("src.bio.decoder._consume_injection", return_value="")
@patch("src.memory.hippocampus.read_identity", return_value="")
def test_build_system_prompt_includes_dynamic_sections(
    mock_identity, mock_inj, mock_pers, mock_client
):
    mock_client.return_value.chat.completions.create.return_value = _mock_llm_response(_SAMPLE_RAW)
    prompt = build_system_prompt("bio report")
    assert "Not reaching for anything." in prompt
    assert "Primary: quiet" in prompt


@patch("src.bio.decoder.get_client")
@patch("src.bio.decoder._load_personality_block", return_value="")
@patch("src.bio.decoder._consume_injection", return_value="")
@patch("src.memory.hippocampus.read_identity", return_value="")
def test_build_system_prompt_retries_on_bad_json(
    mock_identity, mock_inj, mock_pers, mock_client
):
    bad = _mock_llm_response("not json")
    good = _mock_llm_response(_SAMPLE_RAW)
    mock_client.return_value.chat.completions.create.side_effect = [bad, good]
    prompt = build_system_prompt("bio report")
    assert "Not reaching for anything." in prompt


@patch("src.bio.decoder.get_client")
@patch("src.bio.decoder._load_personality_block", return_value="")
@patch("src.bio.decoder._consume_injection", return_value="")
@patch("src.memory.hippocampus.read_identity", return_value="")
def test_build_system_prompt_returns_string_when_all_retries_fail(
    mock_identity, mock_inj, mock_pers, mock_client
):
    bad = _mock_llm_response("not json")
    mock_client.return_value.chat.completions.create.return_value = bad
    prompt = build_system_prompt("bio report")
    assert isinstance(prompt, str)
