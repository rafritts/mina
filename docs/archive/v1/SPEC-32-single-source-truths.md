# SPEC-32: Single Source Truths

## Principle

When multiple subsystems in Mina's architecture need the same data, there must be exactly one authoritative source for it. Subsystems that need that data know where to find it. They do not maintain their own copies, derive their own approximations, or receive stale slices passed through intermediaries.

Violations of this principle produce bugs that are hard to trace: two subsystems disagree on what happened, one sees a truncated version of reality, or a write in one place doesn't propagate to another.

This spec establishes the pattern and implements the first instance of it. Future instances are added here before implementation begins.

---

## Instance 1: Conversation History

### The problem

The full conversation between the user and Mina is not stored anywhere as a first-class construct. Instead, fragments of it exist in multiple places simultaneously:

- **`run/decoder_window.json`** — 20-message sliding window. The rendering artifact the LLM sees. Messages fall off silently.
- **ChromaDB (RAG)** — lossy, embedding-indexed. Cannot be iterated sequentially. Not a record.
- **`run/history.jsonl`** — biological state snapshots only. Not conversation.

Subsystems that need conversation history receive whatever fragment happens to be available at call time:

- Hippocampus consolidation gets `decoder_window` (20 messages). If a conversation was longer between freetime cycles, the earlier turns are already gone — permanently.
- RELATIONSHIP.md is written by a system that only ever saw 20 messages. It is structurally incapable of reflecting anything that happened more than ~10 exchanges ago.
- The encoder, adjudicator, and freetime prompt builder have no history access at all.

### The source of truth: `conversation.jsonl`

```
run/conversation.jsonl
```

An append-only, newline-delimited JSON file. One entry per turn. Never trimmed. This is the record.

#### Entry format

```json
{"role": "user",      "ts": 1744000000.0, "content": "Hey Mina",  "source": "discord"}
{"role": "assistant", "ts": 1744000012.0, "content": "hey 🖤",    "source": "discord"}
{"role": "assistant", "ts": 1744000300.0, "content": "...",        "source": "freetime"}
```

Fields:
- `role` — `"user"` | `"assistant"`
- `ts` — Unix timestamp (float)
- `content` — text content (tool calls stored as their visible output, not raw JSON; `do_action` descriptions included — they are meaningful relationship context)
- `source` — `"discord"` | `"freetime"` | `"cli"`

#### Properties

- **Append-only.** Never rewritten, never trimmed.
- **Not fed to the LLM directly.** It is a source of truth for subsystems, not a context window. The decoder window continues to exist as the LLM rendering artifact it is.
- **Wiped on factory reset.** It is a record of this relationship, not Mina's permanent memory.

### Writers

**`src/runtime/cortex.py` — `run_turn()`**
After each completed exchange, append user message and final assistant response. Tool call intermediate turns are excluded — only user-visible content.

**`src/runtime/freetime.py` — Phase 2**
Append each assistant message produced during freetime with `"source": "freetime"`. `do_action` activity descriptions are included.

### Readers

**`src/memory/hippocampus.py` — `consolidate()`**
Reads `conversation.jsonl` from `last_consolidated_ts` forward instead of receiving `decoder_window`. Tracks cursor in `run/consolidation_state.json`:

```json
{"last_consolidated_ts": 1744000000.0}
```

The hippocampus now always sees everything that happened since it last ran — regardless of how long the conversation was or how many freetime cycles elapsed.

### Factory reset

`_wipe_user_data()` in `discord_gateway.py` deletes `run/conversation.jsonl` and `run/consolidation_state.json`.

### Files touched

| File | Change |
|------|--------|
| `src/runtime/cortex.py` | Append to `conversation.jsonl` after each completed exchange |
| `src/runtime/freetime.py` | Append freetime assistant messages to `conversation.jsonl` |
| `src/memory/hippocampus.py` | Read from `conversation.jsonl` since `last_consolidated_ts`; write `consolidation_state.json` |
| `src/infra/config.py` | Add `CONVERSATION_FILE` and `CONSOLIDATION_STATE_FILE` path constants |
| `src/gateway/discord_gateway.py` | Wipe both files on factory reset |

### Decisions

1. **Backfill on first boot** — no backfill. Factory reset before deploying. No migration code.
2. **File size** — segment once per day, ideally triggered after Mina's long sleep window (4am–8am). Append-only per-day files, e.g. `conversation-2026-04-16.jsonl`.

---

## Instance 2: Memory Writes — Hippocampus as Single Writer

### The problem

