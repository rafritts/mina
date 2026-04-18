"""
Discord sender registry — thin bridge between non-gateway modules and the live Discord client.

Gateway registers a sender on startup. All other modules call send() or send_nowait()
without knowing about Discord internals or channels.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine

_sender: Callable[..., Coroutine[Any, Any, None]] | None = None


def register(fn: Callable[..., Coroutine[Any, Any, None]]) -> None:
    global _sender
    _sender = fn


async def send(content: str = "", image_path: str = "") -> None:
    if _sender is None:
        raise RuntimeError("discord_send: no sender registered (gateway not running?)")
    await _sender(content=content, image_path=image_path)


def send_nowait(content: str = "", image_path: str = "") -> None:
    """Schedule a send from sync context. Must be called from within a running event loop."""
    asyncio.get_event_loop().create_task(send(content=content, image_path=image_path))
