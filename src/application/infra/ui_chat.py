"""
Server-owned UI chat transcript (run/ui_chat.json).

The pipeline / turn job is the only writer of messages. The Next UI reads this
file (via GET /api/chat-store) and may PUT an explicit Clear — never the
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

from src.application.infra.plain_text import strip_image_markup
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


def _clean_message(msg: dict[str, Any]) -> dict[str, Any]:
    content = msg.get("content")
    if not isinstance(content, str):
        content = ""
    cleaned: dict[str, Any] = {
        "id": msg.get("id"),
        "role": msg.get("role"),
        "content": strip_image_markup(content),
    }
    mind = msg.get("mind")
    if msg.get("role") == "assistant" and isinstance(mind, dict):
        cleaned["mind"] = mind
    return cleaned


def _clean_messages(messages: list[Any]) -> list[dict[str, Any]]:
    return [_clean_message(m) for m in messages if isinstance(m, dict)]


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
    return {
        "updatedAt": updated,
        "putRevision": rev,
        "messages": _clean_messages(messages),
    }


def _write_unlocked(store: dict[str, Any]) -> dict[str, Any]:
    UI_CHAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    next_store: dict[str, Any] = {
        "updatedAt": int(time.time() * 1000),
        "putRevision": int(store.get("putRevision") or 0),
        "messages": _clean_messages(list(store.get("messages") or [])),
    }
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
    """Erase transcript messages."""
    with _lock:
        store = _read_unlocked()
        store["messages"] = []
        store["putRevision"] = int(store.get("putRevision") or 0) + 1
        return _write_unlocked(store)


def append_user(content: str) -> dict[str, Any]:
    msg = {
        "id": _new_id("u"),
        "role": "user",
        "content": strip_image_markup(content),
    }
    with _lock:
        store = _read_unlocked()
        store["messages"] = list(store.get("messages") or []) + [msg]
        store["putRevision"] = int(store.get("putRevision") or 0) + 1
        return _write_unlocked(store)


def append_assistant(
    content: str,
    *,
    mind: dict[str, Any] | None = None,
) -> dict[str, Any]:
    msg: dict[str, Any] = {
        "id": _new_id("a"),
        "role": "assistant",
        "content": strip_image_markup(content),
    }
    if mind:
        msg["mind"] = mind
    with _lock:
        store = _read_unlocked()
        store["messages"] = list(store.get("messages") or []) + [msg]
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
