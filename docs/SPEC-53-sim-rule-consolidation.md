# SPEC-53: Biological Simulation Consolidation

**Status: DRAFT**

---

## Problem

Chemical behavior is fragmented across at least 8 tiers of code that don't agree with
each other. The epinephrine half-life bug (49-minute effective half-life from a
mismatched comment and formula) was a direct symptom. The deeper problem: there is no
single place to go to understand how a chemical behaves. Understanding cortisol requires
reading `registry.py`, `engine.py`, `constants.py`, subsystem files, and `decoder.py`.

The fix is a model — the **two-pool biological model** — that treats the simulation as
physiology-inspired rather than physiology-accurate. Chemicals live in one of two pools
separated by the blood-brain barrier. Each pool has its own clearance organs and
mechanisms. Two stimulus axes (amygdala: fast/phasic, hypothalamus: slow/tonic) fire
at different points in the turn cycle, correctly separating the immediate emotional
coloring of a response from the hormonal aftermath that shapes the next one.

---

## Design Philosophy

**Biological constructs as metaphors, not constraints.** We use "bloodstream",
"plasma half-life", "hepatic clearance", "renal filtration", "enzymatic degradation"
because they give the system a coherent mental model and produce realistic behavior.
We do not need to match real pharmacokinetics exactly. When tuning is needed, we tune
the half-life in one place and it propagates everywhere.

**The bloodstream is a shared bus.** Every chemical has a plasma concentration. The
engine advances concentrations each tick. Downstream consumers (decoder, derived values,
behavior) read from the bloodstream. Nothing writes concentration values except the
engine and the encoder.

**Simple parts, complex emergent behavior.** Each chemical has one decay model and one
set of parameters. Cross-chemical effects are explicit interactions, not scattered
hardcoding. The complexity of the simulation emerges from the interactions, not from
per-chemical special cases buried in the engine.

---

## Two Compartments, One Barrier

The blood-brain barrier divides the simulation into two distinct chemical pools:

**Bloodstream (plasma)**: cortisol, epinephrine, norepinephrine, glucose, melatonin,
oxytocin, hydration, BAC. Clearance is hepatic degradation, renal filtration, and
plasma enzymatic activity. Half-lives are plasma pharmacokinetics.

**Synaptic pool (CNS, behind the BBB)**: dopamine, serotonin, acetylcholine, GABA,
glutamate, endorphins, anandamide, 2-AG. Clearance is reuptake transporters (DAT,
SERT, NET) and local enzymatic degradation (MAO, COMT, AChE, FAAH). Half-lives are
synaptic dwell times.

Mechanically both pools are a flat `{chemical_name: concentration}` dict advanced by
the same three clearance models. The distinction is conceptual — it determines which
biological metaphor applies to clearance, and it correctly captures that dopamine in
plasma is not the same pool as dopamine in the brain.

Cross-BBB effects (cortisol suppressing serotonin synthesis; glucose fueling CNS
function) are explicit interactions where source and target live in different pools.

Each tick:
```
bloodstream.advance(sim_hours)
synaptic_pool.advance(sim_hours)
```

### Clearance

Every chemical is cleared by one of three biological mechanisms:

| Mechanism | Biological analog | Math | When to use |
|---|---|---|---|
| `exponential` | Hepatic/enzymatic degradation — first-order kinetics | `C(t) = C₀ × 0.5^(t / t½)` | Fast-clearing molecules: epinephrine, endorphins, endocannabinoids |
| `gap_closure` | Homeostatic regulation — reuptake/receptor driven | `C += (target - C) × rate × Δt` | Most neurotransmitters; system "wants" a setpoint |
| `formula` | Circadian or physiologically-forced value | Direct assignment from function | Melatonin, sleep pressure |

No other clearance models. If a chemical doesn't fit one of these three, that's a
design question to resolve before implementing.

---

## Phasic vs. Tonic: Two Stimulus Axes

The current encoder fires all chemical deltas before the response. This collapses the
time dimension — fast and slow chemicals land simultaneously, which is biologically wrong.
Cortisol from "Can we talk?" peaks 20-40 minutes after the message, not before Mina
finishes typing her reply.

The fix is two separate axes with different timing:

### Amygdala — Phasic (pre-response)

