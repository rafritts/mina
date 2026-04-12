"""Tests for cortex.py — message assembly and history management."""
import json
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.runtime.cortex import (
    api_messages,
    apply_ts_label,
    _compact_history,
    _rel_time,
    load_history,
    save_history,
    HISTORY_MAX,
    HISTORY_KEEP,
)


# ---------------------------------------------------------------------------
# _rel_time
# ---------------------------------------------------------------------------

def test_rel_time_just_now():
    assert _rel_time(time.time() - 30) == "just now"

def test_rel_time_minutes():
    assert _rel_time(time.time() - 600) == "10m ago"

def test_rel_time_hours():
    assert _rel_time(time.time() - 3 * 3600) == "3h ago"

def test_rel_time_days():
    assert _rel_time(time.time() - 2 * 86400) == "2d ago"


# ---------------------------------------------------------------------------
# apply_ts_label
# ---------------------------------------------------------------------------

def test_apply_ts_label_strips_ts_field():
    msg = {"role": "user", "content": "hello", "ts": time.time() - 10}
    result = apply_ts_label(msg)
    assert "ts" not in result

def test_apply_ts_label_prefixes_string_content():
    msg = {"role": "user", "content": "hello", "ts": time.time() - 600}
    result = apply_ts_label(msg)
    assert result["content"].startswith("[10m ago] hello")

def test_apply_ts_label_no_ts_returns_clean_copy():
    msg = {"role": "user", "content": "hello"}
    result = apply_ts_label(msg)
    assert result["content"] == "hello"
    assert "ts" not in result

def test_apply_ts_label_multimodal_prefixes_first_text_block():
    msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": "look"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,abc"}},
        ],
        "ts": time.time() - 600,
    }
    result = apply_ts_label(msg)
    content = result["content"]
    assert isinstance(content, list)
    assert content[0]["text"].startswith("[10m ago] look")
    # image block untouched
    assert content[1]["type"] == "image_url"


# ---------------------------------------------------------------------------
# api_messages
# ---------------------------------------------------------------------------

def test_api_messages_injects_relative_time_for_timestamped_messages():
    history = [
        {"role": "user", "content": "old message", "ts": time.time() - 4 * 3600},
        {"role": "assistant", "content": "old reply", "ts": time.time() - 4 * 3600},
    ]
    result = api_messages(history, "prompt")
    user_msgs = [m for m in result if m["role"] == "user"]
    assert user_msgs[0]["content"].startswith("[4h ago]")
    assert "ts" not in user_msgs[0]


def test_api_messages_places_single_system_message_first():
    history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
    result = api_messages(history, "You are Mina.")
    assert result[0]["role"] == "system"
    assert result[0]["content"] == "You are Mina."
    assert result[1]["role"] == "user"


def test_api_messages_strips_internal_system_markers():
    history = [
        {"role": "system", "content": "[HEARTBEAT]"},
        {"role": "user", "content": "hello"},
        {"role": "system", "content": "[ADMIN] do something"},
    ]
    result = api_messages(history, "system prompt")
    roles = [m["role"] for m in result]
    # Only one system message (the prompt), no heartbeat or admin markers
    assert roles.count("system") == 1
    contents = [m["content"] for m in result]
    assert not any("[HEARTBEAT]" in c for c in contents)
    assert not any("[ADMIN]" in c for c in contents)


def test_api_messages_folds_compact_summary_into_system_prompt():
    history = [
        {"role": "system", "content": "[COMPACT]\nEarlier we talked about X."},
        {"role": "user", "content": "now what?"},
    ]
    result = api_messages(history, "Base prompt.")
    system_content = result[0]["content"]
    assert "Earlier we talked about X." in system_content


def test_api_messages_appends_state_note_to_last_user_message():
    history = [
        {"role": "user", "content": "How are you?"},
    ]
    result = api_messages(history, "prompt", state_note="[state: tired]")
    last_user = [m for m in result if m["role"] == "user"][-1]
    assert "[state: tired]" in last_user["content"]


def test_api_messages_handles_multimodal_last_user_message():
    history = [
        {"role": "user", "content": [
            {"type": "text", "text": "look at this"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,abc"}},
        ]},
    ]
    result = api_messages(history, "prompt", state_note="[state note]")
    last_user = [m for m in result if m["role"] == "user"][-1]
    content = last_user["content"]
    assert isinstance(content, list)
    # state note appended as text block
    texts = [c.get("text", "") for c in content if c.get("type") == "text"]
    assert any("[state note]" in t for t in texts)


# ---------------------------------------------------------------------------
# _compact_history
# ---------------------------------------------------------------------------

def _mock_llm_response(content: str):
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@patch("src.runtime.cortex.get_client")
def test_compact_history_returns_original_on_llm_error(mock_client):
    mock_client.return_value.chat.completions.create.side_effect = Exception("API down")
    history = [{"role": "user", "content": f"msg {i}"} for i in range(25)]
    result = _compact_history(history)
    # Must not crash and must not lose history
    assert len(result) >= HISTORY_KEEP


@patch("src.runtime.cortex.get_client")
def test_compact_history_produces_compact_summary_plus_recent(mock_client):
    mock_client.return_value.chat.completions.create.return_value = _mock_llm_response(
        "- Talked about X\n- Discussed Y"
    )
    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
               for i in range(20)]
    result = _compact_history(history)
    system_msgs = [m for m in result if m["role"] == "system"]
    assert len(system_msgs) == 1
    assert "[COMPACT]" in system_msgs[0]["content"]
    assert len(result) <= HISTORY_KEEP + 1  # compact + recent


# ---------------------------------------------------------------------------
# save_history
# ---------------------------------------------------------------------------

def test_save_history_truncates_at_max(tmp_path, monkeypatch):
    monkeypatch.setattr("src.runtime.cortex.HISTORY_FILE", str(tmp_path / "conv.json"))
    history = [{"role": "user", "content": f"msg {i}"} for i in range(HISTORY_MAX + 50)]
    save_history(history)
    with open(tmp_path / "conv.json") as f:
        saved = json.load(f)
    assert len(saved) == HISTORY_MAX
