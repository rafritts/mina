# SPEC-55: RAG Memory Overhaul

**Status**: DRAFT — flag planted  
**Depends on**: SPEC-27 (stateless decoder), SPEC-33 (relationship knowledge), SPEC-45 (sliding window RAG, still TODO)

---

## Problem

RAG retrieval is currently not producing useful results in practice. The system stores and retrieves memory, but what comes back is not meaningfully influencing responses in the way lived memory should. The current approach needs rethinking from first principles.

Known symptoms (to be expanded with investigation):
- Retrieved chunks don't feel contextually relevant to the current moment
- Retrieval may be competing with or duplicating the conversation window rather than complementing it
- Chunk boundaries, embedding strategy, and collection design have not been validated against real usage

---

## Open Questions (to answer before spec is written)

1. **What is actually being stored?** What do chunks look like — are they raw message text, summaries, or structured records? What metadata is attached?
2. **What queries are being issued?** Is retrieval purely semantic similarity on the incoming message, or is there richer context being passed?
3. **When does retrieval fire?** Every turn? Only on certain triggers? Is there a threshold below which results are discarded?
4. **What does the pipeline do with hits?** How are chunks injected into context, and is the LLM actually using them?
5. **Is the problem retrieval quality, chunk design, embedding coverage, or injection format?**

---

## Candidate Directions (to evaluate)

- Replace flat similarity search with structured memory categories (episodic vs semantic vs relational)
- Store richer metadata per chunk (timestamp, participants, emotional valence, topic tags) and use hybrid search
- Switch from retrieval-at-query-time to a memory synthesis step that produces a standing "what Mina knows about this person/topic" document, refreshed periodically
- Adopt a two-tier model: sliding window RAG (SPEC-45) for recent episodes + long-term distilled knowledge base for stable facts
- Evaluate whether Qdrant collection design, vector model, or chunking strategy is the root cause before changing architecture

---

## Next Step

Audit the current RAG implementation end-to-end — storage path, chunk format, query construction, retrieval results, and injection — and identify the actual failure mode before designing a fix.
