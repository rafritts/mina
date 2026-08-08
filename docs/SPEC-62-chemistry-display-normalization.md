# SPEC-62 — Chemistry Fidelity, Then Display

**Status:** Sim audit complete — **sim fixes before any UI work**  
**Date:** 2026-08-07  
**Priority order (product owner lock):**

1. **Certify / fix the sim** (engine truth)  
2. Update this spec with findings  
3. **UI / chips / labels — dead last**

**Depends on:** `src/sim/params.py`, `tick.py`, `chemistry.py`, `sim.py`, `decoder.py`  
**Related:** SPEC-61 (sleep onset); insula gap doctrine; v1 tombstone (SPEC-60) — v1 died for engine reasons, not chip colors

---

## Product stance (read this first)

The pain that killed v1 was a **broken simulation**, not an ugly dashboard.

> **Primary concern:** Is v2 chemically doing the right thing?  
> **Not primary:** Chip color, badge copy, slider cosmetics.

If the panel looks like a crash but levels sit on setpoint, **the gauge is lying — the sim may still be fine.**  
If the sim ratchets setpoints over days or fails to sleep/recover, **that is the real bug** even if chips look pretty.

This document originally started as a label/UI fix. After audit, it is reframed:

| Phase | Work | Priority |
|-------|------|----------|
| **0** | Certify sim (done — see below) | Required first |
| **1** | Fix real sim defects found in cert | **Next** |
| **2** | Optional sim soft-fidelity improvements | Later |
| **3** | Display normalization / labels / Control UI | **Dead last** |

**Do not implement Phase 3 before Phase 1.**

---

## Phase 0 — Certification report (2026-08-07)

### Method

- Read `params.py`, `tick.py`, `chemistry.py`, `sim.py`, `decoder.py`, `state.py`
- Ran `tests/test_sim_stability.py` (all **6 passed**)
- Deterministic numerical scenarios: fresh baseline, 1h/16h awake, sleep clear, auto-sleep timing, 60 warm messages, multi-day circadian, production `run/sim_state.json`
- Compared setpoints to `docs/neurochemistry/*` at order-of-magnitude level

### Verdict summary

| Question | Answer |
|----------|--------|
| Is baseline a monoamine **death spiral**? | **No** |
| Was the scary Control panel evidence of collapse? | **No** — mostly false UI labels on correct resting nM |
| Is the v2 engine free of all fidelity bugs? | **No** — see real defects below |
| Safe to “only fix chips” and call chemistry done? | **No** — fix sim defects first |
| Safe to ignore chip work forever? | Fine for fidelity; chips still **lie** as instruments |

### What is correct / healthy

#### 1. Resting monoamines and peptides (core)

Fresh Big5-biased baseline (example neuroticism-biased set):

| Chem | ~total | ~norm 0–10 | gap | Assessment |
|------|--------|------------|-----|------------|
| dopamine | ~8.0 nM | ~4.0 | 0 | On setpoint; matches striatal-ish tonic order (docs ~4–20 nM) |
| serotonin | ~5.7 nM | ~3.8 | 0 | On setpoint; extracellular nM order OK |
| norepinephrine | ~3.1 nM | ~1.6 | 0 | On setpoint; resting tone low on 0–10 **by design** (insula) |
| epinephrine | 0.3 nM | ~0.6 | 0 | Resting floor OK |
| oxytocin | ~0.015 nM | ~0.5 | 0 | CSF-ish floor (~17 pg/mL); **correct low absolute** |
| endorphins | 2.5 nM | ~0.6 | 0 | Working-model resting; gap 0 |
| adenosine | 100 nM | 2.0 | 0 | Model floor; see soft notes |
| cortisol | ~250–266 nM | ~2.2 | 0 | Diurnal-mean order OK |

Production `run/sim_state.json` at audit: DA/NE/OT/endorphins **gap≈0**, setpoints **above** death floors. Not crashed.

#### 2. Anti-death-spiral machinery (v1 → v2 intent)

