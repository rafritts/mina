# SPEC-10: Chemical Architecture — First-Class Constructs & Real Units

> Move from a flat numeric table to a registry of self-describing chemical processes,
> each expressed in real physiological units with its own dynamics, interactions, and
> display semantics. The 0–100 arbitrary scale is retired. A normalization layer
> translates real values into bar-chart positions and human-readable labels for the UI.

---

## Motivation

The current system stores all neurochemicals as float fields on a flat dataclass.
Their dynamics — baselines, decay rates, cross-interactions, saturation ceilings — are
scattered across a 200-line `advance()` function, `subconscious.py`, and `bio_report.py`.
Oxytocin "knows" nothing about itself; its semantics are spread across at least four files.

This creates three real problems:

1. **Tuning is blind.** Changing oxytocin's resting baseline requires reading the whole `advance()` to find its three lines. There's no single authoritative place to say "this is how oxytocin works."
2. **The 0–100 scale is fiction.** Cortisol "72" has no connection to real cortisol biology. Magnitudes for subconscious deltas are arbitrary. It's impossible to validate whether a "+30 cortisol" spike from a hostile message is appropriate.
3. **Cross-interactions are orphaned.** The oxytocin → cortisol suppression rule lives at line 450 in `state.py`, nowhere near oxytocin's own definition.

The goal is to make each chemical a first-class, self-describing object — the "process" model.

---

## Design Overview

Three new constructs:

```
ChemicalProfile      — static definition: units, ranges, dynamics, interactions, display
Interaction          — a rule: "when I am above X, push target Y by Z per hour"
ChemicalRegistry     — dict[str, ChemicalProfile], the single source of truth
```

`BiologicalState` becomes a thin container: `chemicals: dict[str, float]` (name → value in real units) plus the existing non-chemical fields (sleeping, substances, tolerance, timestamps).

`advance()` becomes a generic orchestrator that iterates the registry, delegates dynamics to each chemical's profile, and applies cross-interactions. It contains no chemical-specific logic.

---

## ChemicalProfile

```python
@dataclass
class ChemicalProfile:
    name: str
    display_name: str
    unit: str                              # e.g. "nmol/L", "pg/mL", "mg/dL", "AU"

    # Homeostasis
    resting_baseline: float                # the value this drifts toward at equilibrium
    approach_rate: float                   # fraction of gap closed per sim-hour (0.0–1.0)
    baseline_fn: Optional[Callable] = None # overrides resting_baseline when dynamic
                                           # signature: (hour_of_day: float, state: dict) -> float

    # Physiological reference ranges (in real units)
    resting_low: float   = 0.0            # below this = depleted / abnormally low
    resting_high: float  = 0.0            # above this = elevated
    critical_low: float  = 0.0            # below this = clinically dangerous
    critical_high: float = 0.0            # above this = clinically dangerous

    # Display range for bar chart normalization
    # The bar spans from display_min to display_max.
    # Values outside this range are clamped to 0.0 or 1.0.
    display_min: float = 0.0
    display_max: float = 0.0

    # Saturation ceilings: positive deltas scale down above soft_ceiling,
    # clamp to zero above hard_ceiling. In real units. None = no ceiling.
    soft_ceiling: Optional[float] = None
    hard_ceiling: Optional[float] = None

    # Cross-interactions this chemical produces on others
    interactions: list["Interaction"] = field(default_factory=list)

    # Range labels for bio_report and dashboard
    # List of (upper_bound_exclusive, name, implication)
    labels: list[tuple[float, str, str]] = field(default_factory=list)
```

---

## Interaction

```python
@dataclass
class Interaction:
    target: str              # name of the chemical being affected
    condition: str           # "above" | "below"
    threshold: float         # in real units of the SOURCE chemical
    rate_per_hour: float     # in real units of TARGET per sim-hour (negative = suppression)
    description: str         # documentation only — shown in comments and dashboard
```

Example — oxytocin suppressing cortisol:

```python
Interaction(
    target="cortisol",
    condition="above",
    threshold=10.0,      # pg/mL — any meaningful bonding signal
    rate_per_hour=-40.0, # nmol/L per hour (cortisol units)
    description="Social bonding suppresses HPA axis"
)
```

