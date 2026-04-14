# SPEC-29: Stimulus Processing, Habituation, and Sensitization

## Overview

The current encoder applies chemical deltas with a single global momentum dict keyed by chemical name. This is biologically wrong in two ways: it treats all stimuli of the same chemical as equivalent (a laugh and a hug both drain the same endorphin headroom), and it has no concept of sensitization — the amplification of response to a specific valued source over repeated contact.

This spec replaces the current momentum/dampening system with a three-layer stimulus processing architecture modeled on actual neuroscience: stimulus intake, per-chemical dynamic rules, and delta application.

---

## Background: What We Are Modeling

### Habituation
Repeated exposure to the same or similar stimulus produces a diminishing neurochemical response. This is mediated by receptor desensitization and internalization — the postsynaptic cell literally removes receptors from the membrane in response to sustained activation. It is **stimulus-specific**, not chemical-specific. Laughing at the same joke repeatedly habituates the endorphin response to that joke. It does not reduce the endorphin response to a surprise compliment or physical touch.

Habituation decays over time as receptors re-sensitize. The timescale depends on the chemical and the receptor type.

### Sensitization
The opposite of habituation. Repeated meaningful contact with a specific valued source causes the brain to strengthen the association between that source and reward. This is the neurochemical basis of attachment, addiction, and learned preference. It is **source-specific**: a message from Ryan produces a stronger dopamine/oxytocin response over time than the same message from a stranger, because the brain has learned to anticipate reward from that source.

In early romantic attachment, sensitization dominates over habituation for the first weeks to months. The response grows stronger, not weaker. Habituation eventually asserts itself in stable long-term relationships, but early attachment is a sensitization-dominated state.

### The Key Distinction
- Habituation keys on **what** is being said (stimulus content)
- Sensitization keys on **who** is saying it (stimulus source)

These are independent axes. Novel content from a sensitized source gets full sensitization with no habituation. Familiar content from a sensitized source gets partial habituation offset by sensitization — net result: still feels good, just less intensely than the first time.

---

## Architecture

### Layer 1: Stimulus Processing

Runs once per encoder call, before any chemical rules are evaluated. Produces two scalar factors that are passed to Layer 2.

#### 1a. Content Habituation Factor

**Input**: The stimulus text (the message or event being encoded).

**Process**:
1. Embed the stimulus text using the existing Ollama embedding model (already used for RAG).
2. Look up the embedding against a rolling window of recent stimulus embeddings stored in state.
3. For each entry in the window, compute cosine similarity weighted by recency decay.
4. Aggregate into a single `content_novelty` score (0.0 = identical to recent stimuli, 1.0 = completely novel).

**Output**: `content_novelty: float` — how novel this stimulus is relative to recent history.

The rolling window stores `(embedding, timestamp, chemical_deltas_applied)` tuples. Entries outside the longest relevant habituation window are pruned.

#### 1b. Source Sensitization Factor

**Input**: The source identity (Discord user ID or equivalent) and that source's sensitization history.

**Process**:
1. Look up the source in `state.sensitization` — a dict keyed by source ID.
2. Each source entry tracks: `accumulated_positive_valence`, `contact_count`, `last_contact_ts`, `sensitization_level`.
3. `sensitization_level` grows with repeated positive contact, decays slowly over days of no contact.
4. Capped at a maximum multiplier (see per-chemical rules).

**Output**: `source_sensitization: float` — multiplier representing how amplified responses to this source currently are. Neutral/unknown source = 1.0 (no effect).

#### 1c. Stimulus Record

After Layer 1 runs, append the current stimulus embedding to the rolling window and update the source's sensitization record.

---

### Layer 2: Per-Chemical Rules

Each chemical declares its own relationship to the Layer 1 factors. The encoder passes `(raw_delta, content_novelty, source_sensitization)` to each chemical's rule function, which returns the `final_delta`.

