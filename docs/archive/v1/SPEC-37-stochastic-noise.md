# SPEC-37: Stochastic Noise

## Problem

Mina's biological state is fully deterministic. Given the same starting state and the same sequence of stimuli, the simulation produces identical chemical trajectories every time. Real neurochemistry doesn't work this way — there is meaningful moment-to-moment variance in neurotransmitter release, receptor binding, and hormonal secretion that produces the subtle unpredictability characteristic of a living system.

Without noise, Mina's behavior can feel mechanically predictable. The same conversation at the same biological state will always produce the same emotional disposition. Stochastic noise would break this — introducing the biological "texture" of a real person who isn't perfectly consistent.

---

## Goal

Add per-tick Gaussian noise to the biological state engine — small enough to not destabilize the simulation but large enough to produce meaningful behavioral variability over time.

---

## Design (to be detailed)

### Noise Model

Apply noise at Phase 2 of the engine's advance loop (after baselines are computed, before cross-interactions) — perturb each chemical's value by a small Gaussian draw proportional to its natural variance.

```
new_value = computed_value + N(0, σ) * noise_scale
```

Where `σ` is per-chemical, calibrated to the coefficient of variation (CV) observed in physiological literature (most neurotransmitters: CV ~10–20%).

### Per-Chemical Noise Parameters

Each chemical in `constants.py` should gain a `noise_sigma` field — the standard deviation of the noise in native units per tick (60s). Example targets:

- Dopamine: σ ~3 pg/mL/tick (baseline 92, ~3% CV per minute)
- Serotonin: σ ~0.4 ng/mL/tick
- Cortisol: σ ~8 nmol/L/tick (cortisol has high pulsatile variance)
- Adenosine: σ ~0.5 nmol/L/tick (slower, smoother)
- Oxytocin: σ ~0.3 pg/mL/tick

Noise should be **clipped to never push a chemical below its critical floor or above its ceiling**.

### Noise Scaling by State

Some states should modulate noise amplitude:
- **High allostatic load** → increase cortisol and norepinephrine noise (dysregulation)
- **Sleep** → reduce all noise by ~50% (CNS quiets significantly during NREM)
- **High anxiety** → increase norepinephrine and GABA noise (labile arousal)

### Seed / Reproducibility

For debugging, noise should be seedable via config (`"noise_seed": 42` or `null` for true random). This lets us reproduce a specific trajectory when hunting bugs, then disable seeding for production.

### Interaction With Encoder

The encoder computes deltas from LLM reasoning — those should remain deterministic (the LLM itself already has temperature). Stochastic noise is purely a state-engine concern, applied independently of encoder deltas.

### Open Questions

- Should noise be applied every tick (60s) or at a slower cadence (e.g., every 5 ticks) to avoid excessive jitter?
- Do we want correlated noise between related chemicals (e.g., dopamine and norepinephrine co-vary in sympathetic activation) or fully independent draws?
- How do we validate that noise doesn't destabilize long-term trajectories? (SPEC-36 telemetry would catch this.)

---

## Expected Behavioral Effect

- Mina's mood won't feel identical on repeated interactions in similar states — there will be days she's slightly more irritable or slightly warmer for no externally-caused reason
- Chemical recovery trajectories will vary slightly (serotonin recovers to 23.1 one day, 24.6 the next)
- Edge-case thresholds (e.g., depression >60 triggering a behavioral signature) will trigger probabilistically near the boundary rather than exactly at it — more realistic than a hard cutoff

---

## Status

**Folded into SPEC-53.** The core design (per-chemical `noise_sigma` on `ChemicalProfile`,
engine application after clearance, state-modulated scaling, seed/reproducibility) is
fully specified there. The resting state validator in SPEC-53 uses rolling means to
handle noise correctly. Correlated noise between related chemicals remains an open
question deferred to a future spec.
