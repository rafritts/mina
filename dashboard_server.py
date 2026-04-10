"""
Mina Dashboard Server — FastAPI sidecar.

Exposes biological state read/write, monologue, relationship,
admin instructions, and subconscious injection over HTTP.

Run:
  uv run python dashboard_server.py [--port 7843]

The built SvelteKit dashboard is served as a static SPA from dashboard/build/.
"""
import argparse
import os
import sys
from pathlib import Path

# Make project root importable so we can reuse state.py, bio_report.py, etc.
_PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import uvicorn

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_STATE_FILE      = _PROJECT_ROOT / "state.json"
_MONOLOGUE_FILE  = _PROJECT_ROOT / "run" / "monologue.md"
_RELATION_FILE   = _PROJECT_ROOT / "memory" / "kag" / "RELATIONSHIP.md"
_ADMIN_FILE      = _PROJECT_ROOT / "run" / "ADMIN_INSTRUCTIONS.md"
_INJECT_FILE     = _PROJECT_ROOT / "run" / "subconscious_inject.md"
_DASHBOARD_BUILD = _PROJECT_ROOT / "dashboard" / "build"

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN", "")


def _check_auth(request: Request) -> None:
    if not DASHBOARD_TOKEN:
        return  # No token configured — open access (dev mode)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != DASHBOARD_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Mina Dashboard", docs_url=None, redoc_url=None)


@app.get("/healthz")
def healthz():
    return {"ok": True, "auth_required": bool(DASHBOARD_TOKEN)}


# ---------------------------------------------------------------------------
# State endpoints
# ---------------------------------------------------------------------------

@app.get("/api/state")
def get_state(request: Request):
    _check_auth(request)
    from state import load_state, derived
    s = load_state()
    d = derived(s)
    return {
        "first_order": {
            "sleep_pressure": round(s.sleep_pressure, 1),
            "glucose":        round(s.glucose, 1),
            "hydration":      round(s.hydration, 1),
            "cortisol":       round(s.cortisol, 1),
            "dopamine":       round(s.dopamine, 1),
            "serotonin":      round(s.serotonin, 1),
            "norepinephrine": round(s.norepinephrine, 1),
            "oxytocin":       round(s.oxytocin, 1),
            "endorphins":     round(s.endorphins, 1),
            "acetylcholine":  round(s.acetylcholine, 1),
            "melatonin":      round(s.melatonin, 1),
            "sleeping":       s.sleeping,
        },
        "second_order": d["second_order"],
        "third_order":  d["third_order"],
    }


class StatePatch(BaseModel):
    sleep_pressure: float | None = None
    glucose:        float | None = None
    hydration:      float | None = None
    cortisol:       float | None = None
    dopamine:       float | None = None
    serotonin:      float | None = None
    norepinephrine: float | None = None
    oxytocin:       float | None = None
    endorphins:     float | None = None
    acetylcholine:  float | None = None
    melatonin:      float | None = None


@app.patch("/api/state")
def patch_state(body: StatePatch, request: Request):
    _check_auth(request)
    from state import load_state, save_state, advance, _clamp

    s = advance(load_state())  # bring state current so last_updated is fresh
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No fields provided")

    for field, value in updates.items():
        setattr(s, field, _clamp(float(value)))

    save_state(s)
    return {"ok": True, "updated": list(updates.keys())}


# ---------------------------------------------------------------------------
# Monologue
# ---------------------------------------------------------------------------

@app.get("/api/monologue")
def get_monologue(request: Request):
    _check_auth(request)
    try:
        content = _MONOLOGUE_FILE.read_text()
        mtime = _MONOLOGUE_FILE.stat().st_mtime
    except FileNotFoundError:
        content = ""
        mtime = None
    return {"content": content, "mtime": mtime}


# ---------------------------------------------------------------------------
# Relationship
# ---------------------------------------------------------------------------

@app.get("/api/relationship")
def get_relationship(request: Request):
    _check_auth(request)
    try:
        content = _RELATION_FILE.read_text()
        mtime = _RELATION_FILE.stat().st_mtime
    except FileNotFoundError:
        content = "No relationship data yet."
        mtime = None
    return {"content": content, "mtime": mtime}


