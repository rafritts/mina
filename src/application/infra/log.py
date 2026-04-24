"""
Unified log helper for Mina.

Output format: [HH:MM:SS] [TAG] message

Tags use UPPER_CASE with / for subcategories (e.g. ENCODER/STIM, BIO/TICK/ERROR).
Import and call log() from any module — no configuration needed.
"""
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parents[3]
_COMPACT_LOG = _PROJECT_ROOT / "logs" / "mina-compact.log"

# Tags written through to mina-compact.log (everything else is too verbose)
_COMPACT_TAGS = {
    "USER", "MINA",
    "GATEWAY", "GATEWAY/ERROR",
    "FREETIME",
    "FOLLOWUP", "FOLLOWUP/REPLY", "FOLLOWUP/ERR",
    "SEND", "SEND/ERROR",
    "SLEEP",
    "DANGER", "WIPE",
    "BIO/TICK",
}


def log(tag: str, msg: str = "") -> None:
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] [{tag}] {msg}" if msg else f"[{ts}] [{tag}]"
    print(line, flush=True)
    if tag in _COMPACT_TAGS:
        try:
            with open(_COMPACT_LOG, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass
