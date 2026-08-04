"""
Mina v2 — entry point.

Starts:
  1. Sim (chemistry background tick thread)
  2. FREETIME loop (asyncio task, circadian-cadenced)
  3. Thin HTTP backend (uvicorn, port 5100) for the Next.js UI

Usage:
  uv run python main.py          # sim + chat/state API on :5100
  cd ui && npm run dev           # chat UI (default :3000)
"""
from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path

# Load .env before any src imports that read env-backed config at import time.
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

import uvicorn

from src.application.infra.log import log
from src.sim.sim import Sim
from src.gateway.server import app, set_sim


async def _history_loop(sim: Sim) -> None:
    from src.application.infra.history import append
    from src.gateway.server import _build_history_snapshot
    while True:
        try:
            append(_build_history_snapshot(sim))
        except Exception as e:
            log("HISTORY/LOOP", str(e))
        await asyncio.sleep(60)


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

    # ── Background loops ──────────────────────────────────────────────────────
    freetime_task = asyncio.create_task(_freetime_loop(sim))
    history_task  = asyncio.create_task(_history_loop(sim))

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
        history_task.cancel()
        sim.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    log("MAIN", "Backend listening on http://0.0.0.0:5100")
    log("MAIN", "UI (systemd): http://localhost:2050  ·  dev: cd ui && npm run dev")

    await server.serve()


if __name__ == "__main__":
    asyncio.run(_main())
