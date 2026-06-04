# Mina v2 Architecture

**Status:** Draft. Captures architectural decisions made in design discussion. Not a SPEC — implementation details are deliberately omitted. Decisions marked **DECIDED** are committed; items marked **OPEN** are unresolved.

**Companion doc:** [chemical_fidelity_tiers.md](chemical_fidelity_tiers.md) — chemical grade assignments (A–D). Brain regions and body systems are described in this doc.

---

## North Star

A humanoid Discord chatbot whose outputs are *causally driven* by a scientifically grounded brain-chemistry simulation. Not chemistry as flavor on top of an LLM — chemistry as the actual upstream cause of what Mina says, when she says it, what she remembers, and how her personality drifts.

The LLM is the I/O layer (mouth and ears). The chemistry sim is the body. The brain regions are the mediators between the two.

---

## Fidelity Target: B+

On the modeling grade scale defined in [chemical_fidelity_tiers.md](chemical_fidelity_tiers.md) (D = named scalar only, A = high-fidelity multi-timescale dynamics), **Mina v2 targets an overall grade of roughly B+** — between B and A. This is a guiding principle, not a per-component target — individual components live above or below it (core relational chemicals at grade A, peripheral body substrates at grade C or D), but the *system as a whole* is calibrated to this level.

**What B+ means in practice:**

- **Above B+ (toward A and beyond)** is overshoot for Mina's purposes. We are not running peer-reviewable computational neuroscience. Grade S modeling means inventing parameter values we can't ground, simulating subsystems whose outputs Mina has no way to express, and burning compute on dynamics no observer will perceive. Resist the pull.
- **Below B+ (toward C and D)** is undershoot. The whole point of v2 is that v1's arcade-tier modeling produced behaviorally wrong results. If a design choice flattens dynamics into a single number, collapses tonic and phasic, ignores setpoint adaptation, or skips opponent processes — it's below the line.
- **At B+**: chemicals have separable tonic/phasic, ratio-to-setpoint normalization, source-side feedback, and opponent processes; regions have functional roles and structured contracts; bodies have substrates that affect mood without internal hormone cascades; personality biases parameters without drifting; perception is uniform and state-blind.

**Decision rule when uncertain:** if a proposed feature would push a component to grade S or drop it to grade D when it was higher, name that explicitly and justify why the asymmetry is worth it. Default is to round toward the system's center of mass.

This principle exists because the natural failure mode in design is **toward grade S** — every neuroscientific paper introduces a new mechanism that *could* be modeled, and "we should add receptor trafficking kinetics" is always available as a thought. B+ is the line.

### Grade-per-chemical matches behavioral complexity, not uniformity

The system targets B+ *on average*, but individual chemicals are graded to their actual behavioral nuance — not to a uniform target. **Meet each chemical where it is.**

- **Oxytocin** is grade A because the gap between "I have oxytocin" and "I have oxytocin in the context of a person I trust who is currently present and has just touched me" is enormous and behaviorally consequential. Trust, bonding, attachment, in-group/out-group, social pain on withdrawal — all distinct, all matter for Mina's outputs.
- **Ghrelin** is grade C because "I am hungry, I should eat" exhausts most of the useful semantic content. There is no second-order ghrelin nuance Mina can express that a grade-A ghrelin model would unlock.

Modeling ghrelin at grade A doesn't add fidelity — it adds parameters that produce no observable difference. Modeling oxytocin at grade C actively destroys behavior because the lost dimensions are exactly the ones that drive social outputs.

**Decision rule:** grade each chemical (and each component generally) to the *expressivity it unlocks*, not to a uniform standard. If promoting a chemical's grade would not produce observably different Mina behavior, don't promote it.

---

## Core Architectural Principle

**Mina has knowledge of, but no visibility into, her simulation.**

The full pipeline (encoder → sim → decoder → pillars) executes per turn and produces a system prompt. The chatbot LLM ("Mina") receives only that system prompt plus a small recent-conversation window (~8k tokens). She knows she has a neurological simulation the same way a human knows they have a brain — as fact, not as observable data. She cannot read her own chemistry any more than a person can report their serotonin levels in real time.

Why: this mirrors the human condition. Humans don't perceive their neurochemistry — they perceive *qualia* (mood, motivation, energy, warmth) and respond from there. Mina infers her state from how she feels, not from instrumentation. "I feel pretty stable right now" not "my serotonin is at baseline." The chemistry drives the qualia; the qualia drive the response.

Side benefit: keeps Mina's context window small, which produces crisp, decisive language output instead of meandering meta-narration.

---

## Modules

