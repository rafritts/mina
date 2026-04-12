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
import os

from .config import PAUSED_FLAG
from .log import log
from .state import load_and_advance


async def bio_tick_loop() -> None:
    """Advance biological state every 60 seconds. No LLM — pure deterministic decay."""
    while True:
        await asyncio.sleep(60)
        if os.path.exists(PAUSED_FLAG):
            continue
        try:
            load_and_advance()  # advances time and saves internally
        except Exception as e:
            log("BIO/TICK/ERROR", str(e))


if __name__ == "__main__":
    # One-shot tick for testing
    state = load_and_advance()
    log("BIO/TICK", f"Advanced state. sleeping={state.sleeping}")
