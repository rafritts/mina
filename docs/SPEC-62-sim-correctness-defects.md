# SPEC-62 — Sim Correctness Defects (Post-Cert Fixes)

**Status:** Draft — ready to implement (product priority: before any UI / SPEC-63 Phase 3)  
**Date:** 2026-08-07  
**Source:** Certification audit in **SPEC-63** (formerly SPEC-62)  
**Depends on:** current v2 sim (`src/sim/*`)  
**Blocks:** SPEC-63 Phase 3 (display/labels); trustworthy long-run daemon  
**Related:** SPEC-61 (sleep/consciousness persistence should align); SPEC-60 (v1 tombstone)

---

## Problem

SPEC-63 certified that **baseline monoamines are not in a death spiral** and that the scary Control chips were mostly false instruments. The same audit found **real engine defects** that corrupt long-running state — the failure mode that matters for a 24/7 companion.

| ID | Severity | Defect |
|----|----------|--------|
| DEFECT-1 | **HIGH** | Circadian peaks leak into allostatic **setpoint** (melatonin / cortisol ratchet) |
| DEFECT-2 | **MEDIUM** | Sleep / consciousness not persisted in `sim_state.json` |
| DEFECT-3 | **LOW–MEDIUM** | Decoder **gap** ignores circadian target for clock chems |
| DEFECT-4 | **LOW** (engine) | Gateway derived `social_warmth` treats resting OT as cold |

This spec is the implementation contract to **fix those defects**. No UI work.

---

## Goals

1. Setpoint remains **allostatic / chronic** only — **never** the daily clock.  
2. Sleep state survives process restart.  
3. Decoder gap for clock chems does not cry “off baseline” when tonic is correctly on the circadian trough/peak.  
4. Derived warmth does not punish resting OT.  
5. Regression tests lock the above so long-run rot cannot return silently.

---

## Non-goals

- UI labels, chips, `labels.ts`, DISPLAY_RANGES (SPEC-63 Phase 3)  
- Full voluntary sleep-onset machine (SPEC-61) — only persist whatever sleep fields exist today; design so SPEC-61 can extend  
- Re-deriving all `CHEMICAL_PARAMS` from primary literature  
- Changing Class-1 encoder weights, EVENT_GAIN, or opponent topology (unless a fix requires a one-line threshold tweak)  
- Perfect literal adenosine CSF nM  

---

## DEFECT-1 — Circadian setpoint ratchet

### Mechanism (current)

```text
Phase 2:  tonic → setpoint + circadian_offset(hour)
Phase 3:  setpoint → tonic   (slow adapt)
```

When offset &gt; 0 for hours (night melatonin, morning cortisol), tonic sits above the mean setpoint. Phase 3 treats that as chronic elevation and **raises setpoint**. Over days:

| Chem | Natural setpoint | After ~5 simulated days (audit) |
|------|------------------|----------------------------------|
| melatonin | 5 | ~55 |
| cortisol | ~250–266 | ~385 |

Production scars: melatonin setpoint ~42, cortisol ~362.

Same class as v1: **unbounded baseline walk**. Different driver: clock, not opponents.

### Design (locked)

**Rule:** `setpoint` is allostasis only. Circadian is a **temporary offset** and must not enter setpoint adaptation.

**Implementation (preferred):**

In `tick` Phase 3 (setpoint adaptation), for each chemical:

```text
circ = _circadian_offset(name, hour)   # 0 if not in CIRCADIAN
stripped = lvl.tonic - circ            # “what tonic would be without today's clock”
gap_for_adapt = stripped - lvl.setpoint
# then adapt setpoint using gap_for_adapt (with existing SETPOINT_DOWN_SCALE on negative)
```

Phase 2 **unchanged**: tonic still tracks `setpoint + circ` (felt level still has a daily rhythm).

**Why not alternatives:**

| Alternative | Why secondary |
|-------------|----------------|
| `setpoint_adapt_rate = 0` on all circadian_driven | Also blocks real chronic stress / lifestyle allostasis on cortisol |
| Clamp setpoint to band around natural | Band-aids; still adapts wrong signal inside the band |
| Separate phase store | More state; stripped-tonic is enough |

