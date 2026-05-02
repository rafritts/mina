# SPEC-53: Simulation Rule Consolidation

**Status: DRAFT**

Absorbs: SPEC-37 (stochastic noise)

---

## Problem

Chemical behavior is fragmented across at least 8 tiers of code that don't agree with
each other. The epinephrine half-life bug (49-minute effective half-life from a
mismatched comment and formula) was a direct symptom. The deeper problem: there is no
single place to go to understand how a chemical behaves. Understanding cortisol requires
reading `registry.py`, `engine.py`, `constants.py`, subsystem files, and `decoder.py`.

The fix is consolidation. Each chemical's complete lifecycle — decay model, half-life,
threshold notes, cross-chemical interactions — lives in one place: its `ChemicalProfile`
in the registry. The engine becomes a generic executor. Rules move to a single file.

No behavior changes. This is cleanup that makes the system understandable and
maintainable, and lays the foundation for SPEC-54.

---

## Design Philosophy

**Biological constructs as metaphors, not constraints.** We use "plasma half-life",
"hepatic clearance", "reuptake transporter" because they give the system a coherent
mental model and produce realistic behavior. We do not need to match real
pharmacokinetics exactly. When tuning is needed, tune the half-life in one place and
it propagates everywhere.

**Simple parts, complex emergent behavior.** Each chemical has one decay model and one
set of parameters. Cross-chemical effects are explicit interactions, not scattered
hardcoding. The complexity of the simulation emerges from the interactions, not from
per-chemical special cases buried in the engine.

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
    pool: Literal["bloodstream", "synaptic"]   # which compartment this chemical lives in

    # --- Clearance ---
    clearance: Literal["exponential", "gap_closure", "formula"]
    plasma_half_life: Optional[float] = None   # minutes; required for exponential
    approach_rate: Optional[float] = None      # /sim-hour; required for gap_closure
    baseline_fn: Optional[Callable] = None     # required for formula; fallback for gap_closure dynamic targets
    resting_baseline: float = 0.0              # homeostatic target; 0 = no baseline

    # --- Physiological ranges ---
    resting_low: float = 0.0
    resting_high: float = 0.0
    critical_low: float = 0.0
    critical_high: float = 0.0

    # --- Display ---
    display_min: float = 0.0
    display_max: float = 0.0
    labels: list[tuple[float, str, str]] = field(default_factory=list)

    # --- Saturation ---
    soft_ceiling: Optional[float] = None
    hard_ceiling: Optional[float] = None
    soft_floor: Optional[float] = None
    hard_floor: Optional[float] = None

    # --- Biological notes ---
    # Threshold-triggered state descriptions read by the decoder.
    # (threshold, tag, description) — active when concentration crosses threshold.
    notes: list[tuple[float, str, str]] = field(default_factory=list)

    # --- Cross-chemical interactions ---
    interactions: list[Interaction] = field(default_factory=list)
```

Key additions over the current profile:

- `clearance` makes the decay model explicit and co-located with the chemical
- `plasma_half_life` in **minutes** — unambiguous, matches biological reference
- `pool` assigns the chemical to a compartment (used by SPEC-54; metadata only in this spec)
- `notes` replaces the single-chemical threshold cases in `INTERACTION_RULES`

### Clearance models

| Mechanism | Biological analog | Math | When to use |
|---|---|---|---|
| `exponential` | Hepatic/enzymatic first-order kinetics | `C(t) = C₀ × 0.5^(t / t½)` | Fast-clearing: epinephrine, endorphins, endocannabinoids |
| `gap_closure` | Homeostatic regulation — reuptake/receptor driven | `C += (target - C) × rate × Δt` | Most neurotransmitters |
| `formula` | Circadian or physiologically-forced value | Direct assignment from function | Melatonin, sleep pressure |

No other clearance models. If a chemical doesn't fit one of these three, that's a
design question to resolve before implementing.

---

## Interaction Model

Cross-chemical effects are defined on the **source** chemical's profile:

```python
@dataclass
class Interaction:
    target: str
    threshold: float
    direction: Literal["above", "below"]
    rate: float                            # delta/sim-hour applied to target
    tag: str
