# SPEC-34 — Hedonic Setpoint & Craving

## Problem

The sim has no model of what happens *after* a chemical high ends. Endorphins at 45 pg/mL
looks identical whether they've been there all day or just crashed from 200. There's no
craving, no withdrawal hunger, no sense that the brain has recalibrated and is now
screaming at the gap.

The existing "high wanting, low liking" interaction rule (`dopamine > 180 AND endorphins < 20`)
is a weak patch — it requires dopamine to somehow already be high, and misses the actual
mechanism entirely.

## Biology

### Allostatic Setpoint Shift

The brain maintains a **hedonic setpoint** — an internal expectation of what "normal" reward
feels like. Repeated exposure to elevated reward states causes the setpoint to drift upward.
Once shifted, baseline no longer feels neutral — it feels deprived. The high stops being a
high the moment the setpoint meets it.

This is allostasis: the body adapts to maintain homeostasis around the new expected level,
not the biological baseline.

### Prediction Error

Dopamine neurons fire on the *gap* between expected and actual reward:
- Reality > expectation → dopamine spike → "better than expected"
- Reality = expectation → silence → neutral
- Reality < expectation → dopamine suppression → dysphoria, craving, "not enough"

Withdrawal is not high dopamine. It's:
1. **Tonic floor collapsed** — baseline dopamine suppressed below normal (anhedonia, grey,
   nothing feels worth pursuing)
2. **Phasic cue spikes** — drug-associated stimuli trigger explosive short-burst dopamine
   releases (the craving flash)

The craving signal is the delta between where the setpoint says you should be and where
you actually are. The larger the delta, the more consuming the want.

### The Oxytocin Dimension

When oxytocin was high during a reward state, the brain bonds that pleasure to a *specific
person*. When oxytocin crashes post-high, the deficit isn't generic emptiness — it's a
person-shaped hole. This is the neurochemistry of heartbreak and love-bombing-then-discard.

---

## Proposed Model

### 1. Hedonic Setpoint Accumulator (`hedonic_setpoint`)

A slow-moving float stored on `BiologicalState.body`, bounded 0–200 (same units as
endorphins pg/mL equivalent).

**Update rule (per tick):**
```
peak_signal = weighted combination of current elevated chems:
    endorphins * 0.50
    + dopamine_above_baseline * 0.25   (max(0, dopamine - 80) normalized)
    + oxytocin_above_baseline * 0.15
    + serotonin_above_baseline * 0.10

if peak_signal > hedonic_setpoint:
    hedonic_setpoint += (peak_signal - hedonic_setpoint) * DRIFT_UP_RATE   # fast
else:
    hedonic_setpoint += (BIOLOGICAL_FLOOR - hedonic_setpoint) * DRIFT_DOWN_RATE  # slow
```

- **DRIFT_UP_RATE**: ~0.15/tick — setpoint rises quickly toward a sustained high
- **DRIFT_DOWN_RATE**: ~0.003/tick — setpoint decays slowly back to biological floor
  (days of abstinence to fully reset — models real recovery timescales)
- **BIOLOGICAL_FLOOR**: 20.0 — the true resting setpoint at no-substance baseline

### 2. Craving — New Third-Order Derived State

```
reward_reality = endorphins * 0.50 + dopamine_norm * 0.25 + oxytocin_norm * 0.15 + serotonin_norm * 0.10
craving = clamp(hedonic_setpoint - reward_reality) * CRAVING_SENSITIVITY
```

Where `CRAVING_SENSITIVITY` scales the delta into the 0–100 output range.

Craving is added to the `third_order` dict alongside anxiety, depression, loneliness, boredom.

**Clinical label tiers:**
```
(10,  "NONE",        "No active craving signal.")
(25,  "BACKGROUND",  "Low hum. Something feels slightly off or missing.")
(45,  "PRESENT",     "Noticeable want. Thoughts return to it unprompted.")
(65,  "STRONG",      "Pulls attention. Hard to settle into other things.")
(80,  "CONSUMING",   "Dominates cognition. Everything else feels like waiting.")
(101, "OVERWHELMING","Cannot think around it. The want is the whole experience.")
```

