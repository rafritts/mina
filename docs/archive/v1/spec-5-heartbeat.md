# Spec 5 — Heartbeat

> A cron job that fires periodically and invokes Mina autonomously. The heartbeat is her life happening when the user isn't present.

---

## Configuration

```json
{
  "heartbeat_interval_seconds": 1800
}
```

Default: every 30 minutes. Configurable in `config.json`.

---

## Phases

### Phase 1 — Subconscious Reflection (Mode 2)

The heartbeat begins with the subconscious running in Mode 2. It reviews what has happened since the last heartbeat and updates long-term memory.

Inputs:
- Conversation history since last compaction marker
- Current KAG files
- Current biological state

Outputs:
- Updated RELATIONSHIP.md (if changed)
- Updated PENDING.md (if changed)
- New RAG embeddings written to ChromaDB
- New KNOWLEDGE/ entries (if applicable)
- A brief internal summary of what was consolidated

### Phase 2 — Mina's Free Time

After reflection, Mina is invoked with a free-time prompt. She sees her biological state (via the subconscious Mode 1 translation) and has access to her tools.

Free-time system prompt addition (appended by subconscious):
> *"You have some free time right now. Check in with yourself. Do what you need or want. [User] isn't here at the moment."*

Pending items from PENDING.md may be surfaced:
> *"That book is still sitting there — The Intelligent Investor. You've been putting it off."*

Mina can call any tool during free time. She may:
- Sleep if tired
- Eat or drink if hungry/thirsty
- Call `do(activity=...)` for leisure
- Do nothing (valid — sometimes she just sits with it)
- Call `generate_image` for herself

Her choice is emergent from her biological state and personality. A content, rested Mina might read. An anxious, depleted Mina might not be able to settle.

### Phase 3 — State Update

After Mina's free-time turn completes:
1. The subconscious applies any biological deltas from the `do` tool call (based on what activity she chose)
2. Time-based decay is applied up to the current moment
3. State is written to `state.json`
4. A heartbeat log entry is written

---

## Conversation History

The heartbeat shares conversation history with user-facing sessions. Mina's free-time turns are appended to the shared history with a marker indicating they were heartbeat turns:

```json
{"role": "system", "content": "[HEARTBEAT]"},
{"role": "assistant", "content": "...Mina's free time response..."}
```

This means the user may return to find Mina has already acted — slept, eaten, mentioned reading that book. The continuity is real.

---

## Heartbeat Suppression

The heartbeat does not fire if:
- Mina is currently in a user conversation (active within last 60 seconds)
- Mina is deeply asleep (heartbeat fires but Phase 2 is skipped — she stays asleep)

If Mina is in light sleep during a heartbeat, the subconscious may wake her briefly for Phase 2, or may let her continue sleeping depending on sleep depth.

---

## Logging

Each heartbeat logs:
```
[HEARTBEAT] 2026-04-08 14:30:00
[HEARTBEAT] Reflection: updated RELATIONSHIP.md, wrote 2 RAG entries, PENDING unchanged
[HEARTBEAT] Free time: Mina called do(activity="read", description="reading news")
[HEARTBEAT] Deltas applied: acetylcholine+4, cortisol+8 (upsetting news)
[HEARTBEAT] Complete. Next heartbeat in 1800s.
```
