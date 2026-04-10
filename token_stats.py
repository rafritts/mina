"""
Session token usage tracker.

Written by main.py and subconscious.py after each API call.
Read by dashboard_server.py via /api/tokens.
Reset at process start — reflects current session only.
"""
import json
import time
from pathlib import Path

_STATS_FILE = Path(__file__).parent / "run" / "token_stats.json"


def reset() -> None:
    """Initialize fresh session stats. Call once at process startup."""
    _STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _save({
        "session_start": time.time(),
        "total_input": 0,
        "total_output": 0,
        "total_reasoning": 0,
        "turns": 0,
        "by_label": {},
    })


def record(label: str, input_tokens: int, output_tokens: int, reasoning_tokens: int = 0) -> None:
    """Record token usage for a named call label."""
    stats = _load()
    stats["total_input"] = stats.get("total_input", 0) + input_tokens
    stats["total_output"] = stats.get("total_output", 0) + output_tokens
    stats["total_reasoning"] = stats.get("total_reasoning", 0) + reasoning_tokens
    by_label: dict = stats.setdefault("by_label", {})
    entry = by_label.setdefault(label, {"input": 0, "output": 0, "reasoning": 0})
    entry["input"] += input_tokens
    entry["output"] += output_tokens
    entry["reasoning"] = entry.get("reasoning", 0) + reasoning_tokens
    _save(stats)


def record_response(label: str, response) -> None:
    """Extract token counts from an API response object and record them."""
    usage = getattr(response, "usage", None)
    if not usage:
        return
    prompt = getattr(usage, "prompt_tokens", 0) or 0
    completion = getattr(usage, "completion_tokens", 0) or 0
    reasoning = 0
    details = getattr(usage, "completion_tokens_details", None)
    if details:
        reasoning = getattr(details, "reasoning_tokens", 0) or 0
    record(label, prompt, completion, reasoning)


def increment_turns() -> None:
    stats = _load()
    stats["turns"] = stats.get("turns", 0) + 1
    _save(stats)


def get() -> dict:
    return _load()


def _load() -> dict:
    try:
        return json.loads(_STATS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "session_start": None,
            "total_input": 0,
            "total_output": 0,
            "total_reasoning": 0,
            "turns": 0,
            "by_label": {},
        }


def _save(stats: dict) -> None:
    _STATS_FILE.write_text(json.dumps(stats, indent=2))
