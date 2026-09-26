"""
Server-owned chat turn job.

The UI only submits a message and observes status + the durable chat store.
Disconnects / mobile backgrounding cannot cancel or stub the turn.
"""
from __future__ import annotations

import asyncio
import threading
import time
import uuid
from typing import Any

from src.application.infra.log import log
from src.application.infra.stream_bus import StreamEvent, stream_bus
from src.application.infra import ui_chat

# ── Job state (process-global; single-user local daemon) ─────────────────────

_state_lock = threading.Lock()
_state: dict[str, Any] = {
    "status": "idle",  # idle | running | error
    "turn_id": None,
    "started_at": None,
    "finished_at": None,
    "user_message": None,
    "error": None,
    "stage": None,
    "stage_label": None,
}


def get_status() -> dict[str, Any]:
    with _state_lock:
        return dict(_state)


def is_running() -> bool:
    with _state_lock:
        return _state["status"] == "running"


# ── Mind accumulator (mirrors ui/app/lib/stream.ts reduceTurnMind) ───────────

_EMPTY_MIND: dict[str, Any] = {
    "active": False,
    "stage": None,
    "stageLabel": None,
    "stimulus": None,
    "encoder": None,
    "emotion": None,
    "memory": [],
    "context": None,
    "reasoning": None,
    "completed": False,
    "skipped": False,
}


class MindAccumulator:
    def __init__(self) -> None:
        self._mind: dict[str, Any] = {
            **_EMPTY_MIND,
            "memory": [],
        }

    def handle(self, event: StreamEvent) -> None:
        t = event.type
        p = event.payload or {}
        m = self._mind

        if t == "stimulus_land":
            self._mind = {
                **_EMPTY_MIND,
                "active": True,
                "stage": "sense",
                "stageLabel": "Sensing",
                "stimulus": p.get("preview"),
                "memory": [],
            }
            return

        if t == "stage":
            m["active"] = True
            m["stage"] = p.get("stage")
            m["stageLabel"] = p.get("label")
            with _state_lock:
                if _state["status"] == "running":
                    _state["stage"] = m["stage"]
                    _state["stage_label"] = m["stageLabel"]
            return

        if t == "encoder":
            m["active"] = True
            m["encoder"] = p
            if m.get("stage") in (None, "sense"):
                m["stage"] = "chemistry"
                m["stageLabel"] = "Chemistry settling"
            return

        if t == "emotion_pillar":
            m["active"] = True
            m["emotion"] = p
            if not m.get("stage"):
                m["stage"] = "feel"
                m["stageLabel"] = "Feeling"
            return

        if t == "rag_hit":
            m["active"] = True
            mem = list(m.get("memory") or [])
            item: dict[str, Any] = {
                "type": "rag",
                "text": p.get("excerpt") or "",
            }
            if p.get("bucket"):
                item["bucket"] = p["bucket"]
            mem.append(item)
            m["memory"] = mem
            return

        if t == "kag_selection":
            m["active"] = True
            mem = list(m.get("memory") or [])
            mem.append(
                {
                    "type": "kag",
                    "text": p.get("filename") or p.get("excerpt") or "",
                }
            )
            m["memory"] = mem
            return

        if t == "context_pillar":
            m["active"] = True
            m["context"] = p
            if not m.get("stage"):
                m["stage"] = "situate"
                m["stageLabel"] = "Situating"
            return

        if t == "reasoning":
            m["active"] = True
            m["reasoning"] = p
            if not m.get("stage"):
                m["stage"] = "decide"
                m["stageLabel"] = "Deciding"
            return

        if t == "response_complete":
            m["active"] = True
            m["completed"] = True
            m["skipped"] = bool(p.get("skipped"))
            m["stage"] = "speak"
            m["stageLabel"] = "Silence" if m["skipped"] else "Speaking"

    def has_content(self) -> bool:
        m = self._mind
        return bool(
            m.get("stimulus")
            or m.get("encoder")
            or m.get("emotion")
            or m.get("context")
            or m.get("reasoning")
            or m.get("memory")
            or m.get("active")
        )

    def snapshot(self) -> dict[str, Any] | None:
        if not self.has_content():
            return None
        m = self._mind
        return {
            "active": True,
            "stage": m.get("stage"),
            "stageLabel": m.get("stageLabel"),
            "stimulus": m.get("stimulus"),
            "encoder": m.get("encoder"),
            "emotion": m.get("emotion"),
            "memory": list(m.get("memory") or []),
            "context": m.get("context"),
            "reasoning": m.get("reasoning"),
            "completed": bool(m.get("completed")),
            "skipped": bool(m.get("skipped")),
        }


# ── Submit / run ─────────────────────────────────────────────────────────────

def try_begin(
    *,
    user_message: str,
    username: str,
    image_count: str | int,
    image_aspect: str,
    redo: bool,
    rewind_message: str,
) -> tuple[bool, dict[str, Any]]:
    """
    Claim the single-flight turn slot and prepare the UI transcript.

    Returns (ok, payload). On success payload includes turn_id + status.
    On failure payload is an error body for the HTTP response.
    """
    with _state_lock:
        if _state["status"] == "running":
            return False, {
                "error": "Turn already in progress",
                "status": dict(_state),
            }

    # Prepare durable transcript before the pipeline starts so any client
    # that polls (or reconnects later) sees the user bubble immediately.
    try:
        if redo:
            edit = (user_message or "").strip() != (rewind_message or "").strip()
            ui_chat.rewind_ui_for_redo(
                rewind_message,
                new_user_text=user_message if edit else None,
            )
        else:
            ui_chat.append_user(user_message)
    except Exception as e:
        log("TURN/ERR", f"ui_chat prepare failed: {e}")
        return False, {"error": f"Failed to update chat store: {e}"}

    turn_id = uuid.uuid4().hex[:12]
    with _state_lock:
        _state.update(
            {
                "status": "running",
                "turn_id": turn_id,
                "started_at": time.time(),
                "finished_at": None,
                "user_message": user_message,
                "error": None,
                "stage": "sense",
                "stage_label": "Starting",
            }
        )

    stream_bus.emit(
        "turn_status",
        {
            "status": "running",
            "turn_id": turn_id,
            "user_message": user_message[:280],
        },
    )

    return True, {
        "ok": True,
        "turn_id": turn_id,
        "status": "running",
        "accepted": True,
    }


