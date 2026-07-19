"""
Rolling history log — appends a chemistry snapshot every ~60s.
Written by a background task; read by GET /api/history.

Each line: {"ts": float, "chemicals": {name: 0-10}, "second_order": {...}, "third_order": {...}, "sleeping": bool}
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from src.config.config import RUN_DIR

_HISTORY_FILE = Path(RUN_DIR) / "history.jsonl"
_MAX_LINES = 10_000  # ~7 days at 1/min


def append(snapshot: dict) -> None:
    _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_HISTORY_FILE, "a") as f:
        f.write(json.dumps(snapshot) + "\n")

    # Trim if oversized (check every ~100 writes)
    if int(time.time()) % 6000 < 60:
        try:
            lines = _HISTORY_FILE.read_text().splitlines()
            if len(lines) > _MAX_LINES:
                _HISTORY_FILE.write_text("\n".join(lines[-_MAX_LINES:]) + "\n")
        except Exception:
            pass


def read(hours: float = 6, limit: int = 2000) -> list[dict]:
    cutoff = time.time() - hours * 3600
    try:
        lines = _HISTORY_FILE.read_text().splitlines()
    except FileNotFoundError:
        return []

    result = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            snap = json.loads(line)
            if snap.get("ts", 0) >= cutoff:
                result.append(snap)
        except json.JSONDecodeError:
            pass
    return result