**Circadian list today** (`CIRCADIAN` / `circadian_driven`): cortisol, melatonin, orexin, serotonin (mild). Stripped adapt applies whenever `_circadian_offset` ≠ 0 path exists — i.e. any chem in `CIRCADIAN` dict. Safe for amplitude 0 edge.

### Repair of existing scars

On load (extend `_repair_collapsed_setpoints` or sibling):

For each chem in `CIRCADIAN`:

- If `setpoint` is outside `[natural * 0.85, natural * 1.15]` **and** the excess is consistent with multi-day ratchet (optional heuristic), **or** simpler: if `abs(setpoint - natural_big5_biased) / natural > 0.25` for circadian chems only → reset setpoint toward Big5-biased natural (same as init), and pull tonic toward `new_setpoint + current_circadian_offset` without shocking phasic.

**Simpler repair (ship this):** for chems in `CIRCADIAN`, if `setpoint > natural * 1.25` or `setpoint < natural * 0.75`, set `setpoint = natural_with_big5` (recompute bias once), leave tonic to Phase 2 convergence on next ticks. Log repair.

Monoamine non-circadian setpoints: **do not** mass-reset (production DA is fine).

### Tests

```text
test_multiday_circadian_does_not_ratchet_setpoints:
  force hour-of-day through 5 days of ticks (monkeypatch _hour_of_day)
  assert melatonin.setpoint within ±15% of initial (or ± max(2.0, 0.15*natural))
  assert cortisol.setpoint within ±15% of initial
  assert dopamine.setpoint still ≥ 0.65 * natural  # no regression

test_circadian_tonic_still_swings:
  at forced hour=2, melatonin tonic > setpoint (night peak)
  at forced hour=14, melatonin tonic ≤ setpoint-ish (day low)
  # rhythm preserved; only setpoint stable
```

---

## DEFECT-2 — Sleep not persisted

### Mechanism (current)

`Sim._sleeping`, `Sim._sleep_elapsed_s` are memory-only.  
`ChemicalState.to_dict()` / `sim_state.json` → `levels`, `last_updated`, `prev_normalized` only.  
Restart ⇒ always awake.

### Design (locked)

Persist on `ChemicalState` (or a small top-level envelope — prefer **state object** so one file stays SoT):

```json
{
  "levels": { ... },
  "last_updated": ...,
  "prev_normalized": { ... },
  "sleeping": false,
  "sleep_elapsed_s": 0.0
}
```

- `ChemicalState` gains `sleeping: bool = False`, `sleep_elapsed_s: float = 0.0`  
- `to_dict` / `from_dict` / `load` / `save` round-trip them  
- `Sim.__init__` after load: `self._sleeping = state.sleeping`, `self._sleep_elapsed_s = state.sleep_elapsed_s`  
- Whenever sleep toggles (`set_sleeping`, `_maybe_toggle_sleep_locked`): write through to `self._state.sleeping` / `sleep_elapsed_s`  
- Periodic save already every ~3 min — sufficient; optional save on sleep transitions  

**SPEC-61 note:** When consciousness becomes `awake | settling | asleep`, extend the same fields (e.g. `consciousness`, settle timestamps). This spec only persists **current** binary sleep. Do not invent settling here.

### Missing chem keys on old files

`from_dict`: default `sleeping=False`, `sleep_elapsed_s=0.0` if absent.

### Tests

```text
test_sleep_roundtrip_save_load:
  build state, set sleeping True, sleep_elapsed_s = 3600
  save → load
  assert sleeping and elapsed == 3600

test_sim_init_restores_sleep:
  write temp sim_state with sleeping true
  Sim() loads it
  assert sim.is_sleeping()
```

---

## DEFECT-3 — Decoder gap vs circadian target

### Mechanism (current)

```text
gap = norm(tonic+phasic) - norm(setpoint)
```

Evening cortisol tonic correctly near `setpoint + (−large offset)` ⇒ large **negative** gap while physiology is on-clock.

### Design (locked)

For chemicals present in `CIRCADIAN`:

```text
target_nM = setpoint + _circadian_offset(name, hour_now)
gap = norm(tonic+phasic) - norm(target_nM)
```

For all others, keep `gap` vs setpoint only.

`setpoint` field in decoder output remains **allostatic** setpoint normalized (unchanged meaning).  
Optionally add `target` (normalized circadian-adjusted) for debugging — **nice-to-have**, not required if tests assert gap only.

