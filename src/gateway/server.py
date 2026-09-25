"""
Mina HTTP backend — chat turn + admin/state API for the Next.js UI (port 5100).

Chat:
  POST /api/turn             — accept a message; pipeline runs server-side (202)
  GET  /api/turn             — turn job status (idle | running | error)
  POST /v1/chat/completions  — OpenAI-compatible; also async-accepted (202 + poll)
  GET  /v1/models

State / admin (proxied by Next):
  GET  /api/state
  PATCH /api/state
  POST /api/state/advance
  GET  /api/events
  GET  /api/history
  GET  /api/freetime         — recent free-time sessions (what she did alone)
  GET  /api/tokens
  GET  /api/stream
  POST /api/heartbeat
  GET  /api/heartbeat/status
  GET  /api/context           — latest pillar assembly (JSON; ?format=md for markdown)
  GET  /api/context/text     — same assembly as markdown
  GET  /api/scene            — live scene snapshot (agent-authored short-term coherence)
  POST /api/conversation/erase — wipe chat logs + window + sliding RAG (keeps chem/KAG)
  GET  /api/substance         — stub
  GET  /api/billing          — stub

Not an Open WebUI / multi-client gateway. Single-user local process.

The turn is fully server-owned: the UI only submits and observes the durable
chat store + SSE. Client disconnect does not cancel the pipeline.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from src.application.infra.log import log
from src.sim.params import CHEMICAL_PARAMS
from src.sim.labels import annotate_chemical

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

    # OT absolute fraction of max is ~5% at rest (looks "cold"). Center the OT
    # term on gap so resting OT → neutral ~50 (SPEC-62 DEFECT-4).
    ot_component = clamp(50.0 + gap("oxytocin") * 8.0)

    # Weights sum to 1.0 — neutral (all=50) → 50
    second = {
        "energy":            clamp(ne*0.30 + da*0.25 + ach*0.20 + (100-ade)*0.10 + (100-crt)*0.15),
        "hedonic_tone":      clamp(ht*0.30 + da*0.25 + end*0.20 + oxy*0.10 + (100-crt)*0.15),
        "arousal":           clamp(ne*0.45 + epi*0.30 + da*0.25),
        "social_warmth":     clamp(ot_component*0.40 + ht*0.25 + end*0.15 + (100-crt)*0.20),
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
    sleep = sim.sleep_info() if hasattr(sim, "sleep_info") else {
        "sleeping": sleeping,
        "sleep_elapsed_s": 0.0,
        "sleep_started_at": None,
        "last_sleep_started_at": None,
        "last_woke_at": None,
    }

    chemicals = {}
    receptor_sensitivity = {}
    for name, lvl in levels.items():
        p = CHEMICAL_PARAMS.get(name)
        if not p or p["class"] == 4:
            continue
        chemicals[name] = annotate_chemical(
            name,
            tonic=lvl["tonic"],
            phasic=lvl["phasic"],
            setpoint=lvl["setpoint"],
        )
        receptor_sensitivity[name] = round(lvl["sensitivity"], 3)

    return {
        "chemicals":          chemicals,
        "sleeping":           sleeping,
        "sleep_elapsed_s":    sleep.get("sleep_elapsed_s", 0.0),
        "sleep_started_at":   sleep.get("sleep_started_at"),
        "last_sleep_started_at": sleep.get("last_sleep_started_at"),
        "last_woke_at":       sleep.get("last_woke_at"),
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


# ── helpers: photo prefs + username ───────────────────────────────────────────

def _parse_image_count(raw) -> str | int:
    if raw is None or raw == "":
        return "auto"
    if isinstance(raw, bool):
        return "auto"
    if isinstance(raw, int) and 0 <= raw <= 5:
        return raw
    if isinstance(raw, str):
        s = raw.strip().lower()
        if s == "auto":
            return "auto"
        if s.isdigit() and 0 <= int(s) <= 5:
            return int(s)
    return "auto"


def _parse_image_aspect(raw) -> str:
    return raw if raw in ("landscape", "square", "portrait") else "square"


def _username(body: dict | None = None) -> str:
    from src.config.config import load_config
    body = body or {}
    return (
        load_config().get("username") or body.get("user") or "user"
    ).strip().lower() or "user"


# ── /api/turn — server-owned async chat ───────────────────────────────────────

@app.post("/api/turn")
async def post_turn(request: Request):
    """
    Accept one user message and run the pipeline in the background.

    Returns 202 immediately. The durable transcript (run/ui_chat.json) is
    updated by the server; clients observe via GET /api/chat-store + SSE.
    """
    if _sim is None:
        return JSONResponse(status_code=503, content={"error": "Sim not initialized."})

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON."})

    # UI shape: { message, history?, image_count, image_aspect, redo, rewind_message }
    # Also accept OpenAI-ish { messages: [...] } for a single trailing user turn.
    user_msg = (body.get("message") or "").strip()
    if not user_msg:
        for m in reversed(body.get("messages") or []):
            if not isinstance(m, dict) or m.get("role") != "user":
                continue
            content = m.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                )
            user_msg = (content or "").strip()
            if user_msg:
                break

    if not user_msg:
        return JSONResponse(status_code=400, content={"error": "Empty message."})

    image_count = _parse_image_count(body.get("image_count", "auto"))
    image_aspect = _parse_image_aspect(body.get("image_aspect", "square"))
    redo = bool(body.get("redo"))
    rewind_msg = (body.get("rewind_message") or user_msg or "").strip() or user_msg
    username = _username(body)

    log(
        "GATEWAY",
        f"Turn accepted: {user_msg[:80]} (photos={image_count} aspect={image_aspect}"
        f"{', redo' if redo else ''}{', edit' if redo and rewind_msg != user_msg else ''})",
    )

    from src.application.infra.turn_job import submit

    status, payload = await submit(
        sim=_sim,
        user_message=user_msg,
        username=username,
        image_count=image_count,
        image_aspect=image_aspect,
        redo=redo,
        rewind_message=rewind_msg,
    )
    return JSONResponse(status_code=status, content=payload)


@app.get("/api/turn")
async def get_turn():
    """Current turn job status for observers (UI)."""
    from src.application.infra.turn_job import get_status
    return get_status()


# ── /v1/chat/completions ──────────────────────────────────────────────────────

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """
    OpenAI-compatible entry. Same server-owned async job as POST /api/turn.

    Returns 202 with { status, turn_id }. Poll GET /api/turn + chat store for
    the reply — the HTTP request no longer blocks for the full pipeline.
    """
    if _sim is None:
        return JSONResponse(status_code=503, content={"error": "Sim not initialized."})

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON."})

    messages = body.get("messages", [])
    user_msg = (body.get("message") or "").strip()
    if not user_msg:
        for m in reversed(messages or []):
            if not isinstance(m, dict) or m.get("role") != "user":
                continue
            content = m.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                )
            user_msg = (content or "").strip()
            if user_msg:
                break

    if not user_msg:
        return JSONResponse(status_code=400, content={"error": "No user message found."})

    image_count = _parse_image_count(body.get("image_count", "auto"))
    image_aspect = _parse_image_aspect(body.get("image_aspect", "square"))
    redo = bool(body.get("redo"))
    rewind_msg = (body.get("rewind_message") or user_msg or "").strip() or user_msg
    username = _username(body)

    log(
        "GATEWAY",
        f"Received: {user_msg[:80]} (photos={image_count} aspect={image_aspect}"
        f"{', redo' if redo else ''}{', edit' if redo and rewind_msg != user_msg else ''})",
    )

    from src.application.infra.turn_job import submit

    status, payload = await submit(
        sim=_sim,
        user_message=user_msg,
        username=username,
        image_count=image_count,
        image_aspect=image_aspect,
        redo=redo,
        rewind_message=rewind_msg,
    )
    # Keep a chatcmpl-ish id for tools that expect one.
    if status < 400:
        payload = {
            **payload,
            "id": f"chatcmpl-{payload.get('turn_id') or uuid.uuid4().hex[:12]}",
            "object": "chat.completion.accepted",
            "created": int(time.time()),
            "model": "mina",
        }
    return JSONResponse(status_code=status, content=payload)


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


@app.post("/api/state/reset")
async def reset_state():
    """Reset chemistry to Big-5 baselines; wake if sleeping. Keeps memory/chat."""
    if _sim is None:
        return JSONResponse(status_code=503, content={"error": "Sim not initialized."})
    norms = _sim.reset_to_baseline()
    log("GATEWAY", "State reset to baseline.")
    return {"ok": True, "sleeping": False, "chemicals": norms}


@app.post("/api/conversation/erase")
async def erase_conversation():
    """
    Erase chat history Mina can still see: conversation logs, rolling window,
    turn dumps, prior affect stickiness, short-term sliding RAG, UI transcript,
    and the free-time session log.

    Does not touch chemistry, episodic RAG, KAG, or relationships.
    """
    from src.application.infra.turn_job import is_running
    if is_running():
        return JSONResponse(
            status_code=409,
            content={"error": "Cannot erase while a turn is running."},
        )
    from src.brain.pipeline import erase_chat_history
    result = erase_chat_history()
    log("GATEWAY", f"Conversation erased: {result.get('removed')}")
    return result


# ── /api/events ───────────────────────────────────────────────────────────────

@app.get("/api/events")
async def get_events(limit: int = 150):
    from src.application.infra.events import read_events
    return read_events(limit=limit)


# ── /api/freetime ─────────────────────────────────────────────────────────────

@app.get("/api/freetime")
async def get_freetime(limit: int = 40, ts: float | None = None):
    """
    Recent free-time sessions.

    Query:
      limit — how many compact sessions in `recent`
      ts    — if set, also return full `detail` (tools + pillar context)
    """
    from src.freetime.freetime import read_freetime_history
    return read_freetime_history(limit=limit, detail_ts=ts)


@app.get("/api/freetime/text")
async def get_freetime_text(ts: float | None = None):
    """Markdown dump of a free-time session (default: latest with full detail)."""
    from src.freetime.freetime import (
        read_freetime_history,
        format_freetime_markdown,
        write_last_freetime_markdown,
    )
    data = read_freetime_history(limit=5, detail_ts=ts)
    session = data.get("detail")
    if session is None and data.get("last") and data["last"].get("ts") is not None:
        data = read_freetime_history(limit=5, detail_ts=float(data["last"]["ts"]))
        session = data.get("detail")
    if not session:
        return Response(content="(no free-time sessions yet)\n", media_type="text/markdown")
    md = format_freetime_markdown(session)
    if ts is None:
        write_last_freetime_markdown(session)
    return Response(content=md, media_type="text/markdown; charset=utf-8")


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
    """
    SSE: state snapshots + live pipeline events (stream.jsonl) + tick obs.

    Pillar events (emotion_pillar, context_pillar, reasoning, …) arrive as the
    turn runs so the UI can reveal thinking before the reply returns.
    """
    from pathlib import Path
    from src.config.config import RUN_DIR
    obs_file = Path(RUN_DIR) / "obs.jsonl"
    stream_file = Path(RUN_DIR) / "stream.jsonl"

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

        # Tail from end — only live events (not historical backlog)
        obs_offset = obs_file.stat().st_size if obs_file.exists() else 0
        stream_offset = stream_file.stat().st_size if stream_file.exists() else 0
        last_snap_ts = 0.0

        while True:
            await asyncio.sleep(0.35)
            try:
                # Live pipeline / pillar events (fast poll)
                if stream_file.exists():
                    size = stream_file.stat().st_size
                    if size < stream_offset:
                        stream_offset = 0  # rotated / truncated
                    if size > stream_offset:
                        with open(stream_file) as f:
                            f.seek(stream_offset)
                            new_data = f.read()
                            stream_offset = f.tell()
                        for line in new_data.splitlines():
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                evt = json.loads(line)
                                # stream.jsonl lines already have type + payload
                                yield f"data: {json.dumps(evt)}\n\n"
                            except Exception:
                                pass

                # Tick observations
                if obs_file.exists():
                    size = obs_file.stat().st_size
                    if size < obs_offset:
                        obs_offset = 0
                    if size > obs_offset:
                        with open(obs_file) as f:
                            f.seek(obs_offset)
                            new_data = f.read()
                            obs_offset = f.tell()
                        for line in new_data.splitlines():
                            line = line.strip()
                            if line:
                                try:
                                    obs = json.loads(line)
                                    yield f"data: {json.dumps({'type': 'tick_obs', 'payload': obs})}\n\n"
                                except Exception:
                                    pass

                # Periodic full state snapshot
                now = time.time()
                if _sim is not None and now - last_snap_ts >= 8:
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


# ── /api/context ──────────────────────────────────────────────────────────────

@app.get("/api/context")
async def get_context(request: Request):
    """
    Most recent pillar context assembly.

    Default: JSON (structured for UI).
    ?format=md|text  or Accept: text/markdown|text/plain → readable markdown.
    Durable files: run/last_context.json and run/last_context.md (agent-friendly).
    """
    from src.brain.context_log import read_last_context, read_last_context_markdown

    fmt = (request.query_params.get("format") or "").strip().lower()
    accept = (request.headers.get("accept") or "").lower()
    want_text = fmt in ("md", "markdown", "text", "plain") or (
        ("text/markdown" in accept or "text/plain" in accept)
        and "application/json" not in accept
    )

    if want_text:
        body = read_last_context_markdown()
        return Response(
            content=body,
            media_type="text/markdown; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )

    record = read_last_context()
    if record is None:
        return JSONResponse(
            status_code=404,
            content={"error": "No context assembly yet. Send a chat message first."},
        )
    return record


@app.get("/api/context/text")
async def get_context_text():
    """Plain markdown of the latest assembly (agent-friendly)."""
    from src.brain.context_log import read_last_context_markdown
    body = read_last_context_markdown()
    return Response(
        content=body,
        media_type="text/markdown; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/scene")
async def get_scene():
    """
    Live scene snapshot: clothing, positions, scene_time, timeline, plans.
    Agent-authored each reply; host stores and re-injects next turn.
    """
    from src.brain.scene_context import (
        format_scene_block,
        load_scene,
        scene_has_content,
    )
    from src.brain.context_log import read_last_context

    sc = load_scene()
    has = scene_has_content(sc)
    last = read_last_context() or {}
    return {
        "scene": sc if has else {
            "clothing": [],
            "positions": [],
            "scene_time": "",
            "timeline": [],
            "plans": [],
            "updated_at": 0,
        },
        "has_content": has,
        "inject": format_scene_block(sc, for_agent=True) if has else "",
        "system_prompt": last.get("system_prompt") or "",
        "updated_at": sc.get("updated_at") if has else 0,
    }
