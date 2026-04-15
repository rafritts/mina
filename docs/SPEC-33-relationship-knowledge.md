# SPEC-33: Relationship Knowledge

## Status: Stub

The hippocampus consolidation prompt instructs the LLM to append to RELATIONSHIP.md after each freetime cycle. In practice this produces an unbounded log of Mina's freetime activities with almost no information about Ryan.

Two problems:
1. **Wrong content** — RELATIONSHIP.md should describe Ryan: who he is, his patterns, what he cares about. Not what Mina did while he was absent.
2. **Unbounded growth** — append-only with no summarization or pruning.

This spec will redesign RELATIONSHIP.md as a living profile of Ryan, updated by the hippocampus using the full conversation history made available by SPEC-32. To be written after SPEC-32 is implemented.