Use the same `_hour_of_day(time.time())` as tick (wall clock). Document that admin “advance hours” without a sim clock still uses wall hour for circadian (pre-existing limitation; out of scope to add virtual sim clock unless already present).

### Tests

```text
test_evening_cortisol_gap_near_zero_when_on_trough:
  set cortisol tonic ≈ setpoint + offset(hour=20), phasic 0
  decode → |gap| ≤ 1  # noise floor

test_cortisol_true_stress_still_positive_gap:
  tonic well above setpoint + offset
  decode → gap ≥ 2
```

---

## DEFECT-4 — Derived social_warmth vs absolute OT

### Mechanism (current)

Gateway `_compute_derived`: `social_warmth` uses `v("oxytocin")` = fraction of max × 100. Resting OT ~5% of max ⇒ warmth looks cold with gap 0.

### Design (locked)

Center OT contribution on **gap** (and keep mild absolute optional):

```text
# Example — pick one clear formula and test it
ot_component = 50 + gap("oxytocin") * 8.0   # gap 0 → 50 neutral; clamp 0–100
# social_warmth = clamp(ot_component*0.40 + ht*0.25 + end*0.15 + (100-crt)*0.20)
```

At OT gap 0, OT term ≈ 50 (neutral), not ~5.  
`loneliness` already uses OT gap — leave unless double-counting; spot-check defaults at baseline.

### Tests

```text
test_baseline_social_warmth_not_floor:
  fresh state → social_warmth in e.g. 35–65 (not < 20 solely due to OT)
```

---

## Implementation order

| Step | Work | Defects |
|------|------|---------|
| 1 | Stripped-tonic setpoint adapt + multi-day tests | DEFECT-1 |
| 2 | Circadian setpoint scar repair on load | DEFECT-1 |
| 3 | Persist sleep fields | DEFECT-2 |
| 4 | Decoder circadian target gap | DEFECT-3 |
| 5 | Derived social_warmth | DEFECT-4 |
| 6 | Full stability suite green | all |

Single PR preferred if small; split 1–2 vs 3–5 acceptable. **No UI files.**

---

## Files in scope

| File | Change |
|------|--------|
| `src/sim/tick.py` | Phase 3 stripped adapt; maybe export circadian helper |
| `src/sim/decoder.py` | Circadian-adjusted gap for CIRCADIAN chems |
| `src/sim/state.py` | `sleeping`, `sleep_elapsed_s` serialize |
| `src/sim/sim.py` | Load/save sleep; write-through on toggle; repair circadian setpoints |
| `src/sim/params.py` | Optional comment only (adenosine model scale) — no required constant change |
| `src/gateway/server.py` | DEFECT-4 derived formula |
| `tests/test_sim_stability.py` or `tests/test_sim_correctness.py` | New tests above |

**Out of scope:** `ui/**`, `labels.ts`.

---

## Acceptance checklist

- [ ] 5-day forced circadian loop: mel/cort **setpoints** stable within band; monoamines not floored  
- [ ] Night melatonin tonic still rises above daytime (rhythm preserved)  
- [ ] Production-like scarred mel/cort setpoints repaired on load  
- [ ] Sleep true + elapsed survives save/load and `Sim()` init  
- [ ] On-trough evening cortisol \|gap\| small; true elevation still positive gap  
- [ ] Baseline social_warmth not OT-crushed  
- [ ] Existing `test_sim_stability.py` still all pass  
- [ ] No UI-only changes required for this spec to close  

---

## Decision log

| Decision | Choice |
|----------|--------|
| DEFECT-1 fix | Adapt setpoint using **circadian-stripped** tonic |
| DEFECT-2 | Persist `sleeping` + `sleep_elapsed_s` on ChemicalState |
| DEFECT-3 | Gap vs `setpoint + circ_offset` for CIRCADIAN chems |
| DEFECT-4 | OT term centered at gap 0 → neutral ~50 |
| UI | Explicitly out of scope |
| Numbering | This is **SPEC-62**; cert/display deferred doc is **SPEC-63** |

---

## Open questions

None blocking. Virtual sim clock for `advance(hours)` circadian is **out of scope** unless implementation touches hour source anyway — note as follow-up if admin advance remains wall-clock-bound.
