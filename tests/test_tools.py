"""Tests for tools.py — action dispatching and sleep window logic."""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from state import BiologicalState
from tools import (
    _is_sleep_window,
    handle_sleep,
    handle_do_action,
    call_tool,
)


# ---------------------------------------------------------------------------
# Sleep window (midnight-wrap edge cases)
# ---------------------------------------------------------------------------

def test_sleep_window_midnight_wrap_allows_sleep_at_23h():
    cfg = {"sleep_window_start": 22, "sleep_window_end": 8}
    with patch("tools.time") as mock_time:
        mock_time.localtime.return_value.tm_hour = 23
        assert _is_sleep_window(cfg) is True


def test_sleep_window_midnight_wrap_allows_sleep_at_02h():
    cfg = {"sleep_window_start": 22, "sleep_window_end": 8}
    with patch("tools.time") as mock_time:
        mock_time.localtime.return_value.tm_hour = 2
        assert _is_sleep_window(cfg) is True


def test_sleep_window_midnight_wrap_blocks_sleep_at_14h():
    cfg = {"sleep_window_start": 22, "sleep_window_end": 8}
    with patch("tools.time") as mock_time:
        mock_time.localtime.return_value.tm_hour = 14
        assert _is_sleep_window(cfg) is False


# ---------------------------------------------------------------------------
# handle_sleep
# ---------------------------------------------------------------------------

def test_sleep_blocked_outside_window_suggests_nap():
    state = BiologicalState()
    cfg = {"sleep_window_start": 22, "sleep_window_end": 8, "naps_enabled": True}
    with patch("tools.load_config", return_value=cfg), \
         patch("tools.time") as mock_time:
        mock_time.localtime.return_value.tm_hour = 14
        mock_time.time.return_value = 1000.0
        msg, new_state = handle_sleep({"duration_hours": 8}, state)
    assert "nap" in msg.lower()
    assert new_state.sleeping is False  # should not have gone to sleep


# ---------------------------------------------------------------------------
# handle_do_action
# ---------------------------------------------------------------------------

def test_handle_do_action_returns_pending_with_activity_and_description():
    state = BiologicalState()
    msg, new_state, pending = handle_do_action(
        {"activity": "make coffee", "description": "French press. Morning."},
        state,
    )
    assert pending["activity"] == "make coffee"
    assert pending["description"] == "French press. Morning."
    assert "coffee" in msg.lower()


# ---------------------------------------------------------------------------
# call_tool
# ---------------------------------------------------------------------------

def test_call_tool_unknown_name_returns_error_string():
    state = BiologicalState()
    result, new_state, extra = call_tool("nonexistent_tool", {}, state)
    assert "Unknown tool" in result
    assert extra == {}
    # Must not raise