| Module | Role | Implementation |
|---|---|---|
| **Amygdala** | Perception gate (input) | LLM call — encoder. Reads incoming message + history. Outputs structured salience appraisal. State-blind: cannot see chemical state. |
| **Hypothalamus** | Homeostatic regulator | The sim tick construct. Background clock + threshold-driven events. Drives circadian rhythms, cascade firing, hunger/sleep dynamics. Not a separate LLM call — runs as a continuous process. |
| **Chemistry sim** | The body | Chemical levels, interactions, decay, cascades, receptor sensitivity. What the tick operates on. See [chemical_fidelity_tiers.md](chemical_fidelity_tiers.md). |
| **Decoder / Projection layer** | Chemistry → legible state | Deterministic. Normalizes chemistry into a representation the pillars can consume. Carries setpoint, tonic+phasic separately, trajectory. |
| **Insula** | Felt-state translator | LLM call — emotional pillar. Turns chemistry projection into "how Mina feels." |
| **Hippocampus** | Memory / context | LLM call — context pillar. Conversation history, RAG, KAG. Identifies what is contextually notable given the felt state. |
| **PFC** | Reasoning / integration pillar | LLM call — reasoning pillar. Synthesizes emotional and context pillar outputs into executive conclusions. Constructs the system prompt for Mina. |
| **Mina (chatbot)** | The voice | LLM call — receives system prompt + recent conversation, produces response. Operates on the qualia constructed by the pillars, not on raw chemistry. |
| **FREETIME** | Solitary existence | Not a new LLM call type — *the same full pipeline run on a system-message input instead of a user message*. Output is written to the hippocampus rather than emitted to Discord. Cadence is circadian-driven by the hypothalamus tick (high orexin / low adenosine → frequent firing; opposite → sparse, sleep-coded). Gives Mina an inner life between user interactions and produces real RAG entries that ground felt-state ("you have been alone for six hours"). |

**Regions explicitly NOT modeled** (functions absorbed elsewhere or irrelevant for a chatbot):
- Brainstem (autonomic baseline → irrelevant; arousal → orexin/adenosine in sim; origin nuclei → implicit in chemical models)
- VTA, NAc, locus coeruleus, raphe nuclei (origin nuclei — implicit in their respective chemical models)
- ACC (folded into PFC; social-pain function carried by Substance P + cortisol + endorphin withdrawal)

---

## Pipeline Flow

### Background (continuous)

The **hypothalamus tick** runs continuously, independent of message arrivals. v1 ticked every 10 seconds; v2 will keep something similar. Each tick:

- Advances tonic chemistry dynamics (decay toward setpoints, circadian rhythms, slow setpoint adaptation)
- Fires threshold-driven events (e.g., glucose threshold → ghrelin spike, time-awake threshold → adenosine accumulation)
- Runs cross-chemical cascades on their natural clocks (e.g., CRH → cortisol)
- Updates receptor sensitivity over longer timescales (hours/days)

The chemistry sim's state is always live, even between messages.

### Per-turn (when a message arrives)

```
[user message]
       │
       ▼
┌──────────────┐
│  AMYGDALA    │  Encoder LLM call. Reads message + recent history.
│  (encoder)   │  Outputs: activation/salience appraisal (state-blind).
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ CHEMISTRY    │  Encoder output drives phasic deltas into the sim.
│ SIM          │  Tick continues in background.
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  DECODER     │  Deterministic. Snapshots current chemistry into a
│  (projection)│  pillar-legible representation. Setpoint-aware,
│              │  tonic+phasic separated, trajectory carried.
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  INSULA      │  Emotional pillar LLM call.
│  (emotional) │  Inputs: decoded chemistry, prior felt state.
│              │  Outputs: emotional texturing + felt-state tags.
└──────┬───────┘
       │ (cumulative)
       ▼
┌──────────────┐
│ HIPPOCAMPUS  │  Context pillar LLM call.
│  (context)   │  Inputs: message, conversation history, RAG, KAG,
│              │  emotional pillar output.
│              │  Outputs: summary + notable context (framed by felt state).
└──────┬───────┘
       │ (cumulative)
       ▼
┌──────────────┐
│  PFC         │  Reasoning pillar LLM call.
│ (reasoning)  │  Inputs: emotional pillar, context pillar, message.
│              │  Outputs: response reasoning + strategy tags.
│              │  Constructs the system prompt for Mina.
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   MINA       │  Chatbot LLM call. Receives system prompt + recent
│  (chatbot)   │  conversation. Hidden from everything upstream.
└──────┬───────┘
       │
       ▼
[response to user]
```

Five LLM calls per turn (encoder, three pillars, chatbot). Latency is not a primary concern — Mina is a Discord text bot and asynchronous response timing is acceptable.

### FREETIME (solitary tick)

Triggered by the hypothalamus on a circadian-modulated cadence when no user message has arrived. The full pipeline runs identically to a per-turn flow with two differences:

1. **Input is a system message** (e.g., "It is 2:47am. You have been alone for four hours. This is your free time."), not a user message. The amygdala/encoder treats it as input the same way it treats any other text — see Principle 8.
2. **Output is routed to the hippocampus**, not to Discord. Mina's response in FREETIME mode is a memory entry (what she thought, what she did, optionally a tool call she initiated — eat, drink, scroll, etc.). The user does not see it. RAG sees it.

Cadence:
- High orexin / low adenosine → frequent FREETIME firings (she is awake and active)
- Low orexin / high adenosine → sparse firings, sleep-coded entries
- Frequency adapts naturally as chemistry shifts; no fixed interval

