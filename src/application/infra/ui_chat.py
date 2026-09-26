"""
Server-owned UI chat transcript (run/ui_chat.json).

The pipeline / turn job is the only writer of messages. The Next UI reads this
file (via GET /api/chat-store) and may still PUT image prefs — never the
message list while a turn is running.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from src.config.config import RUN_DIR

UI_CHAT_PATH = Path(RUN_DIR) / "ui_chat.json"

_lock = threading.Lock()

_EMPTY: dict[str, Any] = {
    "updatedAt": 0,
    "putRevision": 0,
    "messages": [],
}


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _read_unlocked() -> dict[str, Any]:
    try:
        raw = UI_CHAT_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {
            "updatedAt": 0,
            "putRevision": 0,
            "messages": [],
        }
    if not isinstance(data, dict):
        return dict(_EMPTY)
    messages = data.get("messages")
    if not isinstance(messages, list):
        messages = []
    rev = data.get("putRevision", 0)
    try:
        rev = max(0, int(rev))
    except (TypeError, ValueError):
        rev = 0
    updated = data.get("updatedAt", 0)
    try:
        updated = int(updated) if updated else 0
    except (TypeError, ValueError):
        updated = 0
    out: dict[str, Any] = {
        "updatedAt": updated,
        "putRevision": rev,
        "messages": [m for m in messages if isinstance(m, dict)],
    }
    if data.get("imageAspect") in ("landscape", "square", "portrait"):
        out["imageAspect"] = data["imageAspect"]
    ic = data.get("imageCount")
    if ic == "auto" or (isinstance(ic, int) and 0 <= ic <= 5) or (
        isinstance(ic, str) and ic.isdigit() and 0 <= int(ic) <= 5
    ):
        out["imageCount"] = ic if ic == "auto" else (int(ic) if not isinstance(ic, int) else ic)
    return out


def _write_unlocked(store: dict[str, Any]) -> dict[str, Any]:
    UI_CHAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    next_store: dict[str, Any] = {
        "updatedAt": int(time.time() * 1000),
        "putRevision": int(store.get("putRevision") or 0),
        "messages": list(store.get("messages") or []),
    }
    if store.get("imageAspect") in ("landscape", "square", "portrait"):
        next_store["imageAspect"] = store["imageAspect"]
    if "imageCount" in store:
        next_store["imageCount"] = store["imageCount"]
    tmp = f"{UI_CHAT_PATH}.{os.getpid()}.{time.time_ns()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(next_store, indent=2, ensure_ascii=False))
        f.write("\n")
    os.replace(tmp, UI_CHAT_PATH)
    return next_store


def read_store() -> dict[str, Any]:
    with _lock:
        return _read_unlocked()


def clear_messages() -> dict[str, Any]:
    """Erase transcript messages; keep image prefs."""
    with _lock:
        store = _read_unlocked()
        store["messages"] = []
        store["putRevision"] = int(store.get("putRevision") or 0) + 1
        return _write_unlocked(store)


def append_user(content: str) -> dict[str, Any]:
    msg = {
        "id": _new_id("u"),
        "role": "user",
        "content": content,
    }
    with _lock:
        store = _read_unlocked()
        store["messages"] = list(store.get("messages") or []) + [msg]
        store["putRevision"] = int(store.get("putRevision") or 0) + 1
        return _write_unlocked(store)


def _host_image_urls(images: list[str] | None) -> list[str]:
    if not images:
        return []
    return [
        u
        for u in images
        if isinstance(u, str)
        and (u.startswith("/images/") or u.startswith("/api/generate/"))
    ]


def append_assistant(
    content: str,
    *,
    images: list[str] | None = None,
    mind: dict[str, Any] | None = None,
    image_pending: bool = False,
) -> dict[str, Any]:
    msg: dict[str, Any] = {
        "id": _new_id("a"),
        "role": "assistant",
        "content": content,
    }
    urls = _host_image_urls(images)
    if urls:
        msg["images"] = urls
    if image_pending:
        msg["imagePending"] = True
    if mind:
        msg["mind"] = mind
    with _lock:
        store = _read_unlocked()
        store["messages"] = list(store.get("messages") or []) + [msg]
        store["putRevision"] = int(store.get("putRevision") or 0) + 1
        return _write_unlocked(store)


def update_assistant(
    message_id: str,
    *,
    content: str | None = None,
    images: list[str] | None = None,
    image_pending: bool | None = None,
    mind: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Patch one assistant bubble already on screen (photo landing after the text)."""
    if not message_id:
        return None
    with _lock:
        store = _read_unlocked()
        messages = list(store.get("messages") or [])
        found = False
        for msg in messages:
            if not isinstance(msg, dict) or msg.get("id") != message_id:
                continue
            found = True
            if content is not None:
                msg["content"] = content
            if images is not None:
                urls = _host_image_urls(images)
                if urls:
                    msg["images"] = urls
                else:
                    msg.pop("images", None)
            if image_pending is not None:
                if image_pending:
                    msg["imagePending"] = True
                else:
                    msg.pop("imagePending", None)
            if mind is not None:
                msg["mind"] = mind
            break
        if not found:
            return None
        store["messages"] = messages
        store["putRevision"] = int(store.get("putRevision") or 0) + 1
        return _write_unlocked(store)


def rewind_ui_for_redo(
    user_message: str,
    *,
    new_user_text: str | None = None,
) -> dict[str, Any]:
    """
    Align the UI transcript with pipeline.rewind_for_redo.

    - Pop trailing assistant (if any).
    - If trailing user matches user_message:
        - edit path (new_user_text set and different): replace content
        - plain redo: leave user bubble in place
    """
    target = (user_message or "").strip()
    replacement = (new_user_text or "").strip() or None
    with _lock:
        store = _read_unlocked()
        messages = list(store.get("messages") or [])
        changed = False

        if messages and messages[-1].get("role") == "assistant":
            messages.pop()
            changed = True

        if (
            messages
            and messages[-1].get("role") == "user"
            and (messages[-1].get("content") or "").strip() == target
        ):
            if replacement is not None and replacement != target:
                messages[-1] = {
                    **messages[-1],
                    "content": replacement,
                }
                changed = True
            # plain redo: keep user message
        elif replacement is not None:
            # No matching trailing user — append the new text so the UI isn't blank.
            messages.append(
                {
                    "id": _new_id("u"),
                    "role": "user",
                    "content": replacement,
                }
            )
            changed = True

        if not changed:
            return store
        store["messages"] = messages
        store["putRevision"] = int(store.get("putRevision") or 0) + 1
        return _write_unlocked(store)
