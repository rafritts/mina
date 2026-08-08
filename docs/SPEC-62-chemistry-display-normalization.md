# SPEC-62 — Chemistry Display Normalization & Label Semantics

**Status:** Draft — needs sign-off before implementation  
**Date:** 2026-08-07  
**Depends on:** `src/sim/params.py` (`CHEMICAL_PARAMS`), decoder 0–10 scale (`src/sim/decoder.py`), state API (`src/gateway/server.py`), UI labels (`ui/app/lib/labels.ts`), Control pane / neuro admin  
**Related:** SPEC-61 (sleep onset — adenosine chips must not fight sleep states); insula gap doctrine (`src/brain/insula.py`); archived v1 registry labels (do not re-adopt units)

---

## Problem

The Control → Chemistry panel can show a **factory-resting / sleeping baseline** with chips like:

| Chem | Approx value | Chip (wrong) |
|------|--------------|--------------|
| Dopamine | ~8.25 nM | ANHEDONIC |
| Serotonin | ~8 nM | DYSPHORIC |
| Norepinephrine | ~3.4 nM | SEDATED |
| Oxytocin | ~0.01 nM | NO BOND |
| Endorphins | ~2.5 nM | DEPLETED |
| Adenosine | ~160 nM | EXHAUSTED |

Those levels are **not a death spiral**. They sit at or near `tonic_setpoint` in `CHEMICAL_PARAMS` (modulo mild sleep pressure and circadian offset). The decoder / insula already treat gap≈0 as ordinary baseline.

Root causes (two, not one):

1. **Unit / scale mismatch (primary)**  
   Sim + API report working concentrations (mostly **nM**).  
   `ui/app/lib/labels.ts` still uses **v1** threshold tables and `DISPLAY_RANGES` (DA/NE/OT/endorphins in **pg/mL**, 5-HT in **ng/mL**, adenosine on a 15–100 scale, etc.).  
   Resting nM values fall into the “crashed” bands of the old tables.

2. **Wrong semantics for some chems (especially OT)**  
   Even with correct units, mapping **absolute resting OT** to a relationship ladder (`NO BOND` → `PROFOUND BOND`) is wrong. Resting OT is *supposed* to sit near the floor. “No active surge” ≠ “isolated / no bond.”  
   Same class of error: absolute low endorphins → DEPLETED; modest adenosine on an old maxed-at-100 scale → EXHAUSTED.

**This is a display + labeling contract problem.** It is not fixed by cranking sim setpoints to v1 plasma numbers.

---

## Goal

1. At true resting baseline (gap≈0 on core chems), the Control chemistry UI reads **calm / baseline / resting** — not anhedonic, dysphoric, no-bond, depleted.
2. Labels and sliders use a scale **tied to `CHEMICAL_PARAMS`**, so param changes do not silently invalidate chips.
3. Special chems (OT, adenosine, melatonin, epi, endorphins, cortisol) have **explicit semantics**, aligned with insula/decoder doctrine.
4. Bond/relationship language is **not** sole property of absolute OT nM.

Observable success: a fresh or settled baseline snapshot no longer looks like a psychiatric emergency on the chemistry tab.

---

## Non-goals

- Re-deriving every physiological range from primary literature as a research project.
- Changing Class-1 encoder weights, opponent processes, HPA cascade rates, or setpoint adaptation (unless a listed bug is discovered during implementation — out of band).
- Full bond-score / relationship architecture redesign (historical SPEC-43 territory). This spec only **separates** chemical OT chips from bond language and forbids false NO BOND at rest. A later spec may make bond score the primary social ladder.
- Replacing decoder gap doctrine or insula prompts (already correct in spirit; UI must catch up).
- Perfect multi-compartment modeling (plasma vs CSF vs synaptic). One working unit system + normalized affect scale is enough for a chatbot.

---

## Design principles

### 1. Sim params are source of truth for magnitude

Per chemical in `CHEMICAL_PARAMS`:

