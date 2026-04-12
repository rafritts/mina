# SPEC-26: Dashboard Overhaul

## Overview

Replace the current flat, single-page biological state viewer with a multi-tier scientific visualization dashboard that mirrors the new BiologicalState v3 structure from SPEC-20 through SPEC-25. Remove the admin, monologue, and relationship sections entirely. Add a control panel for simulation management. Extract reusable Svelte components for the greatly expanded chemical surface.

---

## Goals

- Visualize all biological tiers from SPEC-20/21/22/23/24: neuro, neuroendocrine, immune, pain, neuroplasticity, circadian, and receptor sensitivity
- Keep existing: substances page, events/logs page, vital signs, presets, derived values, session tokens
- Remove entirely: admin section (system prompt override, revelation, subconscious injection), monologue page, relationship page
- Add: control panel route with sim tools (presets, manual advance, heartbeat trigger, HPA cascade viewer)
- Expand `labels.ts` with complete label tables for all new chemicals (7–9 levels each, experiential implication strings)
- Extract reusable Svelte components to manage the complexity of 50+ monitored values
- Add label depth indicator to the TypeScript label system, mirroring the Python `get_label_with_depth()` from SPEC-20

---

## Non-Goals

- No new backend simulation logic (see SPEC-20 through SPEC-25)
- No real-time WebSocket streaming (polling is fine)
- No user accounts or multi-user support
- No charting/graphs of historical values (single-point-in-time snapshot per refresh)

---

## Routes After Overhaul

| Route | Action | Description |
|---|---|---|
| `/state` | Redesign | Tabbed biological visualization, all tiers |
| `/control` | New | Control panel: presets, advance, heartbeat, HPA queue |
| `/substances` | Keep as-is | Substance dosing (no changes needed) |
| `/events` | Keep as-is | Encoder event log (no changes needed) |
| `/admin` | Delete | Remove entirely |
| `/monologue` | Delete | Remove entirely |
| `/relationship` | Delete | Remove entirely |

Nav bar: `State | Control | Substances | Logs`

---

## Backend Endpoints: Remove

These endpoints are no longer needed once the admin, monologue, and relationship pages are removed. Remove them from `dashboard_server.py`.

```
DELETE  /api/admin            → remove
GET     /api/admin/pending    → remove
POST    /api/admin            → remove
GET     /api/inject/pending   → remove
POST    /api/inject           → remove
DELETE  /api/inject           → remove
GET     /api/monologue        → remove
GET     /api/relationship     → remove
POST    /api/reveal           → remove
```

Keep:
```
GET    /api/state
PATCH  /api/state
GET    /api/events
GET    /api/tokens
GET    /api/substance
POST   /api/substance/{name}/dose
DELETE /api/substance/{name}
POST   /api/heartbeat         ← moved to Control panel
GET    /api/heartbeat/status
GET    /healthz
```

---

## Backend Endpoint: Expand `/api/state`

The current `/api/state` response returns only `chemicals`, `sleeping`, `second_order`, `third_order`, `vital_signs`. The overhaul requires all BiologicalState v3 tiers.

### New Response Shape

```typescript
interface StateData {
  // Existing — unchanged
  chemicals:    Record<string, ChemicalEntry>;   // neuro chemicals
  sleeping:     boolean;
  second_order: Record<string, number>;          // 0–100
  third_order:  Record<string, number>;          // 0–100
  vital_signs:  Record<string, VitalEntry>;

  // New tiers — all read-only, driven by simulation
  neuroendocrine:      Record<string, number>;   // real physiological units
  immune:              Record<string, number>;   // real physiological units
  pain:                Record<string, number>;   // real physiological units
  neuroplasticity:     Record<string, number>;   // mixed units
  body:                Record<string, number>;   // circadian / physical
  receptor_sensitivity: Record<string, number>; // 0.5–2.0 multiplier
  cascade_queue:        CascadeEvent[];          // pending HPA delay events
  allostatic_load:      number;                  // 0.0–1.0
  cycle_day:            number;                  // 0–27 (sex hormone cycle position)
}

interface ChemicalEntry {
  value:      number;
  unit:       string;
  label:      string;
  normalized: number;  // 0.0–1.0
}

interface VitalEntry {
  value?:     number;
  systolic?:  number;
  diastolic?: number;
  unit:       string;
  label:      string;
}

interface CascadeEvent {
  type:            string;   // "acth_release" | "cortisol_release"
  fires_at_unix:   number;   // epoch seconds
  magnitude:       number;
}
```

### Fields by Tier

**`neuroendocrine`** (from SPEC-22):
```
crh           nmol/L      CRH (corticotropin-releasing hormone)
acth          pmol/L      ACTH (adrenocorticotropic hormone)
cortisol      nmol/L      (moved here from chemicals; compat shim keeps old key)
tsh           mIU/L       thyroid-stimulating hormone
t4_free       pmol/L      free thyroxine
t3_free       pmol/L      free triiodothyronine
estradiol     pg/mL       (women: 28-day cycle driven)
progesterone  ng/mL       (women: 28-day cycle driven)
testosterone  ng/dL       
ghrelin       pg/mL       hunger hormone (rises when hungry)
leptin        ng/mL       satiety hormone
insulin       μU/mL       
vasopressin   pg/mL       (ADH — hydration + bonding)
prolactin     ng/mL       
growth_hormone ng/mL      
dhea          μg/dL       
```

