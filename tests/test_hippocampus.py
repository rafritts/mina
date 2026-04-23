"""Tests for hippocampus.py — memory parsing and robustness."""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.brain.hippocampus.hippocampus import (
    _parse_json_robust,
    _extract_tag,
    _parse_consolidation_output,
    _IDENTITY_DIR,
    _KAG_DIR,
    read_identity,
    read_kag,
)
from src.config.config import REPO_ROOT, PROJECT_ROOT, CONFIG_FILE


# ---------------------------------------------------------------------------
# Path resolution — ensure injected files are reachable after src/ restructure
# ---------------------------------------------------------------------------

def test_repo_root_is_not_src():
    """PROJECT_ROOT points at src/; REPO_ROOT must be one level up."""
    assert os.path.basename(PROJECT_ROOT) == "src"
    assert REPO_ROOT == os.path.dirname(PROJECT_ROOT)


def test_identity_dir_exists():
    assert os.path.isdir(_IDENTITY_DIR), f"identity dir not found: {_IDENTITY_DIR}"


def test_kag_dir_exists():
    assert os.path.isdir(_KAG_DIR), f"KAG dir not found: {_KAG_DIR}"


def test_config_file_exists():
    assert os.path.isfile(CONFIG_FILE), f"config.json not found: {CONFIG_FILE}"


def test_mina_md_readable():
    content = read_identity("MINA.md")
    assert content, "MINA.md returned empty — file missing or unreadable"


def test_customization_md_readable():
    # File is blank by default — Mina fills it herself. Verify it exists, not that it has content.
    content = read_identity("CUSTOMIZATION.md")
    assert content is not None, "CUSTOMIZATION.md not readable — file missing"


def test_relationship_md_readable():
    # SPEC-39: legacy RELATIONSHIP.md removed — SPEC-33 relationship/ryan.md is canonical.
    # This test now verifies the new path works via read_relationship().
    from src.brain.hippocampus.hippocampus import read_relationship
    from src.config.config import load_config
    owner = load_config().get("admin_name", "default")
    content = read_relationship(owner)
    assert content is not None  # allowed to be empty if no relationship written yet


def test_reflection_md_readable():
    content = read_kag("REFLECTION.md")
    assert content is not None  # allowed to be empty string, but not a file-not-found silent failure


def test_identity_files_not_under_src():
    """Guard against regression: identity dir must not be inside src/."""
    assert not _IDENTITY_DIR.startswith(PROJECT_ROOT), (
        f"_IDENTITY_DIR is inside src/ — path resolution regression: {_IDENTITY_DIR}"
    )


def test_kag_dir_not_under_src():
    """Guard against regression: KAG dir must not be inside src/."""
    assert not _KAG_DIR.startswith(PROJECT_ROOT), (
        f"_KAG_DIR is inside src/ — path resolution regression: {_KAG_DIR}"
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