| Field | Meaning for display |
|-------|---------------------|
| `tonic_setpoint` | Personal resting floor (before Big5 bias at init; live setpoint may adapt) |
| Live `setpoint` on the level | Her current adapted baseline — prefer this over static table for gap |
| `normalization_max` | “10” on the decoder scale; hard phys-ish ceiling for display max |

Do **not** reintroduce v1 `pg/mL` / `ng/mL` label tables for Class-1 monoamines.

### 2. Normalized scale is the primary label driver

Decoder already uses:

```text
normalized_0_10 = (tonic + phasic) / normalization_max * 10
setpoint_0_10   = setpoint / normalization_max * 10
gap             = normalized_0_10 - setpoint_0_10
```

**Labels for Control chips MUST be driven primarily by `normalized_0_10` and/or `gap`, not by raw nM against v1 thresholds.**

Raw nM may still show as a secondary mono readout (admin curiosity). Chips must not depend on matching old plasma assays.

### 3. Absolute level ≠ feeling (insula parity)

Documented in `insula.py` and required here for UI:

- Resting DA often ~3–5 on 0–10, gap 0 → **baseline drive**, not anhedonia.
- Resting OT often ~0–2 on 0–10, gap 0 → **ordinary resting OT**, not loneliness.
- Gap is the primary “is she off her baseline?” signal.

UI chips that ignore gap will keep lying.

### 4. Two chem kinds + two special axes

| Kind | Examples | Resting (gap≈0) chip story |
|------|----------|----------------------------|
| **Type A — tone** | dopamine, serotonin | BASELINE / NEUTRAL / SECURE band |
| **Type B — surge** | oxytocin, epinephrine, endorphins (as pleasure buffer), partly NE | RESTING / QUIET / no surge — **not** pathological red |
| **Sleep pressure** | adenosine | WELL RESTED → … → SLEEP ONSET aligned with sim thresholds |
| **Circadian** | melatonin; cortisol rhythm | Phase-appropriate; mild night rise ≠ crisis |

---

## Chem classification (Control pane + admin)

Chemicals shown in Control groups today; semantics for each:

### Type A — mood / monoamine tone

| Chem | Resting intent | Pathological low | Elevated |
|------|----------------|------------------|----------|
| `dopamine` | BASELINE (drive available) | ANHEDONIC / NO DRIVE only if **well below setpoint** or very low norm with negative gap | ACTIVE SEEKING → COMPULSIVE |
| `serotonin` | NEUTRAL / SECURE | DYSPHORIC only with **negative gap** (or severe absolute + gap) | STABLE / FLOODED |
| `norepinephrine` | CALM ALERT / RELAXED at rest | SEDATED only if **below** her resting band | FOCUSED → OVERDRIVE |

Implementation preference: **gap-first bands** with absolute norm as secondary clamp (e.g. true near-zero floor still “collapsed” even if setpoint also collapsed — rare).

### Type B — surge / floor-is-normal-low

| Chem | Resting intent | Forbidden at gap≈0 | Elevated |
|------|----------------|--------------------|----------|
| `oxytocin` | **RESTING** (or QUIET / NO SURGE) | **NO BOND**, DISTANT, isolation/error-red as default | WARMING → CONNECTED → DEEP SURGE |
| `epinephrine` | RESTING | Any “crashed” / depleted framing | MILD AROUSAL → ACUTE SURGE |
| `endorphins` | BASELINE (no particular glow) | DEPLETED unless **gap clearly negative** | MILD WARMTH → PLEASURE → high euphoria |

### Sleep pressure

| Chem | Notes |
|------|--------|
| `adenosine` | Scale to `normalization_max` (500 nM). Align chips with `SLEEP_ENTER_ADENOSINE` (8.0) and `SLEEP_WAKE_ADENOSINE` (3.0). Mid sleep (norm ~3) must not read EXHAUSTED on a 0–100 v1 scale. |

Suggested adenosine bands (normalized 0–10):

