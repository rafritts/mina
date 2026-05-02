# SPEC-49: Unified Data Stream

## Overview

A synchronous event queue that any part of the system can fire events into. Two consumers run as background threads: one writes to `mina.log`, one fans events out to connected SSE clients. Ordering is guaranteed — emit order is delivery order.

---

## Core Design

```
any module calls stream_bus.emit(type, payload)   ← sync, fire and forget
                        ↓
                  queue.SimpleQueue                ← thread-safe FIFO
                        ↓
              single drain thread
              /                  \
        log writer            SSE broadcaster
      (mina.log)           (per-client queues)
                                  ↓
                          EventSource.onmessage
```

Every event carries a `trace_id` set at turn start so the viewer can group all events from a single response cycle.

---

## StreamBus

```python
# src/infrastructure/stream_bus.py

import contextvars
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")


@dataclass
class StreamEvent:
    type: str
    payload: dict
    trace_id: str = ""
    ts: float = field(default_factory=time.time)


class StreamBus:
    def __init__(self):
        self._queue: queue.SimpleQueue[StreamEvent] = queue.SimpleQueue()
        self._handlers: list[Callable[[StreamEvent], None]] = []
        self._thread = threading.Thread(target=self._drain, daemon=True)
        self._thread.start()

    def set_trace(self, tid: str) -> None:
        _trace_id.set(tid)

    def new_trace(self) -> str:
        tid = str(uuid.uuid4())
        _trace_id.set(tid)
        return tid

    def emit(self, type: str, payload: dict) -> None:
        event = StreamEvent(type=type, payload=payload, trace_id=_trace_id.get())
        self._queue.put(event)

    def register(self, handler: Callable[[StreamEvent], None]) -> None:
        self._handlers.append(handler)

    def _drain(self) -> None:
        while True:
            event = self._queue.get()
            for handler in self._handlers:
                try:
                    handler(event)
                except Exception:
                    pass


stream_bus = StreamBus()
```

---

## Consumers

### Log Consumer

Replaces ad-hoc `log()` calls at structured emission sites. Registered at startup.

```python
# src/infrastructure/stream_bus.py (or startup)

import json
from src.application.infra.log import log

def _log_handler(event: StreamEvent) -> None:
    log(event.type.upper(), json.dumps(event.payload))

stream_bus.register(_log_handler)
```

### SSE Consumer

Maintains a list of per-client queues. When a client connects, a queue is added; when they disconnect, it's removed. The drain thread fans each event into all client queues synchronously.

```python
# src/infrastructure/stream_bus.py

class SSEBroadcaster:
    def __init__(self):
        self._lock = threading.Lock()
        self._clients: list[queue.SimpleQueue[StreamEvent]] = []

    def add_client(self) -> queue.SimpleQueue[StreamEvent]:
        q: queue.SimpleQueue[StreamEvent] = queue.SimpleQueue()
        with self._lock:
            self._clients.append(q)
        return q

    def remove_client(self, q: queue.SimpleQueue[StreamEvent]) -> None:
        with self._lock:
            self._clients.remove(q)

    def __call__(self, event: StreamEvent) -> None:
        with self._lock:
            for q in self._clients:
                q.put(event)


sse_broadcaster = SSEBroadcaster()
stream_bus.register(sse_broadcaster)
```

---

## SSE Endpoint

The async generator polls the client's sync queue via `asyncio.to_thread`. The bus and fan-out are entirely sync — only the HTTP transport is async.

```python
# src/application/api/stream.py

import asyncio
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from src.infrastructure.stream_bus import sse_broadcaster

router = APIRouter()

@router.get("/api/stream")
async def sse_stream():
    client_queue = sse_broadcaster.add_client()

    async def generate():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        asyncio.to_thread(client_queue.get), timeout=30
                    )
                    data = json.dumps({
                        "type": event.type,
                        "trace_id": event.trace_id,
                        "ts": event.ts,
                        "payload": event.payload,
                    })
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            sse_broadcaster.remove_client(client_queue)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })
```

---

## Emission Sites

At the start of each turn in `run_turn()`:
```python
stream_bus.new_trace()
```

Each module adds one `stream_bus.emit()` call alongside its existing logic:

| Module | Event | Key payload fields |
|--------|-------|--------------------|
| encoder | `delta` | `source`, `deltas` |
| encoder | `stimulus_land` | `preview`, `valence`, `arousal` |
| hippocampus | `rag_hit` | `score`, `excerpt`, `bucket` |
| KAG loader | `kag_selection` | `filename`, `excerpt` |
| emotional_reasoner | `emotion_pillar` | `dominant_affect`, `arousal`, `valence`, `availability` |
| context_reasoner | `context_pillar` | `situational_summary`, `urgency` |
| response_reasoner | `reasoning` | `approach`, `internal_reaction` |
| gateway | `response_complete` | `text`, `token_count` |
| heartbeat poller | `state_snapshot` | `chemicals`, `second_order`, `third_order` |

---

## Open Questions

None.