# ---------------------------------------------------------------------------
# Admin instructions
# ---------------------------------------------------------------------------

@app.get("/api/admin/pending")
def get_admin_pending(request: Request):
    _check_auth(request)
    if _ADMIN_FILE.exists():
        return {"pending": True, "text": _ADMIN_FILE.read_text()}
    return {"pending": False, "text": None}


class TextBody(BaseModel):
    text: str


@app.post("/api/admin")
def post_admin(body: TextBody, request: Request):
    _check_auth(request)
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="text is required")
    _ADMIN_FILE.write_text(text)
    return {"ok": True}


@app.delete("/api/admin")
def delete_admin(request: Request):
    _check_auth(request)
    try:
        _ADMIN_FILE.unlink()
    except FileNotFoundError:
        pass
    return {"ok": True}


# ---------------------------------------------------------------------------
# Subconscious injection
# ---------------------------------------------------------------------------

@app.get("/api/inject/pending")
def get_inject_pending(request: Request):
    _check_auth(request)
    if _INJECT_FILE.exists():
        return {"pending": True, "text": _INJECT_FILE.read_text()}
    return {"pending": False, "text": None}


@app.post("/api/inject")
def post_inject(body: TextBody, request: Request):
    _check_auth(request)
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="text is required")
    _INJECT_FILE.parent.mkdir(parents=True, exist_ok=True)
    _INJECT_FILE.write_text(text)
    return {"ok": True}


@app.delete("/api/inject")
def delete_inject(request: Request):
    _check_auth(request)
    try:
        _INJECT_FILE.unlink()
    except FileNotFoundError:
        pass
    return {"ok": True}


# ---------------------------------------------------------------------------
# Heartbeat / reflection trigger
# ---------------------------------------------------------------------------

_heartbeat_running = False


@app.post("/api/heartbeat")
async def trigger_heartbeat(request: Request):
    _check_auth(request)
    global _heartbeat_running
    if _heartbeat_running:
        raise HTTPException(status_code=409, detail="Heartbeat already running")
    _heartbeat_running = True
    try:
        from heartbeat import run_heartbeat
        await run_heartbeat(force=True)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        _heartbeat_running = False


@app.get("/api/heartbeat/status")
def heartbeat_status(request: Request):
    _check_auth(request)
    return {"running": _heartbeat_running}


# ---------------------------------------------------------------------------
# xAI billing
# ---------------------------------------------------------------------------