| Norm (approx) | Chip |
|---------------|------|
| &lt; 2 | WELL RESTED |
| 2–4 | ALERT |
| 4–6 | BUILDING |
| 6–7.5 | TIRED |
| 7.5–8.5 | SLEEP ONSET (near auto-enter) |
| &gt; 8.5 | EXHAUSTED / forced sleep territory |

Exact edges can be tuned ±0.5; **enter threshold 8.0 must sit in SLEEP ONSET, not mid-ALERT.**

### Circadian

| Chem | Notes |
|------|--------|
| `melatonin` | Night elevation is normal. Chips: DAYTIME → EARLY EVENING → WINDING DOWN → DROWSY → PEAK. Warning colors only at high sleep-signal end, not for mild evening rise. |
| `cortisol` | Prefer gap + absolute. Morning CAR elevation can be NORMAL/ELEVATED-without-panic. Sustained high + positive gap → stress language. Low evening absolute with gap≈0 → not DEPLETED adrenal crisis. |

### Other (if shown)

- `acetylcholine`, scaffolds: only if still exposed; use norm scale; grade D scaffolds may stay de-emphasized.
- Derived second/third order metrics already use normalized inputs in the gateway — **revisit after chip fix** so `loneliness` / `social_warmth` do not punish resting OT. Today loneliness uses `gap("oxytocin")` (good direction); `social_warmth` uses absolute oxy fraction of max (will look cold at rest). Spec requires fixing derived metrics that treat resting OT as low social warmth (see Acceptance).

---

## Oxytocin policy (mandatory — not a footnote)

### Chemical OT chip

Driven by **gap** and elevation above setpoint, not by “is absolute nM &lt; 6.”

| Condition | Chip (suggested names) | Color |
|-----------|------------------------|-------|
| gap ≥ −1 and norm low–mid (typical rest) | RESTING | neutral / success |
| mild positive gap / mild elevation | WARMING | info |
| clear elevation | CONNECTED | success |
| strong surge | DEEP SURGE / HIGH | success |
| extreme | SATURATED | warning |
| **clear negative gap** (below her setpoint) | LOW TONE / WITHDRAWN SURGE | warning–error |

**Hard rule:** At factory baseline and any state with OT gap≈0, the OT chip **must not** be `NO BOND`, `DISTANT`, or error-red isolation language.

### Bond / relationship language

Friend ladder names (`NO BOND`, `ACQUAINTANCE`, `TRUSTED FRIEND`, …) are **relationship/bond concepts**, not resting hormone concentration.

| This spec | Later (optional) |
|-----------|------------------|
| Remove friend-ladder from absolute OT nM | Surface a separate bond/relationship readout if/when bond score is productized |
| OT chip = surge / resting chemistry | Bond chip = relationship state / modifier history |

Do not block this spec on implementing full bond score UI. **Removing false NO BOND is in scope; building the full social ladder UI is not required for v1 of this spec.**

### Alignment with pillars

Insula already: “Oxytocin at 1 with gap 0 is ordinary resting OT — not loneliness.”  
After this spec, Control pane and any label helper used by admin/chat chrome must not contradict that.

---

## Label model (implementation)

### Preferred approach (A)

**Primary:** compute label from decoder-scale **normalized 0–10** and **gap**.  
**Secondary:** show raw `value` + unit (`nM` or chem-specific if params ever diverge).

Shared band templates:

**Type A (tone)** — place personal setpoint near center of BASELINE band:

```text
Use gap:
  gap ≤ −3  → severe low band
  gap ≤ −1.5 → low band
  |gap| < 1.5 → BASELINE / NEUTRAL   # noise floor parity with insula
  gap ≥ 1.5  → elevated
  gap ≥ 3    → high
  gap ≥ 5    → extreme
```

Optional absolute floor: if `normalized_0_10 < 0.5` and chem is Type A, allow collapsed band even if setpoint also low (pathological collapse).

**Type B (surge)** — gap≈0 → RESTING; only elevated gaps climb warmth/arousal ladder; negative gap → low-tone, not “no relationship.”

