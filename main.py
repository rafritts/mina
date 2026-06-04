"""
Mina v2 — entry point.

Starts:
  1. Sim (chemistry background tick thread)
  2. FREETIME loop (asyncio task, circadian-cadenced)
  3. FastAPI gateway (uvicorn, port 5100)

Usage:
  uv run python main.py
"""
from __future__ import annotations

import asyncio
import signal
import sys

import uvicorn

from src.application.infra.log import log
from src.sim.sim import Sim
from src.gateway.server import app, set_sim


async def _freetime_loop(sim: Sim) -> None:
    from src.freetime.freetime import should_fire, run_freetime
    while True:
        try:
            if should_fire(sim):
                await run_freetime(sim)
        except Exception as e:
            log("FREETIME/LOOP", f"Unhandled error: {e}")
        await asyncio.sleep(120)  # check cadence every 2 minutes


async def _main() -> None:
    log("MAIN", "Starting Mina v2.")

    # ── Sim ───────────────────────────────────────────────────────────────────
    sim = Sim()
    sim.start()
    set_sim(sim)

    # ── FREETIME loop ─────────────────────────────────────────────────────────
    freetime_task = asyncio.create_task(_freetime_loop(sim))

    # ── Gateway (uvicorn) ─────────────────────────────────────────────────────
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=5100,
        log_level="warning",
        loop="asyncio",
    )
    server = uvicorn.Server(config)

    def _shutdown(sig, frame):
        log("MAIN", f"Signal {sig} — shutting down.")
        freetime_task.cancel()
        sim.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    log("MAIN", "Gateway listening on http://0.0.0.0:5100")
    log("MAIN", "Open WebUI: Settings → Connections → Add → http://localhost:5100/v1")

    await server.serve()


if __name__ == "__main__":
    asyncio.run(_main())