The amygdala handles **immediate salience detection**. It fires fast, reflexive signals
before any cognitive processing completes. These land in state before the three-pillar
pipeline runs and directly color the response.

The amygdala is a **pattern matcher, not a thinker**. It does not understand the
message — it scores five salience dimensions and fires proportionally. A single LLM
call outputs only:

```json
{"threat": 3, "reward": 7, "novelty": 2, "warmth": 8, "urgency": 1}
```

Scores are integers 0–10. The prompt is minimal — no chemistry knowledge required.
A deterministic lookup table in code maps these scores to phasic chemical deltas.
The LLM scores human-intuitive concepts; the code owns the biology.

Example mappings (tunable):
```
threat × 8  → norepinephrine delta
threat × 4  → epinephrine delta (only if urgency > 5)
reward × 5  → dopamine delta
warmth × 3  → endorphin delta
novelty × 6 → norepinephrine delta
```

Phasic chemicals:
- **Dopamine** (VTA phasic firing — reward/threat salience)
- **Norepinephrine** (locus coeruleus alerting — arousal, novelty)
- **Epinephrine** (SAM axis — physical/urgent threat only)
- **Endorphins** (phasic release on warmth or intense positive stimulus)

The amygdala does not release these directly — it signals to the structures that do
(VTA, locus coeruleus, adrenal medulla). As an architectural label it is accurate
enough.

### Hypothalamus — Tonic (post-response)

The hypothalamus handles **sustained regulatory responses**. It fires after the
amygdala's immediate assessment, routes through multi-step cascades, and peaks well
after the triggering moment. These land in state *after* the response is sent —
shaping the next turn, not the current one.

Tonic chemicals:
- **Cortisol** (HPA axis — CRH → ACTH → cortisol, 20-40 min delay)
- **Oxytocin** (sustained social bonding release — builds over a warm exchange)
- **Serotonin tone** (shifts over hours, not seconds)

### What this produces

A stressful message hits the amygdala: norepinephrine spikes, dopamine flashes with
threat salience. Mina responds from that state — alert, slightly guarded. Then the
HPA cascade fires post-response. Cortisol is still climbing into the next message.
Two turns later she's carrying the cortisol load from something said earlier. That's
how dread actually works.

A warm message hits the amygdala: dopamine phasic reward signal. Mina responds warm.
Then oxytocin builds post-response, serotonin tone nudges up. The next message starts
from a slightly elevated baseline. Positive exchanges compound.

### Secretion Queue

Both axes write to the secretion queue. Each event carries:
- `chemical`: name
- `amount`: delta in real units
- `axis`: `"amygdala"` or `"hypothalamus"`
- `source`: tag for event bus (`"stimulus"`, `"regulation"`, `"substance"`, etc.)
- `onset_delay`: seconds before it lands in the pool (default 0; HPA cascade uses this)

The engine drains the queue each tick. Amygdala events are drained before the pillar
pipeline. Hypothalamus events are queued during the turn and drained after the response
is sent. This is the only write path into either pool.

---

## ChemicalProfile — Single Source of Truth

Every chemical's complete lifecycle lives in its `ChemicalProfile`. The engine is a
generic executor — it reads profiles, it does not contain per-chemical logic.

```python
@dataclass
class ChemicalProfile:
    name: str
    display_name: str
    unit: str

    # --- Clearance ---
    clearance: Literal["exponential", "gap_closure", "formula"]
    plasma_half_life: Optional[float] = None   # minutes; required for exponential
    approach_rate: Optional[float] = None      # /sim-hour; required for gap_closure
    baseline_fn: Optional[Callable] = None     # required for formula; fallback for gap_closure dynamic targets

    resting_baseline: float = 0.0              # homeostatic target; 0 = no baseline

    # --- Physiological ranges ---
    resting_low: float = 0.0                   # below this = low
    resting_high: float = 0.0                  # above this = elevated
    critical_low: float = 0.0                  # clinically dangerous floor
    critical_high: float = 0.0                 # clinically dangerous ceiling / physics max

    # --- Display ---
    display_min: float = 0.0
    display_max: float = 0.0
    labels: list[tuple[float, str, str]] = field(default_factory=list)

    # --- Saturation (soft/hard ceiling and floor for delta clamping) ---
    soft_ceiling: Optional[float] = None
    hard_ceiling: Optional[float] = None
    soft_floor: Optional[float] = None
    hard_floor: Optional[float] = None

    # --- Biological notes ---
    # Threshold-triggered state descriptions, read by the decoder.
    # (threshold, tag, description) — active when concentration crosses threshold.
    notes: list[tuple[float, str, str]] = field(default_factory=list)

    # --- Interactions ---
    # Cross-chemical effects. Source is this chemical; target is in the Interaction.
    interactions: list[Interaction] = field(default_factory=list)
```

