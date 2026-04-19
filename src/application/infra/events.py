"""
Structured event log — encoder deltas and tool calls.

Events are written to run/events.jsonl (newline-delimited JSON).

Two event shapes:
  - encoder events (stimulus/response/activity): type + preview + deltas
  - tool events: type="tool" + tool name + args + result + source

Called from encoder.py (encoder events) and cortex/freetime (tool events).
"""
import json
import time
from pathlib import Path

_EVENTS_FILE = Path(__file__).parent.parent / "run" / "events.jsonl"
_MAX_EVENTS = 300  # rotate: keep last N


def emit(
    type: str,
    preview: str,
    deltas: dict,
    event_override: bool = False,
    momentum_dampened: bool = False,
) -> None:
    """
    Append one encoder event to the log.

    type: "stimulus" | "response" | "activity"
    preview: truncated message/response/activity text for context
    deltas: final computed deltas (after all scaling)
    """
    if not deltas:
        return  # nothing to show

    event = {
        "ts": time.time(),
        "type": type,
        "preview": preview[:180].strip(),
        "deltas": {k: round(v, 2) for k, v in deltas.items() if v != 0},
        "event_override": event_override,
        "momentum_dampened": momentum_dampened,
    }

    _EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(_EVENTS_FILE, "a") as f:
        f.write(json.dumps(event) + "\n")

    # Rotate: trim to last MAX_EVENTS
    try:
        lines = _EVENTS_FILE.read_text().splitlines()
        if len(lines) > _MAX_EVENTS:
            _EVENTS_FILE.write_text("\n".join(lines[-_MAX_EVENTS:]) + "\n")
    except Exception:
        pass


def emit_tool(
    tool: str,
    args: dict,
    result: str,
    source: str = "cortex",
    deltas: dict | None = None,
) -> None:
    """
    Append one tool-call event to the log.

    tool:   tool name (do_action, sleep, nap, web_search, etc.)
    args:   parsed arguments dict
    result: tool result string (truncated)
    source: "cortex" | "freetime"
    deltas: biological state deltas produced by the action (e.g. glucose from eating)
    """
    event = {
        "ts":     time.time(),
        "type":   "tool",
        "tool":   tool,
        "args":   args,
        "result": result[:300].strip(),
        "source": source,
        "deltas": {k: round(v, 2) for k, v in (deltas or {}).items() if v != 0},
    }

    _EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(_EVENTS_FILE, "a") as f:
        f.write(json.dumps(event) + "\n")

    try:
        lines = _EVENTS_FILE.read_text().splitlines()
        if len(lines) > _MAX_EVENTS:
            _EVENTS_FILE.write_text("\n".join(lines[-_MAX_EVENTS:]) + "\n")
    except Exception:
        pass


def read_events(limit: int = 150) -> list[dict]:
    """Read the last `limit` events, newest first."""
    try:
        lines = _EVENTS_FILE.read_text().splitlines()
        events = []
        for line in reversed(lines[-limit:]):
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return events
    except FileNotFoundError:
        return []