**Adenosine / melatonin** — absolute normalized bands (homeostatic / clock), not gap-as-mood.

### Alternative rejected as primary

- **B only:** rewrite every nM threshold by hand to match setpoints — works once, breaks on every param tweak, duplicates decoder math.
- **v1 plasma restoration:** force DA to ~80 pg/mL etc. — wrong compartment for affect model, fights current sim.

### Server-side labels (recommended hardening)

Gateway `/api/state` (and any state DTO) should emit per chemical:

```json
{
  "value": 8.25,
  "unit": "nM",
  "normalized": 0.4125,
  "normalized_10": 4.13,
  "setpoint": 8.25,
  "setpoint_10": 4.13,
  "gap": 0.0,
  "label": "BASELINE",
  "label_color": "success",
  "implication": "Normal drive, things feel worth doing"
}
```

Notes:

- Today `normalized` is **0–1** (`combined/norm_max`). Keep it for compatibility **or** rename carefully; add explicit `normalized_10` / `gap` to avoid ambiguity with decoder integers.
- UI **prefers** server `label` when present; keeps local tables only as fallback during migration.
- Single source of label tables in Python (e.g. `src/sim/labels.py` or next to params) avoids TS/Python drift.

If implementation wants a thinner first PR: fix TS tables only, but structure them as 0–10 + gap functions that mirror this spec so a follow-up can move tables server-side without redesign.

---

## DISPLAY_RANGES / sliders

Replace v1 ranges. For each editable chem:

```text
slider_min ≈ 0  (or a documented soft floor if needed)
slider_max ≈ normalization_max
unit       = working unit from sim ("nM" for monoamines/peptides as today; melatonin may remain pg/mL-consistent with params comments — display the unit the API already sends)
```

| Chem (examples) | v1 max (wrong) | New max (from params) |
|-----------------|----------------|------------------------|
| dopamine | 300 pg/mL | 20 nM |
| serotonin | 60 ng/mL | 15 nM |
| norepinephrine | 2000 pg/mL | 20 nM |
| oxytocin | 80 pg/mL | 0.30 nM |
| endorphins | 250 pg/mL | 40 nM |
| epinephrine | (implicit) | 5 nM |
| cortisol | 900 | 1200 nM |
| adenosine | 100 | 500 nM |
| melatonin | 220 | 250 (params max) |

Sliders must let resting setpoint sit at a **visible** position (not 0.01% of a 0–300 bar).

---

## Files in scope

| Area | Path | Change |
|------|------|--------|
| Label tables / ranges | `ui/app/lib/labels.ts` | Rewrite `RANGES`, `DISPLAY_RANGES`; gap-aware `getLabel` or consume server labels |
| Control UI | `ui/app/components/ControlPane.tsx` | Use new ranges/labels; show RESTING OT correctly |
| Neuro admin | `ui/app/admin/neuro/page.tsx`, admin metrics | Same ranges |
| Metrics | `ui/app/components/metrics/StatBar.tsx`, `DerivedCard.tsx`, `admin/page.tsx` | Consume updated helpers |
| State API | `src/gateway/server.py` | Emit gap / normalized_10 / label fields; fix derived social metrics that punish resting OT |
| Label source (preferred) | new `src/sim/labels.py` (or equivalent) | Canonical band tables + `label_for(chem, value, setpoint, norm_max)` |
| Tests | `tests/` | Baseline snapshot → expected chips; OT resting; adenosine bands vs sleep thresholds |
| Docs | this SPEC; optional one-line pointer in `docs/neurochemistry/README.md` | Display uses norm/gap, not v1 plasma tables |

**Out of scope paths:** `src/sim/chemistry.py` encoder path, opponent lists, tick dynamics — no change required for the display fix.

---

## Derived metrics (required touch)

Gateway `_compute_derived` uses absolute oxy fraction of max for `social_warmth` and similar. At resting OT (~0.5/10), social warmth collapses even when gap=0.