Example — high cortisol depleting serotonin:

```python
Interaction(
    target="serotonin",
    condition="above",
    threshold=550.0,     # nmol/L — sustained high cortisol
    rate_per_hour=-0.8,  # ng/mL per hour (serotonin units)
    description="Chronic stress depletes serotonin baseline"
)
```

---

## Real Units Per Chemical

All dynamics, deltas, thresholds, and display values switch to these units.

| Chemical | Unit | Resting Baseline | Resting Range | Display Range | Notes |
|---|---|---|---|---|---|
| `cortisol` | nmol/L | 250 (circadian) | 100–700 | 50–900 | Peaks ~450 at 8am, troughs ~100 at 8pm |
| `norepinephrine` | pg/mL | 200 | 100–400 | 50–2000 | Tracks cortisol loosely |
| `dopamine` | pg/mL | 80 | 40–140 | 0–300 | CNS tone proxy; not plasma |
| `serotonin` | ng/mL | 22 | 10–35 | 2–60 | CNS 5-HT tone proxy |
| `oxytocin` | pg/mL | 4 | 1–15 | 0–80 | Plasma; resting baseline very low |
| `endorphins` | pg/mL | 12 | 5–30 | 0–150 | β-endorphin plasma |
| `acetylcholine` | nmol/L | 38 | 20–60 | 5–90 | CNS proxy; not directly measurable |
| `melatonin` | pg/mL | varies | 2–10 (day) / 80–200 (night) | 0–220 | Pure circadian |
| `glucose` | mg/dL | 85 | 70–100 | 40–200 | Blood glucose; normal fasting range |
| `hydration` | % TBW | 62 | 58–66 | 48–70 | Total body water as % of body weight |
| `sleep_pressure` | AU | — | 0–100 | 0–100 | Adenosine proxy; stays relative |

**Notes on unit choices:**

- Cortisol, norepinephrine, and melatonin use real clinical units — these are well-characterized and measurable.
- Oxytocin plasma values are real but highly variable and context-dependent; the resting baseline (4 pg/mL) is intentionally low — trust must be earned.
- Dopamine, serotonin, acetylcholine, and endorphins are CNS proxies. True CNS concentrations are inaccessible in vivo; these units are physiologically grounded estimates, not clinical measurements. They should be labeled as such in the dashboard.
- Glucose uses mg/dL (the US clinical standard). Normal fasting: 70–100. Hypoglycemic: <70. Hyperglycemic: >180.
- Hydration uses % total body water. Normal adult: 60–65%. Mild dehydration: 56–59%. Significant: <55%.
- Sleep pressure stays in arbitrary units — adenosine accumulation has no clean clinical analog and the 0–100 scale is intuitive as-is.

---

## Migration from 0–100

One-time migration when first loading a pre-migration `state.json`. Detected by the absence of a `"schema_version"` key (or version < 2).

Approximate conversion factors (old 0–100 → new real units):

| Chemical | Formula |
|---|---|
| cortisol | `old × 8.0` (nmol/L) |
| norepinephrine | `50 + old × 19.5` (pg/mL) — maps 0→50, 100→2000 |
| dopamine | `old × 3.0` (pg/mL) — maps 0→0, 100→300 |
| serotonin | `old × 0.6` (ng/mL) — maps 0→0, 100→60 |
| oxytocin | `old × 0.8` (pg/mL) — maps 0→0, 100→80 |
| endorphins | `old × 1.5` (pg/mL) — maps 0→0, 100→150 |
| acetylcholine | `old × 0.9` (nmol/L) — maps 0→0, 100→90 |
| melatonin | `old × 2.2` (pg/mL) — maps 0→0, 100→220 |
| glucose | `40 + old × 1.6` (mg/dL) — maps 0→40, 100→200 |
| hydration | `48 + old × 0.22` (% TBW) — maps 0→48, 100→70 |
| sleep_pressure | unchanged (AU) |