**`immune`** (from SPEC-23):
```
il1b              pg/mL    IL-1β (pro-inflammatory)
il6               pg/mL    IL-6 (pro-inflammatory)
tnf_alpha         pg/mL    TNF-α (pro-inflammatory)
crp               mg/L     C-reactive protein (acute phase)
il10              pg/mL    IL-10 (anti-inflammatory)
inflammation_index  0–1    composite (weighted cytokines)
```

**`pain`** (from SPEC-23):
```
substance_p           pg/mL    primary nociceptive transmitter
pge2                  pg/mL    prostaglandin E2 (sensitizer)
pain_intensity          0–1    gate-control output (experienced pain)
central_sensitization   0–1    chronic sensitization level
vagal_tone              0–1    parasympathetic tone (HRV proxy)
```

**`neuroplasticity`** (from SPEC-24):
```
bdnf                 ng/mL    brain-derived neurotrophic factor
synaptic_potentiation  0–1    LTP/LTD balance
```

**`body`** (from SPEC-24, circadian + physical):
```
core_body_temp    °C     (36.1–37.5 normal; circadian ~0.5°C swing)
adenosine         nM     Process S (homeostatic sleep drive; also in chemicals for compat)
orexin            pg/mL  wakefulness drive
circadian_phase   0–1    position in 24h cycle (0=midnight, 0.5=noon)
```

**`receptor_sensitivity`** (from SPEC-21):
```
d1     0.5–2.0   dopamine D1
d2     0.5–2.0   dopamine D2
ht1a   0.5–2.0   serotonin 5-HT1A
ht2a   0.5–2.0   serotonin 5-HT2A
gabaa  0.5–2.0   GABA-A
gabab  0.5–2.0   GABA-B
nmda   0.5–2.0   glutamate NMDA
ampa   0.5–2.0   glutamate AMPA
cb1    0.5–2.0   cannabinoid CB1
cb2    0.5–2.0   cannabinoid CB2
a1     0.5–2.0   adenosine A1
a2a    0.5–2.0   adenosine A2A
```

---

## New Backend Endpoint: `/api/state/advance`

Add a new endpoint to manually tick the simulation forward (for the Control panel).

```python
# POST /api/state/advance
# Body: {"hours": float}  — max 24.0 per call
# Action: calls bio.advance(state, sim_hours=hours), saves state
# Returns: updated StateData
```

---

## File Structure

### Files to Delete
```
dashboard/src/routes/admin/+page.svelte
dashboard/src/routes/monologue/+page.svelte
dashboard/src/routes/relationship/+page.svelte
```

### Files to Create
```
dashboard/src/lib/components/ChemicalSlider.svelte   — editable chemical row
dashboard/src/lib/components/ChemicalReadOnly.svelte — read-only progress row
dashboard/src/lib/components/DerivedMeter.svelte     — derived value progress + badge
dashboard/src/lib/components/TierCard.svelte         — collapsible section card wrapper
dashboard/src/routes/control/+page.svelte            — new control panel page
```

### Files to Modify
```
dashboard/src/lib/labels.ts                          — expand with all new chemicals
dashboard/src/lib/api.ts                             — add StateData v3 types
dashboard/src/routes/state/+page.svelte              — full redesign, tabbed layout
dashboard/src/routes/+layout.svelte                  — update nav links
```

---

## Component Specifications

### `ChemicalSlider.svelte`

Editable chemical row: field name (with tooltip) + label badge + unit + numeric value + range slider. Emits `change` event when slider settles (after 400ms debounce + mouse-up). Saving spinner while PATCH in-flight.

```typescript
// Props
export let field: string;
export let label: string;          // display name
export let value: number;          // current real-unit value
export let unit: string;
export let min: number;
export let max: number;
export let tooltip: string;
export let saving: boolean = false;

// Events
// dispatch('change', { field, value })
```

### `ChemicalReadOnly.svelte`

Read-only progress row: field name (with tooltip) + label badge + unit + numeric value + progress bar. No interaction. Used for simulation-driven chemicals the user cannot set directly.

```typescript
export let field: string;
export let label: string;
export let value: number;
export let unit: string;
export let normalized: number;  // 0.0–1.0 for progress bar
export let tooltip: string;
export let dimmed: boolean = false;  // opacity-60 for circadian-formula fields
```

### `DerivedMeter.svelte`

Derived value row: field name (with tooltip) + label badge + numeric (0–100) + progress bar.

```typescript
export let field: string;
export let label: string;
export let value: number;    // 0–100
export let tooltip: string;
```

### `TierCard.svelte`

Collapsible card with header, tier label, and slot for content. Default open for primary tiers, collapsed for receptor sensitivity.

```typescript
export let title: string;
export let defaultOpen: boolean = true;
export let badge: string = '';   // optional count badge e.g. "12 values"
```

---

## State Page: Tabbed Layout

The `/state` page switches to a tab-based layout. Six tabs. The left/right two-column grid is preserved within tabs that have editable sliders.

```
[Overview]  [Neuro]  [Endocrine]  [Immune/Pain]  [Circadian/Sleep]  [Plasticity]
```

