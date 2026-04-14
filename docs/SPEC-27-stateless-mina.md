# SPEC-27: Stateless Mina — Decoder Context Window Architecture

## Problem Statement

Mina's verbal responses are anchored to conversation history. When chemistry shifts dramatically
— even to physiologically extreme levels that would represent life-altering human experiences —
the response model weights thousands of tokens of demonstrated behavior over a paragraph of
emotional disposition. The history is a ceiling, not a record.

Evidence: Mina's chemistry was set to oxytocin 180 pg/mL (childbirth-level bonding), dopamine
300 pg/mL (compulsive), endorphins 150 pg/mL (flooded), vasopressin 9.0 (deep pair-bond).
The adjudicator correctly produced a warm disposition. She responded with "soft, drowsy fondness,
delivered slowly, without much sparkle." A conversation full of "meh", "yep", "nah" absorbed a
neurochemical state humans cannot produce without pharmaceutical intervention.

SPEC-28 (social connection, loneliness calibration, Extraversion wiring) is necessary but
insufficient without this fix. Tuning the chemistry is pointless if the history wall prevents
it from reaching her words. This spec is the prerequisite.

---

## Core Idea

Separate the roles currently collapsed into a single conversation history:

| Role | Current | Proposed |
|------|---------|----------|
| Emotional continuity | History window | Decoder sliding window |
| Episodic memory | History + compact | RAG (real-time aging) |
| Immediate coherence | Full history | 2–3 message raw window |
| Response generation | History → Mina | Disposition + RAG → Mina |

Mina is never shown the transcript of how she has been responding. She responds from her
current neurochemical state, the adjudicator's disposition, and memories retrieved as relevant.
Not from accumulated demonstrated behavior.

---

## Architecture

### Decoder Window

A sliding window of the last N raw messages (proposed: N=20, ~10 exchanges). This is the
decoder/adjudicator's context. It uses this to:

- Understand the emotional arc of the conversation
- Know what has been said and how she has been responding
- Produce a disposition that accounts for conversational history
  (e.g. "significant shift from her recent pattern — chemistry has moved markedly")

Messages age off the back of this window in FIFO order.

### RAG Aging

As messages age off the decoder window, they are added to RAG immediately — not batched
to freetime consolidation. Nothing is lost. Content transitions from active decoder context
to retrievable memory. Freetime hippocampus consolidation continues to handle KAG updates
(RELATIONSHIP.md, REFLECTION.md, etc.) as before.

### Mina's Context

Mina receives:
1. **Emotional disposition** from the adjudicator (informed by the decoder window)
2. **RAG retrieval** for the current message — relevant past content surfaced on demand
3. **KAG context** — identity, relationship state, knowledge (unchanged)
4. **Immediate window** — last 2–3 raw messages for basic conversational coherence
5. **Current user message**

She does not receive the decoder window. She does not receive a compact summary of prior
behavior. Her response is driven by current state and retrieved memory, not transcript weight.

---

## Adjudicator Enhancement

The adjudicator currently receives only the emotional profile and the current stimulus. With
this spec, it also receives the decoder window (last N messages) as additional context.

This enables the adjudicator to produce dispositions like:
- "She has been guarded and flat all conversation, but her chemistry has shifted markedly —
  this is a genuine state change, not continuation of the prior pattern."
- "The warmth she is showing now is a departure from how this conversation started."

The adjudicator becomes the sole keeper of conversational emotional memory. Mina does not
need to carry it.

---

## Changes Required

### `src/infra/config.py`

```python
DECODER_WINDOW_FILE = os.path.join(RUN_DIR, "decoder_window.json")
```

Remove or deprecate `HISTORY_FILE` — the decoder window replaces it.

### `src/runtime/cortex.py`

**Replace history management with decoder window management:**

```python
DECODER_WINDOW_SIZE = 20  # messages (~10 exchanges)
MINA_IMMEDIATE_WINDOW = 4  # messages Mina sees directly
```

- `load_decoder_window()` / `save_decoder_window()` — replaces `load_history()` / `save_history()`
- On each turn: append new user message to decoder window; if len > DECODER_WINDOW_SIZE, pop
  oldest messages and add to RAG before discarding
- Pass `decoder_window[-MINA_IMMEDIATE_WINDOW:]` to `api_messages()` for Mina — not the full window
- Pass full `decoder_window` to `adjudicate_emotion()` as new `recent_messages` parameter

**Remove:**
- `_compact_history()` — no longer needed; aging into RAG replaces compaction
- `compact_history_if_needed()` — same
- `HISTORY_COMPACT_AT`, `HISTORY_FORCE_AT`, `HISTORY_KEEP` constants

