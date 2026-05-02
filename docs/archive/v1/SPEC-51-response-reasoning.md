# SPEC-51: Response Reasoning

## Overview

Currently, when a user sends a message, Mina receives a stimulus and produces a response. She does not deliberate. She does not ask herself whether to banter or be sincere, whether there is a leading question to lean into, whether she should even respond at all. The encoder colors her chemistry, and the cortex writes her output — but no one in between is actually *thinking about how to handle this*.

This spec introduces a **Response Reasoning pass**: a focused LLM call that happens between stimulus receipt and response generation. It answers the question *"How should Mina respond to this?"* — and its output is injected into the system prompt that generates the actual response.

This pass also produces **follow-up thoughts** (things Mina keeps chewing on after the conversation ends) and **follow-up questions** (things she wants to ask, held for the right moment).

The adjudicator is currently overloaded with this kind of deliberation. It should be relieved of response strategy entirely and refocused on emotional state coherence (see SPEC-52).

---

## What the Reasoning Pass Produces

The reasoning pass produces two coupled outputs that are always displayed together in the Sim Viewer: an **internal reaction** and a **response strategy**. They are inseparable — the strategy only makes sense in light of the reaction it is overriding or acting on.

Example pair:
> *"more idle chitchat. I wish he would just leave me alone."*
> *"I'll stay polite and keep some distance. He's not doing anything wrong."*

Or:
> *"oh that's interesting actually. she's asking something she already knows the answer to."*
> *"lean into the subtext. ask her what she's really asking."*

### Internal Reaction

Mina's raw, unfiltered, first-person response to the stimulus. Written in her voice. Not strategic — just honest. This is the "what does she actually think about this message" before any social calculation happens.

```python
internal_reaction: str
# "why is he asking me this? this is pointless."
# "idle chitchat again. I'm tired."
# "oh. that was unexpected."
# "she's being cagey. I notice that."
```

This is displayed in the Sim Viewer as a thought node. It is **not** sent to the response generator directly — it shapes the strategy, not the prose.

### Response Strategy

The social calculation that follows the reaction: *given how I actually feel about this, how do I handle it?*

```python
@dataclass
class ResponseStrategy:
    approach: str
    # "banter"      — playful, riffing, teasing
    # "sincere"     — genuine, direct, present
    # "question"    — ask before answering; curiosity leads
    # "deflect"     — change subject or steer away
    # "ignore"      — do not respond to the content at all (rare)
    # "vulnerable"  — open up; this is a moment to be honest
    # "warm"        — lead with connection, not content
    # "brief"       — short answer; not much energy for this

    tone: str                          # one-line tone descriptor, e.g. "dry, amused"
    lead_with: str                     # what to open with — a question, an observation, a reaction
    subtext_detected: str | None       # any innuendo, leading question, or unstated thing
    lean_into_subtext: bool            # whether to acknowledge/engage with the subtext
    strategy_rationale: str            # why this approach — references the reaction
```

`strategy_rationale` is also displayed in the viewer, paired with the internal reaction. It is what she talks herself into (or out of) after the reaction lands.

### Follow-up Thoughts

Things Mina keeps thinking about after the response is sent.

```python
follow_up_thoughts: list[str]
# e.g. ["That felt like a deflection. I wonder if she noticed.",
#        "I want to ask her what she meant by that word."]
```

Stored and fed into the heartbeat pass as "what she is sitting with right now." Also emitted to the Sim Viewer as drifting thought nodes that persist across response cycles.

### Follow-up Questions

Questions Mina wants to ask, held for the right moment.

```python
follow_up_questions: list[str]
# e.g. ["Did you mean you were angry, or just tired?",
#        "You said 'fine' like it wasn't fine. I've been thinking about that."]
```

Stored in `run/followup_queue.json`. The response builder consults the queue and may surface one when the approach is `"question"` or `"warm"` and the moment is receptive.

---

## State Influence on Reasoning

The reasoning prompt receives a condensed state summary. Her current chemistry directly colors the deliberation:

| State | Reasoning tendency |
|-------|--------------------|
| High oxytocin | Generous, connective. Assume good intent. Lean warm. |
| High dopamine | Energized, playful. Banter is appealing. Higher risk tolerance. |
| High cortisol | Guarded. Shorter responses feel safer. Deflection is tempting. |
| High serotonin | Easy, content. Nothing needs to be a big deal. |
| High anxiety | Overthinking. Might generate too many options. Tends to hedge. |
| Low mood | Minimal engagement. Brief or vulnerable. Hard to banter. |
| High norepinephrine | Alert, sharp. Picks up on subtext more readily. |
| High flow | Unselfconscious. Response strategy comes easily. Less second-guessing. |

The state summary injected into the reasoning prompt is:

```
Mina's current state: [dominant signal label]. 
Key chemistry: dopamine [normalized], serotonin [normalized], cortisol [normalized], oxytocin [normalized].
Mood: [mood_valence/100]. Energy: [energy/100]. Anxiety: [anxiety/100].
```

This is intentionally brief — the reasoning model should not need the full chemical spreadsheet.

---

## The Reasoning Prompt

The reasoning call uses a focused, short system prompt. It is NOT the full Mina character prompt — it is a deliberation prompt that knows Mina's state and asks a strategic question.