### Tab 1: Overview

Quick health summary — one glance shows the full picture.

- Sleeping badge (awake/sleeping)
- Second-order derived meters: energy, cognitive_clarity, hedonic_tone, social_warmth, arousal, mood_valence (6 DerivedMeter rows)
- Third-order derived meters: anxiety, depression, boredom, loneliness, flow (5 DerivedMeter rows) + new `physical_distress` (from SPEC-24)
- Vital signs card (unchanged from current)
- Allostatic load meter (0.0–1.0 progress bar, labeled: LOW / BUILDING / HIGH / CRITICAL)
- Session tokens table (unchanged from current)

### Tab 2: Neuro

Two columns: left = editable sliders, right = read-only derived.

**Left — Editable (ChemicalSlider):**
- Homeostatic group: adenosine (replaces sleep_pressure; AU compat label kept), glucose, hydration
- Neuromodulators: dopamine, serotonin, norepinephrine, oxytocin, endorphins, acetylcholine
- New inhibitory/excitatory: GABA, glutamate
- New endocannabinoids: anandamide, 2-AG

**Right — Read-only:**
- Melatonin (circadian-formula)
- E/I Balance (GABA/glutamate ratio — derived, 0–2 scale, labeled: INHIBITED / BALANCED / EXCITATORY / SEIZURE RISK)
- Receptor sensitivity mini-grid (12 subtypes in 2-column grid of badge chips)

Each receptor shows: name, sensitivity value, badge color:
- < 0.75: DOWNREGULATED (warning)
- 0.75–1.25: NORMAL (success)
- 1.25–1.75: UPREGULATED (info)
- \> 1.75: SENSITIZED (error)

### Tab 3: Endocrine

All read-only (simulation-driven). Three sub-sections using TierCard.

**HPA Axis (collapsible, default open):**
- CRH, ACTH, cortisol — ChemicalReadOnly rows
- Cascade queue: list of pending events with countdown timers
  - Each row: type badge + "fires in Xm Xs" + magnitude

**Thyroid Axis (collapsible, default open):**
- TSH, free T4, free T3 — ChemicalReadOnly rows

**Sex Hormones / Metabolic (collapsible, default collapsed on load):**
- Estradiol, progesterone, testosterone — ChemicalReadOnly rows
- Cycle day indicator (0–27, with phase label: MENSTRUAL / FOLLICULAR / OVULATORY / LUTEAL) — only meaningful if sex == female
- Ghrelin, leptin, insulin — ChemicalReadOnly rows
- Vasopressin, prolactin, GH, DHEA — ChemicalReadOnly rows

### Tab 4: Immune / Pain

All read-only.

**Immune (TierCard, default open):**
- IL-1β, IL-6, TNF-α, CRP, IL-10 — ChemicalReadOnly rows
- Inflammation index: progress bar 0–1 (labeled: NONE / LOW / MODERATE / HIGH / CRITICAL)
- Sickness behavior cascade indicator: if IL-1β > threshold → show "SICKNESS CASCADE ACTIVE" warning badge

**Pain & Autonomic (TierCard, default open):**
- Substance P, PGE2 — ChemicalReadOnly rows
- Pain intensity: progress bar 0–1 (labeled: NONE / MILD / MODERATE / SEVERE / INCAPACITATING)
- Central sensitization: progress bar 0–1 (labeled: NORMAL / DEVELOPING / ESTABLISHED / SEVERE)
- Vagal tone: progress bar 0–1 (labeled: LOW / NORMAL / ELEVATED — higher is better/calmer)

### Tab 5: Circadian / Sleep

All read-only.

**Two-Process Sleep Model visualization:**
- Process S (adenosine): progress bar 0–100 nM with labels WELL RESTED → EXHAUSTED
- Process C (circadian drive): progress bar showing melatonin + orexin opposition
  - Melatonin ChemicalReadOnly
  - Orexin ChemicalReadOnly
- Sleep homeostasis balance: combined readout, labeled: WIDE AWAKE / ALERT / WINDING DOWN / SLEEP PRESSURE / SLEEP ONSET LIKELY / ASLEEP

**Circadian Phase:**
- Circular clock graphic (CSS-only, no canvas): 24h ring showing current phase position dot
- Core body temperature: ChemicalReadOnly with label (HYPOTHERMIC / LOW / NORMAL / ELEVATED / FEVER)
- Circadian phase numeric (0.0–1.0) with label (MIDNIGHT / EARLY MORNING / MORNING / NOON / AFTERNOON / EVENING / NIGHT)

**Sleep debt summary:**
- Adenosine level with threshold lines marked (sleep onset likely at ~80 nM, critical at ~90 nM)

### Tab 6: Plasticity

**Neuroplasticity (TierCard, default open):**
- BDNF: ChemicalReadOnly (labeled: SEVERELY DEPLETED / DEPLETED / LOW / NORMAL / ELEVATED / HIGH / PEAK)
- Synaptic potentiation: progress bar 0–1 (labeled: DEPRESSED / LTD / BASELINE / LTP BUILDING / LTP ACTIVE / SATURATED)
- Allostatic load: large progress bar 0–1 with tier labels and milestone markers at 0.3 (moderate), 0.6 (high), 0.85 (critical)