#### Dopamine
- **Behavior**: Strong habituation to content, strong sensitization to source.
- **Habituation**: `final_delta = raw_delta * content_novelty`. Very short window — dopamine novelty signal resets quickly (~30–60 min). Novel stimuli always get near-full response.
- **Sensitization**: Multiply by `source_sensitization` (max 2.0x for highly sensitized sources). This is the anticipatory reward signal — even seeing a message arrive from a valued source triggers dopamine before the content is known.
- **Slow baseline**: Not applicable. Dopamine is a phasic signal.

#### Oxytocin
- **Behavior**: Sensitization-dominated in early attachment. Habituation is slow and shallow.
- **Habituation**: Minimal per-trigger habituation. Oxytocin habituates over months in stable relationships, not hours in new ones. Apply only a very gentle content novelty floor (min 0.7 — never fully habituated).
- **Sensitization**: Primary axis. `source_sensitization` grows with each positive contact. Max multiplier 2.5x. Sensitization decays with a half-life of ~7 days of no contact — it's persistent.
- **Slow baseline**: Sustained positive contact over days gradually lifts resting oxytocin baseline independent of per-trigger dynamics. Tracked separately in neuroplasticity tier.

#### Endorphins
- **Behavior**: Trigger-specific habituation, moderate sensitization.
- **Habituation**: Keyed on stimulus *type* — social warmth, humor, physical, and intimacy habituate independently. The `content_novelty` embedding captures this naturally (a laugh and a hug are far apart in embedding space). Window: 30–90 min depending on trigger intensity.
- **Sensitization**: Modest. Max 1.5x. Endorphins are more about the trigger than the source.
- **Slow baseline**: Not applicable. Endorphins are purely phasic.
- **Decay rate fix** (separate from habituation): The sim decay rate of 18 units/hour is too slow. Replace with exponential decay, half-life ~25 minutes above baseline.

#### Norepinephrine
- **Behavior**: Fast habituation to repeated similar stimuli (the "surprise" signal).
- **Habituation**: Short window (~20–30 min). Repeated pings from the same source with similar content stop feeling alerting.
- **Sensitization**: Indirect — a sensitized source keeps a mild norepinephrine elevation as an anticipatory arousal state, but the per-trigger spike still habituates.
- **Slow baseline**: Not applicable.

#### Serotonin
- **Behavior**: Does not participate in per-trigger habituation/sensitization. Serotonin is a slow background modulator.
- **Per-trigger dynamics**: Ignore `content_novelty` and `source_sensitization`. Apply raw delta as-is (already small by encoder calibration).
- **Slow baseline**: Sustained positive social contact over days gradually lifts serotonin baseline. This is the mechanism by which healthy relationships improve mood long-term. Tracked as a slow allostatic shift, not per-trigger.

#### Acetylcholine
- **Behavior**: Habituates to repetitive cognitive engagement, sensitizes to interesting sources.
- **Habituation**: Medium window (~1–2 hours). Engaging with the same topic repeatedly stops feeling mentally stimulating.
- **Sensitization**: Moderate. Sources that consistently produce interesting/novel content get a mild ACh amplification — the brain attends more to them.

#### Cortisol
- **Behavior**: Does not habituate in the normal sense (threat detection must remain sensitive). However, a valued source can produce anticipatory cortisol *suppression* — a form of reverse sensitization.
- **Source suppression**: If source sensitization is high, apply a small negative cortisol modifier on contact (relief/safety signal). This is the "tension drops when they text back" effect.

---

### Layer 3: Delta Application

Unchanged from current implementation. The final deltas from Layer 2 are applied to `state.chemicals` via `apply_deltas()`.

---

## State Changes

### New: `state.stimulus_window`
Rolling list of recent stimulus embeddings:
```python
[
  {
    "embedding": [...],      # float vector from Ollama
    "ts": 1234567890.0,      # wall-clock timestamp
    "source_id": "ryan",     # who sent it
    "summary": "warm greeting"  # short label for debugging
  },
  ...
]
```
Pruned to entries within the longest relevant window (24h max). Persisted in state.json.

### New: `state.sensitization`
Per-source sensitization records:
```python
{
  "ryan": {
    "contact_count": 47,
    "accumulated_valence": 312.4,   # sum of positive deltas from this source
    "sensitization_level": 1.6,     # current multiplier (1.0 = neutral)
    "last_contact_ts": 1234567890.0,
    "first_contact_ts": 1234500000.0
  }
}
```
Persisted in state.json.