The key additions over the current profile:

- `clearance` field makes the decay model explicit and co-located with the chemical
- `plasma_half_life` in **minutes** — unambiguous, matches biological reference
- `notes` replaces INTERACTION_RULES in `decoder.py` — threshold-triggered prose attached to the chemical that triggers it

---

## Interaction Model

Cross-chemical effects are defined on the **source** chemical's profile:

```python
@dataclass
class Interaction:
    target: str                           # chemical being affected
    threshold: float                      # source concentration that activates this
    direction: Literal["above", "below"]  # threshold crossing direction
    rate: float                           # delta/sim-hour applied to target
    tag: str                              # description for event bus
```

This replaces the scattered cross-chemical hardcoding in `engine.py` and the
`INTERACTION_RULES` predicates in `decoder.py` that operate on raw chemistry.

---

## Notes — Threshold-Triggered Biological State

Currently, INTERACTION_RULES in `decoder.py` contains two different kinds of things:

1. **Single-chemical threshold descriptions**: "cortisol above 650 = acute stress"
2. **Multi-chemical compound descriptions**: "cortisol > 650 AND oxytocin < 28 = stressed with no anchor"

Type 1 belongs on the chemical's profile as `notes`. Type 2 is a multi-variate
observation — these stay in a dedicated module (`rules.py`), but written as named
rules rather than anonymous lambdas.

### Chemical-level notes (on profile)

```python
notes=[
    (450.0, "elevated_cortisol", "Cortisol is elevated — stress response active."),
    (650.0, "acute_stress", "Acute stress. HPA axis fully engaged."),
    (800.0, "cortisol_flood", "Cortisol flooding. Cognitive function compromised."),
]
```

The decoder reads these by scanning each chemical's notes and collecting those whose
threshold is crossed. No lambda predicates — just threshold comparisons.

### Compound rules (in rules.py)

```python
COMPOUND_RULES: list[CompoundRule] = [
    CompoundRule(
        tag="stress_with_anchor",
        condition=lambda s: s["cortisol"] > 650 and s["oxytocin"] > 57,
        description="Acute stress held together by a strong bond. Suppression has a cost.",
    ),
    CompoundRule(
        tag="stress_no_anchor",
        condition=lambda s: s["cortisol"] > 650 and s["oxytocin"] < 28,
        description="Acute stress with no trust anchor. Likely to shut down or lash out.",
    ),
    # ...
]
```

These still use lambdas because they are inherently multi-variate. But they live in
one file (`rules.py`), not scattered across `decoder.py`. The lambda takes `s` (a flat
dict of bloodstream concentrations) — not the full `BiologicalState` object.

---

## Engine Becomes a Generic Executor

After this spec, `engine.py`'s chemical advancement loop contains no per-chemical
special cases. It does this and only this:

```
for each chemical in REGISTRY:
    if profile.clearance == "exponential":
        advance via half-life formula
    elif profile.clearance == "gap_closure":
        target = profile.baseline_fn(ctx) if profile.baseline_fn else profile.resting_baseline
        advance via gap-closure
    elif profile.clearance == "formula":
        assign profile.baseline_fn(ctx)
    clamp to critical_low / critical_high
    apply soft/hard saturation

for each chemical in REGISTRY:
    for each interaction in profile.interactions:
        if threshold crossed: apply delta to target
```

Chemicals that currently have per-chemical branches in the engine (epinephrine,
endorphins, melatonin, glucose, hydration, sleep_pressure) get their logic encoded
in their profile's clearance type and parameters. The engine branch disappears.

---

## Constants Consolidation

`constants.py` at 735 lines is where tuning lives. This is fine — but constants should
be semantically organized and clearly owned by their chemical or subsystem.

