"""Tests for hippocampus.py — memory parsing and robustness."""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hippocampus import (
    _parse_json_robust,
    _extract_tag,
    _parse_consolidation_output,
)


# ---------------------------------------------------------------------------
# _parse_json_robust
# ---------------------------------------------------------------------------

def test_parse_json_robust_handles_json_embedded_in_prose():
    text = 'Here is the data: [{"text": "memory one", "metadata": {"type": "episodic"}}] and more text'
    result = _parse_json_robust(text)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["text"] == "memory one"


def test_parse_json_robust_parses_plain_json_object():
    text = '{"RELATIONSHIP.md": "Updated content here", "PENDING.md": null}'
    result = _parse_json_robust(text)
    assert isinstance(result, dict)
    assert result["RELATIONSHIP.md"] == "Updated content here"
    assert result["PENDING.md"] is None


def test_parse_json_robust_returns_none_on_garbage_input():
    result = _parse_json_robust("this is not json at all ))))")
    assert result is None


def test_parse_json_robust_returns_none_on_empty():
    assert _parse_json_robust("") is None
    assert _parse_json_robust("   ") is None


# ---------------------------------------------------------------------------
# _parse_consolidation_output
# ---------------------------------------------------------------------------

_SAMPLE_OUTPUT = """
<reflection_summary>
Had a warm conversation about music preferences.
</reflection_summary>
<rag_entries>
[{"text": "User mentioned loving Radiohead", "metadata": {"type": "episodic", "importance": "medium"}}]
</rag_entries>
<kag_updates>
{"RELATIONSHIP.md": "Trust is building.", "PENDING.md": null}
</kag_updates>
"""


def test_parse_consolidation_output_extracts_rag_entries():
    result = _parse_consolidation_output(_SAMPLE_OUTPUT)
    assert len(result["rag_entries"]) == 1
    assert "Radiohead" in result["rag_entries"][0]["text"]


def test_parse_consolidation_output_extracts_kag_updates():
    result = _parse_consolidation_output(_SAMPLE_OUTPUT)
    assert "RELATIONSHIP.md" in result["kag_updates"]
    assert "Trust is building" in result["kag_updates"]["RELATIONSHIP.md"]


def test_parse_consolidation_output_returns_empty_structure_on_missing_tags():
    result = _parse_consolidation_output("No tags here, just noise.")
    assert result["reflection_summary"] == ""
    assert result["rag_entries"] == []
    assert result["kag_updates"] == {}