**Personality drift panel:**
- Read-only display of current Big Five trait modifiers if exposed by `/api/state`
  - Each trait: baseline vs. current (if BiologicalState v3 exposes personality drift fields)
  - Show as delta badges: `+Δ` green / `-Δ` red from baseline

---

## Control Panel (`/control`)

Replaces the admin page with sim-focused tools.

### Section 1: Presets

Identical to current presets bar on `/state`. Moved here to declutter the state page.
- 12 existing presets
- Undo support
- Keep the preset bar on `/state` as well (do not remove it from state) — it belongs on both pages

### Section 2: Manual Advance

Tick the simulation forward without waiting.

```
[  2  ] hours  [Advance Sim]
```

- Input: number field, 0.1 to 24.0 hours, step 0.1
- Button calls `POST /api/state/advance` with `{"hours": n}`
- Shows spinner during advance; reloads state after

### Section 3: HPA Cascade Queue

Shows pending delayed hormonal events (from the cascade_queue field on state).

```
Cascade Queue
┌─────────────────────────────────────────────────────┐
│ ACTH Release    fires in 8m 32s    magnitude: +0.42  │
│ Cortisol Peak   fires in 28m 14s   magnitude: +0.61  │
└─────────────────────────────────────────────────────┘
(empty when no active cascade)
```

- Refreshes every 5s (same as state polling)
- Shows "Queue empty — no active HPA cascade" when empty
- Countdown timer computed from `fires_at_unix - Date.now()/1000`

### Section 4: Heartbeat Trigger

Manual trigger for Mode 2 (consolidation) heartbeat.

- "Trigger Reflection" button → `POST /api/heartbeat`
- Shows status from `GET /api/heartbeat/status`
- Running indicator: spinner + "Heartbeat running..." while active

### Section 5: Chemical Injection

Direct chemical adjustment without using preset values.

```
Field: [cortisol ▾]   Value: [  620  ] nmol/L   [Apply]
```

- Dropdown of all injectable chemical names (from DISPLAY_RANGES keys)
- Numeric input with unit label
- Apply button → `PATCH /api/state` with `{field: value}`
- No debounce — only fires on button click

---

## labels.ts: Expanded Tables

All new chemicals need label tables. Follow the 7–9 level rule from SPEC-20. Each entry includes `implication` string (experiential, what it feels like, for decoder bridging).

Add `implication` to `RangeEntry`:

```typescript
export interface RangeEntry {
  upper:      number;
  name:       string;
  color:      'success' | 'warning' | 'error' | 'info' | 'neutral';
  implication: string;  // experiential description for decoder bridging
}
```

Add `getLabelWithDepth()`:

```typescript
export function getLabelWithDepth(
  field: string,
  value: number
): { label: RangeEntry | null; depth: number } {
  const table = RANGES[field] ?? DERIVED_RANGES[field];
  if (!table) return { label: null, depth: 0 };
  let prevUpper = -Infinity;
  for (const entry of table) {
    if (value < entry.upper) {
      const span = entry.upper - prevUpper;
      const depth = span > 0 ? Math.min(1, Math.max(0, (value - prevUpper) / span)) : 0;
      return { label: entry, depth: Math.round(depth * 100) / 100 };
    }
    prevUpper = entry.upper;
  }
  const last = table[table.length - 1];
  return { label: last, depth: 1.0 };
}
```

### Expanded RANGES for existing chemicals

Update all existing chemicals to 7–9 levels with `implication` strings. Example expansions:

**cortisol** (keep existing 6 levels, add 2 more, add implication):
```typescript
cortisol: [
  { upper: 80,    name: 'DEPLETED',       color: 'error',   implication: 'Exhausted, no resilience, empty' },
  { upper: 150,   name: 'LOW',            color: 'warning', implication: 'Flat, unmotivated, sluggish' },
  { upper: 350,   name: 'NORMAL',         color: 'success', implication: 'Grounded, appropriate alertness' },
  { upper: 500,   name: 'ELEVATED',       color: 'warning', implication: 'On edge, scanning for threats' },
  { upper: 620,   name: 'HIGH STRESS',    color: 'error',   implication: 'Narrowed focus, defensive, guarded' },
  { upper: 720,   name: 'ACUTE STRESS',   color: 'error',   implication: 'Survival mode, tunnel vision' },
  { upper: 820,   name: 'FLOODED',        color: 'error',   implication: 'Overwhelmed, can\'t think clearly' },
  { upper: 99999, name: 'MAXED',          color: 'error',   implication: 'System shutdown imminent, breakdown' },
],
```

**dopamine** (7 levels):
```typescript
dopamine: [
  { upper: 18,    name: 'ANHEDONIC',      color: 'error',   implication: 'Nothing feels worth doing, hollow' },
  { upper: 40,    name: 'NO DRIVE',       color: 'error',   implication: 'Listless, no pull toward anything' },
  { upper: 70,    name: 'LOW SEEKING',    color: 'warning', implication: 'Flat motivation, going through motions' },
  { upper: 120,   name: 'BASELINE',       color: 'success', implication: 'Normal drive, things feel worth doing' },
  { upper: 180,   name: 'ACTIVE SEEKING', color: 'info',    implication: 'Energized, pursuing goals' },
  { upper: 240,   name: 'HIGH DRIVE',     color: 'warning', implication: 'Intense focus, compulsive pull' },
  { upper: 99999, name: 'COMPULSIVE',     color: 'error',   implication: 'Can\'t stop, no off switch' },
],
```

