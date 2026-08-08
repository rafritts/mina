# SPEC-63 — Chemistry Fidelity Certification & Display (Deferred)

**Status:** Certification complete — **blocked on SPEC-62** for engine fixes; UI still dead last  
**Date:** 2026-08-07  
**Formerly:** SPEC-62 (renumbered 2026-08-07)  
**Depends on:** **SPEC-62** (sim defect corrections must land first)  
**Related:** SPEC-61 (voluntary sleep onset); SPEC-60 (v1 tombstone); insula gap doctrine

---

## Product stance

The pain that killed v1 was a **broken simulation**, not an ugly dashboard.

> **Primary concern:** Is v2 chemically doing the right thing?  
> **Not primary:** Chip color, badge copy, slider cosmetics.

| Phase | Work | Spec | Priority |
|-------|------|------|----------|
| **0** | Certify sim | this doc | Done |
| **1** | Fix real sim defects | **SPEC-62** | **Next — implement first** |
| **2** | Soft sim fidelity | this doc § Phase 2 | Later |
| **3** | Display / labels / Control UI | this doc § Phase 3 | **Dead last** |

**Do not implement Phase 3 before SPEC-62 acceptance.**

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
| Is the v2 engine free of all fidelity bugs? | **No** — tracked in **SPEC-62** |
| Safe to “only fix chips” and call chemistry done? | **No** |
| Safe to ignore chip work forever? | Fine for fidelity; chips still **lie** as instruments |

### What is correct / healthy

#### 1. Resting monoamines and peptides (core)

Fresh Big5-biased baseline (example neuroticism-biased set):

| Chem | ~total | ~norm 0–10 | gap | Assessment |
|------|--------|------------|-----|------------|
| dopamine | ~8.0 nM | ~4.0 | 0 | On setpoint; striatal-ish tonic order (docs ~4–20 nM) |
| serotonin | ~5.7 nM | ~3.8 | 0 | On setpoint; extracellular nM order OK |
| norepinephrine | ~3.1 nM | ~1.6 | 0 | On setpoint; low on 0–10 **by design** (insula) |
| epinephrine | 0.3 nM | ~0.6 | 0 | Resting floor OK |
| oxytocin | ~0.015 nM | ~0.5 | 0 | CSF-ish floor; **correct low absolute** |
| endorphins | 2.5 nM | ~0.6 | 0 | Working-model resting; gap 0 |
| adenosine | 100 nM | 2.0 | 0 | Model floor; see soft notes |
| cortisol | ~250–266 nM | ~2.2 | 0 | Diurnal-mean order OK |

Production `run/sim_state.json` at audit: DA/NE/OT/endorphins **gap≈0**, setpoints **above** death floors. Not crashed.

#### 2. Anti-death-spiral machinery (v1 → v2 intent)

| Mechanism | Status |
|-----------|--------|
| `EVENT_GAIN` (~0.18) caps chat-scale Class-1 spikes | **Pass** |
| Opponent tonic floor 70% of natural | **Pass** |
| Setpoint downward adapt scaled (`SETPOINT_DOWN_SCALE`) | **Pass** (opponent path) |
| OT / totals hard-capped at `normalization_max` | **Pass** |
| Adenosine phasic wake reservoir; sleep clears phasic | **Pass** |
| Auto-sleep enter ~8 / wake ~3 | **Pass** |
| `_repair_collapsed_setpoints` on load | **Pass** |

#### 3. Chat-scale chemistry direction

60 warm encoder bursts: DA/5-HT/NE modest rise; OT strong Class-2 rise — correct bonding direction.

#### 4. Decoder / pillars contract

Felt state uses **decoder gap**. Insula: OT ~1 gap 0 = ordinary rest; DA ~4 gap 0 = baseline drive. Sim agrees for resting monoamines.

#### 5. Opponents at rest

Stress/threat opponents **not** armed at fresh baseline.

---

### Defects (owned by SPEC-62)

| ID | Severity | One-line |
|----|----------|----------|
| **DEFECT-1** | HIGH | Circadian peaks absorbed into setpoint (mel/cort ratchet over days) |
| **DEFECT-2** | MEDIUM | Sleep flag not persisted across restart |
| **DEFECT-3** | LOW–MEDIUM | Decoder gap ignores circadian target |
| **DEFECT-4** | LOW (engine) | Gateway `social_warmth` uses absolute OT |

Full problem statements, designs, acceptance tests: **`docs/SPEC-62-sim-correctness-defects.md`**.

Production already shows DEFECT-1 scars (melatonin setpoint ~42 vs natural 5; cortisol ~362 vs ~250).

---

### Soft fidelity notes (Phase 2 — not blockers)

| Item | Note |
|------|------|
| Adenosine 100 / 500 | Scaled sleep-pressure space, not literal CSF microdialysis |
| Endorphins 2.5 nM | Working units; plasma often pg/mL |
| Melatonin unit tag | Params comment pg/mL; API says nM — label only if dynamics share units |
| NE resting ~1.5/10 | Intentional (insula) |
| Orexin→ADE threshold `>= 5` | Zero drag at exact equality; cosmetic |

---

### What the original “crash” screenshot was

Monoamines on setpoint; OT on floor (correct); modest adenosine; **UI chips lied**.  
Not monoamine collapse. Still not a fully clean long-run sim until SPEC-62.

---

## Phase 2 — Soft sim fidelity (optional; after SPEC-62)

- Document adenosine as sleep-pressure model scale in params header  
- Revisit endorphin units if needed  
- Unify melatonin unit string in API  
- DEFECT-4 derived warmth if not already done in SPEC-62  

---

## Phase 3 — Display / labels (DEAD LAST)

Only after **SPEC-62** acceptance.

### Problem

`ui/app/lib/labels.ts` uses v1 unit thresholds. Resting nM → false crash chips.

### When you finally do this

- Labels from **normalized 0–10 + gap** (circadian-aware if DEFECT-3 fixed)  
- OT at gap≈0 → **RESTING**, never NO BOND  
- Tone / surge / sleep / clock shorthand is **UI only** — not neuroscience, not tonic/phasic  
- Python-first label tables + API `label` preferred  
- Control may show gap as a **sim debug instrument**  
- Sliders max = `normalization_max`  

Success: **instruments tell the truth about the sim** — not “panel looks calm.”

| Shorthand | Resting chip idea | Examples |
|-----------|-------------------|----------|
| Tone | baseline / neutral / calm-alert | DA, 5-HT, NE |
| Surge | RESTING (idle, not broken) | OT, epi, endorphin glow |
| Sleep pressure | aligned with auto-sleep thresholds | adenosine |
| Clock | phase-appropriate | melatonin, cortisol rhythm |

---

## Decision log

| Decision | Choice |
|----------|--------|
| Renumber | Former SPEC-62 → **SPEC-63**; engine fixes → **SPEC-62** |
| Priority | SPEC-62 first; this doc Phase 3 last |
| Baseline monoamine “crash” | Not a sim collapse — false labels |
| Restore v1 pg/mL into sim? | **No** |

---

## Appendix — Stability tests at cert time

`tests/test_sim_stability.py` — 6/6 passed. Multi-day circadian + sleep persistence tests land under SPEC-62.

## Appendix — Plain English

- **Setpoint** = where chemistry thinks home is  
- **Gap** = how far current is from home (pipeline signal)  
- **Death spiral** = home crushed forever (v1)  
- **Cert finding:** DA/5-HT/NE home is fine; melatonin/cortisol home **walks** because the daily clock was mistaken for a new normal — fix in SPEC-62 before painting chips  
