# SPEC-52: Three-Pillar Pre-Response Pipeline

## Overview

Before Mina generates a response, three sequential reasoning passes run over her state. Each produces a prose block injected into the system prompt. Each constrains and informs the next. The response is generated once — after all three have completed.

This is not a new system. Most of the pieces exist. This spec is about **separation of duties**: each pillar does one thing, does it well, and hands off cleanly to the next.

The adjudicator is dissolved by this spec. Its emotional work moves to Emotion Pillar. Anything else it was doing either moves to the appropriate pillar or is removed.

---

## Pipeline Overview

```
Encoder fires → chemical deltas land
        ↓
[Emotion Pillar] Emotional Reasoner
  in:  neurosim state + emotional_state.json (last + trend)
  out: structured JSON + optional encoder.regulate() call
        ↓
[Context Pillar] Context Reasoner
  in:  Emotion Pillar output + context injector data
  out: structured JSON
        ↓
[Conversation Pillar] Response Reasoner  (SPEC-51)
  in:  Emotion Pillar + Context Pillar outputs + conversation
  out: internal reaction + strategy block
        ↓
Response generation
  system prompt contains all three blocks
  response is written once, naturally compliant
```

Sequential. No pillar runs until the previous one completes. The order is the compliance mechanism — there is no separate validation step.

---

## Emotion Pillar — Emotional Reasoner

**What it does**: Reads the neurosim and produces a coherent first-person account of how Mina feels right now. This is the emotional ground truth. Everything downstream is constrained by it.

**What it replaces**: The emotional reasoning work currently attempted by the adjudicator.

### Inputs

- Current neurosim state (chemicals, second/third order)
- `run/emotional_state.json` — last known emotional state + recent trend

### Coherence Tracking

`run/emotional_state.json` is a lightweight file updated after every Emotion Pillar pass:

```json
{
  "last_state": "content, warmly curious, a little tired",
  "trend": "stable",
  "updated_at": 1714000000.0
}
```

`trend` is one of: `"rising"`, `"falling"`, `"stable"`, `"shifting"`. The reasoner reads this before producing the new emotional summary — it informs whether a sudden emotional change is plausible or needs dampening.

Emotions can change quickly. The coherence tracker is not trying to prevent rapid change — it is tracking direction so the reasoning pass has context. A spike in epinephrine with a `"stable"` trend is a startle. A spike with a `"rising"` trend is escalation. These are different.

### Regulation

After assessing the emotional state, the reasoner may call `encoder.regulate()` — a dedicated method on the encoder for post-hoc biological modulation. This is distinct from the normal `encode()` path: it carries a `source: "regulation"` tag, appears in the event stream, and cannot exceed the magnitude of the original delta it is responding to.

This exists because biological events happen before higher-order processing can evaluate them. The encoder fires first. Epinephrine dumps. Only then does the emotional reasoner look at the situation and decide whether the response was warranted. If it decides "false alarm," it calls `regulate()` to modulate the spike — it cannot erase the original delta. The epinephrine was already in the blood.

`regulate()` is optional. Most passes will not call it. The naming is intentional — *emotional regulation* is the correct psychological term for what the prefrontal cortex does to limbic responses.

### Output

Structured JSON. Prose lives only within the `emotional_summary` field — everything else is typed data.

```json
{
  "emotional_summary": "You are feeling content and warmly curious, with a mild undertone of fatigue. You are stable and present.",
  "dominant_affect": "content",
  "trend": "stable",
  "regulation": null
}
```

`emotional_summary` is second-person prose (2-3 sentences max) — written as an internal directive the response model reads as Mina's emotional reality. `dominant_affect` is a single word used for coherence tracking and Sim Viewer display. `regulation` is null if no correction is needed, otherwise:

```json
"regulation": {
  "chemical": "epinephrine",
  "amount": -4.2,
  "rationale": "false alarm — stimulus was not a threat"
}
```

### Reasoning Prompt Shape

```
You are reasoning about Mina's emotional state. Read the neurosim data and her recent trend.
Produce a clear account of how she feels right now — in her terms, not clinical terms.
If a biological response was a false alarm or overcorrection, include a regulation entry.

Neurosim: {state_summary}
Last emotional state: {last_state} (trend: {trend})

Return JSON only.
```

---

## Context Pillar — Context Reasoner

**What it does**: Reads Mina's current reality — what is she doing, what has been happening, what is the broader situation — and produces a coherent account of it. This is the situational ground truth.