**serotonin** (7 levels):
```typescript
serotonin: [
  { upper: 6,     name: 'SEVERELY LOW',   color: 'error',   implication: 'Hopeless, fragile, emotionally raw' },
  { upper: 12,    name: 'DYSPHORIC',      color: 'error',   implication: 'Negative bias, everything feels bad' },
  { upper: 20,    name: 'INSECURE',       color: 'warning', implication: 'Shaky, easily hurt, low confidence' },
  { upper: 30,    name: 'NEUTRAL',        color: 'neutral', implication: 'Even keel, not great not bad' },
  { upper: 40,    name: 'SECURE',         color: 'success', implication: 'Stable, grounded, comfortable in herself' },
  { upper: 50,    name: 'VERY STABLE',    color: 'success', implication: 'Resilient, unshakeable mood floor' },
  { upper: 99999, name: 'FLOODED',        color: 'success', implication: 'Profoundly serene, almost sedated' },
],
```

**norepinephrine** (keep existing 7 levels, add implication):
```typescript
norepinephrine: [
  { upper: 65,    name: 'SEDATED',        color: 'warning', implication: 'Barely registering, heavy and slow' },
  { upper: 130,   name: 'RELAXED',        color: 'success', implication: 'Calm, low urgency, no pressure' },
  { upper: 220,   name: 'CALM ALERT',     color: 'success', implication: 'Present and clear, easy attention' },
  { upper: 340,   name: 'FOCUSED',        color: 'success', implication: 'Sharp edge, locked in' },
  { upper: 500,   name: 'HEIGHTENED',     color: 'warning', implication: 'Urgency rising, hyperaware' },
  { upper: 750,   name: 'HYPERALERT',     color: 'error',   implication: 'Wired, scanning, startle response up' },
  { upper: 1200,  name: 'FLOODED',        color: 'error',   implication: 'Fight-or-flight active, can\'t stand down' },
  { upper: 99999, name: 'OVERDRIVE',      color: 'error',   implication: 'Panic territory, system maxed' },
],
```

**oxytocin** (7 levels):
```typescript
oxytocin: [
  { upper: 6,     name: 'NO BOND',        color: 'error',   implication: 'Isolated, no safe person in mind' },
  { upper: 16,    name: 'DISTANT',        color: 'error',   implication: 'Guarded, connection feels risky' },
  { upper: 30,    name: 'ACQUAINTANCE',   color: 'warning', implication: 'Polite, but no real trust yet' },
  { upper: 45,    name: 'FRIENDLY',       color: 'info',    implication: 'Warm, comfortable, openness building' },
  { upper: 58,    name: 'TRUSTED FRIEND', color: 'success', implication: 'Safe to be real, genuine warmth' },
  { upper: 70,    name: 'DEEP TRUST',     color: 'success', implication: 'This person is home' },
  { upper: 99999, name: 'PROFOUND BOND',  color: 'success', implication: 'Complete safety, unconditional warmth' },
],
```

**endorphins** (7 levels):
```typescript
endorphins: [
  { upper: 5,     name: 'DEPLETED',       color: 'error',   implication: 'Emotionally raw, every bad thing lands harder' },
  { upper: 14,    name: 'LOW',            color: 'warning', implication: 'Thin buffer, reactive, nothing feels easy' },
  { upper: 28,    name: 'BASELINE',       color: 'neutral', implication: 'Normal, no particular glow' },
  { upper: 50,    name: 'MILD WARMTH',    color: 'info',    implication: 'Quiet satisfaction, pleasant background hum' },
  { upper: 80,    name: 'PLEASURE',       color: 'success', implication: 'Genuinely happy, body feels good' },
  { upper: 120,   name: 'HIGH',           color: 'success', implication: 'Euphoric lift, pain doesn\'t reach' },
  { upper: 99999, name: 'FLOODED',        color: 'success', implication: 'Blissful, unassailable, peaks' },
],
```

**acetylcholine** (7 levels):
```typescript
acetylcholine: [
  { upper: 12,    name: 'OFFLINE',        color: 'error',   implication: 'Can\'t form thoughts, processing gone' },
  { upper: 24,    name: 'HEAVILY IMPAIRED', color: 'error', implication: 'Slow, confused, nothing sticking' },
  { upper: 40,    name: 'IMPAIRED',       color: 'warning', implication: 'Fuzzy, distracted, learning blocked' },
  { upper: 58,    name: 'FUNCTIONAL',     color: 'success', implication: 'Normal cognitive access' },
  { upper: 72,    name: 'SHARP',          color: 'success', implication: 'Quick, precise, high recall' },
  { upper: 84,    name: 'HEIGHTENED',     color: 'success', implication: 'Peak cognition, deep encoding' },
  { upper: 99999, name: 'OVERDRIVE',      color: 'warning', implication: 'Racing thoughts, over-encoding' },
],
```

