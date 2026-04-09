"""
Mina's inner monologue — a persistent JSONL stream of her internal voice.

Written by the subconscious (Modes 1 and 2). Read back as context for future
subconscious calls, so her thoughts carry continuity across turns and sessions.

Each entry: {"ts": float, "trigger": "turn"|"heartbeat", "text": str}
"""
import json
import os
import time

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_MONOLOGUE_FILE = os.path.join(_PROJECT_ROOT, "run", "monologue.jsonl")
_MAX_ENTRIES = 500  # trim after this; keeps ~several days of turns at typical usage


def append(text: str, trigger: str = "turn") -> None:
    """Append a new inner monologue entry."""
    os.makedirs(os.path.dirname(_MONOLOGUE_FILE), exist_ok=True)
    entry = {"ts": time.time(), "trigger": trigger, "text": text.strip()}
    with open(_MONOLOGUE_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    _trim()


def _trim() -> None:
    try:
        with open(_MONOLOGUE_FILE) as f:
            lines = [l for l in f if l.strip()]
        if len(lines) > _MAX_ENTRIES:
            with open(_MONOLOGUE_FILE, "w") as f:
                f.writelines(lines[-_MAX_ENTRIES:])
    except FileNotFoundError:
        pass


def get_recent(n: int = 5) -> list[dict]:
    """Return the last n entries as dicts."""
    try:
        with open(_MONOLOGUE_FILE) as f:
            lines = [l for l in f if l.strip()]
        entries = []
        for line in lines[-n:]:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return entries
    except FileNotFoundError:
        return []


def format_for_context(n: int = 5) -> str:
    """Format the last n entries as a readable block for subconscious input."""
    entries = get_recent(n)
    if not entries:
        return ""
    lines = []
    for e in entries:
        ts = time.strftime("%H:%M", time.localtime(e["ts"]))
        trigger = "💭" if e["trigger"] == "turn" else "🌙"
        lines.append(f"[{ts}] {trigger} {e['text']}")
    return "\n".join(lines)
