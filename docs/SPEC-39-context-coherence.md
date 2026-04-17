# SPEC-39: Context Coherence — Present-State Injection & File System Audit

## Problem

Two compounding issues undermine Mina's coherence on a per-turn basis:

### 1. Context Injection Contamination

`build_memory_context()` is a single LLM call that sees the decoder window AND RAG memories simultaneously. This means the [CONVERSATION] summary — which should be a clean account of what's actually happening right now — can be colored by retrieved episodic memories. When a user references a past event ("I really enjoyed last night"), RAG floods the context with emotional content from that event, and the context LLM blurs it into the present. Mina processes it as immediate reality rather than a referenced memory.

There is also no block that tells Mina what she is doing *right now* in present-tense, active terms. She has chemistry, she has memories, she has emotional disposition — but nothing that says "you are here, doing this, now."

### 2. File System Disorder

The runtime file layout has accumulated redundancies, orphaned files, and structural inconsistencies across three separate migrations (pre-SPEC-27, SPEC-27, SPEC-32/33). Several files believed to be active are dead. Several files that exist are never read. The `.last_user_active` file lives in the wrong place. A 5.2MB orphaned file sits in `/run/`. The legacy `RELATIONSHIP.md` persists alongside the SPEC-33 replacement.

---

## Goals

1. Split context injection into two parallel, isolated LLM calls with a hard wall between present and past
2. Add `[YOUR PRESENT STATE]` — a present-tense synthesis from the decoder window only
3. Rename blocks for clarity: [RECENT] → [RECENT CONTEXT], [HISTORY] → [HISTORICAL CONTEXT]
4. Audit and delete all orphaned, redundant, and dead files
5. Fix `.last_user_active` path to live inside `/run/` with all other runtime state
6. Remove dead code references (PENDING.md fallback, legacy RELATIONSHIP.md fallback)

---

## Current Context Injection Flow

```
build_memory_context(query, kag_context, rag_recent, rag_historical, decoder_window)
  → single LLM call sees ALL of: decoder window + RAG recent + RAG historical + KAG
  → returns: [CONVERSATION] + [RECENT] + [HISTORY]  ← all from same call, cross-contaminated
```

**Runs in parallel with:** `adjudicate_emotion()` (already isolated, no changes needed)

---

## New Context Injection Flow

Two parallel calls, hard-isolated inputs:

### Call A — Window Synthesis (decoder window only, no RAG)

**Input:** decoder_window (last N messages), current username, current user_input  
**Sees:** Nothing from RAG or KAG — only what has actually happened in the rolling window  
**Returns:**

```
[CONVERSATION]
1–3 sentences. What has happened in this conversation before the messages Mina sees directly.
Topic shifts, decisions made, things established. If she already sees the full conversation: none.

[YOUR PRESENT STATE]
2–4 sentences, present tense, active verbs only. What is Mina doing right now?
Who is she talking to? What are they in the middle of? What is the immediate conversational
context she is operating in? Ground this in the window — do not infer or speculate beyond it.
If the window is empty or this is the first message: none.
```

### Call B — Memory Retrieval (RAG/KAG, no decoder window)

**Input:** query (current user message), rag_recent results, rag_historical results, kag_context  
**Sees:** Nothing from the decoder window — only retrieved memories and knowledge  
**Returns:**

```
[RECENT CONTEXT]
(formerly [RECENT]) 1–2 sentences. Recent episodic memory relevant to this moment.
Only include if it adds something not already in [CONVERSATION]. Otherwise: none.

[HISTORICAL CONTEXT]
(formerly [HISTORY]) 1 sentence max. A dead-ringer historical fact for this specific moment.
Not thematically adjacent — only if it directly applies. Otherwise: none.
```

### Assembly Order in System Prompt

```
[IDENTITY BLOCK]          ← MINA.md + customization (unchanged)

---

[CONVERSATION]            ← Call A output
[YOUR PRESENT STATE]      ← Call A output
[RECENT CONTEXT]          ← Call B output
[HISTORICAL CONTEXT]      ← Call B output

---

[EMOTIONAL DISPOSITION]   ← adjudicate_emotion() (unchanged)

[TIME CONTEXT]            ← unchanged
[state_note]              ← appended to last user message (unchanged)
```

### Why This Works