```

This replaces the scattered cross-chemical hardcoding in `engine.py`.

---

## Notes and Rules

`INTERACTION_RULES` in `decoder.py` contains two kinds of things:

1. **Single-chemical threshold descriptions** — "cortisol above 650 = acute stress"
2. **Multi-chemical compound descriptions** — "cortisol > 650 AND oxytocin < 28 = no anchor"

Type 1 moves onto the chemical's profile as `notes`. Type 2 moves to `rules.py` as
named `CompoundRule` entries.

### Chemical-level notes (on profile)

```python
notes=[
    (450.0, "elevated_cortisol", "Cortisol is elevated — stress response active."),
    (650.0, "acute_stress", "Acute stress. HPA axis fully engaged."),
    (800.0, "cortisol_flood", "Cortisol flooding. Cognitive function compromised."),
]
```

The decoder scans each chemical's notes and collects those whose threshold is crossed.
No lambda predicates — just threshold comparisons.

### Compound rules (rules.py)

```python
COMPOUND_RULES: list[CompoundRule] = [
    CompoundRule(
        tag="stress_with_anchor",
        condition=lambda s, d: s["cortisol"] > 650 and s["oxytocin"] > 57,
        description="Acute stress held together by a strong bond. Suppression has a cost.",
    ),
    ...
]
```

The lambda takes `s` (flat concentration dict) and `d` (derived values dict) — the
same two inputs the current predicates use, just consistently typed. No `BiologicalState`
attribute access inside rules.

---

## Stochastic Noise (absorbed from SPEC-37)

Real neurochemistry is not deterministic. Neurotransmitter release, receptor binding,
and hormonal secretion all have meaningful moment-to-moment variance. Without noise,
the same conversation at the same biological state always produces identical chemistry.

Noise is a per-chemical parameter on the profile and is applied in the engine loop.

### ChemicalProfile additions

```python
noise_sigma: float = 0.0       # std dev of per-tick Gaussian noise in native units
                                # 0.0 = no noise (default for formula chemicals)
```

`noise_sigma` is calibrated to the coefficient of variation (CV) observed in
physiological literature — most neurotransmitters run ~10–20% CV per minute. Examples:

| Chemical | noise_sigma | Rationale |
|---|---|---|
| dopamine | 3.0 pg/mL | ~3% CV, pulsatile VTA firing |
| serotonin | 0.4 ng/mL | smoother tonic release |
| cortisol | 8.0 nmol/L | high pulsatile variance |
| oxytocin | 0.3 pg/mL | slow, low variance |
| melatonin | 0.0 | formula-driven, no noise |

### Engine application

Applied after clearance, before cross-interactions:

```python
if profile.noise_sigma > 0:
    noise = random.gauss(0, profile.noise_sigma) * noise_scale
    value = clamp(value + noise, profile.critical_low, profile.critical_high)
```

`noise_scale` is a global scalar (default 1.0) that can be reduced for debugging or
increased to stress-test the sim. It is driven by state conditions:

- **Sleep**: `noise_scale *= 0.5` — CNS quiets significantly during NREM
- **High allostatic load**: cortisol and norepinephrine `noise_sigma *= 1.5` — dysregulation increases variance
- **High anxiety**: norepinephrine and GABA `noise_sigma *= 1.3` — labile arousal

Noise is always clipped to `critical_low` / `critical_high`. It cannot push a chemical
into a dangerous range on its own.

### Reproducibility

Noise is seedable via config: `"noise_seed": 42` for a fixed seed, `null` for true
random. Fixed seed lets you reproduce a specific trajectory when debugging, then
disable for production.

### Validator interaction

The resting state validator uses **rolling means** over the last 500 ticks rather than
point values when noise is enabled. A chemical that has settled within ±2σ of its
resting baseline for 500 consecutive ticks is considered stable. The validator reports
the rolling mean as the settled value and includes the measured noise amplitude.

### Not in this spec

Correlated noise between related chemicals (dopamine/norepinephrine co-varying during
sympathetic activation) is left for a future spec. Independent per-chemical noise is
sufficient for biological texture.

---

## Engine Becomes a Generic Executor

After this spec, `engine.py`'s advancement loop contains no per-chemical special cases:

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
        if threshold crossed: apply rate × sim_hours to target
```

Chemicals with current per-chemical engine branches (epinephrine, endorphins, melatonin,
glucose, hydration, sleep_pressure) get their logic encoded in their profile's clearance
type and parameters. The branch disappears.

---

## Constants Consolidation

`constants.py` at 735 lines is where tuning lives — that's fine. But values should be
clearly owned by their chemical or subsystem.

Changes:
1. Add section headers linking constant groups to the chemical/subsystem they belong to
2. Move the three melatonin constants imported by `registry.py` into the registry directly — registry should not import from constants
3. Half-life values currently inline in `engine.py` move to constants: `EPINEPHRINE_PLASMA_HALF_LIFE_MINUTES = 2.0`, `ENDORPHIN_PLASMA_HALF_LIFE_MINUTES = 25.0`

No value changes. No deletions unless a value is unreferenced after the refactor.

---

## decoder.py Simplification

After this spec, `decoder.py`'s bio report does:

1. Scan REGISTRY profiles → collect active `notes` (threshold crossed)
2. Evaluate `COMPOUND_RULES` from `rules.py` against `(concentrations, derived)` dicts
3. Compute derived values from `derived.py` as before
4. Assemble bio report string

No lambdas inline. No `BiologicalState` attribute access inside predicates.

---

## Resting State Validator

A core deliverable of this spec is a headless simulation runner that validates resting
chemical behavior by advancing the engine through N ticks of pure math — no LLM calls,
no stimuli, no encoder. Just the engine loop running forward in time.