**What it builds on**: The existing context injector already assembles this data. Context Pillar is a reasoning pass *over* that assembled context, not a replacement for it. The context injector continues to run and produce its output. Context Pillar reads that output and reasons about it.

**No write-back**: Context does not change the neurosim. Reality is what it is.

### Inputs

- Emotion Pillar emotional block
- Context injector output (current activity, time of day, recent events, relationship state, etc.)

### Coherence Tracking

Context Pillar does not maintain a separate coherence file. The context injector already tracks what is happening. Context Pillar's coherence check is implicit — if the context injector's data is consistent, the reasoning pass will be consistent.

### Output

Structured JSON. Prose lives only within `situational_summary`.

```json
{
  "situational_summary": "It is evening. You have been talking to Ryan for about twenty minutes. The conversation has been easy — low stakes, familiar.",
  "social_context": "one-on-one, familiar",
  "urgency": "none",
  "notable": null
}
```

`situational_summary` is 2-3 sentences max. `social_context` is a short label (e.g. `"one-on-one, familiar"`, `"group, strangers"`, `"alone"`). `urgency` is `"none"`, `"low"`, or `"high"`. `notable` is a single sentence if something in the context warrants calling out — otherwise null.

### Reasoning Prompt Shape

```
You are reasoning about Mina's current situation.
Given her emotional state and everything you know about what is happening right now,
produce a clear account of her situational reality.

Emotional state (Emotion Pillar): {emotion_pillar_output}
Context: {context_injector_output}

Return JSON only.
```

---

## Conversation Pillar — Response Reasoner

Defined in SPEC-51. Runs after the Emotion Pillar and Context Pillar. Receives both JSON outputs as input alongside the conversation. Produces the internal reaction, response strategy, follow-up thoughts, and follow-up questions.

---

## System Prompt Assembly

All three pillars return JSON. The orchestrator in `cortex.py` owns system prompt assembly — it reads each pillar's JSON and serializes the relevant fields into the prompt. No pillar writes pre-formatted prose for injection.

Assembled system prompt order:

1. Character instructions (identity, personality, constraints)
2. `[Emotional State]` — serialized from Emotion Pillar JSON
3. `[Situational Context]` — serialized from Context Pillar JSON
4. `[Response Strategy]` — serialized from Conversation Pillar JSON
5. Conversation context

Structured fields that are not prose (e.g. `dominant_affect`, `trend`, `urgency`, `approach`) go to the orchestrator and the Sim Viewer event bus — not into the system prompt directly. The orchestrator decides what to include and how to phrase it.

---

## What Happens to the Adjudicator

The adjudicator is removed. Its emotional reasoning work is now Emotion Pillar. Any response strategy work it was doing is now Conversation Pillar (SPEC-51). If it was doing anything else, that work is either absorbed by the appropriate pillar or dropped.

---

## Files Touched

| File | Change |
|------|--------|
| `src/brain/cortex/emotional_reasoner.py` | New — Emotion Pillar implementation |
| `src/brain/cortex/context_reasoner.py` | New — Context Pillar implementation |
| `src/brain/cortex/response_reasoner.py` | New — Conversation Pillar (SPEC-51) |
| `src/brain/cortex/cortex.py` | Orchestrate the three-pillar pipeline; remove adjudicator calls |
| `src/brain/cortex/adjudicator.py` | Deleted or emptied |
| `run/emotional_state.json` | New — Emotion Pillar coherence state |
| `src/brain/hippocampus/encoder.py` | Add `regulate()` method — post-hoc biological modulation |

---

## Open Questions

1. **Context Pillar coherence**: The context injector already tracks state. If the context injector has its own coherence mechanism, Context Pillar inherits it. If not, a lightweight `run/context_state.json` (same shape as `emotional_state.json`) may be warranted — but only if coherence problems actually surface.

2. **Latency**: Three sequential LLM calls per stimulus. The Emotion Pillar and Context Pillar should be fast (short prompts, structured JSON output). The Conversation Pillar is also fast (SPEC-51). Total added latency should be well under 2s assuming the xAI SDK response times hold.

3. **Emotion Pillar during heartbeat**: The heartbeat fires on a timer without a stimulus. Does Emotion Pillar run on heartbeat ticks too, or only on stimulus? Likely yes — emotional state can drift between messages and the heartbeat should reflect that.