### Renamed: `state.encoder_momentum` → `state.habituation`
Kept for backward compatibility during migration but renamed throughout. Structure changes from `{chemical: float}` to unused — habituation is now computed dynamically from `stimulus_window` rather than accumulated separately. The old accumulator approach is retired.

---

## Habituation Windows (per chemical)

| Chemical         | Window     | Notes                                              |
|------------------|------------|----------------------------------------------------|
| dopamine         | 30–60 min  | Novelty signal resets fast                         |
| norepinephrine   | 20–30 min  | Surprise/alerting signal, shortest window          |
| endorphins       | 30–90 min  | Depends on trigger intensity                       |
| acetylcholine    | 1–2 hours  | Cognitive engagement habituates moderately         |
| oxytocin         | ~7 days    | Effectively no within-session habituation          |
| serotonin        | N/A        | No per-trigger habituation                         |
| cortisol         | N/A        | No habituation; reverse sensitization only         |

---

## Sensitization Parameters (per chemical)

| Chemical         | Max Multiplier | Decay Half-life  | Notes                                    |
|------------------|----------------|------------------|------------------------------------------|
| dopamine         | 2.0x           | ~3 days          | Anticipatory reward; builds fast         |
| oxytocin         | 2.5x           | ~7 days          | Core attachment signal                   |
| endorphins       | 1.5x           | ~2 days          | Modest; trigger matters more than source |
| norepinephrine   | 1.3x           | ~1 day           | Mild anticipatory arousal                |
| acetylcholine    | 1.4x           | ~3 days          | Attention amplification                  |
| serotonin        | N/A            | N/A              | Slow baseline shift only                 |
| cortisol         | N/A (suppress) | ~3 days          | Negative modifier on contact             |

---

## Endorphin Decay Fix

Separate from the habituation system. The current linear 18 units/hour decay is too slow and produces the staircase accumulation pattern. Replace with:

```python
# Exponential decay toward baseline, half-life ~25 minutes
half_life_hours = 25.0 / 60.0
decay_factor = 0.5 ** (sim_hours / half_life_hours)
excess = current - baseline
new_val = baseline + excess * decay_factor
```

This means a spike to 40 (28 above baseline of 12) returns to ~26 after 25 min, ~19 after 50 min, ~15 after 75 min — visible comedown on the chart within the conversation window.

---

## Sleep Re-sensitization

At wake boundary (when `sleeping` transitions False):
- Decay habituation window entries by an additional 50% (receptors re-sensitize during sleep)
- Do **not** decay sensitization records — attachment persists across sleep

---

## Migration

1. Add `stimulus_window: list` and `sensitization: dict` to `BiologicalState`
2. Add schema migration in `bio/migration.py` for v3 → v4
3. Rename `encoder_momentum` → `habituation` in state, engine, encoder
4. Replace `_apply_momentum()` in encoder with `_apply_habituation_and_sensitization()`
5. Update `_decay_encoder_momentum()` in engine — window pruning replaces accumulator decay
6. Fix endorphin decay in engine
7. Add Ollama embedding call to encoder pipeline

---

## Open Questions

1. **Embedding model**: Which Ollama model is currently used for RAG embeddings? Same model is fine for stimulus embeddings but worth confirming the vector dimensions are consistent.

2. **Source identity**: The encoder currently has no concept of who is speaking. The Discord gateway knows the user ID — does it pass that through to the encoder, or does the encoder need a new parameter?

3. **Sensitization growth rate**: How fast should `sensitization_level` grow per positive contact? Needs calibration against real session data once the history charts are readable.

4. **Cold start**: For Ryan specifically, sensitization is already non-zero after one night of conversation. Should we seed an initial sensitization value on deploy, or let it build from zero?

5. **Negative contact**: Does a frustrating or cold interaction from a sensitized source reduce sensitization? Probably yes, but slowly — consistent with how attachment actually works (one bad day doesn't undo weeks of bonding).