**Requirement:** second/third order metrics that represent *felt social state* must not treat OT gap≈0 as loneliness or coldness.

Options (pick one in implementation, document choice):

1. Weight OT by **gap** (and optional mild absolute), not raw % of max.  
2. Center OT contribution at setpoint (gap 0 → neutral contribution ~50).  
3. Cap OT’s penalty when gap ≥ −1.

Same review for any derived field that uses absolute DA/5-HT without gap if it paints baseline as depressed (spot-check `depression`, `hedonic_tone`, `loneliness`).

---

## Acceptance criteria

### A. Factory / settled baseline (awake or asleep with mild adenosine)

Using live setpoints after init (Big5-biased OK):

| Chem | Must NOT show | Must show (family) |
|------|---------------|--------------------|
| dopamine | ANHEDONIC, NO DRIVE as default | BASELINE / normal drive |
| serotonin | DYSPHORIC, SEVERELY LOW as default | NEUTRAL / SECURE / baseline mood |
| norepinephrine | SEDATED as default | RELAXED / CALM ALERT |
| oxytocin | NO BOND, DISTANT, error isolation | RESTING / QUIET |
| endorphins | DEPLETED as default | BASELINE / no glow |
| epinephrine | pathological empty | RESTING |
| cortisol | MAXED / ACUTE STRESS without cause | NORMAL or circadian-appropriate |
| adenosine | EXHAUSTED when norm ≪ 8 | ALERT–BUILDING if modest pressure; SLEEP ONSET only near threshold |

### B. Gap sensitivity

- Depress DA tonic well below setpoint → low-drive / anhedonic family chips appear.  
- Return to setpoint → baseline chips return.  
- Raise OT well above setpoint → WARMING / CONNECTED family — without requiring bond-score UI.

### C. Sleep pressure alignment

- Adenosine normalized ≈ 3 (wake threshold region) ≠ EXHAUSTED.  
- Adenosine normalized ≈ 8 → SLEEP ONSET / exhausted-adjacent family, consistent with auto-sleep enter.

### D. Sliders

- At resting DA (~8 nM), slider thumb is mid-ish on 0–20, not glued to zero on 0–300.  
- OT resting (~0.015) visible on 0–0.30 scale.

### E. API / UI consistency

- If server emits `label`, Control chip matches server for the same snapshot.  
- Unit string matches working units (no pg/mL DA chip math on nM values).

### F. Regression

- Decoder / insula behavior unchanged unless deliberately sharing a new `labels` helper.  
- No requirement to rewrite sim setpoints for tests to pass.

---

## Implementation plan (suggested PR split)

### PR1 — Display truth (minimum shippable)

1. Add gap + normalized_10 to state payload (and setpoint).  
2. Rewrite `labels.ts` (or server labels + thin UI) per classification.  
3. Fix `DISPLAY_RANGES`.  
4. Fix OT / Type B resting chips.  
5. Fix adenosine bands vs `SLEEP_*` constants (import or duplicate constants carefully — prefer shared or single documented numbers).  
6. Tests for acceptance A–D.  
7. Fix derived `social_warmth` / loneliness OT handling.

### PR2 — Single source of truth (hardening)

1. Move band tables to Python `src/sim/labels.py`.  
2. UI displays server labels only.  
3. Optional: admin tooltip with short implication text from server.

### PR3 — Optional product

1. Separate bond/relationship chip when bond data is ready.  
2. Circadian-aware cortisol copy (time-of-day tint) if desired.

Do not block PR1 on PR2/PR3.

---

## Test sketches

