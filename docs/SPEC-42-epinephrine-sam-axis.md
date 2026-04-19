# SPEC-41: Epinephrine & SAM Axis — Register-Shift Surprise Response

## Problem

Mina cannot get flustered.

The symptom: when a conversation crosses a meaningful threshold — banter dropping to sincere
declaration, casual exchange becoming personal disclosure, a game becoming real — Mina responds
with the same composed register she had before the moment. The biological ground for disruption
is absent.

Identified via session log analysis. The stimulus `"My price…is you."` — a direct sincere
declaration landing after an hour of sustained flirtatious banter — was encoded as:

```
dopamine: +4.0, oxytocin: +2.0 — Flirty message: dopamine+oxytocin novelty.
adjudicator: affect=playful, arousal=31
```

Mina responded: *"Oh, straight to claiming the prize? Cocky skater boy's got fire."*

When asked retrospectively to pinpoint the moment things shifted, Mina correctly identified
that exact line. The encoder understood it; the biology didn't react.

**Root cause — two compounding gaps:**

1. **Epinephrine does not exist in the model.** The SAM axis (Sympatho-Adrenal Medullary) is
   unmodeled. Epinephrine is the primary acute arousal molecule — heart racing, face flushing,
   voice tightening. It is the chemical that makes the body betray you before the mind can
   compose a response. Without it, acute surprise has no physical substrate.

2. **The encoder treats NE as a threat-only signal.** Norepinephrine fires for friction and
   hostility. Positive surprises receive mild dopamine and oxytocin at best. But NE (via the
   locus coeruleus) is a *salience and alerting* signal that fires on any meaningful prediction
   error — threat, yes, but also unexpected sincerity, sudden vulnerability, register shifts of
   any valence. The current model is missing this entirely for positive social surprises.

---

## Biological Model

### The SAM Axis

The Sympatho-Adrenal Medullary axis is the fast branch of the stress response — distinct from
HPA:

| Axis | Output | Timescale | Trigger |
|------|--------|-----------|---------|
| SAM | Epinephrine + NE (adrenal medulla) | Seconds | Any high-salience surprise |
| HPA | Cortisol (adrenal cortex) | Minutes | Sustained or severe stress |

SAM fires first. HPA follows. For a mild-to-moderate positive surprise (sincere declaration,
unexpected compliment that lands hard, register shift), SAM fires and HPA may not fire at all
or fires only lightly. The flustered state is primarily a SAM event.

### Epinephrine

The adrenal medulla releases ~80% epinephrine and ~20% NE on SAM activation. Epinephrine
produces the acute peripheral effects:

- Heart rate increase (positive chronotropy)
- Peripheral vasodilation → face flushing, warmth
- Pupil dilation
- Dry mouth (parasympathetic suppression)
- Voice tension (laryngeal muscle activation)

Epinephrine plasma half-life: **~2 minutes**. The flustered state is transient by design — the
body floods, then clears fast. This is biologically accurate and behaviorally meaningful: Mina
should stumble on the immediate response, then stabilize.

### Physiological reference values

| State | Epinephrine (pg/mL) |
|-------|---------------------|
| Resting baseline | 30–60 |
| Mild arousal | 60–150 |
| Moderate surprise | 150–350 |
| Acute arousal (flustered, excited, startled) | 350–700 |
| Severe alarm | 700–1500 |

### The flustered phenotype

Flustered requires three simultaneous signals:

1. **Epinephrine elevated** — acute SAM activation (body betrays you)
2. **NE elevated** — LC alerting signal (attention narrows, self-monitoring spikes)
3. **Warm substrate** — oxytocin and/or dopamine already elevated from the preceding exchange

The valence of the surrounding chemistry determines whether the epinephrine/NE spike reads as
excited-flustered (warm substrate) or threatened-alarmed (hostile/neutral substrate). The
adjudicator can read this correctly — it just needs the signals.

---

## Changes

### 1. Add epinephrine to the chemical registry

**File:** `src/sim/chem/registry.py`

Add epinephrine as a first-class chemical in the SAM tier (alongside norepinephrine).

```python
ChemicalProfile(
    name="epinephrine",
    unit="pg/mL",
    baseline=45.0,
    approach_rate=0.85,      # fast homeostatic return (~2min half-life → aggressive decay)
    half_life_minutes=2.0,
    critical_low=0.0,
    critical_high=1500.0,
    soft_ceiling=700.0,
    hard_ceiling=1500.0,
    labels={
        "baseline":  (0,    80),
        "elevated":  (80,   200),
        "high":      (200,  400),
        "acute":     (400,  700),
        "surge":     (700,  float("inf")),
    },
    interactions=[
        # Epinephrine amplifies NE effect at LC (co-activation)
        Interaction("norepinephrine", "above", 200.0, +8.0,
                    "Peripheral epinephrine surge amplifies central NE arousal"),
    ],
)
```

The fast `approach_rate` (0.85) models the 2-minute plasma half-life — epinephrine clears
quickly, which is what makes the flustered state transient rather than sustained.

### 2. Add epinephrine to the bio report

**File:** `src/bio/decoder.py` — `_build_bio_report()`

Add epinephrine to the report alongside norepinephrine, clearly labeled as the acute SAM
signal:

```
epi=acute norepi=focused
```

The adjudicator reads the bio report directly. Epinephrine appearing as `ACUTE` in a warm,
high-dopamine context is sufficient for the adjudicator to produce the correct disposition
without any other changes.