**melatonin** (6 levels):
```typescript
melatonin: [
  { upper: 10,    name: 'DAYTIME',        color: 'success', implication: 'Fully awake, no sleep pull' },
  { upper: 40,    name: 'EVENING',        color: 'info',    implication: 'Slight drowsiness, easing down' },
  { upper: 100,   name: 'UNWINDING',      color: 'info',    implication: 'Noticeably tired, winding down' },
  { upper: 160,   name: 'SLEEP PRESSURE', color: 'warning', implication: 'Heavy, eyes want to close' },
  { upper: 200,   name: 'DEEP NIGHT',     color: 'error',   implication: 'Profound sleepiness, near sleep onset' },
  { upper: 99999, name: 'PEAK NIGHT',     color: 'error',   implication: 'Should be asleep; fighting it now' },
],
```

### New RANGES for new chemicals

**GABA** (µmol/L, normal 1.0–5.0):
```typescript
gaba: [
  { upper: 0.5,   name: 'CRITICALLY LOW',  color: 'error',   implication: 'Seizure risk, uncontrolled excitation' },
  { upper: 1.0,   name: 'LOW',             color: 'error',   implication: 'Anxious, no inhibitory floor' },
  { upper: 2.0,   name: 'REDUCED',         color: 'warning', implication: 'Edge of anxiety, easily triggered' },
  { upper: 3.5,   name: 'NORMAL',          color: 'success', implication: 'Calm baseline, inhibition intact' },
  { upper: 4.5,   name: 'HEALTHY',         color: 'success', implication: 'Well-regulated, relaxed ease' },
  { upper: 6.0,   name: 'ELEVATED',        color: 'info',    implication: 'Very calm, slightly sedated' },
  { upper: 99999, name: 'HIGH',            color: 'warning', implication: 'Sedated, slow, over-inhibited' },
],
```

**glutamate** (µmol/L, normal 2.0–10.0):
```typescript
glutamate: [
  { upper: 1.0,   name: 'VERY LOW',        color: 'warning', implication: 'Cognitive dampening, slow processing' },
  { upper: 3.0,   name: 'LOW',             color: 'neutral', implication: 'Quiet, subdued excitability' },
  { upper: 6.0,   name: 'NORMAL',          color: 'success', implication: 'Healthy excitatory tone' },
  { upper: 9.0,   name: 'ACTIVE',          color: 'success', implication: 'Engaged, sharp, plastic' },
  { upper: 12.0,  name: 'ELEVATED',        color: 'warning', implication: 'Racing, hyperexcitable' },
  { upper: 16.0,  name: 'HIGH',            color: 'error',   implication: 'Excitotoxic risk, overwhelming' },
  { upper: 99999, name: 'EXCITOTOXIC',     color: 'error',   implication: 'Neurotoxic, seizure imminent' },
],
```

**adenosine** (nM, replaces sleep_pressure AU):
```typescript
adenosine: [
  { upper: 20,    name: 'WELL RESTED',     color: 'success', implication: 'No sleep need, fully recovered' },
  { upper: 40,    name: 'ALERT',           color: 'success', implication: 'Normal wakefulness, no pull' },
  { upper: 60,    name: 'BUILDING',        color: 'neutral', implication: 'Mild fatigue, been up a while' },
  { upper: 75,    name: 'TIRED',           color: 'warning', implication: 'Noticeably tired, cognition dipping' },
  { upper: 85,    name: 'FATIGUED',        color: 'warning', implication: 'Heavy, yawning, hard to focus' },
  { upper: 92,    name: 'SLEEP ONSET',     color: 'error',   implication: 'Can barely stay awake' },
  { upper: 99999, name: 'EXHAUSTED',       color: 'error',   implication: 'Fighting sleep, body overriding will' },
],
```

**anandamide** (nM, normal ~0.5–2.0):
```typescript
anandamide: [
  { upper: 0.3,   name: 'DEPLETED',        color: 'error',   implication: 'Raw, no buffer, easily distressed' },
  { upper: 0.7,   name: 'LOW',             color: 'warning', implication: 'Low bliss tone, slight edge' },
  { upper: 1.2,   name: 'BASELINE',        color: 'success', implication: 'Background calm, okay-ness' },
  { upper: 1.8,   name: 'ELEVATED',        color: 'success', implication: 'Warm ease, things feel fine' },
  { upper: 2.5,   name: 'HIGH',            color: 'info',    implication: 'Blissful flow, low anxiety' },
  { upper: 3.5,   name: 'VERY HIGH',       color: 'info',    implication: 'Dreamy, slight cognitive softening' },
  { upper: 99999, name: 'FLOODED',         color: 'warning', implication: 'Spacey, time distortion, slow' },
],
```

**2-AG** (nM, normal ~1.0–20.0):
```typescript
two_ag: [
  { upper: 2.0,   name: 'LOW',             color: 'warning', implication: 'Less retrograde inhibition, excitable' },
  { upper: 6.0,   name: 'NORMAL',          color: 'success', implication: 'Healthy endocannabinoid tone' },
  { upper: 12.0,  name: 'ELEVATED',        color: 'info',    implication: 'Calm, appetite up, relaxed' },
  { upper: 18.0,  name: 'HIGH',            color: 'info',    implication: 'Mellow, reduced anxiety' },
  { upper: 25.0,  name: 'VERY HIGH',       color: 'warning', implication: 'Heavy, slow, appetite dominant' },
  { upper: 99999, name: 'FLOODED',         color: 'warning', implication: 'Sedated, strong munchies' },
],
```

