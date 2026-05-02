# SPEC-45: Sliding Window RAG

## Problem

The current RAG write strategy stores entire conversation blocks as single ChromaDB documents — either the whole decoder window (old `_rag_write_and_trim`) or everything since last consolidation (current `consolidate()`). A 20-30 message block produces one embedding that averages the semantic content of every topic discussed. Specific statements ("lace bodysuits with turtlenecks are normie slayers") get buried in signal from unrelated exchanges, producing poor retrieval precision.

## Solution

Write a 10-message (5-turn) chunk to RAG on every individual message — user and Mina alike. Each message ends up represented in up to 10 overlapping chunks, each carrying different surrounding context. Retrieval expands the matching chunk by ±3 sequence positions, recovering coherent context on both sides of the semantic match.

---

## Design

### Collection

A dedicated ChromaDB collection `mina_sliding` separate from `mina_experiences`. Using the same `_OllamaEmbeddingFunction` and storage directory (`memory/rag/`). This keeps sliding window chunks from polluting episodic memory queries and vice versa.

### Chunk shape

- **Window**: last 10 messages from decoder_window (5 turns), or fewer if conversation is shorter
- **Format**: `_format_conversation_block()` — same format used by existing RAG writes
- **Metadata**:
  - `seq` (int): monotonically incrementing sequence number, global across all writes
  - `timestamp` (float): Unix timestamp of the last entry in the window
  - `source` (str): `"sliding_window"`

### Sequence counter

Stored in `run/sliding_seq.json` as `{"seq": N}`. Read-increment-write on every `sliding_rag_write()` call. The counter is never reset between restarts (sequence continuity is required for expansion queries). Reset only on full wipe.

### Write triggers

Called from `cortex.py` at two points per exchange:

1. **After user message appended**: line ~534, immediately after `decoder_window.append({"role": "user", ...})`
2. **After Mina's reply appended**: after `decoder_window.extend(new_entries)` + trim, before `_save_decoder_window()`

Also called from `freetime.py` after each assistant message is appended to `decoder_window`.

These are fire-and-forget (non-blocking) — call via `asyncio.to_thread` or synchronously; the embed call is the expensive part but it's already on a thread.

### Retrieval with expansion

```
sliding_rag_query(query, expand_radius=3) -> str
```

1. Query `mina_sliding` for best semantic match → get chunk with seq = N
2. Fetch backward: `collection.get(where={"seq": {"$in": [N-3, N-2, N-1]}})`
3. Fetch forward: `collection.get(where={"seq": {"$in": [N+1, N+2, N+3]}})`
4. Union all chunks (up to 7 docs total), sort by seq
5. Extract all messages from each chunk's formatted text, deduplicate by content, reassemble in order
6. Return as formatted string

**Expected output**: ~16 unique messages (10 from the matching chunk + 3 earlier + 3 later). In practice, adjacent chunks overlap by 9 messages so deduplication reduces this, but the recovered context always spans the exchange before and after the semantic match.

### Integration into context assembly

`cortex.py` currently assembles response context in a parallel gather:

```python
kag_context, _relational_rag, (rag_recent, rag_semi_recent, rag_historical) = await asyncio.gather(
    asyncio.to_thread(build_kag_context),
    asyncio.to_thread(build_rag_context_relational, stimulus),
    asyncio.to_thread(build_rag_context_bucketed, user_input),
)
```

With sliding windows:

```python
kag_context, _relational_rag, (rag_semi_recent, rag_historical), rag_sliding = await asyncio.gather(
    asyncio.to_thread(build_kag_context),
    asyncio.to_thread(build_rag_context_relational, stimulus),
    asyncio.to_thread(_rag_bucketed_no_recent, user_input),   # semi_recent + historical only
    asyncio.to_thread(sliding_rag_query, user_input),
)
```

`rag_sliding` replaces `rag_recent` in the `build_rag_context()` call:

```python
build_rag_context(stimulus, kag_context, rag_sliding, rag_semi_recent, rag_historical)
```

The `[RECENT CONTEXT]` label in the context block remains — the sliding window result is semantically the "recent context", just retrieved with much higher precision.

`build_rag_context_bucketed` needs a variant that skips the recent bucket (since sliding windows own that), or the recent result is simply ignored and `rag_sliding` used instead. Either is fine.

### Consolidation rolling write removal

`consolidate()` in hippocampus.py currently writes conversation blocks to `mina_experiences`. With sliding windows writing per-message, the rolling block write is redundant and should be removed. LLM-generated episodic memories from consolidation are retained — they capture meaning (what happened, why it mattered) that raw conversation text does not.

---

## Affected Files

| File | Change |
|------|--------|
| `src/brain/hippocampus/hippocampus.py` | Add `mina_sliding` collection; add `sliding_rag_write()`; add `sliding_rag_query()`; add `sliding_rag_wipe()`; remove rolling block write from `consolidate()` |
| `src/brain/cortex/cortex.py` | Call `sliding_rag_write()` at two points per turn; pass `rag_sliding` as `rag_recent` in context assembly |
| `src/brain/subconscious/freetime.py` | Call `sliding_rag_write()` after each assistant message appended |
| `src/brain/brainstem/vital_signs.py` | Call `sliding_rag_wipe()` on overdose reset |

---

## Open Questions

1. **Minimum window**: If fewer than 10 messages exist (very start of conversation), write whatever is in the window. No minimum threshold — even a 2-message chunk is useful.

2. **Wipe on `/reset`**: `sliding_rag_wipe()` should be called alongside `rag_wipe()` everywhere a reset clears the RAG store.

3. **Expansion deduplication**: Adjacent chunks overlap by 9 messages. Dedup by (role, content) tuple to avoid repeating the same exchange twice in the assembled result. Preserve order by seq.

4. **Latency**: Each write embeds a 10-message block via Ollama. On a per-message basis this adds embed latency to every turn. Since it runs via `asyncio.to_thread`, it's concurrent with other post-response work. If Ollama is slow (>2s), consider fire-and-forget (don't await). Monitor in practice.

5. **seq gap on wipe**: After a wipe, sequence starts fresh. Old seq numbers from the wiped collection are gone. This is fine — expansion queries for nonexistent seqs simply return nothing.

6. **relational_rag context_hint unchanged**: The relational RAG that feeds `encode_stimulus` and `adjudicate_emotion` (`build_rag_context_relational`, 30-day half-life) is independent of this spec. It queries `mina_experiences`. No change needed there.

---

## Non-Goals

- Full-text search or keyword matching — this is embedding-only
- Cross-session linking (connecting chunks from different days) — chunks from different sessions are naturally retrievable by cosine similarity; no special handling needed
- Chunking freetime tool calls — tool output (web search results, etc.) should not be embedded as conversation; filter by `role != "tool"` before chunking