async def run_claimed(
    *,
    sim,
    user_message: str,
    username: str,
    image_count: str | int,
    image_aspect: str,
    redo: bool,
    rewind_message: str,
    turn_id: str,
) -> None:
    """Execute pipeline for a slot already claimed by try_begin."""
    from src.brain.pipeline import rewind_for_redo, run_turn

    if redo:
        try:
            rewind_for_redo(rewind_message)
        except Exception as e:
            log("TURN/ERR", f"redo rewind failed: {e}")
            _finish_error(turn_id, f"Redo rewind failed: {e}")
            return

    mind = MindAccumulator()
    stream_bus.register(mind.handle)
    try:
        log("TURN", f"start {turn_id}: {user_message[:80]}")
        published: dict[str, str | None] = {"id": None}

        def on_voice(text: str) -> str | None:
            store = ui_chat.append_assistant(
                text,
                image_pending=True,
                mind=mind.snapshot(),
            )
            messages = store.get("messages") or []
            mid = messages[-1]["id"] if messages else None
            published["id"] = mid
            return mid

        def on_photos(message_id: str, text: str, images: list[str]) -> None:
            ui_chat.update_assistant(
                message_id,
                content=text,
                images=images,
                image_pending=False,
                mind=mind.snapshot(),
            )

        result = await run_turn(
            user_message,
            username,
            sim,
            image_count=image_count,
            image_aspect=image_aspect,
            on_voice=on_voice,
            on_photos=on_photos,
        )
        if isinstance(result, dict):
            reply = (result.get("reply") or "").strip()
            images = result.get("images") or []
            ui_message_id = result.get("ui_message_id") or published["id"]
        else:
            reply = (result or "").strip()
            images = []
            ui_message_id = published["id"]

        if not reply:
            reply = "(empty reply)"

        # Ensure image markdown is present for the durable bubble.
        for url in images:
            if isinstance(url, str) and url.startswith("/images/") and url not in reply:
                reply = f"{reply}\n\n![photo]({url})"

        if ui_message_id:
            ui_chat.update_assistant(
                ui_message_id,
                content=reply,
                images=[u for u in images if isinstance(u, str)],
                image_pending=False,
                mind=mind.snapshot(),
            )
        else:
            ui_chat.append_assistant(
                reply,
                images=[u for u in images if isinstance(u, str)],
                mind=mind.snapshot(),
            )
        _finish_ok(turn_id)
        log("TURN", f"done {turn_id}")
    except Exception as e:
        log("TURN/ERR", f"{turn_id}: {e}")
        # Durable partial mind if any — never invent a fake "no reply" stub.
        snap = mind.snapshot()
        if snap:
            ui_chat.append_assistant(
                f"(turn failed: {e})",
                mind=snap,
            )
        _finish_error(turn_id, str(e))
    finally:
        stream_bus.unregister(mind.handle)


def _finish_ok(turn_id: str) -> None:
    with _state_lock:
        if _state.get("turn_id") != turn_id:
            return
        _state.update(
            {
                "status": "idle",
                "finished_at": time.time(),
                "error": None,
                "stage": None,
                "stage_label": None,
            }
        )
    stream_bus.emit(
        "turn_status",
        {"status": "idle", "turn_id": turn_id},
    )


def _finish_error(turn_id: str, error: str) -> None:
    with _state_lock:
        if _state.get("turn_id") != turn_id:
            return
        _state.update(
            {
                "status": "error",
                "finished_at": time.time(),
                "error": error,
                "stage": None,
                "stage_label": None,
            }
        )
    stream_bus.emit(
        "turn_status",
        {"status": "error", "turn_id": turn_id, "error": error},
    )


async def submit(
    *,
    sim,
    user_message: str,
    username: str,
    image_count: str | int = "auto",
    image_aspect: str = "square",
    redo: bool = False,
    rewind_message: str | None = None,
) -> tuple[int, dict[str, Any]]:
    """
    Accept a turn and schedule it. Returns (http_status, body).

    Always returns immediately — pipeline runs as an asyncio task.
    """
    rewind = (rewind_message or user_message or "").strip() or user_message
    ok, body = try_begin(
        user_message=user_message,
        username=username,
        image_count=image_count,
        image_aspect=image_aspect,
        redo=redo,
        rewind_message=rewind,
    )
    if not ok:
        code = 409 if "already" in (body.get("error") or "").lower() else 500
        return code, body

    turn_id = body["turn_id"]

    async def _job() -> None:
        await run_claimed(
            sim=sim,
            user_message=user_message,
            username=username,
            image_count=image_count,
            image_aspect=image_aspect,
            redo=redo,
            rewind_message=rewind,
            turn_id=turn_id,
        )

    asyncio.create_task(_job())
    return 202, body
