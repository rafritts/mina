"""
StreamBus — SPEC-49: Unified Data Stream.

Sync, fire-and-forget event emitter. Every call to emit() appends a JSON line to
run/stream.jsonl (cross-process IPC) and calls any registered in-process handlers
synchronously in order.

The dashboard server tails stream.jsonl to serve SSE. The gateway registers a log
handler so mina.log is also driven from the bus.

Trace IDs propagate via contextvars — set stream_bus.new_trace() at turn start and
every downstream emit() in that call chain picks up the same ID automatically,
including calls made inside asyncio.to_thread().
"""
import contextvars
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from src.config.config import RUN_DIR

_STREAM_FILE = Path(RUN_DIR) / "stream.jsonl"
_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")


@dataclass
class StreamEvent:
    type: str
    payload: dict
    trace_id: str = ""
    ts: float = field(default_factory=time.time)


class StreamBus:
    def __init__(self) -> None:
        self._handlers: list[Callable[[StreamEvent], None]] = []

    def register(self, handler: Callable[[StreamEvent], None]) -> None:
        self._handlers.append(handler)

    def set_trace(self, tid: str) -> None:
        _trace_id.set(tid)

    def new_trace(self) -> str:
        tid = str(uuid.uuid4())
        _trace_id.set(tid)
        return tid

    def emit(self, type: str, payload: dict) -> None:
        event = StreamEvent(type=type, payload=payload, trace_id=_trace_id.get())
        line = json.dumps({
            "type": event.type,
            "trace_id": event.trace_id,
            "ts": event.ts,
            "payload": event.payload,
        })
        try:
            _STREAM_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_STREAM_FILE, "a") as f:
                f.write(line + "\n")
        except Exception:
            pass
        for handler in self._handlers:
            try:
                handler(event)
            except Exception:
                pass


stream_bus = StreamBus()
