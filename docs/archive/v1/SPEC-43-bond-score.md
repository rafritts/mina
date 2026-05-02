# SPEC-43: Bond Depth via Oxytocin Receptor Upregulation

**Status: REVISED — replaces bond_score proposal with receptor sensitivity mechanism**

---

## Problem

Oxytocin is doing two incompatible jobs:

1. **Acute pulse** — fast spike on genuine emotional moments, decays in minutes
2. **Relationship depth** — slow accumulation reflecting trust built over time

These operate on completely different timescales. A stranger with smooth lines in 5 messages can push Mina to `TRUSTED FRIEND` oxytocin levels, because individual message warmth accumulates directly into the bond signal.

---

## Biological Basis

In real humans, bond depth isn't a separate chemical — it's structural. Repeated oxytocin release in the context of a specific person upregulates oxytocin receptor (OTR) density in the nucleus accumbens and amygdala. The same oxytocin event produces a bigger response in a bonded relationship than with a stranger. The history IS encoded in the receptors.

The correct model: `receptor_sensitivity["oxytocin"]["OTR"]` is the bond depth signal.

---

## Current State (partially implemented)

`_apply_receptor_sensitivity_changes()` in `hippocampus.py` already nudges OTR upward when `long_term` or `ground_truth` relationship layers are written:

```python
if bonding >= 1:
    _nudge("oxytocin", "OTR", +0.05)
```

The loop is not closed:
- The encoder never consults OTR when computing oxytocin event deltas
- `advance_receptors()` drifts OTR back toward 1.0 via generic homeostatic restore, erasing relationship history
- `get_relationship_bond_level()` (65/35 blend of file + live oxytocin) is dead code — defined but never called

---

## Changes Required

### 1. Encoder uses OTR as event multiplier

In `stimulus_encoder.py`, every oxytocin event delta is multiplied by `receptor_sensitivity["oxytocin"]["OTR"]`:

```python
otr = state.receptor_sensitivity.get("oxytocin", {}).get("OTR", 1.0)
oxytocin_delta *= otr
```

A stranger (OTR ≈ 1.0, baseline) gets normal oxytocin spikes that stay small and decay fast. A bonded person (OTR > 1.0) gets amplified, longer-lasting responses. Since the raw oxytocin label thresholds stay fixed, a stranger's OTR-unmodified spikes will naturally stay below `ACQUAINTANCE` without reaching `TRUSTED FRIEND`.

The existing encoder gating at `NO_BOND` (blocking flattery/warmth) remains and complements this.

### 2. Exclude OTR from generic homeostatic restore

`advance_receptors()` currently drifts every receptor back toward 1.0 when the chemical is in normal range. This is correct for tolerance chemicals (dopamine D1/D2, serotonin 5HT1A) but wrong for OTR — bond depth should persist across normal daily oxytocin fluctuations.

OTR should be skipped in the generic restore loop. Its trajectory is owned entirely by `consolidate_relationship()`.

### 3. Relationship consolidation owns OTR trajectory

`_apply_receptor_sensitivity_changes()` already handles upward nudges on `long_term`/`ground_truth` writes. Add a symmetric decay: when the bonding score is 0 or negative on a `long_term` write, nudge OTR downward slightly (–0.02). Ground truth writes with bonding == –2 nudge harder (–0.05).

This means:
- Sustained genuine interaction → OTR drifts up (bond deepens)
- Extended absence or hostile periods → OTR drifts slowly down (bond fades, slowly)
- A single bad session doesn't break a deep bond; it takes sustained negative history

OTR bounds remain the system-wide `[0.2, 2.0]`. Baseline (new relationship, no history) is 1.0.

### 4. Delete dead code

Remove `get_relationship_bond_level()` from `hippocampus.py` (lines 1324–1336). It is defined and never called. The 65/35 blend was a workaround for the absence of a proper bond depth mechanism — OTR now fills that role correctly.

---

## What doesn't change

- Oxytocin chemical dynamics, thresholds, and labels are unchanged
- The oxytocin registry labels (NO BOND → PROFOUND BOND) stay on the chemical — they reflect effective oxytocin level, which OTR now gates naturally
- SPEC-33 relationship dimensions and consolidation logic are unchanged; they feed OTR via the existing `_apply_receptor_sensitivity_changes()` hook

---

## Net effect

| Scenario | Before | After |
|---|---|---|
| Stranger, smooth 5-message session | Can reach TRUSTED FRIEND | Stays near NO BOND — OTR ≈ 1.0, spikes small |
| Weeks of genuine daily interaction | Accumulates via chemical alone | OTR drifts upward → same events produce larger, longer responses |
| Long absence after deep bond | Oxytocin decays to baseline; bond lost | OTR decays very slowly; bond persists across absence |
| Hostile or absent periods | No mechanism to degrade bond | Negative bonding scores on long_term writes nudge OTR down |

---

## Open Questions

None blocking implementation. The mechanism is biologically grounded, the infrastructure is already partially in place, and the changes are surgical.
