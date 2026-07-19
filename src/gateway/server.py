"""
Mina HTTP backend — chat turn + admin/state API for the Next.js UI (port 5100).

Chat:
  POST /v1/chat/completions  — run one pipeline turn (used by ui /api/chat)
  GET  /v1/models

State / admin (proxied by Next):
  GET  /api/state
  PATCH /api/state
  POST /api/state/advance
  GET  /api/events
  GET  /api/history
  GET  /api/tokens
  GET  /api/stream
  POST /api/heartbeat
  GET  /api/heartbeat/status
  GET  /api/substance         — stub
  GET  /api/billing          — stub

Not an Open WebUI / multi-client gateway. Single-user local process.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.application.infra.log import log
from src.sim.params import CHEMICAL_PARAMS

app = FastAPI(title="Mina Gateway", version="2.0")

_sim = None


def set_sim(sim) -> None:
    global _sim
    _sim = sim


# ── helpers ───────────────────────────────────────────────────────────────────

def _chem_value(tonic: float, phasic: float) -> float:
    return tonic + phasic


def _norm_1(tonic: float, phasic: float, norm_max: float) -> float:
    """0-1 fraction of normalization_max."""
    return (tonic + phasic) / norm_max if norm_max else 0.0


def _compute_derived(levels: dict) -> tuple[dict, dict]:
    """Compute second_order (0-100) and third_order (0-100) from raw levels."""

    def v(chem: str) -> float:
        """Current normalized value, 0-100 scale."""
        lvl = levels.get(chem)
        if not lvl:
            return 50.0
        p = CHEMICAL_PARAMS.get(chem)
        if not p:
            return 50.0
        return min(100.0, _norm_1(lvl["tonic"], lvl["phasic"], p["normalization_max"]) * 100.0)

    def gap(chem: str) -> float:
        """Deviation from setpoint, -10 to +10 scale."""
        lvl = levels.get(chem)
        if not lvl:
            return 0.0
        p = CHEMICAL_PARAMS.get(chem)
        if not p:
            return 0.0
        nm = p["normalization_max"]
        combined = (lvl["tonic"] + lvl["phasic"]) / nm * 10.0
        setpt = lvl["setpoint"] / nm * 10.0
        return combined - setpt

    def clamp(x: float) -> float:
        return round(max(0.0, min(100.0, x)), 1)

    da  = v("dopamine")
    ht  = v("serotonin")
    ne  = v("norepinephrine")
    epi = v("epinephrine")
    oxy = v("oxytocin")
    crt = v("cortisol")
    ach = v("acetylcholine")
    end = v("endorphins")
    ade = v("adenosine")

    # Weights sum to 1.0 — neutral (all=50) → 50
    second = {
        "energy":            clamp(ne*0.30 + da*0.25 + ach*0.20 + (100-ade)*0.10 + (100-crt)*0.15),
        "hedonic_tone":      clamp(ht*0.30 + da*0.25 + end*0.20 + oxy*0.10 + (100-crt)*0.15),
        "arousal":           clamp(ne*0.45 + epi*0.30 + da*0.25),
        "social_warmth":     clamp(oxy*0.40 + ht*0.25 + end*0.15 + (100-crt)*0.20),
        "cognitive_clarity": clamp(ach*0.40 + ne*0.25 + (100-ade)*0.20 + (100-crt)*0.15),
        "mood_valence":      clamp(ht*0.30 + da*0.20 + oxy*0.15 + end*0.15 + (100-crt)*0.20),
    }

    # Gap-relative pathological signals — near zero at neutral
    third = {
        "anxiety":           clamp(25.0 + gap("cortisol")*5.0 + gap("norepinephrine")*3.0),
        "depression":        clamp(20.0 - gap("dopamine")*4.0 - gap("serotonin")*4.0),
        "boredom":           clamp(50.0 - second["arousal"]*0.30 - second["cognitive_clarity"]*0.20),
        "loneliness":        clamp(25.0 - gap("oxytocin")*5.0 - (ht - 50.0)*0.10),
        "flow":              clamp(second["cognitive_clarity"]*0.50 + second["energy"]*0.30 + da*0.20),
        "physical_distress": clamp(10.0 + gap("cortisol")*3.0),
        "craving":           clamp(15.0 - gap("dopamine")*4.0),
    }

    return second, third


def _build_state(sim) -> dict:
    levels, sleeping = sim.raw_snapshot()
    second, third = _compute_derived(levels)

    chemicals = {}
    receptor_sensitivity = {}
    for name, lvl in levels.items():
        p = CHEMICAL_PARAMS.get(name)
        if not p or p["class"] == 4:
            continue
        combined = lvl["tonic"] + lvl["phasic"]
        norm_max = p["normalization_max"]
        chemicals[name] = {
            "value":      round(combined, 3),
            "unit":       "nM",
            "label":      name.replace("_", " ").title(),
            "normalized": round(combined / norm_max, 4),
        }
        receptor_sensitivity[name] = round(lvl["sensitivity"], 3)

    return {
        "chemicals":          chemicals,
        "sleeping":           sleeping,
        "second_order":       second,
        "third_order":        third,
        "vital_signs":        {},
        "neuroendocrine":     {},
        "immune":             {},
        "pain":               {},
        "neuroplasticity":    {},
        "personality_drift":  {},
        "body":               {},
        "receptor_sensitivity": receptor_sensitivity,
        "cascade_queue":      [],
        "secretion_queue":    [],
        "allostatic_load":    0.0,
        "cycle_day":          0,
    }


def _build_history_snapshot(sim) -> dict:
    levels, sleeping = sim.raw_snapshot()
    second, third = _compute_derived(levels)

    chemicals: dict[str, float] = {}
    for name, lvl in levels.items():
        p = CHEMICAL_PARAMS.get(name)
        if not p or p["class"] == 4:
            continue
        combined = lvl["tonic"] + lvl["phasic"]
        chemicals[name] = round(combined / p["normalization_max"] * 10.0, 2)

    return {
        "ts":           time.time(),
        "chemicals":    chemicals,
        "second_order": {k: v / 10.0 for k, v in second.items()},  # rescale to 0-10
        "third_order":  {k: v / 10.0 for k, v in third.items()},
        "sleeping":     sleeping,
    }


# ── /v1/models ────────────────────────────────────────────────────────────────

@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [{"id": "mina", "object": "model", "created": 0, "owned_by": "mina"}],
    }


# ── /v1/chat/completions ──────────────────────────────────────────────────────

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    if _sim is None:
        return JSONResponse(status_code=503, content={"error": "Sim not initialized."})

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON."})

    messages = body.get("messages", [])
    if not messages:
        return JSONResponse(status_code=400, content={"error": "No messages provided."})

    from src.config.config import load_config
    username = (
        load_config().get("username") or body.get("user") or "user"
    ).strip().lower() or "user"

    user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    part.get("text", "") for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                )
            user_msg = content.strip()
            break

    if not user_msg:
        return JSONResponse(status_code=400, content={"error": "No user message found."})

    log("GATEWAY", f"Received: {user_msg[:80]}")

    from src.brain.pipeline import run_turn
    try:
        reply = await run_turn(user_msg, username, _sim)
    except Exception as e:
        log("GATEWAY/ERR", str(e))
        return JSONResponse(status_code=500, content={"error": str(e)})

    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "mina",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


# ── /health ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


# ── /api/state ────────────────────────────────────────────────────────────────

@app.get("/api/state")
async def get_state():
    if _sim is None:
        return JSONResponse(status_code=503, content={"error": "Sim not initialized."})
    return _build_state(_sim)


@app.patch("/api/state")
async def patch_state(request: Request):
    if _sim is None:
        return JSONResponse(status_code=503, content={"error": "Sim not initialized."})
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON."})

    updated = []
    for chemical, value in body.items():
        if _sim.set_chemical(chemical, float(value)):
            updated.append(chemical)
    return {"ok": True, "updated": updated}


@app.post("/api/state/advance")
async def advance_state(request: Request):
    if _sim is None:
        return JSONResponse(status_code=503, content={"error": "Sim not initialized."})
    try:
        body = await request.json()
        hours = float(body.get("hours", 1.0))
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON."})

    _sim.advance(hours)
    return {"ok": True, "advanced_hours": hours}


# ── /api/events ───────────────────────────────────────────────────────────────

@app.get("/api/events")
async def get_events(limit: int = 150):
    from src.application.infra.events import read_events
    return read_events(limit=limit)


# ── /api/history ──────────────────────────────────────────────────────────────

@app.get("/api/history")
async def get_history(hours: float = 6, limit: int = 2000):
    from src.application.infra.history import read
    return read(hours=hours, limit=limit)


# ── /api/tokens ───────────────────────────────────────────────────────────────

@app.get("/api/tokens")
async def get_tokens():
    from src.application.infra import token_stats
    return token_stats.get()


# ── /api/stream ───────────────────────────────────────────────────────────────

@app.get("/api/stream")
async def stream_state():
    from pathlib import Path
    from src.config.config import RUN_DIR
    obs_file = Path(RUN_DIR) / "obs.jsonl"

    async def generator():
        # Send an initial state snapshot so the client has data immediately
        if _sim is not None:
            try:
                snap = _build_history_snapshot(_sim)
                payload = {
                    "chemicals":    snap["chemicals"],
                    "second_order": {k: v * 10 for k, v in snap["second_order"].items()},
                    "third_order":  {k: v * 10 for k, v in snap["third_order"].items()},
                    "sleeping":     snap["sleeping"],
                }
                yield f"data: {json.dumps({'type': 'state_snapshot', 'payload': payload})}\n\n"
            except Exception:
                pass

        offset = obs_file.stat().st_size if obs_file.exists() else 0
        last_snap_ts = 0.0

        while True:
            await asyncio.sleep(2)
            try:
                # Tail obs.jsonl — emit new tick observations as they arrive
                if obs_file.exists():
                    size = obs_file.stat().st_size
                    if size > offset:
                        with open(obs_file) as f:
                            f.seek(offset)
                            new_data = f.read()
                            offset = f.tell()
                        for line in new_data.splitlines():
                            line = line.strip()
                            if line:
                                try:
                                    obs = json.loads(line)
                                    yield f"data: {json.dumps({'type': 'tick_obs', 'payload': obs})}\n\n"
                                except Exception:
                                    pass

                # Also send a full state snapshot every 10 seconds
                now = time.time()
                if _sim is not None and now - last_snap_ts >= 10:
                    snap = _build_history_snapshot(_sim)
                    payload = {
                        "chemicals":    snap["chemicals"],
                        "second_order": {k: v * 10 for k, v in snap["second_order"].items()},
                        "third_order":  {k: v * 10 for k, v in snap["third_order"].items()},
                        "sleeping":     snap["sleeping"],
                    }
                    yield f"data: {json.dumps({'type': 'state_snapshot', 'payload': payload})}\n\n"
                    last_snap_ts = now
            except Exception:
                pass

    return StreamingResponse(generator(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


# ── /api/obs ──────────────────────────────────────────────────────────────────

@app.get("/api/obs")
async def get_obs(limit: int = 200, hours: float | None = None):
    from src.sim.observer import read_obs
    return read_obs(limit=limit, hours=hours)


# ── /api/heartbeat ────────────────────────────────────────────────────────────

_heartbeat_state: dict = {"last_run": None, "running": False}


@app.post("/api/heartbeat")
async def run_heartbeat():
    if _sim is None:
        return JSONResponse(status_code=503, content={"error": "Sim not initialized."})
    if _heartbeat_state["running"]:
        return {"ok": False, "message": "Already running"}
    _heartbeat_state["running"] = True
    try:
        from src.freetime.freetime import run_freetime
        await run_freetime(_sim)
        _heartbeat_state["last_run"] = time.time()
        return {"ok": True, "message": "Freetime run complete"}
    except Exception as e:
        return {"ok": False, "message": str(e)}
    finally:
        _heartbeat_state["running"] = False


@app.get("/api/heartbeat/status")
async def heartbeat_status():
    return {
        "last_run":   _heartbeat_state["last_run"],
        "is_running": _heartbeat_state["running"],
    }


# ── /api/substance ────────────────────────────────────────────────────────────

@app.get("/api/substance")
async def get_substances():
    return {}


# ── /api/billing ─────────────────────────────────────────────────────────────

@app.get("/api/billing")
async def get_billing():
    return {"cap": 0.0, "used": 0.0, "remaining": 0.0, "period": "n/a"}
