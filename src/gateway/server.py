"""
FastAPI gateway — OpenAI-compatible endpoint on port 5100.

Implements:
  POST /v1/chat/completions  — routes incoming messages through Mina's pipeline
  GET  /v1/models            — returns a model list so Open WebUI connects cleanly

No auth. Local-only. Streaming not implemented (synchronous response).

Open WebUI setup:
  Settings → Connections → Add connection → http://localhost:5100/v1
"""
from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.application.infra.log import log

app = FastAPI(title="Mina Gateway", version="2.0")

# Sim is injected at startup via set_sim()
_sim = None


def set_sim(sim) -> None:
    global _sim
    _sim = sim


# ── /v1/models ────────────────────────────────────────────────────────────────

@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": "mina",
                "object": "model",
                "created": 0,
                "owned_by": "mina",
            }
        ],
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

    # Resolve username: config.json > request body "user" field > "user"
    from src.config.config import load_config
    username = (
        load_config().get("username")
        or body.get("user")
        or "user"
    ).strip().lower() or "user"

    # Extract the last user message
    user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content", "")
            if isinstance(content, list):
                # multipart content — join text parts
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
            {
                "index": 0,
                "message": {"role": "assistant", "content": reply},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


# ── health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}