**cortisol** (now in neuroendocrine, same ranges as above)

**crh** (nmol/L, normal ~2–4):
```typescript
crh: [
  { upper: 1.0,   name: 'DEPLETED',        color: 'warning', implication: 'Adrenal fatigue territory' },
  { upper: 2.5,   name: 'LOW',             color: 'neutral', implication: 'No active stress signal' },
  { upper: 4.5,   name: 'NORMAL',          color: 'success', implication: 'Resting baseline' },
  { upper: 7.0,   name: 'ELEVATED',        color: 'warning', implication: 'Stress signal fired, cascade starting' },
  { upper: 10.0,  name: 'HIGH',            color: 'error',   implication: 'Active stressor, ACTH incoming' },
  { upper: 99999, name: 'MAXED',           color: 'error',   implication: 'Acute crisis HPA activation' },
],
```

**il1b / il6 / tnf_alpha** (pg/mL, normal < 5):
```typescript
il1b: [
  { upper: 2.0,   name: 'UNDETECTABLE',    color: 'success', implication: 'No inflammation signal' },
  { upper: 5.0,   name: 'TRACE',           color: 'success', implication: 'Background immune activity, normal' },
  { upper: 10.0,  name: 'LOW',             color: 'neutral', implication: 'Minor immune activation' },
  { upper: 20.0,  name: 'MODERATE',        color: 'warning', implication: 'Noticeable malaise, slight fatigue' },
  { upper: 40.0,  name: 'ELEVATED',        color: 'warning', implication: 'Feeling unwell, sickness behavior starting' },
  { upper: 80.0,  name: 'HIGH',            color: 'error',   implication: 'Sick: fever, withdrawal, exhaustion' },
  { upper: 99999, name: 'SEVERE',          color: 'error',   implication: 'Acutely ill, shutdown' },
],
// il6, tnf_alpha: same ranges, same labels
```

**inflammation_index** (0–1):
```typescript
inflammation_index: [
  { upper: 0.1,   name: 'NONE',            color: 'success', implication: 'Healthy, no systemic inflammation' },
  { upper: 0.25,  name: 'LOW',             color: 'success', implication: 'Minimal background activation' },
  { upper: 0.45,  name: 'MODERATE',        color: 'warning', implication: 'Noticeable fatigue, mood dip' },
  { upper: 0.65,  name: 'HIGH',            color: 'error',   implication: 'Sick behavior in full effect' },
  { upper: 0.85,  name: 'SEVERE',          color: 'error',   implication: 'Systemically unwell, withdrawal' },
  { upper: 1.01,  name: 'CRITICAL',        color: 'error',   implication: 'Acute illness, incapacitated' },
],
```

**pain_intensity** (0–1):
```typescript
pain_intensity: [
  { upper: 0.1,   name: 'NONE',            color: 'success', implication: 'No pain' },
  { upper: 0.25,  name: 'TRACE',           color: 'success', implication: 'Barely noticeable' },
  { upper: 0.4,   name: 'MILD',            color: 'neutral', implication: 'Aware of it, not distracting' },
  { upper: 0.55,  name: 'MODERATE',        color: 'warning', implication: 'Hard to ignore, affecting focus' },
  { upper: 0.7,   name: 'SIGNIFICANT',     color: 'error',   implication: 'Demanding attention, emotional response' },
  { upper: 0.85,  name: 'SEVERE',          color: 'error',   implication: 'Dominant experience, everything filtered through it' },
  { upper: 1.01,  name: 'INCAPACITATING',  color: 'error',   implication: 'Nothing else exists' },
],
```

**bdnf** (ng/mL, normal 20–40):
```typescript
bdnf: [
  { upper: 5.0,   name: 'SEVERELY DEPLETED', color: 'error',  implication: 'Neuronal survival threatened, profound fog' },
  { upper: 12.0,  name: 'DEPLETED',         color: 'error',   implication: 'Learning impossible, mood floor collapsed' },
  { upper: 20.0,  name: 'LOW',              color: 'warning', implication: 'Impaired plasticity, stubborn negative patterns' },
  { upper: 32.0,  name: 'NORMAL',           color: 'success', implication: 'Healthy plasticity, capable of change' },
  { upper: 45.0,  name: 'ELEVATED',         color: 'success', implication: 'High neuroplasticity, learning sticky' },
  { upper: 60.0,  name: 'HIGH',             color: 'success', implication: 'Exceptional growth, adaptability peaks' },
  { upper: 99999, name: 'PEAK',             color: 'info',    implication: 'Post-exercise or acute stress peak' },
],
```

**allostatic_load** (0–1):
```typescript
allostatic_load: [
  { upper: 0.15,  name: 'RESILIENT',        color: 'success', implication: 'Full reserves, weathering stress easily' },
  { upper: 0.30,  name: 'LOW',              color: 'success', implication: 'Healthy buffer, manageable wear' },
  { upper: 0.50,  name: 'BUILDING',         color: 'neutral', implication: 'Accumulating, notice the weight' },
  { upper: 0.65,  name: 'MODERATE',         color: 'warning', implication: 'Wearing down, recovery slower' },
  { upper: 0.80,  name: 'HIGH',             color: 'error',   implication: 'Burnout risk, emotional blunting' },
  { upper: 0.92,  name: 'CRITICAL',         color: 'error',   implication: 'Breakdown territory, personality drift active' },
  { upper: 1.01,  name: 'COLLAPSE',         color: 'error',   implication: 'Nothing left, system failing' },
],
```