The temporal contamination problem occurs because a single LLM call sees both "what Ryan said last night" (from RAG) and "what Ryan is saying right now" (from the decoder window) simultaneously. It cannot help but blend them. By separating the calls, `[CONVERSATION]` and `[YOUR PRESENT STATE]` are guaranteed to contain only what is actually happening — the RAG content arrives separately, clearly labeled as past context. Mina receives "here is now" and "here is then" as distinct blocks rather than a blended narrative.

---

## File System Cleanup

### Files to Delete

| File | Reason |
|------|--------|
| `/run/history.jsonl` | 5.2MB orphan — no reader in current codebase |
| `/run/conversation.json.archived` | Migration artifact — one-time migration complete |
| `/memory/kag/RELATIONSHIP.md` | Superseded by `memory/kag/relationship/ryan.md` (SPEC-33). Fallback path in code will be removed. |
| `/.last_user_active` (repo root) | Duplicate — active file is `/src/.last_user_active` |

### File to Move

| From | To | Reason |
|------|----|--------|
| `src/.last_user_active` | `run/.last_user_active` | Runtime state belongs in `/run/` with everything else. Currently scattered because `PROJECT_ROOT` resolves to `src/` during runtime. Fix `LAST_ACTIVE_FILE` path in `config.py`. |

### Dead Code to Remove

| Location | What | Why |
|----------|------|-----|
| `hippocampus.py: build_kag_context()` | `read_kag("RELATIONSHIP.md")` fallback branch | SPEC-33 migration is complete. If `relationship/ryan.md` doesn't exist, the fallback to the deleted legacy file should not exist either. |
| `hippocampus.py: build_kag_context()` | `read_kag("PENDING.md")` | File is never written anywhere in the codebase. Either implement it or remove the read. Remove for now. |
| `hippocampus.py: kag_fix_word_filter()` | "PENDING.md" in hardcoded list | Same — remove. |

### Files to Leave Alone

| File | Why |
|------|-----|
| `/run/bio_history.jsonl` | Written by heartbeat, read by dashboard — correct, intentional |
| `/run/events.jsonl` | Audit trail for dashboard — correct, intentional |
| `/run/token_stats.json` | Dashboard telemetry — correct, intentional |
| `/memory/kag/relationship/state.json` | Active relationship layer state — needed by consolidation |

---

## Decoder Window Size

Call A (window synthesis) should receive the full decoder window (currently 20 messages). This is already what the context LLM sees today — no change needed. The key change is isolation, not depth.

---

## Implementation Plan

### Phase 1 — File System Cleanup
1. Delete orphaned/redundant files listed above
2. Move `.last_user_active` to `run/` — update `LAST_ACTIVE_FILE` in `config.py`, remove old file
3. Remove dead code: PENDING.md reads, legacy RELATIONSHIP.md fallback
4. Verify nothing breaks by running tests

### Phase 2 — Context Injection Refactor
1. Add `build_window_context(decoder_window, username, user_input) -> str` to `decoder.py`
   - New LLM call, window-only inputs, returns `[CONVERSATION]\n...\n[YOUR PRESENT STATE]\n...`
2. Rename existing RAG context builder to `build_rag_context(query, kag_context, rag_recent, rag_historical) -> str`
   - Remove decoder_window parameter — it must not see it
   - Rename output blocks: [RECENT] → [RECENT CONTEXT], [HISTORY] → [HISTORICAL CONTEXT]
3. In `cortex.py run_turn()`: run both calls in parallel (alongside existing `adjudicate_emotion()`)
4. Assemble output: window_context + rag_context as the memory injection block
5. Update `[CONTEXT/INJECT]` log to reflect new structure

### Phase 3 — Verification
1. Read `logs/context_window.log` after a live turn and confirm:
   - `[YOUR PRESENT STATE]` block is present and grounded
   - `[RECENT CONTEXT]` / `[HISTORICAL CONTEXT]` blocks contain only past memory, not present narration
   - No cross-contamination between the two call outputs
2. Run full test suite

---

## Open Questions

- **[YOUR PRESENT STATE] on first message:** If the decoder window is empty (fresh conversation), the block should output `none` and be omitted from injection rather than injecting a blank section.
- **Freetime turns:** Freetime uses a different turn path. Window synthesis should still run there — freetime has its own decoder window and Mina should know she's in an autonomous moment, not a conversation.
- **Three-way parallelism:** `build_window_context`, `build_rag_context`, and `adjudicate_emotion` can all run in parallel. This should reduce per-turn latency slightly compared to the current two-call parallel setup.