`cortex.py` currently calls `_rag_write_and_trim()` at the end of every freetime cycle — the **decoder is writing to RAG**. This rolling window dump (last 20 messages → ChromaDB text block) is actually working well: it's the mechanism that gives Mina long-term conversational coherence with almost no effort. The behavior is correct. The location is wrong.

This is memory consolidation. It belongs to the hippocampus.

### The rule

**The hippocampus is the only system that writes to RAG, KAG, or any persistent memory store.**

- `cortex.py` — writes to `conversation.jsonl` only. Nothing else.
- `freetime.py` — writes to `conversation.jsonl` only. Nothing else.
- `hippocampus.py` — reads `conversation.jsonl`, writes RAG + KAG. That's the interface.

### Change

Move the rolling RAG write from `cortex.py`/`freetime.py` into `hippocampus.py`. The hippocampus's `consolidate()` function — running each freetime Phase 1 — already writes structured KAG updates and RAG entries from its LLM call. It should also perform the rolling window dump of `conversation.jsonl` entries since last consolidation, preserving the behavior that produces long-term coherence.

`_rag_write_and_trim()` is removed from `cortex.py` and `freetime.py`. Its logic lives in the hippocampus.

### Files touched

| File | Change |
|------|--------|
| `src/runtime/cortex.py` | Remove `_rag_write_and_trim()` call and import |
| `src/runtime/freetime.py` | Remove `_rag_write_and_trim()` call and import |
| `src/memory/hippocampus.py` | Add rolling RAG write of new `conversation.jsonl` entries alongside existing LLM consolidation |

---

## Instance 3: Physiological Timeseries

### The problem

The biological simulation runs as a stateless tick — it knows the current level of every chemical and physiological signal, but has no memory of how long any signal has been at its current level. Duration of physiological states has real behavioral consequences that current-level alone cannot capture:

| Signal | Duration-blind gap |
|--------|-------------------|
| Glucose | Hypoglycemia for 10 min vs 3 hours produce very different cognitive states |
| Cortisol | Acute stress spike vs sustained elevation for 24+ hours (burnout) |
| Sleep pressure | Tired after 14h awake vs microsleep risk after 22h awake |
| Pain | Acute pain vs chronic pain — diverge emotionally after ~8h |
| Hunger (ghrelin) | Appetite vs fasting metabolism state after ~4–6h |

Currently, `run/history.jsonl` records state snapshots over time — but it is written **only by the dashboard server**, not by the sim. The sim cannot read it. It exists for visualization, not computation.

### The source of truth: `run/bio_history.jsonl`

A sliding-window newline-delimited JSON file written by the **sim engine**, not the dashboard. Appended each heartbeat tick (~60s). Capped at a rolling 48-hour window (~2880 entries). This is the sim's own record of its physiological history.

#### Entry format

Each entry is the biological state snapshot at that tick — same structure the dashboard already uses, so the migration from dashboard-written to sim-written is low cost.

```json
{"ts": 1744000000.0, "chemicals": {...}, "second_order": {...}, "third_order": {...}, "body": {...}}
```

#### What the sim gains

Duration-dependent effects can now be computed properly. Example:

```python
# How long has cortisol been above 500?
cortisol_elevated_hours = _hours_above_threshold(bio_history, "chemicals.cortisol", 500)
```

This enables SPEC-31's isolation deterioration stages to be supplemented by actual measured duration rather than inferred from level alone. It enables hunger duration, sleep deprivation elapsed time, and chronic stress onset to drive behavioral effects correctly.

#### Dashboard migration

`dashboard_server.py`'s `_history_loop()` currently writes its own snapshots to `run/history.jsonl`. After this change, the dashboard reads from `run/bio_history.jsonl` instead of writing its own copy. The dashboard becomes a reader, not a writer.

### Files touched

| File | Change |
|------|--------|
| `src/runtime/heartbeat.py` | Append state snapshot to `bio_history.jsonl` each tick; prune entries older than 7 days |
| `src/infra/config.py` | Add `BIO_HISTORY_FILE` path constant |
| `src/gateway/dashboard_server.py` | Read from `bio_history.jsonl`; remove `_history_loop()` write logic |
| `src/sim/engine.py` | Expose helper `_hours_above_threshold(history, field_path, threshold)` for duration queries |

### Decisions

1. **Window** — 7 days. At 60s ticks: ~10,080 entries × ~500 bytes = ~5MB. Negligible.
2. **Tick interval** — 60s ticks confirmed. No change needed.

---

## Future instances

As new constructs are identified that suffer from the same fragmentation problem, they are added here as additional numbered instances before implementation begins.

Candidates:
- Relationship knowledge — see SPEC-33