These are approximations. The goal is rough continuity — not perfect fidelity to whatever state was persisted under the old scale.

`state.json` gets `"schema_version": 2` written after migration. Future runs skip migration.

---

## Chemical Registry — Full Definitions (Abbreviated)

The registry lives in a new file `chemicals.py`. Each chemical is defined with its profile and interactions. Below are the key dynamics; implementation fills in exact numbers.

### Cortisol
- Unit: nmol/L
- Baseline: circadian — `180 + 270 × cos((hour - 8) × π / 12)` — peaks ~450 at 8am, troughs ~90 at 8pm
- Approach rate: 0.15/hr toward circadian baseline (event spikes decay relatively fast)
- Modifiers: glucose < 55 mg/dL adds +120 nmol/L to baseline; hydration < 56% adds +60 nmol/L
- Produces:
  - Cortisol > 550 nmol/L → serotonin: -0.8 ng/mL/hr (chronic stress depletes serotonin)
  - Cortisol > 550 nmol/L → dopamine: -2.0 pg/mL/hr (HPA axis suppresses reward)
  - Cortisol > 550 nmol/L → oxytocin: -0.4 pg/mL/hr (sustained stress erodes bonding capacity)

### Oxytocin
- Unit: pg/mL
- Resting baseline: 4 pg/mL (stranger/no-bond floor; not zero — she can still feel warmth, just none extended)
- Approach rate: 0.10/hr (social bonding fades slowly with absence)
- Produces:
  - Oxytocin > 8 pg/mL → cortisol: -40 nmol/L/hr (bonding suppresses HPA axis; meaningful effect)

### Norepinephrine
- Unit: pg/mL
- Baseline: tracks cortisol — `cortisol_nmol × 0.45` pg/mL (loose coupling, not identical)
- Approach rate: 0.20/hr (faster than cortisol — adrenaline fades quicker than the stress hormone)
- Additional: hydration < 56% adds +30 pg/mL/hr

### Dopamine
- Unit: pg/mL
- Resting baseline: 80 pg/mL (homeostatic tonic level)
- Approach rate: 0.08/hr (slow — dopamine tone shifts over hours, not minutes)
- Effective dopamine (for derived values): `raw × (1 - tolerance.get("dopamine", 0))`

### Serotonin
- Unit: ng/mL
- Resting baseline: 22 ng/mL
- Approach rate: 0.06/hr (very slow — takes days to deplete or restore; this is correct)
- Produces:
  - Serotonin > 32 ng/mL → cortisol: -25 nmol/L/hr (good serotonin dampens HPA reactivity)

