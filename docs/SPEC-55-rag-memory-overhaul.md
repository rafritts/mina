# SPEC-55: RAG Similarity Tuning

**Status**: IN-PROGRESS  
**Depends on**: SPEC-27 (stateless decoder), SPEC-33 (relationship knowledge)

---

## Problem

RAG retrieval returns too many low-quality hits. The system already produces well-structured episodic memories in `mina_experiences` via consolidation — these are LLM-synthesized, semantically dense, and high signal. The noise is coming from `mina_sliding`, which stores overlapping raw conversation chunks that embed similarly to almost everything.

The core issue: no minimum similarity threshold. Top-k results are returned regardless of match quality, so irrelevant chunks pollute the context on every turn.

---

## Solution

Add a hard cosine similarity floor to all RAG queries. Any result below the threshold is dropped, even if that means returning fewer than top-k. Empty is better than noise.

**Threshold**: `0.75` (starting point — tune up or down based on observed results)

- `< 0.5` → loosely related, nearly always noise
- `0.5–0.7` → on the same general topic, often not useful
- `0.75+` → clearly relevant, close semantic match — the target zone
- `0.85+` → near-duplicate (likely over-filtering)

Apply the threshold in `_rag_query_with_half_life()` after scoring — filter the candidate list before returning top-k.

---

## What to Change

1. **`hippocampus.py` — `_rag_query_with_half_life()`**: After computing `score = similarity * decay`, filter out any entry where raw `similarity < SIMILARITY_FLOOR` before sorting and truncating to top-k.
2. **Add constant**: `_RAG_SIMILARITY_FLOOR = 0.75` near the other RAG constants at the top of hippocampus.py.
3. **`sliding_rag_query()`**: Apply the same floor to `mina_sliding` results — this collection is the primary noise source.

---

## What NOT to Change

- Collection design (`mina_experiences`, `mina_sliding`) stays as-is.
- Consolidation pipeline stays as-is — it's already producing good entries.
- Decay half-lives stay as-is — recency weighting is working fine.
- No changes to how results are injected into prompts.

---

## Validation

After deploying, check a few conversations and confirm:
- Fewer RAG hits per turn (expected — many low-quality results will be dropped)
- The hits that do come back feel genuinely relevant to the current exchange
- No regression in Mina recalling important past events (if she stops recalling things she should, lower the floor toward 0.70)