| Mechanism | Status |
|-----------|--------|
| `EVENT_GAIN` (~0.18) caps chat-scale Class-1 spikes | **Pass** — one warm turn DA Δnorm ∈ (0.2, 2) |
| Opponent tonic floor 70% of natural | **Pass** — 16h awake does not floor DA/NE setpoints |
| Setpoint downward adapt scaled (`SETPOINT_DOWN_SCALE`) | **Pass** (for opponent drag path) |
| OT / totals hard-capped at `normalization_max` | **Pass** — sustained warm Class-1 does not OT-runaway |
| Adenosine accumulates in **phasic** wake reservoir; sleep clears phasic | **Pass** |
| Auto-sleep enter ~norm 8, wake ~3, min duration | **Pass** — ~12h continuous wake to enter from rest; 30h cycle sleeps and wakes |
| `_repair_collapsed_setpoints` on load | **Pass** — lifts old 25% scars |

#### 3. Chat-scale chemistry direction

60 warm encoder bursts (~30 min wall-ish):

- DA/5-HT/NE rise modestly (gap ~+1–2)  
- OT rises strongly (gap ~+5) via Class-2 accumulation — **correct direction for bonding**  
- Not instantaneous phys max flood  

#### 4. Decoder / pillars contract

- Felt state for brain pipeline: **decoder gap**, not absolute “% of childbirth max”  
- Insula already documents: OT at ~1 norm gap 0 = ordinary rest; DA at ~4 gap 0 = baseline drive  
- **Sim + decoder agree with that doctrine for resting monoamines**

#### 5. Opponents at rest

At fresh baseline, stress/threat opponents are **not** armed.  
(Adenosine→DA arms only after long wake when ADE norm ≥ 6 — intended sleepiness drag.)

---

### Real sim defects (Phase 1)

These are **engine** issues, not chip colors.

#### DEFECT-1 — Circadian setpoint ratchet (HIGH)

**What:** `tick` Phase 2 pulls tonic toward `setpoint + circadian_offset`. Phase 3 adapts setpoint toward tonic. Nightly melatonin (and daily cortisol CAR) **raises tonic above the “mean” setpoint**, so setpoint **absorbs the circadian peak over days**.

**Evidence (forced multi-day hour loop):**

| Day | Melatonin setpoint | Cortisol setpoint |
|-----|--------------------|-------------------|
| start | 5 | ~266 |
| end day 4 | **~55** | **~385** |

Production state matches the scar: melatonin setpoint **~42** (natural 5), cortisol setpoint **~362** (natural 250).

**Why it matters:** Long-running daemon is the real deployment. Over a week, “baseline” for clock hormones becomes nonsense; gap signals and recovery drift. This is the closest thing found to a **slow v2 correctness rot** (different shape than v1 monoamine death spiral, same class: **unbounded baseline walk**).

**Fix direction (implement in Phase 1, not UI):**

- Do **not** run setpoint adaptation on pure circadian residual, **or**
- Adapt only toward a **circadian-stripped** tonic (tonic − current offset), **or**
- Mark `circadian_driven` chems with `setpoint_adapt_rate: 0` / separate “phase offset” store that never enters setpoint, **or**
- Clamp circadian chems’ setpoints to a band around natural `tonic_setpoint`

Prefer one clear rule: **setpoint = allostatic / chronic exposure baseline; circadian is never allostasis.**

#### DEFECT-2 — Sleep flag not persisted (MEDIUM)

`Sim._sleeping` / `_sleep_elapsed_s` live only in memory. `sim_state.json` has `levels`, `last_updated`, `prev_normalized` only.

**Effect:** Process restart → always awake, even if adenosine still high or she was mid-sleep. Breaks continuity of sleep/clear dynamics across restarts.

**Fix:** Persist consciousness/sleep fields with state (align with SPEC-61 when that lands).

#### DEFECT-3 — Decoder gap vs circadian target (LOW–MEDIUM)

Gap = normalized(tonic+phasic) − normalized(**setpoint**), not vs `setpoint + circadian_offset`.

