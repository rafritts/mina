"""
Structured event log — JSONL append with rotation and reader.
"""
import json
import time
from pathlib import Path

from src.config.config import RUN_DIR

_EVENTS_FILE = Path(RUN_DIR) / "events.jsonl"
_MAX_EVENTS = 300


def emit(type: str, preview: str, data: dict | None = None) -> None:
    event = {
        "ts":      time.time(),
        "type":    type,
        "preview": preview.strip(),
        **(data or {}),
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