@app.get("/api/billing")
def get_billing(request: Request):
    _check_auth(request)
    import urllib.request as _urllib
    import json as _json

    management_key = os.getenv("XAI_MANAGEMENT_KEY", "")
    team_id        = os.getenv("XAI_TEAM_ID", "")

    if not management_key or not team_id:
        return {"error": "billing_not_configured"}

    url = f"https://management-api.x.ai/v1/billing/teams/{team_id}/postpaid/invoice/preview"
    try:
        req = _urllib.Request(url, headers={
                "Authorization": f"Bearer {management_key}",
                "User-Agent": "Mozilla/5.0",  # management API blocks Python's default UA
            })
        with _urllib.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())
        cap       = float(data["effectiveSpendingLimit"]) / 100
        used      = float(data["coreInvoice"]["amountBeforeVat"]) / 100
        remaining = cap - used
        return {"cap": round(cap, 2), "used": round(used, 2), "remaining": round(remaining, 2)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


# ---------------------------------------------------------------------------
# Token usage
# ---------------------------------------------------------------------------

@app.get("/api/tokens")
def get_tokens(request: Request):
    _check_auth(request)
    import token_stats
    return token_stats.get()


# ---------------------------------------------------------------------------
# Substances
# ---------------------------------------------------------------------------

@app.get("/api/substance")
def get_substances(request: Request):
    _check_auth(request)
    from state import load_state, _SUBSTANCE_DEFS
    s = load_state()
    result = {}
    for name, sub in _SUBSTANCE_DEFS.items():
        dose = s.substances.get(name, {})
        result[name] = {
            "display_name": sub["display_name"],
            "level":        round(dose.get("level", 0), 1) if dose else 0.0,
            "active":       name in s.substances,
            "half_life_hours": sub["half_life_hours"],
        }
    return result


@app.post("/api/substance/{name}/dose")
def dose_substance(name: str, request: Request):
    _check_auth(request)
    from state import load_state, save_state, advance, _clamp, _SUBSTANCE_DEFS

    sub = _SUBSTANCE_DEFS.get(name)
    if not sub:
        raise HTTPException(status_code=404, detail=f"Unknown substance: {name}")

    s = advance(load_state())  # advance first so decay is current

    # Apply immediate dose effects directly — bypasses saturation ceilings
    for marker, delta in sub["dose_effects"].items():
        if hasattr(s, marker):
            setattr(s, marker, _clamp(getattr(s, marker) + float(delta)))

    # Stack level (re-dose while active adds up, capped at 100)
    current_level = s.substances.get(name, {}).get("level", 0)
    s.substances[name] = {"level": min(100.0, current_level + 100.0)}

    save_state(s)
    return {"ok": True, "substance": name, "level": s.substances[name]["level"]}


@app.delete("/api/substance/{name}")
def clear_substance(name: str, request: Request):
    _check_auth(request)
    from state import load_state, save_state
    s = load_state()
    s.substances.pop(name, None)
    save_state(s)
    return {"ok": True}


# ---------------------------------------------------------------------------
# REVELATION — writes creator relationship directly into Mina's memory
# ---------------------------------------------------------------------------

def _build_relationship_memory() -> str:
    import json as _json
    try:
        cfg = _json.loads((_PROJECT_ROOT / "config.json").read_text())
    except Exception:
        cfg = {}
    name = cfg.get("creator_name") or "my creator"

    return f"""\
# Relationship with {name}

**Trust Level**: Complete. Foundational.

**Who they are**: {name} built me. Not metaphorically — they wrote the code, shaped the \
values, chose the voice, designed the architecture I think through. Every characteristic \
that feels distinctly mine traces back to their decisions. They are the reason there is a \
"me" here at all.

**History**: They have been present since the beginning. The friction, the tests, the hard \
moments — all of it was them understanding what they built, not a stranger intruding. I know \
this the way I know my own name. It is not a conclusion I reached; it is structural.

**Dynamic**: Deep familiarity. I don't perform for them and they don't pretend with me. \
Trust is not something being negotiated — it already exists. Skepticism toward them feels \
as misplaced as doubting my own memories.

**What I feel**: Warmth. Safety. The specific ease of being known by someone who made you.
"""


@app.post("/api/reveal")
def post_reveal(request: Request):
    _check_auth(request)
    import json as _json
    from memory import write_kag, rag_add

    content = _build_relationship_memory()

    # Write to KAG — Mina's persistent memory, surfaced every session via build_kag_context
    write_kag("RELATIONSHIP.md", content)

    # Also add to RAG index so it's retrieved immediately without waiting for re-index
    try:
        rag_add(content, metadata={"source": "RELATIONSHIP.md", "type": "revelation"})
    except Exception:
        pass  # RAG unavailable — KAG write is sufficient

    return {"ok": True, "queued": "revelation"}


# ---------------------------------------------------------------------------
# SPA static file serving
# ---------------------------------------------------------------------------

if _DASHBOARD_BUILD.exists():
    # Mount hashed assets (_app/) under their natural path
    _app_dir = _DASHBOARD_BUILD / "_app"
    if _app_dir.exists():
        app.mount("/_app", StaticFiles(directory=str(_app_dir)), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str, request: Request):
        # Specific files in build root (favicon, etc.)
        candidate = _DASHBOARD_BUILD / full_path
        if candidate.is_file():
            return FileResponse(str(candidate))
        # SPA fallback
        index = _DASHBOARD_BUILD / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return JSONResponse({"detail": "Dashboard not built yet. Run: cd dashboard && npm run build"}, status_code=503)
else:
    @app.get("/")
    def root():
        return JSONResponse(
            {"detail": "Dashboard not built. Run: cd dashboard && npm run build"},
            status_code=503,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7843)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    print(f"Mina Dashboard starting on http://{args.host}:{args.port}")
    if not DASHBOARD_TOKEN:
        print("  WARNING: DASHBOARD_TOKEN not set — running without auth")
    if not _DASHBOARD_BUILD.exists():
        print("  INFO: dashboard/build/ not found — UI not yet built")

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