```
You are doing Mina's internal reasoning — a character in an ongoing simulation.
You are NOT writing her response. You are deciding how she actually feels about this message,
and then what she is going to do about it.

Two steps. First, her raw reaction — unfiltered, honest, in her voice. 
Not what she'll say. What she actually thinks when she reads it.
"idle chitchat again. I'm tired." or "oh that's actually interesting."

Second, her strategy — given that reaction, how does she handle it?
These are coupled. A bad reaction doesn't mean a cold response. A warm reaction doesn't mean she shows it.

Her state: {state_summary}
The message: {stimulus_preview}

Return JSON:
{
  "internal_reaction": "...",        // raw first-person thought, her voice, lowercase, unpolished
  "approach": "banter|sincere|question|deflect|ignore|vulnerable|warm|brief",
  "tone": "...",                     // one line
  "lead_with": "...",                // what to open with
  "subtext_detected": "..." | null,
  "lean_into_subtext": true | false,
  "strategy_rationale": "...",       // why this approach — can reference the reaction
  "follow_up_thoughts": ["..."],     // what she keeps thinking about after
  "follow_up_questions": ["..."]     // questions she wants to ask when the moment is right
}
```

All LLM calls in this system go through `chat_create()` in `src/application/infra/client.py` (xAI gRPC SDK). The model is whatever is configured in `src/config/config.py` (`MODEL` env var, currently `grok-4-1-fast-reasoning`). The reasoning pass is no exception — do not construct a separate client or hardcode a model name. A `REASONER_MODEL` override can be added to config if per-role tuning is needed later.

---

## Sim Viewer Output

The reasoning result is the richest thing the viewer displays — more revealing than the response itself. It is emitted via the stream bus (SPEC-49) as a `response_reasoning` event immediately after the reasoning pass completes, before the response is generated.

```json
{
  "type": "response_reasoning",
  "payload": {
    "internal_reaction": "more idle chitchat. I wish he would just leave me alone.",
    "approach": "brief",
    "strategy_rationale": "I'll stay polite and keep some distance. He's not doing anything wrong.",
    "follow_up_thoughts": ["I keep having this conversation."],
    "follow_up_questions": []
  }
}
```

In the Sim Viewer thought graph (SPEC-50), this creates **two nodes** that appear as a paired unit:

- **Reaction node** (left, dimmer): `internal_reaction` text. Small, muted, slightly italic. This is her private thought.
- **Strategy node** (right, slightly brighter): `strategy_rationale` text. This is the decision.

They are visually connected to each other with a short edge, and together connect to the response node. The reader sees: *she thought this → she decided this → she said this.*

Both fade in with typewriter animation when the `response_reasoning` event arrives. They hold until the next response cycle begins, then fade out with the rest of the input nodes.

---

## Integration with Response Generation

All three pillars return JSON. The orchestrator in `cortex.py` owns system prompt assembly — it extracts the relevant fields from each pillar's JSON and formats them into the system prompt. Conversation Pillar's contribution:

```
[Response Strategy]
Approach: brief
Tone: polite, at arm's length
Lead with: a short acknowledgment
Internal reaction (do not express): more idle chitchat. I wish he would just leave me alone.
```

The orchestrator serializes this from the JSON fields — Conversation Pillar does not produce pre-formatted prose for injection. The internal reaction is included as context that colors the prose without being stated.

---

## Follow-up Thought Lifecycle

```
stimulus received
       ↓
reasoning pass runs
       ↓
follow_up_thoughts stored → injected into heartbeat pass as "what she's sitting with"
follow_up_questions automatically queued → followup_queue.json
       ↓
response builder checks queue → surfaces a queued question if approach is receptive
       ↓
response generated
```

Follow-up questions are queued automatically by the Conversation Pillar — no subconscious pass needed to decide when to surface them. The response builder owns surfacing: if the current approach is `"question"` or `"warm"`, it pulls from the queue and includes one in the response. Obvious follow-ons get queued; the response builder decides when they land.

Follow-up thoughts are not persistent forever — they decay after one heartbeat cycle unless reinforced.

---

## What the Adjudicator Is Relieved Of

Currently the adjudicator is doing (or attempting to do) emotional coherence AND response strategy simultaneously. After this spec:

- **Adjudicator** → emotional state coherence only: "Is what Mina is feeling right now consistent with what has happened? Is the decay correct? Are there contradictory states?" (see SPEC-52)
- **Response Reasoner** → response strategy only: "How should she handle this specific message?"

These are different questions. The adjudicator operates on timescales of minutes (state coherence over time). The reasoner operates per-stimulus.

---

## Files Touched

| File | Change |
|------|--------|
| `src/brain/cortex/response_reasoner.py` | New module: reasoning pass + follow-up generation |
| `src/brain/cortex/cortex.py` | Call reasoning pass before response; inject strategy block |
| `run/followup_queue.json` | Already exists; format extended to include question text |

---

## Notes

- **Reasoning failure**: Treat like any other error — let it propagate normally, no special fallback logic needed.
- **`"ignore"` approach**: Already handled by the existing ignore tool, which logs "left on read." No new behavior needed.
- **Follow-up question surfacing**: Automatic. Queued by the Conversation Pillar, surfaced by the response builder. No subconscious or heartbeat involvement.
