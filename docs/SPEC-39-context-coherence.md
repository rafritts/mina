# SPEC-39: Context Coherence — Present-State Injection & File System Audit

## Problem

Two compounding issues undermine Mina's coherence on a per-turn basis:

### 1. Context Injection Contamination and Coverage Gap

`build_memory_context()` is a single LLM call that sees the decoder window AND RAG memories simultaneously. This means the [CONVERSATION] summary — which should be a clean account of what's actually happening right now — can be colored by retrieved episodic memories. When a user references a past event ("I really enjoyed last night"), RAG floods the context with emotional content from that event, and the context LLM blurs it into the present. Mina processes it as immediate reality rather than a referenced memory.

There is also no block that tells Mina what she is doing *right now* in present-tense, active terms. She has chemistry, she has memories, she has emotional disposition — but nothing that says "you are here, doing this, now."

Additionally, Mina's temporal coverage has a structural gap:

```
0 ←——————————————————————————————————————————————————→ past
[4 msgs direct]  [GAP ~50 msgs]  [RAG blurry]  [RAG historical]
```

The immediate window (4 messages) and RAG have no clean bridge. The [CONVERSATION] block was meant to fill this but is contaminated. The RAG pools use soft half-life decay with no hard time boundaries, so it's unclear what "recent" means — an event from 90 minutes ago and an event from 23 hours ago both fall into the same pool.

### 2. File System Disorder

The runtime file layout has accumulated redundancies, orphaned files, and structural inconsistencies across three separate migrations (pre-SPEC-27, SPEC-27, SPEC-32/33). Several files believed to be active are dead. Several files that exist are never read. The `.last_user_active` file lives in the wrong place. A 5.2MB orphaned file sits in `/run/`. The legacy `RELATIONSHIP.md` persists alongside the SPEC-33 replacement.

---

## Goals

1. Split context injection into two parallel, isolated LLM calls with a hard wall between present and past
2. Add `[YOUR PRESENT STATE]` — a present-tense synthesis from the decoder window only
3. Replace two fuzzy RAG half-life pools with three hard time-bucketed pools covering the full timeline
4. Rename [CONVERSATION] → [CONVERSATION RIGHT NOW] for clarity
5. Audit and delete all orphaned, redundant, and dead files
6. Fix `.last_user_active` path to live inside `/run/` with all other runtime state
7. Remove dead code references (PENDING.md fallback, legacy RELATIONSHIP.md fallback)

---

## Current Context Injection Flow

```
build_memory_context(query, kag_context, rag_recent, rag_historical, decoder_window)
  → single LLM call sees ALL of: decoder window + RAG recent + RAG historical + KAG
  → returns: [CONVERSATION] + [RECENT] + [HISTORY]  ← all from same call, cross-contaminated

RAG pools:
  rag_recent     → half-life 20 min (soft decay, no hard cutoff)
  rag_historical → half-life 48 hr  (soft decay, no hard cutoff)
```

**Runs in parallel with:** `adjudicate_emotion()` (already isolated, no changes needed)

---

## New Context Injection Flow

Two parallel LLM calls (three-way parallel with adjudicator), hard-isolated inputs:

### Call A — Window Synthesis (decoder window only, no RAG)

**Input:** decoder_window (last 20 messages), current username, current user_input
**Sees:** Nothing from RAG or KAG — only what has actually happened in the rolling window
**Returns two blocks — both are rich paragraphs, not bullet points or summaries:**

**[CONVERSATION RIGHT NOW]**
A flowing paragraph covering the live conversational moment and the immediate past
through the full decoder window. Intentionally overlaps with Mina's 4-message direct
window — this overlap is the anchor, ensuring no seam between what she reads here
and what she sees directly. The most recent exchange should be the most vivid and
specific. Further back in the window gets lighter. Present tense for the immediate
beat, past tense for what led here.

Do NOT describe emotional state, mood, affect, or how anything "lands" — that is the
adjudicator's domain. Stick to: what was said, what is happening, what has been
established. Situational facts only.

**[YOUR PRESENT STATE]**
A flowing paragraph grounded in the window. Where is Mina physically? What is she
doing? What is the immediate situation she is operating in? Active verbs, present
tense. Should feel like placing her in the room — specific physical and situational
details drawn from the window (location, proximity, activity, atmosphere).

Do NOT describe how she feels emotionally, her mood, or her internal state — the
adjudicator owns that. Stick to physical and situational facts: where she is, what
she's doing, what's around her.

