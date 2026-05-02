# SPEC-58 — Memory Seeding (RAG/KAG)

**Status:** DRAFT  
**Priority:** Medium

## Problem

Mina starts every new session with no memories. RAG and KAG are populated entirely by lived experience — consolidation runs during freetime, relationship compaction runs over time. For a fresh install or a new relationship, she has nothing to draw on. There is also no way to bootstrap her with known facts about a person, the world, or herself beyond what is hardcoded in the KAG knowledge files.

## Goal

A seeding mechanism that lets an operator pre-populate RAG and KAG with authored memories before any conversation takes place, or inject notable memories retroactively without needing to synthesize them through lived experience.

## Scope

- **RAG seeding** — write episodic memories directly to the hippocampus RAG store, bypassing consolidation. These should be structurally identical to what `consolidate()` produces so they age and query correctly.
- **KAG seeding** — write structured knowledge entries (facts about people, places, persistent truths) directly into the KAG store.
- **Format** — likely a seed file (JSON or YAML) that an operator can author and load at startup or on-demand via an admin endpoint.
- **Idempotency** — seeding the same file twice should not duplicate entries.

## Open Questions

- Should seeds have a different provenance tag than consolidation-generated memories, or be indistinguishable?
- Should RAG seeds be time-stamped to a specific simulated past date, or just inserted as "old" memories?
- Is there a CLI command, an admin endpoint, or both?

## Non-Goals

- Automated memory generation from external sources (scraping, imports).
- Editing or deleting existing memories (separate concern).