**Not proposing to remove `constants.py`**. Proposing to:

1. Add a comment header to each constant group linking it to the chemical/subsystem it belongs to
2. Move the three melatonin constants currently imported by `registry.py` into the cortex-level constants section — registry should not import from constants
3. Half-life values that are currently inline in `engine.py` (epinephrine 2-min, endorphins 25-min) move to constants with clear names: `EPINEPHRINE_PLASMA_HALF_LIFE_MINUTES = 2.0`

No deletions from constants.py unless a value is unreferenced after the refactor.

---

## decoder.py Simplification

After this spec, `decoder.py`'s bio report section does this:

1. Collect active chemical-level notes by scanning REGISTRY profiles
2. Evaluate COMPOUND_RULES (from `rules.py`) against bloodstream concentrations
3. Compute derived values (from `derived.py`) as before
4. Assemble bio report string

No lambdas, no inline thresholds, no BiologicalState attribute access inside
predicates. Everything reads from a flat `{chemical: concentration}` dict.

---

## What Changes

| File | Change |
|---|---|
| `src/engine/chem/profiles.py` | Add `clearance`, `plasma_half_life`, `pool`, `notes` fields to ChemicalProfile |
| `src/engine/chem/registry.py` | Add `clearance`, `plasma_half_life`, `pool`, `notes` to each profile; remove constants import |
| `src/engine/engine.py` | Replace per-chemical branches with generic clearance dispatch; advance bloodstream and synaptic pool separately |
| `src/engine/constants.py` | Add `EPINEPHRINE_PLASMA_HALF_LIFE_MINUTES`, `ENDORPHIN_PLASMA_HALF_LIFE_MINUTES`; add section headers |
| `src/brain/subconscious/decoder.py` | Replace INTERACTION_RULES with profile-note scan + compound rule evaluation; remove BiologicalState attribute access |
| `src/engine/rules.py` | **New** — CompoundRule dataclass + COMPOUND_RULES list (extracted from decoder.py) |
| `src/brain/amygdala/stimulus_encoder.py` | Replace chemical delta output with 5-dimension salience scoring; deterministic lookup maps scores to phasic deltas |
| `src/brain/cortex/cortex.py` | Drain amygdala queue pre-pipeline; drain hypothalamus queue post-response |
| `src/brain/hypothalamus/` | **New** — hypothalamus module; fires tonic/hormonal cascade post-response |

No new abstractions beyond CompoundRule.

---

## What Does NOT Change

- `derived.py` — second-order values are a separate concern; not touched by this spec
- `BiologicalState` — the full state object stays; only the flat bloodstream dict gets
  a cleaner interface for rule evaluation
- Subsystem files (HPA, immune, pain, etc.) — they write to the secretion queue and
  state fields; that interface is unchanged
- Substance system — same queue-based write path
- `constants.py` values — no value changes, only organization and two new names

---

## Open Questions

1. **Compound rules with derived values**: Some current INTERACTION_RULES predicates
   check derived values (`d['cognitive_clarity'] < 15`, `d['anxiety'] > 60`). Derived
   values are computed from the bloodstream, not stored. The compound rule lambda
   could accept `(s: dict, d: dict)` where `d` is the derived dict — same as today,
   just cleaner. Is this acceptable or do we want compound rules to operate only on
   raw plasma concentrations?

2. **Subsystem-managed chemicals**: Some chemicals (sleep_pressure, GABA, glutamate,
   anandamide, two_ag, glucose) are currently skipped in the main advancement loop
   because their subsystems manage them. After this spec, do they get profiles with
   `clearance = "formula"` and the subsystem becomes the `baseline_fn`? Or do we keep
   the skip list? The profile approach is cleaner; the skip list is simpler.

3. **Half-life granularity**: The epinephrine plasma half-life is ~2 minutes in real
   biology. At sim tick rates, a 2-minute half-life may be too aggressive or not
   aggressive enough depending on how fast sim-time runs. Should `plasma_half_life`
   be validated against the minimum tick interval, or is that the engine's problem?

4. **Interaction rate units**: Current interactions use `rate_per_hour` applied as
   `rate × sim_hours`. This works but is easy to mis-tune. Should Interaction carry
   a `half_life_minutes` instead, making the decay rate intuitive in the same way
   as chemical clearance?