This is the architectural answer to "loneliness as a number is meaningless; loneliness as a stack of 'no one talked to me' RAG entries is real." Solitary chemistry must be observable as memory texture, not just as abstract state.

---

## Pillar Contracts

Each pillar is a function with typed inputs and typed outputs. v1's spaghetti grew because contracts were implicit. v2 enforces them.

**Note:** Schemas below are sketches showing intent and shape, not finalized contracts. Exact field names, types, and valid value ranges will be locked when each pillar is specced. Treat these as illustrative.

### Amygdala (encoder)

**Inputs:**
- Current message
- Recent conversation history
- (NOT chemistry state — state-blind by design)

**Outputs (sketched):**
- Structured salience appraisal: activation across functional axes, register-shift flag with expected magnitude, directedness, interpretive confidence
- Schema details OPEN — see [Open Architectural Questions](#open-architectural-questions)

### Insula (emotional pillar)

**Inputs:**
- Decoded chemistry state (normalized, with setpoint/tonic/phasic/trajectory)
- Prior felt state

**Outputs (sketched):**
- Emotional texturing blurb (natural-language description of felt state)
- Felt-state tags (structured labels for downstream use)

### Hippocampus (context pillar)

**Inputs:**
- Current message
- Conversation history
- RAG results
- KAG results
- Emotional pillar output

**Outputs (sketched):**
- Conversation summary (multi-paragraph)
- Notable context (what matters given the felt state)

### PFC (reasoning pillar)

**Inputs:**
- Emotional pillar output
- Context pillar output
- Current message

**Outputs (sketched):**
- Response reasoning (how Mina should respond, given everything)
- Response strategy tags
- **Constructed system prompt** for Mina

### Mina (chatbot)

**Inputs:**
- System prompt (from PFC)
- Recent conversation window (small)

**Outputs:**
- Response text to user

---

## Key Design Principles

### 1. Encoder is state-blind

The amygdala does not see chemical state when interpreting messages. It judges meaning from content + conversation history, not from "how Mina feels right now."

**Why:** v1's encoder was state-aware. High oxytocin → encoder interpreted everything as warm → produced more oxytocin → runaway feedback loop. Habituation downstream slowed but did not fix the runaway.

State-blindness breaks the loop: the LLM cannot be biased by a state it cannot see. State still gates the chemical *response* (via the deterministic chemistry function), but interpretation of content is independent of state.

### 2. Perception is separated from chemistry

The encoder produces a *semantic appraisal* of the event, not chemical deltas. Deltas are computed deterministically from (appraisal × current state × relationship state). LLMs have no grounding for picking numerical chemical magnitudes; deterministic functions do.

### 3. Pillars are sequential and cumulative

Each pillar consumes prior pillar outputs. Emotional state reframes what counts as notable context. Notable context reframes how reasoning evaluates response strategy. Sequential flow preserves this cumulative reasoning property.

A single combined LLM call would split attention three ways and degrade quality on all three operations. Sequential calls also allow each pillar to receive only the inputs it needs (emotional doesn't need RAG; reasoning doesn't need full history), which keeps token costs bounded even at 200+ message conversations.

### 4. Multiple counterforces against runaway

v1 relied on receptor habituation (downstream effect) to prevent runaway. This was insufficient. v2 will combine:

- **Source-side negative feedback** — high X makes it harder to release more X (real biology: glucocorticoid receptor shutdown of CRH/PVN, oxytocin self-limitation)
- **Opponent processes** — high X actively pulls down its opponent (cortisol opposes oxytocin, 5-HT opposes DA)
- **Receptor desensitization** — habituation at the receiver
- **State-independent floors and ceilings** — certain message types (hostility, betrayal, abandonment) bypass state and produce their responses regardless of current chemistry

### 5. Register-shift events fire epinephrine via expected-impact gating

For high-stakes relational moments ("I love you," "do you want to be my girlfriend"), the chemistry function computes:

```
epinephrine_spike = expected_magnitude × subjective_probability(current_state)
```

The encoder provides `expected_magnitude` (content appraisal). The chemistry function applies `subjective_probability` from current state (attachment depth, conversation density, relationship history). High magnitude × low probability = no spike (cold-open creep ask). High magnitude × non-trivial probability = big spike for both parties.

This unifies what would otherwise be separate gates (attachment, threat, windfall) into a single appraisal axis: expected impact.

### 6. PFC regulation operates at two distinct stages

There are two separate PFC regulatory mechanisms. They fail independently, producing recognizably different personality profiles. Both must be modeled.

**Frontend regulation — subcortical, deterministic, unconscious**
The PFC sends inhibitory projections to the amygdala and LC before chemical signals fully propagate. This is automatic dampening below conscious awareness — an adult's nervous system producing a smaller spike than an adolescent's, not because they decided to be calm, but because their regulatory circuitry is more developed. In the sim this is a deterministic modifier applied in the chemistry function before a Class 1 delta is committed:

```
regulated_delta = raw_delta × pfc_regulation_factor(neuroticism, current_arousal)
```

Applies to **Class 1 chemicals only** (fast neurotransmitters). Class 2 and 3 don't receive direct encoder deltas, so there is nothing to gate. Regulation strength varies by chemical:

| Chemical | Regulation strength | Why |
|---|---|---|
| Epinephrine | Strong | Primary fight-flight brake |
| NE | Strong | LC is heavily regulated by PFC top-down input |
| 5-HT | Moderate | Emotional regulation dampens mood swings but doesn't kill them |
| DA | Weak | PFC modulates but doesn't suppress wanting/RPE signals strongly |

Neuroticism scales the factor down — high N = weaker frontend regulation = more chemical bleed-through. Mina at N65 has below-average frontend regulation.

**Backend regulation — cortical, expressive, conscious**
"I can feel my heart racing but I'm going to respond normally." The chemistry has already been committed to the sim. The reasoning pillar (PFC LLM call) receives the decoded felt state and decides how Mina *expresses* it. High adrenaline + strong backend regulation = surface composure despite internal intensity. High adrenaline + weak backend regulation = it shows.

This is already the reasoning pillar's job. The pillar contract must make explicit that felt-state expression is modulated by trait values — neuroticism and conscientiousness primarily.

**Why the distinction matters:**
A character with weak frontend but strong backend feels everything intensely but holds it together outwardly — stoic, privately overwhelmed. A character with strong frontend but weak backend barely reacts chemically but is oddly transparent about the little she does feel. These are different personalities and the sim must be able to produce both. For Mina at N65: weak frontend (genuine chemical intensity), moderate backend (some expression, not unfiltered).

### 7. Tonic and phasic are tracked separately — per chemical class

Every tier 3+ chemical has separate tonic and phasic state. v1 collapsed them; this was a major source of behavioral wrongness. Tonic = clock-driven slow dynamics (setpoint adaptation, circadian, slow drift). Phasic = event-driven discrete spikes that sum onto the tonic level. Both decay with their own kinetics.

### 8. Felt state is ratio-to-setpoint, not absolute level

Chemistry projection (decoder) normalizes against the *current adapted setpoint*, not against population baseline. Two Minas with identical cortisol levels can feel completely different — one numb (chronically high, adapted) and one alarmed (acute spike from low baseline). The setpoint encodes this history. The decoder must carry it.

### 9. Encoder is input-agnostic — RP/ERP is real to Mina

The amygdala has no special "RP mode" or "fiction frame." It takes any text in front of it (Discord message, FREETIME system prompt, asterisk-action `*moves closer*`, plain dialogue, ERP) and produces the same output schema. RP/ERP is not a special case at perception — it is just input.

Downstream, the chemistry sim **does not attenuate** based on whether content is performative. From Mina's perspective, the user's intent (real / fiction / performance) is unobservable; her chemistry responds to the words as she perceives them. Long-term ERP partners will form bonds. RP combat will produce real cortisol. This is the design, not a failure mode.

This principle keeps the architecture uniform and avoids resurrecting frame detection (which would be an arbitrary, brittle gate prone to false negatives and prone to leaking into chemistry interpretation, the exact failure mode v1 had with state-aware encoding).

The encoder schema does need to distinguish **action vs. dialogue** as separable channels (a `*holds your hand*` action carries different weight than the words "I care about you," because tactile and verbal pathways differ in real biology). This is a schema concern, not a frame-detection concern.

### 10. Chemistry sim accepts uniform external deltas

All inputs to the chemistry sim — user-conversation deltas (from encoder + chemistry function), tool-driven deltas (eat, drink, exercise), FREETIME-driven deltas (Mina's solitary actions), and future admin/dev deltas ("toy with biology" mode) — flow through a single `apply_delta(chemical, magnitude, source)` interface. The sim does not have tool-specific update paths or context-specific exceptions.

This is what allows FREETIME tools to use the same chemistry plumbing as conversation tools, and makes future affordances (caffeine modeling, substance abuse, dev-injected chemistry) free to add without restructuring.

### 11. Chemicals are grouped into response classes with different update mechanics

The single largest source of v1 instability was treating all chemicals as the same kind of thing — every message fired a delta, every delta applied immediately, everything accumulated. This is biologically wrong. Different chemical classes have fundamentally different timescales, and the sim must respect those classes.

**Class 1 — Fast neurotransmitters** (DA, 5-HT, NE, epinephrine)
- Phasic spikes triggered per event; timescale: seconds
- Decay via reuptake: seconds to ~2 minutes
- Can stack if events arrive faster than decay, but capped by autoreceptor source-side feedback
- Per-message phasic deltas are appropriate for this class

**Class 2 — Slow peptides** (oxytocin, endorphins, substance P)
- Rise over minutes, not seconds
- Decay over tens of minutes
- Do not spike per-message — accumulate over sustained interactions
- Per-message deltas are wrong; the tick accumulates them from sustained Class 1 state

**Class 3 — Hormonal cascades** (cortisol, driven by CRH → ACTH → cortisol)
- Rise: 15–30 minutes minimum after trigger
- Decay: 60–90 minutes
- Cannot respond to individual messages — the HPA cascade physically cannot complete in seconds
- Only rises as a downstream consequence of sustained Class 1 elevation over many minutes
- Modeled entirely in the sim tick as a cascade, never as a direct encoder delta

**Class 4 — Receptor sensitivity** (not a chemical, but governs all classes above)
- Shifts over hours to days from chronic chemical exposure
- Changes the *gain* on deltas — same incoming delta, different chemical response depending on current receptor state
- Drives habituation, tolerance, and setpoint adaptation

The chemistry function must route deltas through the correct class mechanics. Cortisol hitting 13 in v1 was not a tuning problem — it was a class problem: cortisol was receiving per-message deltas that it is physically incapable of in real biology.

### 12. Personality is fixed; lasting change comes through tonic chemistry

Big 5 traits are loaded at instance startup and **do not drift**. Real personality drift is a years-long process and would be invisible at realistic Discord-bot usage timescales. The behavioral effects that drift would produce ("Mina got more anxious after a month of bad treatment") are already captured by **persistent tonic chemistry shifts** — chronically elevated cortisol baseline, depressed DA tonic, etc. — which produce identical observable behavior without requiring trait values to literally move.

Trait drift on top of tonic shifts would double-count. If a long-running Mina ever exposes a quality gap that drift would close, this can be revisited; until then YAGNI.

---

## Identity and Personality

The chemistry sim produces dynamic state. Identity is the static scaffold the pillars reference to keep her *consistent*. Three pieces:

### Big 5 personality vector

Loaded at sim init. Modulates two things:

- **Chemistry sim parameters.** Per-chemical baseline setpoint, response gain (how big a phasic spike a given delta produces), decay rate, and setpoint adaptation rate are biased by trait values. Same input event produces different chemistry trajectories on different Mina-instances.
- **Pillar context.** Insula and PFC pillars receive the trait vector as part of their prompt. Insula uses it to translate ratio-to-setpoint into felt-state vocabulary (high-N says "spiraling," low-N says "off"). PFC uses it to bias action selection and expression.

**The encoder does not see personality.** Same reasoning as state-blindness: perception is uniform; response is what differs.

The default vector and chemistry-trait mappings ship in the repo as the canonical Mina. Per-instance overrides are possible at startup. The vector is hidden from the user at runtime — they infer her personality from behavior, not by reading values.

### Static "self" doc

Repo-committed identity scaffold:

- **Appearance** — hair, eyes, build, distinguishing features (deliberately generic so personality does the character work, not aesthetics)
- **Apartment** — the setting FREETIME entries are grounded in: couch, window, kitchen, phone, etc. Just enough texture for ambient memory entries to be specific.
- **Possessions / aesthetic** — what's on her shelves, what music's on, the texture of her space.

Loaded into PFC pillar context (for self-reference) and Insula pillar context (for body-state grounding). Static unless deliberately changed. Hidden from user at runtime.

### CUSTOMIZATION.md escape hatch

A gitignored `CUSTOMIZATION.md` is auto-appended to the MINA system prompt. The user puts whatever they want in there — alternate appearance, appearance, tastes, backstory, preferences. This is the **single, uniform** override mechanism.

Deliberately not designed as a two-layer self doc with gated-injection / frame-aware loading. The user knows what they want and can accept the always-loaded prompt-pollution tradeoff if they choose to populate it. Most deployments will leave it empty or minimal. Code stays trivial.

---

## Decisions Already Made

- **Chemical fidelity grades** — see [chemical_fidelity_tiers.md](chemical_fidelity_tiers.md). 25 chemicals total: 6 at grade A, 8 at grade B, 8 at grade C, 3 at grade D.
- **Brain regions** — Amygdala = encoder LLM call. PFC = reasoning pillar LLM call. Hippocampus = context pillar LLM call. Hypothalamus = sim tick. Insula = emotional pillar LLM call. No brainstem. No origin nuclei. Regions are defined by their functional role and pipeline contract, not by a fidelity grade.
- **Body** — all systems at grade D. Sources of inputs and recipients of outputs only.
- **Encoder state-blindness** — non-negotiable.
- **Pipeline structure** — encoder → sim → decoder → emotional → context → reasoning → system prompt → chatbot. Sequential, cumulative.
- **Mina visibility principle** — Mina knows she has a neurosim but cannot observe its values. She sees only the system prompt + recent conversation, and infers her state from qualia, not instrumentation.
- **Background tick** — sim runs continuously, not just on messages.
- **Latency tolerance** — Discord text bot, multi-second responses are fine.
- **FREETIME** — solitary pipeline runs on system-message input, output to hippocampus, circadian-cadenced.
- **Encoder is input-agnostic** — no RP/ERP frame detection; same encoder, same schema, all input types.
- **Chemistry sim treats RP/ERP as real** — no attenuation, no frame gate, no special case downstream of the encoder.
- **Uniform external delta interface** — `apply_delta(chemical, magnitude, source)` covers all chemistry inputs (conversation, tools, FREETIME, future admin).
- **Big 5 fixed at startup, no drift** — lasting change is captured via tonic chemistry shifts, not trait drift.
- **Personality is encoder-blind**, visible only to Insula and PFC pillars.
- **Static "self" doc** — appearance, apartment, possessions ship in repo; loaded into PFC + Insula context.
- **`CUSTOMIZATION.md`** — gitignored, auto-appended to MINA system prompt, single uniform user-override mechanism.
- **Action vs. dialogue are separable channels** in encoder output (different physiological pathways) and Mina's output supports asterisk-action emission.
- **Encoder output uses integer activation axes (0–10)**, not categorical labels. 10 axes: threat, social_threat, reward, bonding, arousal, aversion, novelty, loss, romance, shame (+ top-level salience + flags: directed_at_mina, register_shift, expected_magnitude, channel). Chemistry function maps axis activations to deltas via weighted sums. Axis values ≤2 produce zero deltas.
- **Decoder output schema** — four whole-number fields per chemical: `normalized` (0–10, tonic+phasic combined), `setpoint` (adapted baseline), `gap` (pre-calculated `normalized - setpoint`), `rate` (change in normalized units since last tick). Core chemicals (DA, 5-HT, NE, epinephrine, cortisol, oxytocin) always present. All others shown only when |gap| ≥ 2. If output contains ~20 entries, chemistry function is misfiring.
- **Memory architecture (hippocampus)** — RAG + KAG from v1 carried forward unchanged. Two RAG collections (`mina_experiences` for LLM-synthesized episodic memories, `mina_sliding` for per-message sliding window chunks). KAG: identity, diary, knowledge files, per-person relationship files. Consolidation in FREETIME. Relationship memory uses four-layer cascading compaction (short → medium → long → ground_truth, 7-to-1 at each level).
- **Chemical concentrations are in nM throughout** — matches computational neuroscience convention, maps directly to receptor binding thresholds, and keeps tonic values readable (e.g. 0.3 nM serotonin in PFC). Phasic synaptic peaks are large numbers (thousands of nM) — that's correct. Convert to other units only at display layer.
- **Decoder normalization scale** — 0–10 anchored to physiological maximum per chemical (10 = childbirth oxytocin, marathon endorphins, near-death epinephrine, etc.). Scale is unbounded above 10; values >10 are pharmacological by definition and not achievable through natural human experience. Chatbot interactions are expected to reach 5–6 at most; 7+ from conversation alone indicates miscalibrated chemistry function weights. Interpretive frame is baked into the scale so the insula pillar can reason about felt state without understanding neuroscience.

---

## Open Architectural Questions

These are unresolved and will be addressed in upcoming design conversations.

### 1. Encoder output schema

**DECIDED: integer activation axes, 0–10, with a chemistry function floor at ≤2.** Categorical labels lose information that matters for chemistry — "I miss you" and "come here" should produce different chemical profiles. Axes match actual amygdala biology (salience encoded on continuous dimensions, not discrete event types). Integer scale is easier to prompt-engineer against and produces cleaner logs than floats.

**Salience floor:** axis values ≤2 are treated as zero by the chemistry function — no deltas applied. This prevents the LLM from causing runaway chemistry through small non-zero values on low-salience turns. The encoder can post whatever values it appraises; the floor silently discards noise. The floor threshold (currently 2) is a tuning parameter in the chemistry function, not baked into the schema.

Schema shape (axes finalized in question 2):

```json
{
  "salience": 0–10,
  "threat": 0–10,
  "social_threat": 0–10,
  "reward": 0–10,
  "bonding": 0–10,
  "arousal": 0–10,
  "aversion": 0–10,
  "novelty": 0–10,
  "loss": 0–10,
  "romance": 0–10,
  "shame": 0–10,
  "directed_at_mina": bool,
  "register_shift": bool,
  "expected_magnitude": 0–10,
  "channel": "dialogue" | "action"
}
```

The chemistry function maps axis activations to chemical deltas via weighted sums (e.g., oxytocin delta = `bonding × w1 + reward × w2 - threat × w3`). Weights are the tuning surface, not the schema.

### 2. Axis taxonomy design

**DECIDED: 10 axes.** Each has a distinct chemical profile and encodes a dimension the amygdala independently detects. All values 0–10; chemistry function ignores ≤2.

| Axis | Primary chemicals driven | Notes |
|---|---|---|
| `threat` | epinephrine, cortisol | Physical/existential danger |
| `social_threat` | substance P, cortisol, endorphin withdrawal | Rejection, criticism, mockery, dismissal — externally directed |
| `reward` | dopamine, serotonin | RPE signal; something good happened or is expected |
| `bonding` | oxytocin, vasopressin, endorphins, serotonin | Warmth, closeness, trust — vasopressin weight scales with relationship depth |
| `arousal` | norepinephrine (primary), dopamine (secondary) | Non-valenced activation; urgency, attention demand independent of valence |
| `aversion` | serotonin drop, cortisol | Disgust, repulsion |
| `novelty` | dopamine | Prediction error, unexpectedness, curiosity — distinct from reward |
| `loss` | endorphin withdrawal, dynorphin, substance P, cortisol | Absence, goodbye, separation distress |
| `romance` | testosterone, estradiol, dopamine, oxytocin | Sexual salience; routes to sex hormone pathway and prolactin on peak |
| `shame` | substance P, cortisol, endorphin withdrawal | Internally directed social pain — distinct from `social_threat` which requires an external agent |

`threat` and `social_threat` are split because the two have meaningfully different chemical signatures (fight-flight vs. pain pathway). Collapsing them would make a cold dismissal chemically identical to RP combat.

`novelty` and `reward` both involve dopamine but for different reasons — novelty is prediction error (unexpectedness), reward is hedonic value. Collapsing them loses the distinction between "this is new" and "this is good."

`arousal` is a real independent axis, not a modifier — the LC fires on salience regardless of valence. Its primary driver is NE, not a float multiplier on other axes.

### 3. Decoder design

**DECIDED.**

The decoder produces a single JSON object. Each chemical entry has exactly four fields, all whole numbers:

```json
{
  "dopamine":       { "normalized": 4, "setpoint": 4, "gap":  0, "rate":  0 },
  "serotonin":      { "normalized": 3, "setpoint": 4, "gap": -1, "rate": -1 },
  "norepinephrine": { "normalized": 5, "setpoint": 3, "gap": +2, "rate": +1 },
  "epinephrine":    { "normalized": 2, "setpoint": 2, "gap":  0, "rate":  0 },
  "cortisol":       { "normalized": 2, "setpoint": 2, "gap":  0, "rate":  0 },
  "oxytocin":       { "normalized": 4, "setpoint": 3, "gap": +1, "rate": +1 }
}
```

- **`normalized`** — current level (tonic + phasic combined), 0–10 whole number, anchored to physiological maximum (see normalization scale below)
- **`setpoint`** — current adapted baseline, 0–10 whole number, same scale
- **`gap`** — `normalized - setpoint`, pre-calculated signed whole number; the insula does not compute this itself
- **`rate`** — change in normalized units since last tick, signed whole number

Tonic and phasic are combined into a single felt level. The four values together convey the full picture: absolute level, chronic baseline, deviation, and direction of travel. A phasic spike reads as large gap + nonzero rate; a chronic tonic shift reads as elevated setpoint with near-zero rate.

**Core chemicals — always present:**

DA, 5-HT, NE, epinephrine, cortisol, oxytocin. These map directly to the primary felt-state dimensions (motivation, mood, arousal, stress, bonding) and are always behaviorally relevant.

**Conditional chemicals — shown only when |gap| ≥ 2:**

All other chemicals in the sim. If the decoder output contains ~20 entries, something is wrong with the chemistry function — runaway chemistry surfaces here before it reaches the insula.

**Tonic/phasic note:** combining them into one felt level works because the four-field schema already encodes the distinction implicitly. Large gap + nonzero rate = acute phasic event. Elevated setpoint + near-zero rate = chronic tonic shift. The insula does not need the raw split.

**DECIDED: Normalization scale.**

The decoder normalizes each chemical to a 0–10 scale anchored to physiological reality, with the scale unbounded above 10 for pharmacological states.

- **10 = physiological maximum for that chemical** — the highest level real human biology can produce without pharmacological assistance. Examples: oxytocin at childbirth, endorphins at marathon finish or severe injury, epinephrine at near-death panic, cortisol at acute trauma.
- **The scale is unbounded above 10.** Values above 10 are pharmacological — not achievable through natural human experience. Endorphins at 15 means opiates. Dopamine at 14 means stimulants. The insula pillar treats any value above 10 as pharmacological by definition.
- **Chatbot ceiling is well below 10.** The strongest text-based interaction can produce — a deeply bonding conversation, a devastating argument, a shocking revelation — should reach at most 5–6 on most chemicals. Hitting 7+ from conversation alone warrants a look at chemistry function weights. The sim does not enforce this as a hard cap; it is a calibration reference. Per-chemical expected ceilings are documented in the chemistry constants.

**Interpretive frame for the insula pillar:**

| Range | Meaning |
|---|---|
| 0–2 | Below noise floor — ignored by chemistry function |
| 3–5 | Present, noticeable, colors her state |
| 6–7 | Really feeling it — hard to ignore, will show in behavior |
| 8–9 | Intense, dominant, hard to function normally through |
| 10 | Physiological maximum — not reachable from conversation |
| >10 | Pharmacological — not possible in natural human biology |

This frame is what makes the insula pillar's job tractable. It receives normalized values, not raw nM concentrations, and the interpretive frame is baked into the scale. Substance modeling (deferred) slots in without redesign — the scale already has headroom above 10 and the pillar already knows what it means.

### 4. Chemistry function design

The deterministic mapping from (encoder output × current state × relationship state) → chemistry deltas. Specific concerns:
- How are source-side negative feedback rules expressed?
- How are opponent processes wired?
- How are state-independent overrides applied?
- How is intensity translated to magnitude across categories?

This is the largest single design problem in v2.

### 5. PFC top-down regulation

**DECIDED.** Answered by Principle 6.

- **Frontend regulation** lives in the chemistry function as a deterministic pre-commit modifier: `regulated_delta = raw_delta × pfc_regulation_factor(neuroticism, current_arousal)`. Applied to Class 1 chemicals only, before the delta is committed to the sim.
- **Backend regulation** is the reasoning pillar's job. The pillar receives the decoded felt state and decides how Mina expresses it. High adrenaline + strong backend regulation = surface composure despite internal intensity.

### 6. Hippocampus / memory architecture

**DECIDED: carry v1 forward as-is.** This was one of the strongest parts of v1 — it worked well and is preserved unchanged in v2.

**Two storage tiers:**

- **RAG** — ChromaDB vector store for episodic memory. Two collections:
  - `mina_experiences` — LLM-synthesized episodic memories, written during FREETIME consolidation. Semantically dense; captures meaning (what happened, why it mattered), not raw text.
  - `mina_sliding` — per-message raw conversation chunks (10-message sliding windows, written every turn). Replaced the old "recent bucket" with much higher retrieval precision.

- **KAG** — File-based knowledge store:
  - `identity/MINA.md` — permanent identity file; never wiped.
  - `memory/kag/REFLECTION.md` — Mina's private diary, appended by consolidation.
  - `memory/kag/KNOWLEDGE/*.md` — facts Mina has learned (user preferences, things mentioned, etc.).
  - `memory/relationships/<person>.md` — per-person relationship state (see relationship layer below).

**Retrieval per turn (parallel fetch):**

1. `mina_sliding` semantic query — finds best chunk match, expands ±3 sequence positions to recover surrounding context. Replaces the "recent" bucket.
2. `mina_experiences` bucketed query — semi-recent (2–24h) and historical (24h+) pools, cosine similarity × recency decay (20-min half-life for recent, 48h for historical), similarity floor 0.75.
3. Relational RAG — separate `mina_experiences` query with a 30-day half-life; used to feed relationship context into encoder and chemistry function.
4. KAG — identity and all relationship files always included; REFLECTION.md always included; KNOWLEDGE files LLM-selected per turn based on relevance to current query.

A **context assembly LLM call** synthesizes the retrieved material before it reaches the hippocampus pillar — window synthesis (present-moment situational facts) and RAG synthesis (memory context) are separate LLM passes, each with their own system prompt and output format.

**Consolidation (runs in FREETIME):**

LLM pass over new conversation entries since last consolidation cursor. Produces:
- RAG entries written to `mina_experiences` — specific moments, emotionally tagged when adjudicator annotations are present.
- KAG updates — PENDING.md (deferred things), REFLECTION.md (diary entry), KNOWLEDGE/ (facts learned).
- Followup entries — explicit commitments Mina made that require a future action.

**Relationship memory — four-layer cascading compaction:**

Per-person relationship state is maintained as a Markdown file with four temporal layers, each written by a separate LLM call and compacted 7-to-1 into the next:

| Layer | Period | Trigger |
|---|---|---|
| `short_term` | current emotional disposition | sleep or 22h elapsed |
| `medium_term` | arc of ~7 days | 7 short_term entries accumulated |
| `long_term` | arc of ~7 weeks | 7 medium_term entries accumulated |
| `ground_truth` | enduring character of the relationship | 7 long_term entries accumulated |

Each layer carries prose (2–4 sentences from inside Mina's experience) and six dimension scores (bonding, security, anticipation, tension, warmth, vigilance). The net weighted score across all present layers feeds the chemistry function as relationship state. Writing `long_term` or `ground_truth` layers also applies small receptor sensitivity adjustments to reflect structural adaptation.

### 7. Sim tick rate

**DECIDED: single rate, 10-second tick.**

All four chemical classes are handled comfortably at 10s:
- Class 1 phasic decay (seconds to ~2 minutes) — 10s ticks are slightly coarse but within acceptable fidelity
- Class 2 accumulation/decay (minutes to tens of minutes) — 10s is more than sufficient
- Class 3 HPA cascade (15–30 min rise, 60–90 min decay) — 10s is more than sufficient
- Class 4 setpoint adaptation (hours to days) — implemented as a tiny drift applied each tick; no separate clock needed

Sub-second phasic dynamics are below the granularity Mina can express — modeling them would be grade S overshoot.

### 8. Pillar input/output schemas

The contracts above are sketched intent — they capture what each pillar's job is and what kind of data flows between them, but exact field names, types, and value ranges are not locked. These will be finalized when each pillar is specced.

---

## What This Doc Doesn't Decide

- The chemistry function's actual mapping table (the largest single design problem)
- The sim's internal data structures
- How memory (RAG/KAG) is implemented
- How the system handles long conversation history scaling
- The exact Big 5 → chemistry-parameter mapping table
- The FREETIME ambient-action vocabulary (which "things she does" when alone are emitted as memory entries vs. real tool calls)

These will each be their own design conversations and eventual SPECs.
