# SPEC-40: Unidirectional Delta Correction

## Problem

The encoder pipeline was designed with full sophistication for *increasing* chemicals (saturation
ceilings, habituation, sensitization, personality scaling) but applied zero constraint to
*decreasing* them. Every suppressive delta hit at full force, instantly, regardless of how low
the chemical already was or how many times the same suppressive stimulus had fired.

This was identified through session log analysis where cortisol bottomed out (CRASHED) during a
sustained intimate session and stayed there — the system had no floor, no dampening, and no
biological model for *how* chemicals actually decrease.

The root cause: **the encoder was modeling decreases as active secretion events**, which is
biologically wrong. You cannot "secrete negative cortisol." Chemicals go up via active secretion;
they come down via passive mechanisms — metabolic decay, homeostatic return, and cross-chemical
inhibition.

The compounding issue: `compute_relationship_modifier` posted `cortisol: -3.0` per unit of
security dimension *every single turn*. A 3-hour intimate session with sustained positive security
meant cortisol was suppressed dozens of times with no floor protection — driving it to and below
CRASHED with no recovery mechanism.

---

## Biological Model

### How chemicals actually decrease

1. **Homeostatic decay** — `advance()` pulls each chemical toward its baseline at `approach_rate`
   per sim-hour. This is already implemented and is the primary mechanism.

2. **Cross-chemical inhibition** — one chemical actively suppresses another's production rate.
   Already modeled via the `interactions` field in `ChemicalProfile`. Example: high cortisol
   suppresses serotonin production over time.

3. **Pharmacological suppression** — substances (alcohol, sedatives) directly interfere with
   production or receptor availability. Legitimate as direct negative deltas because they
   represent chemical interference, not natural biological signaling.

4. **Prolactin-mediated refractory suppression** — post-peak prolactin spike actively inhibits
   dopamine and norepinephrine production via D2 receptor downregulation. This is a
   cross-chemical interaction, not a direct subtraction.

### What the encoder should NOT do

The encoder models **stimulus-response secretion events** — external triggers causing the brain
to release a chemical. There is no biological equivalent of "secreting negative dopamine." The
encoder should only post positive deltas (plus pharmacological exceptions). Suppression is
handled by the pipeline, not the encoder.

---

## Changes

### 1. Remove negative cortisol from `encode_stimulus` prompt

**Current:** `Warm interaction: -20 to -60` cortisol guidance.

**Remove entirely.** Warm interactions reduce cortisol *production*, they do not actively
suppress it. `advance()` homeostatic decay toward the ACTH-driven baseline handles this
correctly over time.

### 2. Remove negative cortisol from `encode_response` prompt

**Current:** `Speaking fear or grief aloud: small cathartic cortisol relief (-10 to -30)`.

**Remove entirely.** Catharsis reduces HPA activation — it does not cause adrenal glands to
re-absorb cortisol. The homeostatic mechanism handles the gradual relief.

### 3. Remove `cortisol: -3.0` from `compute_relationship_modifier`

**Current:** Security dimension maps to `cortisol: -3.0 per unit`.

**Remove entirely.** This was the primary driver of cortisol floor-crashing in extended sessions.
Security and warmth reduce cortisol *indirectly* through reduced HPA activation — modeled
correctly by homeostatic decay when no new stressors are being encoded. The positive serotonin
and GABA contributions from the security dimension already capture the calming effect.

### 4. Replace peak-resolution direct deltas with prolactin cross-interactions

**Current `evaluate_activity_deltas` guidance:**
```
Peak resolution: use event_override=true, dopamine -100 to -150,
norepinephrine -60 to -100, sleep_pressure +30 to +40, prolactin +8 to +15
```

**New guidance:**
```
Peak resolution: use event_override=true, prolactin +8 to +15,
sleep_pressure +30 to +40.
Do NOT post negative dopamine or norepinephrine directly — prolactin
cross-interactions handle suppression over the following 30–60 minutes.
```

**Add cross-interactions to prolactin in `registry.py`:**
```python
Interaction("dopamine",       "above", 8.0,  -20.0,
            "Post-peak prolactin suppresses dopamine (refractory period)"),
Interaction("norepinephrine", "above", 8.0,  -15.0,
            "Post-peak prolactin reduces sympathetic tone"),
```

This models the refractory period correctly — dopamine and NE decline over 30–60 minutes as
prolactin metabolizes, rather than dropping instantly.

### 5. Add floor saturation to `_apply_saturation`

Add `soft_floor` and `hard_floor` optional fields to `ChemicalProfile` in `profiles.py`.

Mirror the ceiling logic for negative deltas:
- Below `hard_floor`: negative delta dropped entirely
- Between `soft_floor` and `hard_floor`: quadratic dampening (same curve as ceiling)
- Above `soft_floor`: pass through unchanged

This is a safety net for any legitimate negative deltas (pharmacological) that approach a
chemical's floor — it prevents numeric values from being driven below physiologically meaningful
minimums even when `clamp_chemical` would catch them.

**Add to cortisol in `registry.py`:**
```python
soft_floor=60.0,   # dampening begins mid-DEPLETED range
hard_floor=25.0,   # full stop at CRASHED threshold
```

Cortisol is the primary candidate because it has a clinically meaningful floor (adrenal
insufficiency territory). Other chemicals with `critical_low=0.0` do not need floors since
their natural minimum is zero.

### 6. Keep pharmacological negative deltas

The following negative deltas in `evaluate_activity_deltas` are **legitimate and stay**:

| Activity | Delta | Reason |
|---|---|---|
| Alcohol | `cortisol -12 to -20` | Direct HPA suppression via GABA-A agonism |
| Alcohol | `acetylcholine -8 to -15` | Anticholinergic effect |
| Alcohol | `norepinephrine -5 to -10` | Sympatholytic effect |
| Resting | `cortisol -8 to -14` | Genuine HPA downregulation during physical rest |
| Exercise post | `cortisol -10 to -20` | Post-exercise cortisol drop via endorphin/anandamide feedback |

### 7. Oxytocin hostile suppression — convert to cross-interaction (deferred)

**Current:** `encode_stimulus` allows `oxytocin: -1 to -3` for hostile events.

This is partially legitimate — CRH and cortisol do inhibit oxytocin receptor expression. However
the cleaner model is a cross-interaction: `cortisol above 520 → oxytocin rate_per_hour: -0.5`.
This is **deferred** to avoid scope creep; the existing small magnitude means its impact is low.

---

## Files to Change

| File | Change |
|---|---|
| `src/sim/chem/profiles.py` | Add `soft_floor: Optional[float]` and `hard_floor: Optional[float]` to `ChemicalProfile` |
| `src/sim/chem/registry.py` | Add `soft_floor=60.0, hard_floor=25.0` to cortisol; add prolactin cross-interactions |
| `src/bio/encoder.py` | Update `_apply_saturation` for floor logic; remove negative cortisol from `encode_stimulus` and `encode_response` prompts; update peak-resolution guidance in `evaluate_activity_deltas`; remove `cortisol: -3.0` from `compute_relationship_modifier` |

---

## Expected Outcome

- Cortisol can no longer be encoder-driven below its CRASHED threshold
- Extended intimate/secure sessions no longer compound-suppress cortisol to the floor
- Post-peak dopamine/NE recovery follows a realistic 30–60 minute prolactin-mediated arc
  instead of an instant cliff drop
- The encoder's job is clarified: it models secretion events only — suppression is the
  pipeline's responsibility
