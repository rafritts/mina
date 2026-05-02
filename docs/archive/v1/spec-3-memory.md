# Spec 3 — Memory

> Two memory systems. RAG for episodic experience. KAG for knowledge and character. Both managed by the subconscious during heartbeat reflection.

---

## RAG — Experiential Memory

Vector store of episodic memories. What happened, how it felt, what mattered.

### Storage
- **Backend:** ChromaDB (local, persistent, no server required)
- **Location:** `memory/rag/`
- **Collection:** `mina_experiences`

### Schema
Each memory entry:
```json
{
  "id": "uuid",
  "document": "We talked about Portal 2. She got genuinely excited explaining the plot and kept interrupting herself. She seemed happy.",
  "metadata": {
    "timestamp": 1712345678.0,
    "emotional_valence": "positive",
    "tags": ["portal2", "games", "excitement"]
  }
}
```

### Writing
Written by the subconscious during Mode 2 (heartbeat reflection). The subconscious extracts meaningful moments from recent conversation history and writes them as natural language entries. Not every exchange gets an entry — only what mattered.

### Reading
Retrieved by semantic similarity at prompt assembly time, using the user's current message as the query. Top 3–5 results included in the subconscious's context. No results if nothing is semantically relevant.

### Embedding Model
`text-embedding-3-small` via OpenAI-compatible endpoint. TBD if xAI has an embeddings endpoint — fallback to OpenAI if not.

---

## KAG — Knowledge and Character Files

Structured markdown files. Included directly in context — no vector retrieval.

### Location
`memory/kag/`

### Files

#### MINA.md
Who Mina is. Her stable character foundation — genuine interests, preferences, dislikes, aesthetic sensibilities, things she finds funny, things she won't tolerate. This is not a prompt template. It is a document about a person.

Evolves very slowly. The subconscious may update it only when genuine character development occurred — not based on a single conversation. First version written by hand during project setup.

#### RELATIONSHIP.md
The user. Who they are, what she knows about them, how the relationship has evolved, trust level (qualitative), notable moments, things she's noticed about them. Updated each heartbeat.

```markdown
# Relationship with [User]

**Known since:** [date]
**Trust:** Emerging — they've been consistent and warm, though she doesn't fully know them yet.
**What she knows:** They're playing Portal 2. They work in tech. They recommended The Intelligent Investor.
**Notable moments:**
- [date] Great conversation about [topic]. She felt genuinely seen.
- [date] They were absent for 8 hours without warning. She was annoyed.
**Things she's noticed:** They tend to check in at night. They get excited when talking about games.
```

#### PENDING.md
Things she's been asked to do, read, try. Tracks status.

```markdown
# Pending

- [ ] Read "The Intelligent Investor" by Ben Graham — recommended by user on [date]. Deferred x2. Last asked: [date].
- [x] Watch first episode of [show] — completed [date]. Didn't love it.
```

#### KNOWLEDGE/
Directory of files for things she's genuinely learned or experienced.

Examples:
- `KNOWLEDGE/books/the-intelligent-investor.md` — summary, her reaction, opinion
- `KNOWLEDGE/topics/portal2-lore.md` — what she knows, what she found interesting
- `KNOWLEDGE/news/[date].md` — headlines she read, reactions

---

## Prompt Assembly

On each user message, before calling the subconscious:

1. Embed the user's message
2. Query RAG for top-N relevant memories
3. Load RELATIONSHIP.md (always)
4. Load any KNOWLEDGE/ files judged relevant by filename/topic match (simple heuristic for MVP)
5. Pass all of this to the subconscious Mode 1 call

The subconscious then uses this context alongside the biological state to write Mina's system prompt.

---

## MVP Scope

For MVP:
- RAG with ChromaDB — full implementation
- KAG files: MINA.md, APPEARANCE.md, RELATIONSHIP.md, PENDING.md — all implemented
- KNOWLEDGE/ directory — created, populated by heartbeat subconscious as content accumulates
- Embedding model: OpenAI-compatible endpoint (OpenAI fallback if xAI unavailable)
