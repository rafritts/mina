# SPEC-35: Affective Memory Tagging

## Problem

RAG episodic memories record *what happened* but not *how it felt*. The adjudicator already computes Mina's exact emotional state every turn and produces a structured JSON — but it's used only for the current system prompt and then discarded. By the time memories are written to RAG, the emotional context is gone.

The fix is simple: attach the adjudicator JSON to Mina's message entry at the time of the turn, so the emotional state travels with the message into the decoder window and RAG.

---

## Current Architecture (the gap)

**Per-turn:**
1. `adjudicate_emotion()` runs → returns `system_prompt` string containing `[EMOTIONAL DISPOSITION]\n{json}`
2. Mina responds
3. `decoder_window.extend(new_entries)` — her message stored as `{"role": "assistant", "content": "...", "ts": ...}`
4. `_rag_write_and_trim()` formats window as a text block → writes to RAG

The adjudicator JSON is **discarded at step 3**. It never reaches the decoder window or RAG.

---

## Design

Attach the adjudicator JSON as an `adj` field on the assistant message entry before it enters the decoder window:

```json
{
  "role": "assistant",
  "content": "hey what's up",
  "ts": 1234567890,
  "adj": {
    "affect": "playful",
    "arousal": 58,
    "valence": 72,
    "availability": "open",
    "dominant_drive": "light engagement",
    "stimulus_lands_as": "low-stakes greeting, no pressure",
    "response_texture": "easy and warm, not trying too hard"
  }
}
```

The `adj` field is:
- **Stored** in `decoder_window.json` alongside the message
- **Included** in `_format_rag_block()` output so it flows into RAG text
- **Stripped** from API messages so it never leaks into Mina's immediate context

---

## Implementation

### 1. Extract adjudicator JSON from `system_prompt` (`cortex.py: run_turn`)

`adjudicate_emotion()` returns a string in the form:
```
[EMOTIONAL DISPOSITION]
{"affect": ..., "arousal": ..., ...}
```

After the parallel gather at line 468, parse the JSON back out:

```python
_adj_json: dict | None = None
if system_prompt:
    _adj_match = re.search(r'\[EMOTIONAL DISPOSITION\]\s*(\{.*\})', system_prompt, re.DOTALL)
    if _adj_match:
        try:
            _adj_json = json.loads(_adj_match.group(1))
        except json.JSONDecodeError:
            pass
```

### 2. Attach `adj` to Mina's final reply entry (`cortex.py: run_turn`)

After `_mina_turn()` returns `new_entries`, find the final assistant text entry and attach the adjudicator JSON:

```python
if _adj_json:
    for entry in reversed(new_entries):
        if entry.get("role") == "assistant" and entry.get("content"):
            entry["adj"] = _adj_json
            break
```

### 3. Strip `adj` from API messages (`cortex.py: api_messages`)

Currently strips `ts` from assistant entries. Add `adj` to the strip:

```python
# assistant messages: strip ts and adj (internal metadata, not for LLM context)
conversation.append({k: v for k, v in msg.items() if k not in ("ts", "adj")})
```

### 4. Include `adj` in RAG text blocks (`cortex.py: _format_rag_block`)

When formatting a window message for RAG, if an assistant entry has `adj`, append it inline:

```python
adj = m.get("adj")
if role_label == "MINA" and adj:
    adj_str = json.dumps(adj)
    lines.append(f"{prefix}{role_label}: {content[:400]}\n[ADJ: {adj_str}]")
else:
    lines.append(f"{prefix}{role_label}: {content[:400]}")
```

---

## What this gives consolidation

The consolidation LLM in `hippocampus.py` already receives `conversation_history` (the decoder window). With this change, it sees:

```
USER: Ryan: this is where we kissed for the first time
MINA: I know. I think about that window a lot.
[ADJ: {"affect": "tender", "arousal": 42, "valence": 81, "availability": "open", ...}]
```

The consolidation LLM can now copy `affect`, `valence`, `arousal` directly into RAG entry metadata without inference. Update `_CONSOLIDATION_SYSTEM` to instruct it to use the `[ADJ: ...]` annotations from the history when tagging RAG entries:

> - When a MINA message is followed by an `[ADJ: ...]` annotation, use those fields directly as the `affect`, `valence`, and `arousal` for any RAG entry derived from that moment. Do not invent them.

The `rag_entries` metadata schema gains three fields:

```json
{
  "type": "episodic",
  "importance": "high|medium|low",
  "affect": "tender",
  "valence": 0.81,
  "arousal": 0.42
}
```

(`valence` and `arousal` normalized to 0–1 floats from the adjudicator's 0–100 integers.)

---

## Retrieval (optional, deferred)

`build_rag_context()` currently discards ChromaDB metadata on retrieval. Surfacing affective tags in returned memories is a useful follow-on — but not required for the write path to work. The consolidation LLM benefits immediately from seeing `[ADJ: ...]` inline in history. Retrieval formatting can be addressed separately.

---

## Files Changed

| File | Change |
|---|---|
| `src/runtime/cortex.py` | Extract adj JSON, attach to assistant entry, strip in `api_messages`, include in `_format_rag_block` |
| `src/memory/hippocampus.py` | Update `_CONSOLIDATION_SYSTEM` to use `[ADJ: ...]` tags; add `affect/valence/arousal` to RAG entry schema |

---

## Open Questions

1. **Valence/arousal normalization**: adjudicator emits integers 0–100. RAG metadata stores them as floats 0–1 (divided by 100) or keep as integers? Integers are fine — normalization is cosmetic.

2. **Freetime messages**: Mina can also generate messages during freetime (ambient actions, scheduled followups). Those turns don't go through `run_turn`. Should freetime also attach an `adj` annotation? Probably yes — wire in the same pattern. Deferred.