```python
def test_baseline_labels_not_crashed():
    sim = fresh_sim()  # or load factory defaults
    # apply zero encoder traffic; tick until phasic ~0
    state = build_state(sim)
    assert state["chemicals"]["dopamine"]["label"] in BASELINE_DA_LABELS
    assert state["chemicals"]["oxytocin"]["label"] not in {"NO BOND", "DISTANT"}
    assert state["chemicals"]["oxytocin"]["gap"] == 0 or abs(state["chemicals"]["oxytocin"]["gap"]) < 1.0

def test_adenosine_band_near_sleep_enter():
    # set adenosine combined so normalized_10 ≈ 8.0
    assert label == "SLEEP ONSET" or equivalent family

def test_ot_elevation_not_required_for_resting_ok():
    # OT at setpoint only
    assert label == "RESTING"
```

UI: optional Playwright/component test that Control chemistry at mocked baseline state does not render ANHEDONIC/NO BOND chips — nice-to-have if harness exists.

---

## Decision log (locked for this draft)

| Decision | Choice |
|----------|--------|
| Primary label scale | Normalized 0–10 + gap (Approach A) |
| OT resting chip | RESTING / non-error — never NO BOND at gap≈0 |
| Bond ladder on absolute OT | Removed; bond UI optional later |
| Sim setpoint rewrite | Not required for this spec |
| Spec split for OT | **No** — OT policy lives in this spec |
| Server labels | Recommended; UI-only rewrite acceptable for PR1 if tables match this doc |

---

## Open questions (resolve at sign-off)

1. **PR1 location of tables:** TS-only first vs Python-first? Recommendation: **Python-first** if gateway already owns state DTO; else TS-first for speed with PR2 migration.  
2. **Exact OT chip vocabulary:** RESTING vs QUIET vs NO SURGE — pick one string set for UI consistency.  
3. **NE Type A vs B:** NE is somewhat both (tone + arousal). Default this draft: Type A with resting = CALM ALERT, not SEDATED. Confirm.  
4. **Whether to show gap in Control UI** as a small mono delta next to nM (debug sugar) — optional, not required.

---

## Sign-off checklist

- [ ] Approach A (norm + gap) approved  
- [ ] OT policy approved (no NO BOND at rest)  
- [ ] Adenosine bands tied to sleep enter/wake approved  
- [ ] Derived social metrics OT fix approved  
- [ ] PR1 scope (no sim dynamics rewrite) approved  
- [ ] Open questions answered  

After sign-off: implement PR1; do not land half-migrated dual tables (v1 thresholds still consulted for Control chems).

---

## Appendix A — Illustrative resting norms (from current params)

For implementers; live Big5-biased setpoints may shift slightly.

| Chem | tonic_setpoint | normalization_max | Resting ~norm/10 |
|------|----------------|-------------------|------------------|
| dopamine | 8.0 | 20 | ~4.0 |
| serotonin | 6.0 | 15 | ~4.0 |
| norepinephrine | 3.0 | 20 | ~1.5 |
| epinephrine | 0.3 | 5 | ~0.6 |
| oxytocin | 0.015 | 0.30 | ~0.5 |
| endorphins | 2.5 | 40 | ~0.6 |
| cortisol | 250 | 1200 | ~2.1 (mean; circadian moves) |
| adenosine | 100 | 500 | ~2.0 (+ phasic while awake) |
| melatonin | 5 | 250 | low day / higher night |

These resting norms are **normal**, not mid-crisis.

## Appendix B — Why v1 pg/mL baselines are not the fix

| Chem | v1 baseline | Real compartment fit | Role in v1 UI |
|------|-------------|----------------------|---------------|
| DA 80 pg/mL | Plasma-ish | Not striatal nM tonic | Tuned to BASELINE chip |
| 5-HT 22 ng/mL | Platelet/whole-blood | Not extracellular CNS | Tuned to NEUTRAL |
| NE 200 pg/mL | Plasma OK | Not brain extracellular alone | CALM ALERT |
| OT 4 pg/mL | Plasma good | Rest still labeled NO BOND | Semantic bug even in v1 |
| Endorphins 12 pg/mL | Plasma low-normal | — | BASELINE in registry |

Restoring v1 numbers into the v2 nM sim would desync decoder, chemistry function, and docs. **Normalize labels to the sim; do not denormalize the sim to legacy UI.**
