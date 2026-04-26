# SPEC-54: Biological Timing Model

**Status: DRAFT**

Depends on: SPEC-53 (registry consolidation, `pool` field on `ChemicalProfile`)

---

## Problem

The current encoder fires all chemical deltas before the response. Fast and slow
chemicals land simultaneously. Cortisol from "Can we talk?" peaks 20-40 minutes after
the message — not before Mina finishes her reply. Oxytocin from a warm exchange builds
over the conversation, it doesn't spike at the first message. The sim has no concept
of this time dimension.

The result: Mina's chemistry is shaped by a collapsed snapshot of everything at once,
rather than by what actually arrived fast and what arrived slow.

---

## Design

Two things change:

1. **Two chemical pools** separated by the blood-brain barrier
2. **Two stimulus axes** that fire at different points in the turn cycle

---

## Two Pools

The blood-brain barrier divides all chemicals into two compartments:

**Bloodstream (plasma)**: cortisol, epinephrine, norepinephrine, glucose, melatonin,
oxytocin, hydration, BAC. Clearance is hepatic degradation, renal filtration, plasma
enzymatic activity.

**Synaptic pool (CNS, behind the BBB)**: dopamine, serotonin, acetylcholine, GABA,
glutamate, endorphins, anandamide, 2-AG. Clearance is reuptake transporters (DAT,
SERT, NET) and local enzymatic degradation (MAO, COMT, AChE, FAAH).

Mechanically both pools are flat `{chemical: concentration}` dicts advanced by the
same three clearance models from SPEC-53. The distinction determines which biological
metaphor applies and correctly captures that plasma dopamine is not the same pool as
CNS dopamine.

Cross-BBB effects (cortisol suppressing serotonin synthesis; glucose fueling CNS
function) are explicit `Interaction` entries where source and target live in different
pools.

Each heartbeat tick:
```
bloodstream.advance(sim_hours)
synaptic_pool.advance(sim_hours)
```

---

## Two Stimulus Axes

### Amygdala — Phasic (fires before response)

The amygdala is a **pattern matcher, not a thinker**. It detects emotional salience
in a stimulus and fires immediately — before the cortex has processed anything. It does
not understand the message. It scores it.

A single LLM call outputs five salience dimensions:

```json
{"threat": 3, "reward": 7, "novelty": 2, "warmth": 8, "urgency": 1}
```

Scores are integers 0–10. The prompt contains no chemistry knowledge. A deterministic
lookup table in code maps scores to phasic chemical deltas. The LLM scores
human-intuitive concepts; the code owns the biology.

Example lookup (tunable):
```python
def salience_to_deltas(scores, personality, habituation) -> dict:
    threat  = scores["threat"]  / 10.0
    reward  = scores["reward"]  / 10.0
    novelty = scores["novelty"] / 10.0
    warmth  = scores["warmth"]  / 10.0
    urgency = scores["urgency"] / 10.0

    return {
        "norepinephrine": (threat * 150 + novelty * 80) * habituation,
        "epinephrine":    (threat * urgency * 60)       * habituation,
        "dopamine":       (reward * 60)                 * habituation,
        "endorphins":     (warmth * 20)                 * habituation,
    }
```

Personality multipliers sit on top — high neuroticism amplifies threat responses.
Habituation is a scalar (0.2–1.0) computed from recent stimulus similarity.

Phasic chemicals (synaptic pool):
- **Dopamine** — reward/threat salience (VTA phasic firing)
- **Norepinephrine** — arousal, novelty (locus coeruleus)
- **Epinephrine** — urgent physical threat only (SAM axis → bloodstream)
- **Endorphins** — warmth, intense positive stimulus

These deltas land in state **before** the three-pillar pipeline runs. They directly
color the response.

### Hypothalamus — Tonic (fires after response)

The hypothalamus handles sustained regulatory responses. It fires after the amygdala's
immediate assessment, routes through multi-step cascades, and peaks well after the
triggering moment. These deltas land in state **after** the response is sent — shaping
the next turn, not the current one.

The hypothalamus reads the same salience scores the amygdala produced and runs its own
tonic lookup:

```python
def salience_to_tonic(scores) -> dict:
    threat = scores["threat"] / 10.0
    warmth = scores["warmth"] / 10.0

    return {
        "cortisol":  threat * 120,   # HPA axis — peaks 20-40 min later via onset_delay
        "oxytocin":  warmth * 8,     # sustained social bonding release
        "serotonin": warmth * 2,     # tonic tone nudge, positive exchanges compound
    }
```