Evening cortisol can show gap ≈ −1.5 while tonic correctly tracks the evening trough. Pillars may see “below baseline cortisol” when the body is just on the clock.

**Fix options:** gap against circadian-adjusted target for `circadian_driven` chems; or expose `circadian_gap` separately; or teach pillars that clock chems use absolute phase (heavier). Prefer math fix in decoder for cort/mel/orexin.

#### DEFECT-4 — Gateway derived metrics misuse absolute OT (LOW for engine; MEDIUM if anything treats them as truth)

`_compute_derived` `social_warmth` weights raw OT as fraction of max → resting OT looks “cold.”  
`loneliness` uses OT **gap** (better).

History/stream may log second_order. Pillars primarily use decoder, not these — confirm before over-weighting.

**Fix:** center OT (and similar) on gap/setpoint for derived warmth. Still not as urgent as DEFECT-1.

---

### Soft fidelity notes (Phase 2 — not blockers)

| Item | Note |
|------|------|
| Adenosine floor 100 nM / max 500 | Docs: CSF ~40–90, BF ~30. Model is **scaled sleep-pressure space**, not literal microdialysis. OK if documented; optional retune later |
| Endorphins 2.5 nM working units | Plasma β-endorphin often pg/mL; treat as abstract CNS-ish working units unless re-grounded |
| Melatonin params comment says pg/mL; API tags all chems `nM` | Unit **label** inconsistency; internal dynamics self-consistent if offset/amplitude share units |
| Serotonin mild gap after hours | Small circadian amplitude (1 nM) + neuroticism bias — usually within noise floor for insula |
| Orexin→adenosine opponent threshold 5.0 | Resting orexin norm ~5 → edge-armed; drag ∝ (norm−threshold) so **zero at exact 5**. Harmless today; use `>` not `>=` if picky |
| NE resting norm ~1.5/10 | Intentional (insula). Not a crash |

**Order-of-magnitude param check (docs):** DA, 5-HT, OT, cortisol, epi — **acceptable**. Endorphins/adenosine — **model-soft**. Melatonin — **unit tag soft**.

---

### What the original “crash” screenshot was

Production-like resting/sleeping state:

- Monoamines **on setpoint**  
- OT **on floor** (correct)  
- Adenosine elevated with sleep pressure / sleep (not max 500)  
- UI chips (v1 pg/mL tables) said ANHEDONIC / NO BOND / EXHAUSTED  

**Conclusion:** That painpoint was **instrument failure**, not monoamine collapse.  
**But** production melatonin/cortisol **setpoint scars** show DEFECT-1 is already live. So: **not the drama the chips claimed; still not a fully clean long-run sim.**

---

## Phase 1 — Required sim work (before any UI)

### Goals

1. Stop circadian allostatic ratchet (DEFECT-1)  
2. Persist sleep (DEFECT-2)  
3. (Recommended same PR train) Circadian-aware gap for clock chems (DEFECT-3)  
4. Regression tests so v1-style “long run secretly corrupts baseline” cannot return  

### Acceptance (sim)

- [ ] Multi-day simulated clock (forced hour-of-day loop, ≥5 days): melatonin **setpoint** stays within a documented band of natural (e.g. ±20% or absolute ±2 nM/pg working units — pick one and test it), not 5→55  
- [ ] Same for cortisol setpoint (no unbounded walk from CAR alone)  
- [ ] Existing stability tests still pass  
- [ ] New test: 5 simulated days idle → monoamine setpoints still ≥ 65% natural; clock chem setpoints stable per band  
- [ ] Sleep flag survives save/load  
- [ ] Optional: evening cortisol gap vs circadian target not large when on the trough  

### Non-goals for Phase 1

- Rewriting all of `CHEMICAL_PARAMS` from primary literature  
- UI labels, chips, DISPLAY_RANGES  
- Full bond-score product  
- Perfect adenosine nM matching every paper  

---

## Phase 2 — Soft sim fidelity (optional)

