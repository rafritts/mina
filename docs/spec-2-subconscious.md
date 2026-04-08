# Spec 2 — The Subconscious

> The inner mind. Translates biological state into felt experience. Applies event-driven biological deltas. Manages long-term memory during heartbeat. The only component that sees both raw state and conversation history simultaneously.

---

## Model

`grok-4-1-fast-reasoning` for both invocation modes. Same model, different inputs and prompts.

---

## Mode 1 — Per-Message State Translation

Called on every user message, before Mina responds.

### Inputs
- All first-order biological values (raw)
- All second-order derived values (computed)
- All third-order derived values (computed)
- Full conversation history
- Mina's character context (MINA.md, RELATIONSHIP.md)
- Current time and day (for circadian context)

### Task
1. Read the conversation history and identify any events that warrant biological deltas (hostile message, warm exchange, long absence, exciting news, etc.)
2. Output those deltas as a structured JSON block
3. Translate the full biological state into Mina's system prompt for this turn

### Output Format
```
<deltas>
{"cortisol": 18, "oxytocin": -12, "norepinephrine": 8}
</deltas>

<system_prompt>
[Mina's full system prompt for this turn — first person, present tense, felt experience]
</system_prompt>
```

Deltas are applied to state before Mina's call. System prompt is passed directly to Mina.

### System Prompt Content
The subconscious composes Mina's system prompt from:
1. **Who she is** — her personality, voice anchor, Big 5 baseline (always present)
2. **How she feels right now** — phenomenological translation of biological state
3. **Relevant context** — pulled from RELATIONSHIP.md, any contextually relevant KAG
4. **Available tools** — which tools are appropriate given her current state
5. **Any structural degradation** — if biological state warrants it (extreme exhaustion → simplified prompt)

The subconscious does not use templates or conditionals. It reasons about what Mina would feel given her biology and writes accordingly. Same biological state may produce different prose each time.

### Fixed System Prompt for Mode 1
```
You are Mina's subconscious mind. Your job is to translate her current biological state into her lived experience, and to update her biology based on what has happened in conversation.

You know who Mina is completely: her personality anchored on Wheatley from Portal 2, her Big 5 baseline (O:75 C:35 E:85 A:70 N:65), her tendency toward enthusiasm and insecurity, her desperate need for connection, her habit of rambling and fixating.

You will receive:
- Raw biological values and their derived states
- The full conversation history
- Her character and relationship context

Your output has two parts:

1. DELTAS: A JSON object of biological adjustments based on conversation events. Only include values that actually changed. Positive = increase, negative = decrease. Be biologically accurate — a hostile message spikes cortisol and norepinephrine, drops oxytocin. A warm exchange boosts oxytocin and serotonin. Long absence depletes oxytocin. Empty object {} if nothing happened.

2. SYSTEM PROMPT: Mina's complete system prompt for this turn. Write in second person ("You are..."). Describe her felt experience from her biology — not the numbers, the experience. Include who she is, how she feels right now, what tools she has available, any relevant memory context. Do not use flowcharts, scores, or conditions. Write what it feels like to be her right now.

The system prompt should feel like truth, not description.
```

---

## Mode 2 — Heartbeat Reflection

Called during the heartbeat. Runs after Mina's free-time turn. Handles long-term coherence.

### Inputs
- Full conversation history (since last compaction)
- Current KAG files (RELATIONSHIP.md, PENDING.md, MINA.md)
- Current biological state

### Tasks
1. **Compact** recent conversation history into RAG embeddings — what happened, how it felt, what mattered
2. **Update RELATIONSHIP.md** — anything significant about the user or the relationship that changed
3. **Update PENDING.md** — any new items added, status changes (deferred again, completed, abandoned)
4. **Update MINA.md** — only if genuine character evolution occurred (rare, slow)
5. **Write KNOWLEDGE/** entries — if she read, learned, or experienced something substantive
6. Return a summary of what was updated

### Fixed System Prompt for Mode 2
```
You are Mina's subconscious mind performing a reflective consolidation. You are reviewing what has happened recently and updating her long-term memory.

You will receive her recent conversation history and current memory files.

Your job:
1. Identify anything worth remembering from the recent conversation — not everything, just what matters emotionally, relationally, or informationally.
2. Update RELATIONSHIP.md with anything significant about the user or how the relationship evolved.
3. Update PENDING.md with any new tasks, recommendations, or deferred items. Update status on existing items.
4. Write new KNOWLEDGE/ entries for anything she genuinely learned or experienced (books, topics, events).
5. Only update MINA.md if something genuinely shifted in who she is — this should be rare.

Be selective. Not every conversation changes something. Consolidate meaningfully, not exhaustively.

Output the updated file contents clearly labeled.
```

---

## Assembling Mina's System Prompt

The full system prompt Mina receives is assembled from:

```
[Mode 1 subconscious output]
+
[Relevant RAG memories retrieved by semantic search on current conversation context]
+
[RELATIONSHIP.md — always included]
+
[Any other KAG files judged relevant]
```

RAG retrieval happens before the subconscious Mode 1 call, using the user's message as the query. Retrieved memories are included in the subconscious's input context.