### Purpose

The epinephrine half-life bug survived because there was no way to run the sim and ask
"does epinephrine actually clear in 2 minutes?" This tool answers that question for
every chemical at once. It is the regression harness for all future tuning changes.

### What it does

1. Load `BiologicalState` at default resting values
2. Advance the engine N ticks (configurable; default 10,000) at a fixed sim-time step
3. Record each chemical's concentration at every tick
4. At the end, compute per-chemical statistics: mean, min, max, std deviation, and
   final settled value
5. Compare settled values against each profile's `resting_baseline` and
   `resting_low`/`resting_high` range
6. Flag any chemical that:
   - Settled outside its `resting_low`/`resting_high` range
   - Drifted monotonically (never stabilized)
   - Hit `critical_low` or `critical_high` at any point
   - Has std deviation above a threshold (oscillating instead of settling)

### Output

Plain text report to stdout. One line per chemical:

```
PASS  cortisol        settled: 248.3 nmol/L   expected: 250.0   drift: -0.7%
PASS  epinephrine     settled:  44.8 pg/mL    expected:  45.0   drift: -0.4%
FAIL  serotonin       settled:  11.2 ng/mL    expected:  22.0   drift: -49.1%  [below resting_low]
WARN  melatonin       peak: 198.4 pg/mL  trough: 4.8 pg/mL  [circadian — range check only]
```

Circadian chemicals (`clearance = "formula"`) are not expected to settle — they get a
range check instead: peak and trough must fall within biological plausible bounds.

### Usage

```
python -m src.tools.sim_baseline
python -m src.tools.sim_baseline --ticks 10000 --step 0.05
python -m src.tools.sim_baseline --ticks 50000 --step 0.1 --chemical cortisol
```

`--step` is sim-hours per tick (default 0.05 = 3 sim-minutes). `--chemical` runs
the validator for a single chemical and prints its full concentration history.

### Implementation notes

- No I/O beyond reading the registry and default state. No file writes during the run.
- The engine's subsystem calls (HPA, immune, etc.) run normally — this validates the
  full system, not just the clearance math.
- Stimuli are not fired. The encoder does not run. This is resting state only.
- A separate `--stimulus` mode (future) could fire a single stimulus event and measure
  the chemical response curve — useful for validating lookup table magnitudes in SPEC-54.

---

## What Changes

| File | Change |
|---|---|
| `src/engine/chem/profiles.py` | Add `clearance`, `plasma_half_life`, `pool`, `notes` fields to `ChemicalProfile` |
| `src/engine/chem/registry.py` | Populate new fields on each profile; move melatonin constants inline |
| `src/engine/engine.py` | Replace per-chemical branches with generic clearance dispatch |
| `src/engine/constants.py` | Add `EPINEPHRINE_PLASMA_HALF_LIFE_MINUTES`, `ENDORPHIN_PLASMA_HALF_LIFE_MINUTES`; add section headers |
| `src/brain/subconscious/decoder.py` | Replace `INTERACTION_RULES` with profile-note scan + compound rule evaluation |
| `src/engine/rules.py` | **New** — `CompoundRule` dataclass + `COMPOUND_RULES` list |
| `src/tools/sim_baseline.py` | **New** — headless resting state validator; uses rolling means when noise is enabled |

---

## What Does NOT Change

- `derived.py` — untouched
- `BiologicalState` — untouched
- Subsystem files (HPA, immune, pain, etc.) — untouched
- Substance system — untouched
- All constant values — no tuning changes in this spec
- Encoder behavior — no changes to when or how chemistry fires

---

## Resolved Design Decisions

1. **Compound rules use `(s, d)`** — the brain responds to psychological states, not
   raw concentrations. Anxiety is a second-order state, not "norepinephrine above X."
   Compound rules receive both the concentration dict `s` and the derived values dict
   `d`. Biologically correct.

2. **Subsystem-managed chemicals get profiles; skip list removed** — all chemicals
   have biological clearance mechanisms. GABA has reuptake transporters (GAT-1),
   anandamide has FAAH enzymatic degradation, glucose has hepatic regulation. The skip
   list is an implementation artifact. Each gets a `clearance` profile; the subsystem
   becomes its `baseline_fn`. The engine skip list disappears.

3. **10-second ticks work correctly** — at 10s per tick (`sim_hours = 0.00278`),
   epinephrine decay factor is `0.5^(0.00278 / 0.0333) = 0.944` per tick. After 12
   ticks (2 real minutes), ~50% of excess cleared — matches the 2-minute half-life
   exactly. No validation needed at profile definition.

4. **Interactions keep `rate_per_hour`** — half-life implies decay toward zero, but
   interactions apply a continuous delta to a target that has its own homeostasis.
   `rate_per_hour` reads as "cortisol suppresses serotonin at 2 ng/mL/hr while above
   threshold" — semantically correct and unambiguous.