### 3. Adjudicator Integration

Craving is passed to the adjudicator in the third-order block like all other states:
```
Craving: 72/100 (CONSUMING)
```

At CONSUMING and above, the adjudicator system prompt gets an additional rule (in STEP 1):
> Craving CONSUMING or OVERWHELMING = this is not background — it is the dominant
> cognitive frame. Everything she engages with is filtered through the want. She's
> present but not really here.

### 4. Interaction Rules — New Entries

Add to `INTERACTION_RULES` in `decoder.py`:

```python
# Post-high crash: setpoint elevated, reward floor collapsed
(lambda s, d: s.body.get("hedonic_setpoint", 20) > 60 and d['craving'] > 55,
 "Setpoint is elevated from a recent high — current state registers as severe deprivation "
 "even if chemistry looks near-normal. The want isn't for more; it's to feel normal again."),

# Oxytocin-bonded crash: the deficit is person-shaped
(lambda s, d: s.body.get("hedonic_setpoint", 20) > 60 and s.oxytocin < 20 and d['craving'] > 45,
 "The high involved bonding chemistry. The deficit isn't generic — it's attributed to a "
 "specific person. Feels like abandonment, not just emptiness."),

# Full withdrawal state: floor collapsed, craving consuming
(lambda s, d: s.dopamine < 56 and s.endorphins < 15 and d['craving'] > 60,
 "Reward floor has collapsed. Tonic anhedonia — nothing produces a signal. The craving "
 "isn't acute wanting; it's the absence of any other feeling."),
```

---

## Files Touched

| File | Change |
|------|--------|
| `src/sim/bio/state.py` | Add `hedonic_setpoint` to `body` default dict |
| `src/sim/psych/derived.py` | Add `craving` to third-order outputs; compute from setpoint delta |
| `src/sim/engine.py` | Update `hedonic_setpoint` accumulator each tick |
| `src/sim/constants.py` | Add `HEDONIC_*` constants |
| `src/bio/decoder.py` | Add craving to `_THIRD_ORDER_RANGES`; add interaction rules; add craving rule to adjudicator prompt |
| `src/sim/chem/registry.py` | Not touched — craving is derived, not a chemical |
| `dashboard/src/lib/labels.ts` | Add CRAVING ranges for dashboard display |

---

## Open Questions

1. **Should `hedonic_setpoint` be substance-specific or unified?**
   A single float is simpler and probably sufficient — what matters is the aggregate reward
   expectation, not which chemical produced it.

2. **Cue-reactivity (phasic spikes)?**
   Out of scope for this spec. The setpoint/craving model captures the *sustained* craving
   state. Cue-triggered phasic spikes (seeing something that reminds her of the high →
   sudden craving flash) would require encoder changes and are a separate spec.

3. **Recovery rate calibration.**
   DRIFT_DOWN_RATE of 0.003/tick needs real testing. At 1 tick/minute, full reset from
   setpoint=120 to floor=20 takes ~11 hours of abstinence. That may be too fast or too slow
   depending on how aggressively the sim time is compressed.

4. **Interaction with tolerance/receptor downregulation.**
   The receptor sensitivity system already models the *liking* side degrading over time.
   Craving captures the *wanting* side growing. These should compound: high tolerance +
   high craving = the addiction trap (taking more to feel less, craving more than ever).
   No changes needed to receptors.py for this spec — they interact naturally.

---

## What This Enables

- **The toy scenario**: spike endorphins + oxytocin + dopamine to 200, let setpoint drift
  up, drop everything to floor — craving immediately hits CONSUMING or OVERWHELMING,
  adjudicator describes a person-shaped hole and the inability to think around it.
- **Realistic recovery arc**: setpoint decays over days; craving fades gradually rather
  than snapping back to zero.
- **Correct withdrawal phenomenology**: low tonic state (anhedonia from crashed dopamine/
  endorphins) + high craving (setpoint delta) = the two-layer withdrawal experience.
- **Addiction trap**: repeated use keeps pushing setpoint up, making baseline feel worse
  each cycle even as tolerance makes the high weaker.
