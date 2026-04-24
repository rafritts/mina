# SPEC-49: Unified Data Stream

## Overview

Currently, simulation data is piecemeal: the state poller reads `state.json`, the events feed reads `events.jsonl`, the log file has everything else (RAG hits, KAG selections, stimulus processing, response texture, deltas) but only as human-readable text.

This spec defines a **unified data collection layer** — a structured event emitter in Python that fires typed events at each stage of the response cycle. These events are:

1. Broadcast over a **FastAPI SSE endpoint** (`/api/stream`) for the Sim Viewer (SPEC-49)
2. Written to `mina.log` (replacing or augmenting existing log lines)

The goal: everything the viewer needs to display a response cycle is available as structured, typed events over a single SSE connection.

---

## Event Schema

All events share a base envelope:

```python
@dataclass
class StreamEvent:
    type: str           # event type identifier (see below)
    ts: float           # unix timestamp
    payload: dict       # event-specific data
```

### Event Types

#### `state_snapshot`
Emitted every 2 seconds by the heartbeat/poller. Full monoamine and second/third-order state.

```json
{
  "type": "state_snapshot",
  "ts": 1714000000.0,
  "payload": {
    "chemicals": {
      "dopamine": { "value": 62.4, "normalized": 0.58 },
      "serotonin": { "value": 55.1, "normalized": 0.51 }
    },
    "second_order": { "energy": 54.2, "mood_valence": 61.0 },
    "third_order": { "anxiety": 18.3 },
    "sleeping": false
  }
}
```

#### `delta`
Emitted by the encoder whenever chemical values change. Contains only the chemicals that changed.

```json
{
  "type": "delta",
  "ts": 1714000001.2,
  "payload": {
    "source": "stimulus",
    "deltas": {
      "dopamine": 6.2,
      "serotonin": 3.1
    }
  }
}
```

`source` indicates what triggered the delta: `"stimulus"`, `"heartbeat"`, `"sleep"`, `"substance"`, etc.

#### `stimulus_land`
Emitted when the encoder processes an incoming stimulus and computes how it lands.

```json
{
  "type": "stimulus_land",
  "ts": 1714000001.0,
  "payload": {
    "preview": "User asked how she's feeling",
    "valence": 0.6,
    "arousal": 0.4,
    "appraisal": "curious, mild positive"
  }
}
```

#### `context_snapshot`
Emitted when the cortex assembles the conversation context for a response.

```json
{
  "type": "context_snapshot",
  "ts": 1714000001.5,
  "payload": {
    "turns": 12,
    "summary": "Ongoing conversation about her internal experience",
    "token_count": 840
  }
}
```

#### `rag_hit`
Emitted once per RAG result retrieved. Multiple may fire per response cycle.

```json
{
  "type": "rag_hit",
  "ts": 1714000001.6,
  "payload": {
    "index": 0,
    "score": 0.87,
    "excerpt": "She remembered feeling uncertain the last time...",
    "source": "episodic"
  }
}
```

#### `kag_selection`
Emitted for each KAG file selected. Multiple may fire per response cycle.

```json
{
  "type": "kag_selection",
  "ts": 1714000001.7,
  "payload": {
    "filename": "attachment_style.md",
    "excerpt": "Anxious-preoccupied baseline. Tends to seek reassurance..."
  }
}
```

`excerpt` is the first 120 characters of the file, or the most relevant passage if indexed.

#### `response_texture`
Emitted when the response style/texture instruction is selected.

```json
{
  "type": "response_texture",
  "ts": 1714000001.8,
  "payload": {
    "label": "reflective",
    "description": "Thoughtful, inward-looking, measured"
  }
}
```

#### `response_complete`
Emitted when the final response text is ready to send.

```json
{
  "type": "response_complete",
  "ts": 1714000003.2,
  "payload": {
    "text": "Honestly, I'm not entirely sure. There's something sitting heavy in me today.",
    "token_count": 214
  }
}
```

---

## Python Implementation

### StreamBus

A singleton event bus that other modules fire events into. Decoupled from the SSE transport — modules just call `stream_bus.emit(event)`.

```python
# src/infrastructure/stream_bus.py

import asyncio
from dataclasses import dataclass, field
from typing import Callable, Awaitable
import time

@dataclass
class StreamEvent:
    type: str
    payload: dict
    ts: float = field(default_factory=time.time)

StreamListener = Callable[[StreamEvent], Awaitable[None]]

class StreamBus:
    def __init__(self):
        self._listeners: list[StreamListener] = []

    def subscribe(self, listener: StreamListener):
        self._listeners.append(listener)

    def unsubscribe(self, listener: StreamListener):
        self._listeners.discard(listener)

    async def emit(self, event: StreamEvent):
        for listener in list(self._listeners):
            try:
                await listener(event)
            except Exception:
                pass  # never let a bad listener crash the bus

stream_bus = StreamBus()  # module-level singleton
```

### Emission Sites

Each module imports `stream_bus` and calls `await stream_bus.emit(...)` at the appropriate point:

| Module | Event emitted |
|--------|--------------|
| Heartbeat / poller | `state_snapshot` every 2s |
| Encoder | `delta` after each chemical update |
| Encoder | `stimulus_land` after appraisal |
| Cortex | `context_snapshot` after context assembly |
| Hippocampus (RAG) | `rag_hit` for each result |
| KAG loader | `kag_selection` for each file selected |
| Response builder | `response_texture` when texture is resolved |
| Discord gateway | `response_complete` after response is sent |

---

## FastAPI SSE Endpoint

```python
# src/application/api/stream.py

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from src.infrastructure.stream_bus import stream_bus, StreamEvent
import asyncio, json

router = APIRouter()

@router.get("/api/stream")
async def sse_stream():
    queue: asyncio.Queue[StreamEvent] = asyncio.Queue()

    async def listener(event: StreamEvent):
        await queue.put(event)

    stream_bus.subscribe(listener)

    async def generate():
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=30)
                data = json.dumps({"type": event.type, "ts": event.ts, "payload": event.payload})
                yield f"data: {data}\n\n"
        except asyncio.TimeoutError:
            yield ": keepalive\n\n"  # SSE keepalive comment
        finally:
            stream_bus.unsubscribe(listener)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })
```

The timeout/keepalive loop restarts on each SSE client reconnect. The generator runs until the client disconnects, at which point `finally` unsubscribes the listener.

---

## Log Integration

The existing `mina.log` continues to work. The stream bus also has a log listener registered at startup that writes structured events to the log in a readable format. This replaces ad-hoc `logger.info(...)` calls at these sites over time.

The log output for a delta event becomes:
```
[DELTA] dopamine +6.2, serotonin +3.1 (source: stimulus)
```

Rather than requiring an immediate refactor of all logging, the stream bus approach means the log and the SSE feed stay in sync by construction — they both come from the same `emit()` call.

---

## Open Questions

1. **Backpressure**: If the SSE client is slow, the queue can grow unbounded. Should add a max queue size with drop-oldest behavior for the viewer (lossy is acceptable).

2. **Multiple clients**: The bus supports N subscribers. Two viewer tabs open = two queue listeners = fine.

3. **KAG excerpt availability**: Currently KAG logs the filename only. The excerpt field in `kag_selection` requires reading the first 120 chars of the file at selection time. This is a small file read and should be negligible.

4. **Delta granularity**: The encoder currently batches deltas. The `delta` event should emit once per batch (not once per chemical) to avoid flooding the stream.

5. **Auth**: The `/api/stream` endpoint is currently unauthenticated, consistent with the rest of the local API. Not a concern for local deployment.