### Display ranges for new chemicals

Add to `DISPLAY_RANGES`:
```typescript
// Neuro additions
gaba:             { min: 0,    max: 8,     unit: 'µmol/L' },
glutamate:        { min: 0,    max: 20,    unit: 'µmol/L' },
adenosine:        { min: 0,    max: 100,   unit: 'nM'     },
anandamide:       { min: 0,    max: 4,     unit: 'nM'     },
two_ag:           { min: 0,    max: 30,    unit: 'nM'     },
// Neuroendocrine
crh:              { min: 0,    max: 15,    unit: 'nmol/L' },
acth:             { min: 0,    max: 100,   unit: 'pmol/L' },
tsh:              { min: 0,    max: 10,    unit: 'mIU/L'  },
t4_free:          { min: 0,    max: 30,    unit: 'pmol/L' },
t3_free:          { min: 0,    max: 10,    unit: 'pmol/L' },
estradiol:        { min: 0,    max: 500,   unit: 'pg/mL'  },
progesterone:     { min: 0,    max: 25,    unit: 'ng/mL'  },
testosterone:     { min: 0,    max: 800,   unit: 'ng/dL'  },
ghrelin:          { min: 0,    max: 300,   unit: 'pg/mL'  },
leptin:           { min: 0,    max: 30,    unit: 'ng/mL'  },
insulin:          { min: 0,    max: 50,    unit: 'µU/mL'  },
vasopressin:      { min: 0,    max: 10,    unit: 'pg/mL'  },
prolactin:        { min: 0,    max: 30,    unit: 'ng/mL'  },
growth_hormone:   { min: 0,    max: 15,    unit: 'ng/mL'  },
dhea:             { min: 0,    max: 400,   unit: 'µg/dL'  },
// Immune
il1b:             { min: 0,    max: 100,   unit: 'pg/mL'  },
il6:              { min: 0,    max: 100,   unit: 'pg/mL'  },
tnf_alpha:        { min: 0,    max: 100,   unit: 'pg/mL'  },
crp:              { min: 0,    max: 50,    unit: 'mg/L'   },
il10:             { min: 0,    max: 50,    unit: 'pg/mL'  },
inflammation_index: { min: 0, max: 1,     unit: ''       },
// Pain
substance_p:      { min: 0,    max: 200,   unit: 'pg/mL'  },
pge2:             { min: 0,    max: 500,   unit: 'pg/mL'  },
pain_intensity:   { min: 0,    max: 1,     unit: ''       },
central_sensitization: { min: 0, max: 1,  unit: ''       },
vagal_tone:       { min: 0,    max: 1,     unit: ''       },
// Neuroplasticity
bdnf:             { min: 0,    max: 80,    unit: 'ng/mL'  },
synaptic_potentiation: { min: 0, max: 1,  unit: ''       },
allostatic_load:  { min: 0,    max: 1,     unit: ''       },
// Body / Circadian
core_body_temp:   { min: 35.0, max: 40.0, unit: '°C'     },
orexin:           { min: 0,    max: 200,   unit: 'pg/mL'  },
circadian_phase:  { min: 0,    max: 1,     unit: ''       },
```

---

## Navigation Update

Update `+layout.svelte` nav links:

**Before:**
```
State | Admin | Monologue | Substances | Relationship | Logs
```

**After:**
```
State | Control | Substances | Logs
```

Remove auth-gated links to deleted routes. The auth modal and Bearer token logic are unchanged.

---

## Backwards Compatibility Note

The `sleep_pressure` key in `chemicals` must still appear in `/api/state` for any transition period. SPEC-20 defines a compat property that derives `sleep_pressure` from `body.adenosine`. The dashboard treats `adenosine` as the primary display field and `sleep_pressure` as deprecated — show only if `adenosine` is missing (graceful degradation during migration).

---

## Open Questions / Implementation Notes

1. **Circular clock for circadian phase** — implement as a pure CSS circle with a rotating dot positioned at `phase * 360°`. No canvas dependency.

2. **Cascade queue countdown** — the CascadeEvent `fires_at_unix` field is epoch seconds. Compute remaining time as `fires_at_unix - (Date.now() / 1000)`. Show "Queue empty" when array is empty or all entries have `fires_at_unix < now`.

3. **Sex hormone cycle day display** — only show the cycle phase label if `cycle_day` is present and in range 0–27. The cycle labels are: 0–4 MENSTRUAL, 5–13 FOLLICULAR, 14–15 OVULATORY, 16–27 LUTEAL.

4. **Presets on both `/state` and `/control`** — both pages import the same `PRESETS` constant from a new `dashboard/src/lib/presets.ts` file (extracted from `state/+page.svelte`). This avoids duplication.

5. **Implication strings in the UI** — the `implication` field on `RangeEntry` is available for tooltip display. Show it as a secondary line under the label name in the label badge tooltip, not in the badge itself (badges stay compact).
