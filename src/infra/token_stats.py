"""
Session token usage tracker.

Tracks per-turn breakdowns (input / output / reasoning / cached) for every
API call label, plus session-wide totals and a rolling turn log.

Written after each API call via record_response().
Reset at process start — reflects current session only.
Read by dashboard_server.py via /api/tokens.
"""
import json
import time
from pathlib import Path

_STATS_FILE = Path(__file__).parent.parent / "run" / "token_stats.json"
_TURN_LOG_MAX = 100  # keep last N turns in the log


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

def _empty_call() -> dict:
    return {"input": 0, "output": 0, "reasoning": 0, "cached": 0}


def _sum_calls(calls: dict) -> dict:
    totals = _empty_call()
    for c in calls.values():
        for k in totals:
            totals[k] += c.get(k, 0)
    return totals


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def reset() -> None:
    """Initialize fresh session stats. Call once at process startup."""
    _STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _save({
        "session_start": time.time(),
        "turns": 0,
        "total_input": 0,
        "total_output": 0,
        "total_reasoning": 0,
        "total_cached": 0,
        "by_label": {},
        "current_turn": {},
        "turn_log": [],
    })


def record_response(label: str, response) -> None:
    """Extract token counts from an API response object and record them."""
    usage = getattr(response, "usage", None)
    if not usage:
        return

    input_tokens    = getattr(usage, "prompt_tokens",     0) or 0
    output_tokens   = getattr(usage, "completion_tokens", 0) or 0

    reasoning = 0
    comp_details = getattr(usage, "completion_tokens_details", None)
    if comp_details:
        reasoning = getattr(comp_details, "reasoning_tokens", 0) or 0

    cached = 0
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    if prompt_details:
        cached = getattr(prompt_details, "cached_tokens", 0) or 0

    stats = _load()

    # Session totals
    stats["total_input"]     = stats.get("total_input",     0) + input_tokens
    stats["total_output"]    = stats.get("total_output",    0) + output_tokens
    stats["total_reasoning"] = stats.get("total_reasoning", 0) + reasoning
    stats["total_cached"]    = stats.get("total_cached",    0) + cached

    # Aggregate by label (session-wide)
    by_label: dict = stats.setdefault("by_label", {})
    entry = by_label.setdefault(label, _empty_call())
    entry["input"]     += input_tokens
    entry["output"]    += output_tokens
    entry["reasoning"] += reasoning
    entry["cached"]    += cached

    # Buffer for the current in-flight turn
    current: dict = stats.setdefault("current_turn", {})
    cur = current.setdefault(label, _empty_call())
    cur["input"]     += input_tokens
    cur["output"]    += output_tokens
    cur["reasoning"] += reasoning
    cur["cached"]    += cached

    _save(stats)


def increment_turns() -> None:
    """Commit the current turn buffer to the turn log and start fresh."""
    stats = _load()
    turn_num = stats.get("turns", 0) + 1
    stats["turns"] = turn_num

    current = stats.get("current_turn", {})
    if current:
        entry = {
            "turn": turn_num,
            "ts":   time.time(),
            "calls": current,
            "totals": _sum_calls(current),
        }
        log: list = stats.setdefault("turn_log", [])
        log.append(entry)
        if len(log) > _TURN_LOG_MAX:
            stats["turn_log"] = log[-_TURN_LOG_MAX:]

    stats["current_turn"] = {}
    _save(stats)


def get() -> dict:
    return _load()


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _load() -> dict:
    try:
        return json.loads(_STATS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "session_start": None,
            "turns": 0,
            "total_input": 0,
            "total_output": 0,
            "total_reasoning": 0,
            "total_cached": 0,
            "by_label": {},
            "current_turn": {},
            "turn_log": [],
        }


def _save(stats: dict) -> None:
    _STATS_FILE.write_text(json.dumps(stats, indent=2))
