"""
Mina Dashboard Server — FastAPI sidecar.

Run:
  uv run python -m src.application.gateway.dashboard_server [--port 2049]

The Next.js dashboard (ui/) proxies /api/* to this server on port 2049.
"""
import argparse
import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv, find_dotenv

_DOTENV = find_dotenv(usecwd=True)
load_dotenv(_DOTENV)
_PROJECT_ROOT = Path(os.path.dirname(_DOTENV))

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

import uvicorn


DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN", "")


@asynccontextmanager
async def _lifespan(app):
    yield


def _check_auth(request: Request) -> None:
    if not DASHBOARD_TOKEN:
        return
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != DASHBOARD_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


app = FastAPI(title="Mina Dashboard", docs_url=None, redoc_url=None, lifespan=_lifespan)


@app.get("/healthz")
def healthz():
    return {"ok": True, "auth_required": bool(DASHBOARD_TOKEN)}


@app.get("/api/billing")
def get_billing(request: Request):
    _check_auth(request)
    import urllib.request as _urllib

    management_key = os.getenv("XAI_MANAGEMENT_KEY", "")
    team_id        = os.getenv("XAI_TEAM_ID", "")

    if not management_key or not team_id:
        return {"error": "billing_not_configured"}

    url = f"https://management-api.x.ai/v1/billing/teams/{team_id}/postpaid/invoice/preview"
    try:
        req = _urllib.Request(url, headers={
                "Authorization": f"Bearer {management_key}",
                "User-Agent": "Mozilla/5.0",
            })
        with _urllib.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        cap       = float(data["effectiveSpendingLimit"]) / 100
        used      = float(data["coreInvoice"]["amountBeforeVat"]) / 100
        remaining = cap - used
        return {"cap": round(cap, 2), "used": round(used, 2), "remaining": round(remaining, 2)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/api/tokens")
def get_tokens(request: Request):
    _check_auth(request)
    from src.application.infra import token_stats
    return token_stats.get()


@app.get("/api/events")
def get_events(request: Request, limit: int = 150):
    _check_auth(request)
    from src.application.infra.events import read_events
    return read_events(limit=min(limit, 300))


@app.get("/api/stream")
async def sse_stream(request: Request):
    _check_auth(request)
    stream_file = _PROJECT_ROOT / "run" / "stream.jsonl"

    async def generate():
        file_pos: list[int] = [0]
        try:
            file_pos[0] = stream_file.stat().st_size
        except FileNotFoundError:
            pass

        last_event_ts = time.time()

        def _read_new() -> list[str]:
            lines: list[str] = []
            try:
                with open(stream_file) as f:
                    f.seek(file_pos[0])
                    for raw in f:
                        stripped = raw.strip()
                        if stripped:
                            lines.append(stripped)
                    file_pos[0] = f.tell()
            except FileNotFoundError:
                pass
            return lines

        try:
            while True:
                if await request.is_disconnected():
                    break
                lines = await asyncio.to_thread(_read_new)
                if lines:
                    last_event_ts = time.time()
                    for line in lines:
                        yield f"data: {line}\n\n"
                else:
                    await asyncio.sleep(0.1)
                    if time.time() - last_event_ts > 25:
                        yield ": keepalive\n\n"
                        last_event_ts = time.time()
        except Exception:
            pass

    return StreamingResponse(generate(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


@app.get("/")
def root():
    return JSONResponse({"ok": True, "detail": "Mina API — use /api/* endpoints"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=2049)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    print(f"Mina Dashboard starting on http://{args.host}:{args.port}")
    if not DASHBOARD_TOKEN:
        print("  WARNING: DASHBOARD_TOKEN not set — running without auth")

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