- Document adenosine as “sleep pressure units mapped to nM-like scale” in params header  
- Revisit endorphin units if pillars ever need real plasma analogy  
- Unify melatonin unit string in API with params  
- Derived warmth OT gap-centering (if history/UI used for anything that feeds behavior)

---

## Phase 3 — Display / labels (DEAD LAST)

Only after Phase 1 acceptance.

### Problem (unchanged, deprioritized)

`ui/app/lib/labels.ts` still uses v1 unit thresholds. Resting nM → false crash chips.

### When you finally do this

- Labels from **normalized 0–10 + gap** (and circadian-aware gap if DEFECT-3 fixed)  
- OT at gap≈0 → **RESTING**, never NO BOND  
- Type A vs Type B is **UI shorthand only** (not neuroscience) — see appendix  
- Python-first label tables + API emit `label` preferred  
- Control may show gap as a debug instrument (useful for **sim** debugging)  
- Sliders max = `normalization_max`  

### Explicit non-priority

Chip colors, pretty bands, and “panel looks calm” are **not** success criteria for chemistry correctness.  
Success for Phase 3 is: **instruments tell the truth about the sim.**

Full UI design notes from the earlier draft are retained in spirit; do not implement until Phase 1 is done. Details:

#### Chem labeling shorthand (UI only — not engine types)

| Shorthand | Resting chip idea | Examples |
|-----------|-------------------|----------|
| Tone (was “Type A”) | baseline / neutral / calm-alert | DA, 5-HT, NE |
| Surge (was “Type B”) | RESTING (idle, not broken) | OT, epi, endorphin glow |
| Sleep pressure | tiredness scale aligned with auto-sleep thresholds | adenosine |
| Clock | phase-appropriate | melatonin, cortisol rhythm |

#### OT chemical vs bond language

Resting OT floor is **sim-correct**. Friend-ladder chips on absolute OT were never correct biology *or* correct sim readout.

---

## Decision log

| Decision | Choice |
|----------|--------|
| Priority | Sim cert/fix → then instruments; UI last |
| Baseline monoamine “crash” | **Not a sim collapse** — false labels |
| Long-run clock hormones | **Sim defect** (setpoint ratchet) — fix in Phase 1 |
| Implement labels first? | **No** |
| Type A/B | UI shorthand only; not neuroscience; not tonic/phasic |
| Restore v1 pg/mL into sim? | **No** — denormalizes a working nM-ish affect model |

---

## Open questions

None for priority. Phase 1 fix design for DEFECT-1 (which of the four options) can be chosen at implement time; recommendation: **circadian offset never enters setpoint adaptation** (adapt using circadian-stripped tonic).

---

## Appendix A — Stability tests (current)

`tests/test_sim_stability.py` — all passing at cert time:

1. Event gain single-turn bound  
2. OT cap under sustained warm Class-1  
3. 16h awake monoamine setpoints  
4. Sleep clears adenosine phasic  
5. Auto-sleep cycle recovers  
6. Repair lifts old floor scars  

**Missing (add in Phase 1):** multi-day circadian setpoint stability; sleep persistence round-trip.

## Appendix B — Production snapshot notes (audit)

Illustrative `run/sim_state.json`:

- DA/NE/OT/endorphins: healthy vs floors, gap ~0  
- Cortisol tonic can sit slightly under opponent floor during evening approach (circadian) — minor  
- Melatonin/cortisol **setpoints elevated** vs natural — **DEFECT-1 already visible in prod**

## Appendix C — Plain English for non-neuroscientists

- **Setpoint** = “where her chemistry thinks home is.”  
- **Tonic** = slow level. **Phasic** = short spike.  
- **Gap** = how far current felt level is from home (what the brain pipeline mostly cares about).  
- **Death spiral** = home and levels get crushed and never recover (v1 failure mode).  
- **This audit:** home for DA/5-HT/NE is fine; home for melatonin/cortisol is **slowly walking away** because the daily clock is being mistaken for a new normal. Fix that before painting chips.