**Gradient richness principle:** The closer to now, the richer the detail. The most
recent beat of the conversation is the most specific. Events from 18 messages ago
get a clause, not a paragraph.

**Critical prompt requirement — intra-window time gaps:**

Messages in the decoder window already carry `[Xm ago]` / `[Xh ago]` / `[Xd ago]`
timestamp labels on every user message (applied by `apply_ts_label()`). The window
synthesis prompt must explicitly instruct the LLM:

> "The messages below are ordered chronologically but may have large time gaps between
> them. Message N and message N+1 being adjacent does NOT mean they are close in time —
> they may be hours apart. The timestamp on each message is ground truth. A 3-hour gap
> between two messages means the conversation may have completely changed topic. Do not
> narrate across a large time gap as if it were continuous. If the most recent messages
> are on a completely different topic than earlier ones, [CONVERSATION RIGHT NOW] should
> reflect the current topic — not average across the whole window."

**Default when window is empty (first message or fresh session):**

No LLM call is made. The following is injected verbatim:
```
[YOUR PRESENT STATE]
You are hanging out in your Discord channel, sitting on the couch.
```

**Freetime turns:** Window synthesis runs identically. The decoder window reflects
whatever Mina was doing autonomously. Her present state carries forward naturally
into the next user conversation because the decoder window persists across both.

### Call B — Memory Retrieval (RAG, no decoder window)

**Input:** query (current user message), three time-bucketed RAG result sets, kag_context
**Sees:** Nothing from the decoder window — only retrieved memories and knowledge

**Gradient richness principle applies here too:** richness decreases with distance.
[RECENT CONTEXT] can be a short paragraph. [SEMI-RECENT CONTEXT] is 1–2 sentences.
[HISTORICAL CONTEXT] is a single sentence at most.

Do NOT describe emotional states, mood, or internal experience in any block — the
adjudicator owns that. Facts only: what happened, what was said, what was established.

**Returns:**

```
[RECENT CONTEXT — last 2 hours]
Short paragraph if material exists. Situational facts about what happened recently
that's relevant to this moment. Omit if nothing qualifies: none.

[SEMI-RECENT CONTEXT — 2 to 24 hours ago]
1–2 sentences. A relevant fact from the last day. Omit if nothing qualifies: none.

[HISTORICAL CONTEXT — more than 24 hours ago]
1 sentence max. A dead-ringer historical fact — not thematically adjacent, only if
it directly applies. Omit if nothing qualifies: none.
```

**The time range is part of the section header label** — it appears verbatim in
Mina's system prompt so she knows exactly how old the information in each block is.
Mina reads "[SEMI-RECENT CONTEXT — 2 to 24 hours ago]" and knows that what follows
is not right now, without having to infer it from content alone.

### RAG Time Buckets (replacing half-life pools)

Replace `_rag_query_with_half_life()` with a single query + hard timestamp filtering:

| Block | Time Range | ChromaDB filter |
|-------|-----------|-----------------|
| `[RECENT CONTEXT]` | 0 – 2 hours | `ts >= now - 7200` |
| `[SEMI-RECENT CONTEXT]` | 2 – 24 hours | `now - 86400 <= ts < now - 7200` |
| `[HISTORICAL CONTEXT]` | 24h+ | `ts < now - 86400` |

One ChromaDB query per bucket (three queries), results passed to Call B. If a bucket returns no results, that section outputs `none` and is omitted from injection.

### Full Coverage Map (After)

```
0 ←————————————————————————————————————————————————————→ past
[4 msgs direct]
[CONVERSATION RIGHT NOW — decoder window, last 20 msgs]
[YOUR PRESENT STATE — decoder window, present anchor]
                [RECENT CONTEXT — 0–2h, hard cutoff]
                            [SEMI-RECENT — 2–24h]
                                          [HISTORICAL — 24h+]
```

No gap. No contamination between present and past.

### Assembly Order in System Prompt

```
[IDENTITY BLOCK]                                    ← MINA.md + customization (unchanged)

---

[CONVERSATION RIGHT NOW]                            ← Call A output
[YOUR PRESENT STATE]                                ← Call A output
[RECENT CONTEXT — last 2 hours]                     ← Call B output
[SEMI-RECENT CONTEXT — 2 to 24 hours ago]           ← Call B output
[HISTORICAL CONTEXT — more than 24 hours ago]       ← Call B output

---

[EMOTIONAL DISPOSITION]       ← adjudicate_emotion() (unchanged)

[TIME CONTEXT]                ← unchanged
[state_note]                  ← appended to last user message (unchanged)
```