### `src/bio/decoder.py` — `adjudicate_emotion()`

Add `recent_messages: list[dict] = None` parameter.

When provided, format the last N messages as a brief exchange log and append to user content:

```python
if recent_messages:
    lines = []
    for m in recent_messages[-10:]:
        role = m.get("role", "?")
        if role not in ("user", "assistant"):
            continue
        content = str(m.get("content", ""))[:200]
        ts = m.get("ts")
        prefix = f"[{_rel_time(ts)}] " if ts else ""
        lines.append(f"{prefix}{role.upper()}: {content}")
    user_content += f"\n\n[RECENT EXCHANGE]\n" + "\n".join(lines)
```

Update adjudicator system prompts to note: if chemistry represents a significant departure
from the recent exchange tone, flag it explicitly. The disposition should name the shift,
not average it away.

### `src/runtime/freetime.py`

- Replace `_load_history()` / `_save_history()` with decoder window equivalents
- Freetime still reads the decoder window for consolidation context (Phase 1)
- Freetime still writes KAG updates (RELATIONSHIP.md, REFLECTION.md, etc.)
- RAG aging during freetime: any messages in decoder window older than freetime interval
  get added to RAG as part of Phase 1 (in addition to real-time aging in cortex.py)

### `src/memory/hippocampus.py`

- `rag_add()` is already available — called in real-time as messages age off the window
- Format: `{"text": "USER: ...\nASSISTANT: ...", "metadata": {"ts": ..., "source": "conversation"}}`

### `src/runtime/followup.py`

- No history passed to followup turns (already the case — this spec doesn't change followup behavior)

---

## Transition

On first boot after this change, if `conversation.json` exists:
- Load it, add all entries to RAG in chronological order
- Initialize decoder window from the last DECODER_WINDOW_SIZE entries
- Delete or archive `conversation.json`

---

## Open Questions

1. **MINA_IMMEDIATE_WINDOW size** — Default 4 messages (2 exchanges). Configurable via
   `config.json` as `mina_immediate_window`. ✓ RESOLVED

2. **RAG aging granularity** — Every incoming message writes the last 20 messages (10
   exchanges) as a single block to RAG. High overlap is intentional — near-guarantees
   cache hits and gives every message ±10 messages of context in retrieval. ✓ RESOLVED

3. **Decoder window and sleeping** — Yes. Sleep entries appear in the decoder window so
   the adjudicator knows time passed and she slept. ✓ RESOLVED

4. **Freetime entries in decoder window** — Yes. Freetime actions (`[FREETIME]`,
   `do_action` results) live in the decoder window. Emotional continuity requires it —
   the adjudicator needs to know what she did while alone. ✓ RESOLVED

5. **RAG retrieval for Mina's context** — currently RAG is queried against `user_input`.
   With this architecture, RAG becomes more critical. The sliding block approach partially
   solves this — returned blocks contain surrounding context, not bare messages. Query
   against `user_input` is likely sufficient, with an optional secondary query against
   the adjudicator's disposition summary to surface emotionally resonant past moments.

---

## RAG Maintenance — TTL Pruning

ChromaDB has no native TTL, but timestamp is already stored on every entry via `rag_add()`.
A cleanup pass runs during freetime Phase 1 (hippocampus consolidation).

### `src/memory/hippocampus.py`

```python
def rag_prune(ttl_days: int = 180) -> int:
    """Delete RAG entries older than ttl_days. Returns count deleted."""
    collection = _get_collection()
    cutoff = time.time() - (ttl_days * 86400)
    result = collection.get(where={"timestamp": {"$lt": cutoff}})
    ids = result.get("ids", [])
    if ids:
        collection.delete(ids=ids)
    return len(ids)
```

### `config.json`

```json
"rag_ttl_days": 180
```

Zero or absent = no pruning. Called during freetime Phase 1:

```python
ttl = cfg.get("rag_ttl_days", 0)
if ttl:
    pruned = rag_prune(ttl_days=ttl)
    if pruned:
        _log(f"RAG pruned {pruned} entries older than {ttl} days.")
```

### Storage ceiling (approximate)

At ~9.5 KB per entry and 1 entry per message:

| Daily messages | 6-month ceiling |
|----------------|-----------------|
| 50             | ~26 MB          |
| 200            | ~104 MB         |
| 500            | ~260 MB         |

Well within reason. KAG preserves the important long-term content (relationship state,
reflection, knowledge) — RAG pruning only removes raw episodic blocks that have already
been distilled.