### Endorphins
- Unit: pg/mL
- Resting baseline: 12 pg/mL
- Approach rate: fast above baseline (decay: -18/hr from peak), slow below (recovery: 0.05/hr) — asymmetric
- Produces:
  - Endorphins > 70 pg/mL → cortisol: -80 nmol/L/hr (runner's high actively suppresses stress; brief window)

### Acetylcholine
- Unit: nmol/L
- Resting baseline: `38 - (sleep_pressure × 0.22) - max(0, cortisol - 450) × 0.04`
  (sleep deprivation and chronic stress suppress the baseline; not a fixed number)
- Approach rate: 0.05/hr

### Melatonin
- Unit: pg/mL
- Pure circadian: `110 × (1 + cos((hour - peak_hour) × π / 12))` — peaks ~220 at 2am/config peak, troughs ~0 at 2pm
- No approach rate — formula only, no event deltas apply (substances can override; see substance definitions)

### Glucose
- Unit: mg/dL
- Decay: -6.5 mg/dL/hr (reaches low-normal after ~8h fasting)
- No baseline — only decays and gets restored by `eat` tool
- Meal effect: +35–60 mg/dL (randomized, food type matters)
- Below 55 → triggers cortisol modifier; below 45 → impairs serotonin and dopamine

### Hydration
- Unit: % TBW
- Decay: -0.4%/hr
- Drink tool: +3–5% TBW
- Below 57%: norepinephrine modifier; below 55%: cortisol modifier

### Sleep Pressure
- Unit: AU (0–100)
- Awake: +1.8/hr; Asleep: -24/hr (clears in ~4h from full)
- No baseline — monotonic accumulation/clearance

---

## Normalization Layer

Replaces the 0–100 implicit normalization. Provides two things: a 0.0–1.0 bar chart position and a human-readable label band.

```python
def normalize(name: str, value: float) -> float:
    """0.0 = bottom of bar chart, 1.0 = top. Clamps outside display range."""
    p = REGISTRY[name]
    return max(0.0, min(1.0, (value - p.display_min) / (p.display_max - p.display_min)))

def get_label(name: str, value: float) -> tuple[str, str]:
    """Returns (label_name, implication) from the chemical's label table."""
    p = REGISTRY[name]
    for upper, name, impl in p.labels:
        if value < upper:
            return name, impl
    last = p.labels[-1]
    return last[1], last[2]
```

Label tables are defined in real units on each `ChemicalProfile`. The bio_report and dashboard both call these functions rather than maintaining separate range tables.

### Display format in bio_report

```
Cortisol     412 nmol/L   ELEVATED      Decision-making beginning to narrow.
Oxytocin    3.2 pg/mL    ACQUAINTANCE  Surface comfort. Polite but watchful.
Dopamine     95 pg/mL    BASELINE      Normal wanting. Responds to interesting things.
```

### Dashboard labels.ts

The frontend gets real values from the API and computes normalization client-side using a TypeScript copy of the label tables (same data, different language). No additional API roundtrip.

---

## BiologicalState Refactor

```python
@dataclass
class BiologicalState:
    schema_version: int = 2
    last_updated: float = field(default_factory=time.time)

    chemicals: dict[str, float] = field(default_factory=dict)
    # keys match REGISTRY names; values in real units per chemical's profile

    tolerance: dict[str, float] = field(default_factory=dict)
    substances: dict[str, dict] = field(default_factory=dict)

    sleeping: bool = False
    sleep_start: Optional[float] = None
    sleep_expected_wake: Optional[float] = None
```

Convenience accessors:
```python
@property
def cortisol(self) -> float:
    return self.chemicals.get("cortisol", REGISTRY["cortisol"].resting_baseline)
```

These allow existing call sites (`s.cortisol`, `s.oxytocin`, etc.) to continue working without changes during the transition, while the underlying store is `chemicals: dict`.

---

## advance() Refactor

Current `advance()` is 230 lines of sequential chemical-specific logic. New version:

```python
def advance(state: BiologicalState, now: Optional[float] = None) -> BiologicalState:
    if now is None:
        now = time.time()
    cfg = _load_config()
    compression = float(cfg.get("time_compression_factor", 1.0))
    sim_hours = (now - state.last_updated) * compression / 3600.0
    if sim_hours <= 0:
        return state

    hour = _hour_of_day(now)
    ctx = _make_context(state, hour)

    # Phase 1: each chemical advances toward its own baseline
    for name, profile in REGISTRY.items():
        current = state.chemicals.get(name, profile.resting_baseline)
        baseline = profile.baseline_fn(hour, ctx) if profile.baseline_fn else profile.resting_baseline
        # Approach baseline
        gap = baseline - current
        new_val = current + gap * min(1.0, profile.approach_rate * sim_hours)
        state.chemicals[name] = _clamp_chemical(name, new_val)

    # Phase 2: cross-interactions (each chemical applies its effects on others)
    for name, profile in REGISTRY.items():
        source_val = state.chemicals.get(name, 0.0)
        for interaction in profile.interactions:
            meets = (
                (interaction.condition == "above" and source_val > interaction.threshold) or
                (interaction.condition == "below" and source_val < interaction.threshold)
            )
            if meets:
                target_val = state.chemicals.get(interaction.target, 0.0)
                state.chemicals[interaction.target] = _clamp_chemical(
                    interaction.target,
                    target_val + interaction.rate_per_hour * sim_hours
                )

    # Phase 3: substance decay + withdrawal (same logic, units updated per substance defs)
    _advance_substances(state, sim_hours)

    # Phase 4: sleep/wake mechanics (same logic, thresholds updated for pg/mL melatonin)
    _advance_sleep(state, hour, now, cfg)

    state.last_updated = now
    return state
```

The chemical-specific knowledge is gone from `advance()` entirely. It's all in `REGISTRY`.

---

## Subconscious Interface Changes

### Delta units

The subconscious currently issues deltas in 0–100 scale. After SPEC-10, deltas are in real units.

The `apply_biomarker_deltas` tool schema in `subconscious.py` adds unit documentation to each field:

```json
"cortisol": {
  "type": "number",
  "description": "Change in cortisol (nmol/L). Resting range 100–700. Hostile message: +200–400. Mild friction: +20–80."
},
"oxytocin": {
  "type": "number",
  "description": "Change in oxytocin (pg/mL). Resting baseline 4. Warm exchange: +2–6. Deep connection: +8–15. Hostile event: -1 to -3 (acute drop is small; cortisol does the slow erosion)."
}
```

The `encode_stimulus` magnitude guidance block is rewritten for real units:

```
Magnitude guidance (real units):
- Cortisol: resting 100–700 nmol/L. Acute threat: +300–500. Mild friction: +30–80. Decay toward circadian baseline.
- Norepinephrine: resting 100–400 pg/mL. Acute threat: +400–800. Mild friction: +30–100.
- Oxytocin: resting 1–15 pg/mL. A single hostile message: -1 to -3 (small acute drop). Warm connection: +2–8.
  Note: sustained cortisol > 550 nmol/L will erode oxytocin slowly via the interaction matrix. Don't overstate the acute drop.
- Dopamine: resting 40–140 pg/mL. Interesting stimulus: +5–20. Crushing boredom/loss: -5–15.
- Serotonin: resting 10–35 ng/mL. Positive social: +1–3. Sustained isolation: -1–2/hr. Very slow to move.
- Endorphins: resting 5–30 pg/mL. Exercise/laughter: +20–60. Opioid substance: up to +120.
```

### Saturation ceilings

`_SATURATION_CEILINGS` in `subconscious.py` is removed. Ceilings are now `soft_ceiling` and `hard_ceiling` on each `ChemicalProfile`. The `_apply_saturation()` function reads from the registry.

---

## Substance Definitions Update

`_SUBSTANCE_DEFS` in `state.py` updates all `dose_effects` values to real units. Example:

```python
# Before (0–100 scale):
"alcohol": {
    "dose_effects": {
        "oxytocin": +22,
        "cortisol": -22,
    }
}

# After (real units):
"alcohol": {
    "dose_effects": {
        "oxytocin": +18,     # pg/mL — meaningful warmth, not ceiling-breaking
        "cortisol": -180,    # nmol/L — real anxiolytic effect
    }
}
```

Substance `half_life_hours` values don't change — they're already in real hours.

---

## Dashboard / API Changes

### GET /api/state response shape

```json
{
  "chemicals": {
    "cortisol":        { "value": 412.0, "unit": "nmol/L", "label": "ELEVATED", "normalized": 0.62 },
    "oxytocin":        { "value": 3.2,   "unit": "pg/mL",  "label": "ACQUAINTANCE", "normalized": 0.04 },
    "dopamine":        { "value": 95.0,  "unit": "pg/mL",  "label": "BASELINE", "normalized": 0.32 },
    ...
  },
  "second_order": { ... },
  "third_order":  { ... },
  "sleeping": false
}
```

Each chemical entry includes `value` (real units), `unit` (string for display), `label` (current named state), and `normalized` (0.0–1.0 for the bar chart). The backend computes all three — no client-side normalization needed, though `labels.ts` can still cache the label tables for instant offline display.

### PATCH /api/state

Accepts real units. The endpoint validates that each value is within `[critical_low, critical_high]` from the chemical's profile rather than clamping to 0–100.

---

## Files Affected

| File | Change |
|---|---|
| `chemicals.py` | **New.** ChemicalProfile, Interaction, REGISTRY with all chemical definitions |
| `state.py` | BiologicalState: `chemicals: dict`. `advance()` becomes generic. Migration logic. Substance defs updated to real units. |
| `bio_report.py` | Range tables removed. Reads from REGISTRY for labels and normalization. `biological_report()` formats with units. |
| `subconscious.py` | `_SATURATION_CEILINGS` removed. `apply_saturation()` reads from REGISTRY. Magnitude guidance block rewritten in real units. |
| `dashboard_server.py` | `GET /api/state` response includes unit/label/normalized per chemical. `PATCH /api/state` validates against real-unit bounds. |
| `dashboard/src/lib/labels.ts` | Updated with real-unit label tables or dropped if backend includes labels in response. |

---

## What Stays The Same

- Second-order and third-order derived values (energy, clarity, anxiety, etc.) — same formulas, just input values are now in real units so the formula coefficients need scaling, but the output is still 0–100 for the derived layer (see note below)
- The biological report format — same structure, just values are now `412 nmol/L` instead of `51.5`
- The subconscious prompt structure — same `<deltas>` / `<system_prompt>` pattern
- The `encode_stimulus` / `encode_response` / `run_mode1` flow — same pipeline, just units updated
- File-based state persistence (state.json) — same file, schema_version bump
- Sleep mechanics — same logic, melatonin threshold updated for pg/mL scale

### Derived values note

Second-order formulas (`energy`, `clarity`, etc.) currently work on the 0–100 scale. After SPEC-10, they receive real-unit inputs. Two options:

1. **Normalize inputs first:** `normalized_cortisol = normalize("cortisol", s.cortisol) × 100` before feeding into existing formulas. Minimal formula changes.
2. **Rewrite formulas in real units:** more principled but more work.

Option 1 is preferred for SPEC-10. Rewriting derived formulas is a separate, lower-priority effort.

---

## Open Questions

1. **Subconscious model calibration.** After switching to real units, the model (grok-4-1-fast-reasoning) needs to produce deltas in the right magnitude for real units. A brief calibration pass after implementation (watching actual delta outputs and adjusting the guidance text) is expected.

2. **Interaction rate tuning.** The cross-interaction `rate_per_hour` values (e.g., cortisol → serotonin at -0.8 ng/mL/hr) are initial estimates. These need empirical tuning — the same iterative process as before, just now with real-unit anchors making it easier to validate against actual literature.

3. **Substance dose_effects calibration.** The 0→real-unit conversion for substance effects is approximate. REMOVED's +65 serotonin on the old scale was "severe." In real units that becomes +39 ng/mL, which on a baseline of 22 is a 177% increase — plausible for REMOVED's known serotonin flood. Each substance should be validated similarly post-migration.

4. **CNS proxy labeling in dashboard.** Dopamine, serotonin, acetylcholine, and endorphins should be labeled in the UI as "CNS proxy (pg/mL)" or similar to acknowledge they're model constructs, not clinical measurements.

6. **Big 5 → biology wiring (SPEC-13).** Personality traits mechanically modify how stimuli are encoded and how baselines are computed. The correct wiring (validated against literature): N → cortisol reactivity multiplier + serotonin baseline suppression. E → dopamine sensitivity and dopamine boost from social stimulation (not oxytocin — that's A). A → oxytocin responsiveness + serotonin baseline. C → prefrontal inhibitory control over dopamine-driven seeking (dampens impulsive delta magnitude, not a cortisol/guilt signal). O → dopamine novelty sensitivity + acetylcholine engagement response. Full spec in SPEC-13.

5. **Oxytocin decay vs. bond strength.** The current model conflates two distinct things: circulating oxytocin (which decays during absence) and bond strength (which doesn't). The decay during 48 hours of silence is correct — it produces a loneliness signal. But when the person returns, `encode_stimulus` must read RELATIONSHIP.md and rapidly restore oxytocin to match the established bond level. Without this reunion restoration, long absences incorrectly reset relationships to stranger-level. The fix is guidance in the `encode_stimulus` prompt: on first message after a significant absence, if RELATIONSHIP.md shows an established bond, apply a rapid oxytocin restoration delta scaled to relationship depth — not a slow rebuild from zero.