### Why This Works

The temporal contamination problem occurs because a single LLM call sees both "what Ryan said last night" (from RAG) and "what Ryan is saying right now" (from the decoder window) simultaneously. It cannot help but blend them. By separating the calls, [CONVERSATION RIGHT NOW] and [YOUR PRESENT STATE] are guaranteed to contain only what is actually happening — the RAG content arrives separately, clearly labeled with explicit time ranges. Mina receives "here is now" and "here is then" as distinct, labeled blocks rather than a blended narrative.

Hard time cutoffs replace soft half-life decay. Mina can read "[RECENT CONTEXT]" and know it means the last 2 hours — not "recent-ish depending on a scoring function."

---

## File System Cleanup

### Files to Delete

| File | Reason |
|------|--------|
| `/run/history.jsonl` | 5.2MB orphan — no reader in current codebase |
| `/run/conversation.json.archived` | Migration artifact — one-time migration complete |
| `/memory/kag/RELATIONSHIP.md` | Superseded by `memory/kag/relationship/ryan.md` (SPEC-33). Fallback path in code will be removed. |
| `/.last_user_active` (repo root) | Duplicate — active file is at path resolved from PROJECT_ROOT |

### File to Move

| From | To | Reason |
|------|----|--------|
| `{PROJECT_ROOT}/.last_user_active` | `run/.last_user_active` | Runtime state belongs in `/run/` with everything else. Update `LAST_ACTIVE_FILE` in `config.py`. |

### Dead Code to Remove

| Location | What | Why |
|----------|------|-----|
| `hippocampus.py: build_kag_context()` | `read_kag("RELATIONSHIP.md")` fallback branch | SPEC-33 migration complete. Remove fallback. |
| `hippocampus.py: build_kag_context()` | `read_kag("PENDING.md")` | Never written anywhere — remove read reference. |
| `hippocampus.py: kag_fix_word_filter()` | "PENDING.md" in hardcoded list | Same — remove. |

### Files to Leave Alone

| File | Why |
|------|-----|
| `/run/bio_history.jsonl` | Dashboard telemetry — correct, intentional |
| `/run/events.jsonl` | Audit trail for dashboard — correct, intentional |
| `/run/token_stats.json` | Dashboard telemetry — correct, intentional |
| `/memory/kag/relationship/state.json` | Active relationship layer state — needed by consolidation |

---

## Implementation Plan

### Phase 1 — File System Cleanup
1. Delete orphaned/redundant files listed above
2. Move `.last_user_active` into `run/` — update `LAST_ACTIVE_FILE` in `config.py`
3. Remove dead code: PENDING.md reads, legacy RELATIONSHIP.md fallback
4. Run tests — verify nothing breaks

### Phase 2 — RAG Bucketing
1. In `hippocampus.py`: replace `build_rag_context_dual()` with `build_rag_context_bucketed(query) -> tuple[str, str, str]`
   - Three ChromaDB queries with hard timestamp WHERE filters
   - Returns `(rag_recent, rag_semi_recent, rag_historical)`
2. Update call site in `cortex.py`

### Phase 3 — Context Injection Refactor
1. Add `build_window_context(decoder_window, username, user_input) -> str` to `decoder.py`
   - Window-only inputs, no RAG
   - Returns `[CONVERSATION RIGHT NOW]\n...\n[YOUR PRESENT STATE]\n...`
   - If window empty: return hardcoded default present state, skip LLM call
2. Refactor `build_memory_context()` → `build_rag_context(query, kag_context, rag_recent, rag_semi_recent, rag_historical) -> str`
   - Remove decoder_window parameter entirely
   - Output blocks: [RECENT CONTEXT], [SEMI-RECENT CONTEXT], [HISTORICAL CONTEXT]
3. In `cortex.py run_turn()`: run all three in parallel — `build_window_context`, `build_rag_context`, `adjudicate_emotion`
4. Assemble: `window_context + "\n\n" + rag_context` as the memory injection block
5. Update `[CONTEXT/INJECT]` log tag

### Phase 4 — Verification
1. Read `logs/context_window.log` after a live turn and confirm:
   - [CONVERSATION RIGHT NOW] and [YOUR PRESENT STATE] contain only present conversation content
   - [RECENT CONTEXT] / [SEMI-RECENT CONTEXT] / [HISTORICAL CONTEXT] are clearly past-only
   - No cross-contamination
2. Run full test suite
