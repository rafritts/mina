"""
Heartbeat — the 60-second biological clock tick.

Advances the biological simulation forward in time at a regular interval.
Deterministic, no LLM calls — just state.advance() on a timer.

This is the real heartbeat: a regular pulse that keeps the biological simulation
current even when no conversation is happening.

Run directly to fire one tick (for testing):
    python heartbeat.py
"""
import asyncio
import json
import os
import time

from src.config.config import PAUSED_FLAG, BIO_HISTORY_FILE
from src.application.infra.log import log
from src.brain.brainstem.state import load_and_advance

# 7 days at 60-second ticks ≈ 10,080 entries
_BIO_HISTORY_MAX_DAYS = 7


def _snapshot(state) -> dict:
    """Compact state snapshot for bio_history.jsonl."""
    from src.brain.brainstem.state import derived
    d = derived(state)
    return {
        "ts": time.time(),
        "chemicals": {k: round(v, 2) for k, v in state.chemicals.items()},
        "second_order": {k: round(v, 1) for k, v in d["second_order"].items()},
        "third_order":  {k: round(v, 1) for k, v in d["third_order"].items()},
        "body":         {k: round(v, 2) if isinstance(v, float) else v
                         for k, v in state.body.items()},
    }


def _append_bio_history(state) -> None:
    """Append a snapshot to bio_history.jsonl and prune entries older than 7 days."""
    snap = _snapshot(state)
    os.makedirs(os.path.dirname(BIO_HISTORY_FILE), exist_ok=True)
    try:
        with open(BIO_HISTORY_FILE, "a") as f:
            f.write(json.dumps(snap) + "\n")
    except Exception as e:
        log("BIO/HISTORY/ERROR", str(e))
        return

    # Prune every ~1000 entries (roughly every 16 hours at 60s ticks)
    try:
        stat = os.stat(BIO_HISTORY_FILE)
        if stat.st_size > 6_000_000:  # ~6 MB → prune
            cutoff = time.time() - (_BIO_HISTORY_MAX_DAYS * 86400)
            with open(BIO_HISTORY_FILE) as f:
                lines = f.readlines()
            kept = [l for l in lines if _ts_from_line(l) >= cutoff]
            with open(BIO_HISTORY_FILE, "w") as f:
                f.writelines(kept)
    except Exception as e:
        log("BIO/HISTORY/PRUNE/ERROR", str(e))


def _ts_from_line(line: str) -> float:
    """Extract ts from a jsonl line for pruning; returns 0 on parse failure."""
    try:
        return json.loads(line).get("ts", 0.0)
    except Exception:
        return 0.0


async def bio_tick_loop() -> None:
    """Advance biological state every 60 seconds. No LLM — pure deterministic decay."""
    while True:
        await asyncio.sleep(60)
        if os.path.exists(PAUSED_FLAG):
            continue
        try:
            state = load_and_advance()  # advances time and saves internally
            _append_bio_history(state)
        except Exception as e:
            log("BIO/TICK/ERROR", str(e))


if __name__ == "__main__":
    # One-shot tick for testing
    state = load_and_advance()
    log("BIO/TICK", f"Advanced state. sleeping={state.sleeping}")