Tonic chemicals (bloodstream / synaptic):
- **Cortisol** (bloodstream) — HPA axis; `onset_delay` in the secretion queue models the CRH → ACTH → cortisol cascade delay
- **Oxytocin** (bloodstream) — builds over warm exchanges
- **Serotonin** (synaptic) — tonic tone shift, hours not seconds

### What This Produces

A stressful message hits the amygdala: norepinephrine spikes, dopamine flashes with
threat salience. Mina responds from that state — alert, slightly guarded. Then the
hypothalamus fires post-response. Cortisol is still climbing into the next message.
Two turns later she's carrying the load from something said earlier. That's how dread
actually works.

A warm message hits the amygdala: dopamine phasic reward. Mina responds warm. Then
oxytocin builds, serotonin tone nudges up. The next message starts from a slightly
elevated baseline. Positive exchanges compound.

---

## Secretion Queue Changes

The secretion queue gains an `axis` field:

```python
{
    "chemical": "cortisol",
    "amount": 85.0,
    "axis": "hypothalamus",      # "amygdala" | "hypothalamus"
    "source": "stimulus",
    "onset_delay": 1800          # seconds; HPA cascade delay
}
```

`cortex.py` drains the queue in two passes:
1. **Pre-pipeline**: drain all `axis == "amygdala"` events → apply to state → run three-pillar pipeline → generate response
2. **Post-response**: drain all `axis == "hypothalamus"` events → apply to state → save

---

## What Happens to the Existing Encoder Pieces

| Current piece | What it becomes |
|---|---|
| `_call_delta_json()` | Replaced by 5-dimension salience LLM call |
| `_apply_habituation_and_sensitization()` | Stays; produces the `habituation` scalar fed into the lookup table |
| `_compute_content_novelty()` | Stays; feeds the `novelty` dimension score |
| `_apply_personality_scaling()` | Moves into the lookup table as personality multipliers |
| `_apply_saturation()` | Moves into the pool — saturation is a pool property, not an encoder property |
| `compute_relationship_modifier()` | Moves to hypothalamus axis — it's a tonic background effect |
| `evaluate_activity_deltas()` | Moves to hypothalamus axis — slow, sustained |
| `encode_response()` | Stays phasic; becomes a second amygdala pass on Mina's own words |
| `regulate()` | Unchanged — emotion pillar post-hoc correction |

---

## What Changes

| File | Change |
|---|---|
| `src/brain/amygdala/stimulus_encoder.py` | Replace `_call_delta_json` with 5-dimension salience call; add lookup table; restrict to phasic chemicals |
| `src/brain/hypothalamus/__init__.py` | **New** — tonic axis; reads salience scores, fires slow cascade post-response |
| `src/brain/cortex/cortex.py` | Drain amygdala queue pre-pipeline; drain hypothalamus queue post-response |
| `src/engine/bio/state.py` | Secretion queue events gain `axis` field |

---

## What Does NOT Change

- Three-pillar pipeline (SPEC-52) — unchanged
- `derived.py` — unchanged
- Subsystem files — unchanged; HPA subsystem is effectively the hypothalamus axis's cortisol implementation
- `regulate()` — unchanged
- All tuning values — no constant changes in this spec

---

## Open Questions

1. **Norepinephrine pool**: Norepinephrine exists in both compartments (adrenal medulla
   → bloodstream; locus coeruleus → CNS synaptic). The registry currently puts it in
   bloodstream. Does it need to be in both pools, or is one pool an acceptable
   simplification?

2. **Oxytocin pool**: Oxytocin's behavioral effects are CNS but it's measurable in
   plasma. The spec puts it in bloodstream. Is this right, or should it be synaptic?

3. **Hypothalamus salience input**: The hypothalamus reads the amygdala's salience
   scores. Does it need its own separate input, or is sharing the amygdala's scores
   the right model? Biologically the hypothalamus receives amygdala projections
   directly — sharing scores is accurate.

4. **encode_response() scoring**: When Mina's own words run through the amygdala as a
   second pass, do they produce a full 5-dimension score via LLM call, or does a
   simpler heuristic suffice? A second LLM call per turn adds latency.