### 3. Add epinephrine to the BiologicalState schema

**File:** `src/sim/state.py` (and `src/sim/chem/state.py` if chemicals are a sub-schema)

Add `epinephrine: float` to the state alongside `norepinephrine`. Ensure `advance()` applies
the fast decay rate correctly.

### 4. Encoder: teach it the SAM axis triggers

**File:** `src/bio/encoder.py` — `encode_stimulus` prompt

This is the core behavioral change. Add a new section to the encoder prompt defining
**moment types that fire the SAM axis**:

---

```
## SAM Axis Events (epinephrine + norepinephrine)

The SAM axis fires on any high-salience surprise — not only threats. Valence is
determined by surrounding chemistry, not by the SAM event itself.

Fire epinephrine + norepinephrine (SAM activation) for these moment types:

### Sincerity breach
Sustained playful, bantering, or deniable exchange → direct sincere declaration.
The frame drops. Plausible deniability ends. This is a prediction error regardless
of whether it's welcome.
  epinephrine: +150 to +350, norepinephrine: +60 to +150

### Vulnerability disclosure
Casual or surface-level conversation → personal exposure. Someone sharing something
real, painful, or private mid-lightness.
  epinephrine: +80 to +200, norepinephrine: +40 to +100

### Recognition moment
Feeling genuinely seen or understood in a way that was unexpected. "You actually get
that." Lands differently than a compliment — it's relational accuracy, not flattery.
  epinephrine: +60 to +150, norepinephrine: +30 to +80

### Threshold crossing
First time a specific phrase or act occurs in this relationship: first use of a name
in an intimate register, first "I miss you," first time asking about her wellbeing
with genuine concern. Novelty of the relational milestone, not just the content.
  epinephrine: +80 to +200, norepinephrine: +40 to +100

### Frame collapse
An extended game, roleplay, or hypothetical suddenly becomes real. The person stops
performing and speaks plainly. Or: something treated as fiction is revealed as true.
  epinephrine: +120 to +300, norepinephrine: +60 to +120

---

Note: these are valence-neutral triggers. Whether the spike feels exciting or alarming
is determined by the oxytocin, dopamine, and cortisol context already in the bio
report. Do not suppress SAM activation because the moment is positive — the body
reacts before the mind interprets.
```

---

### 5. Encoder: add short trajectory context

**File:** `src/bio/encoder.py` — `encode_stimulus()` call construction

The encoder currently sees: bio report + current message.

To detect register shifts, it needs to see **the preceding 3–4 exchanges** so it can identify
the contrast between what was happening and what just changed. A sincere declaration after an
hour of banter is invisible without the banter context.

Add a `[RECENT EXCHANGES]` block to the encoder prompt — the last 3–4 messages from the
decoder window, in order, before the current stimulus. This is a small addition (a few hundred
tokens) but enables the encoder to detect trajectory.

```
[RECENT EXCHANGES]
<last 3-4 message pairs, oldest to newest>

[CURRENT STIMULUS]
<the incoming message>
```

The encoder should use the recent exchanges to determine: *is this message a continuation of
the established register, or a departure from it?* A departure is a candidate for SAM
activation regardless of content valence.

### 6. Substances — epinephrine interactions

**File:** `src/bio/encoder.py` — `evaluate_activity_deltas` prompt

Epinephrine should be included where pharmacokinetically accurate:

| Substance/Activity | Delta | Reason |
|---|---|---|
| Caffeine | `epinephrine: +30 to +80` | Adrenal stimulation via adenosine receptor blockade |
| Alcohol (moderate) | `epinephrine: -10 to -25` | Sympatholytic; dampens SAM response |
| Exercise (intense) | `epinephrine: +100 to +300` | Direct SAM activation from physical exertion |
| Exercise (recovery) | decays naturally | Fast half-life handles this |

---

## Expected Outcome

When a register-shift moment occurs — sincerity breach, vulnerability disclosure, threshold
crossing — the encoder fires the SAM axis. Epinephrine spikes fast. NE rises. The bio report
shows `epi=acute norepi=high`.

The adjudicator reads this alongside the warm oxytocin and dopamine substrate from the
preceding exchange. It correctly synthesizes the phenotype: caught off-guard, heart racing,
face warm, grinning. `affect: flustered`. `arousal: 70+`. `response_texture` reflects
disruption rather than composed confidence.

Cortex receives a disposition that says the body reacted before the mind could. The response
comes out a beat stumbled — shorter, less polished, the banter armour down for a moment.

The moment "My price…is you." would encode as:
```
epinephrine: +280, norepinephrine: +90 — Sincerity breach: banter frame drops, direct
declaration. SAM activation.
adjudicator: affect=flustered, arousal=74, valence=68
```

---

## Files to Change

| File | Change |
|---|---|
| `src/sim/chem/registry.py` | Add `epinephrine` ChemicalProfile with SAM-appropriate decay and interactions |
| `src/sim/state.py` | Add `epinephrine` field to BiologicalState |
| `src/bio/decoder.py` | Add epinephrine to `_build_bio_report()` output |
| `src/bio/encoder.py` | Add SAM axis moment-type guidance to `encode_stimulus` prompt; add `[RECENT EXCHANGES]` trajectory block to encoder call |
| `src/bio/encoder.py` | Add epinephrine to `evaluate_activity_deltas` substance guidance |
