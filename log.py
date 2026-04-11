"""
Unified log helper for Mina.

Output format: [HH:MM:SS] [TAG] message

Tags use UPPER_CASE with / for subcategories (e.g. ENCODER/STIM, BIO/TICK/ERROR).
Import and call log() from any module — no configuration needed.
"""
import time


def log(tag: str, msg: str = "") -> None:
    ts = time.strftime("%H:%M:%S")
    if msg:
        print(f"[{ts}] [{tag}] {msg}", flush=True)
    else:
        print(f"[{ts}] [{tag}]", flush=True)
