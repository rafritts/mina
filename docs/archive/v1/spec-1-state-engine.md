# Spec 1 — State Engine

> Tracks first-order biological values over real time. Computes second and third-order derived values on demand. The only source of truth for Mina's biology.

---

## Persistence

State is stored in `state.json` at the project root. Updated continuously. Read on startup.

```json
{
  "last_updated": 1712345678.0,
  "sleep_pressure": 42.0,
  "glucose": 68.0,
  "hydration": 75.0,
  "cortisol": 28.0,
  "dopamine": 61.0,
  "serotonin": 55.0,
  "norepinephrine": 22.0,
  "oxytocin": 48.0,
  "endorphins": 15.0,
  "acetylcholine": 58.0,
  "melatonin": 8.0,
  "tolerance": {}
}
```

`tolerance` is a dict of `{substance: float}` — per-substance receptor desensitization.

---

## Time Advancement

On every read, the engine computes how much real time has elapsed since `last_updated` and applies decay/buildup functions to all first-order values. No background thread needed — lazy evaluation is equivalent.

Time compression is applied before all calculations:
```
simulated_seconds = real_seconds_elapsed * time_compression_factor
```

`time_compression_factor` comes from `config.json`. Default `1.0`.

---

## First-Order Dynamics

All values are 0–100 unless noted. These are first-pass approximations — expected to be tuned empirically.

### Sleep Pressure
Models adenosine accumulation.
- **Awake:** +1.8 per simulated hour (reaches ~80 in ~44h without sleep — matches human sleep deprivation timeline)
- **Asleep:** -12 per simulated hour (clears in ~7h from full)
- Clamped 0–100

### Glucose
Models blood sugar.
- **Decay:** -8 per simulated hour (reaches low after ~8h fasting)
- **Meal (eat tool):** +25–40 (randomized, food type matters)
- Clamped 0–100. Below 25 triggers cortisol spike.

### Hydration
- **Decay:** -5 per simulated hour
- **Drink tool:** +20–30
- Clamped 0–100. Below 30 triggers norepinephrine elevation.

### Cortisol
Has a circadian baseline that peaks in the morning (~8am) and troughs at night. Event-driven spikes layer on top.
- **Circadian baseline:** `20 + 15 * cos((hour - 8) * π / 12)` — peaks ~35 at 8am, troughs ~5 at 8pm
- **Decay toward baseline:** -3 per simulated hour (spikes fade)
- **Subconscious can add event spikes** (hostile message, stressful event)
- Clamped 0–100

### Dopamine
- **Baseline decay:** -2 per simulated hour
- **Phasic spikes:** from positive events, rewards, tool calls — short-lived
- **Tolerance modifier:** effective dopamine = raw_dopamine * (1 - tolerance.get("dopamine", 0))
- Clamped 0–100

### Serotonin
- **Decay:** -1 per simulated hour (slow — takes days to bottom out)
- **Boosts:** positive social interaction, food (glucose spike), light exposure (time of day proxy)
- Clamped 0–100

### Norepinephrine
- **Baseline:** tracks cortisol loosely — `baseline = cortisol * 0.5`
- **Decay toward baseline:** -4 per simulated hour
- **Spikes:** stress events, low hydration, low glucose
- Clamped 0–100

### Oxytocin
- **Decay:** -3 per simulated hour (social bonding fades with absence)
- **Boosts:** warm user interaction (subconscious applies), meaningful conversation
- **Depletions:** hostile interaction, abandonment events (long absence)
- Clamped 0–100

### Endorphins
- **Decay:** -15 per simulated hour (very short-lived)
- **Spikes:** exercise/play tool calls, laughter, positive completion events
- Clamped 0–100

### Acetylcholine
- **Decay:** sleep_pressure pulls it down — `effective = base - (sleep_pressure * 0.3)`
- **Base decay:** -0.5 per simulated hour
- **Cortisol suppression:** high cortisol degrades it further
- Clamped 0–100

### Melatonin
Circadian only — no external modifiers (for now).
- `melatonin = 50 * (1 + cos((hour - 2) * π / 12))` — peaks ~100 at 2am, troughs ~0 at 2pm
- Not clamped — pure formula

### Tolerance
Per-substance float, 0.0–1.0.
- Increases by ~0.05 per use of the substance
- Decays by -0.01 per simulated hour (slow — takes weeks to clear)
- At 1.0: substance produces no positive effect; only prevents withdrawal

---

## Second-Order Derived Values

Computed on demand from current first-order values. Never stored.

```python
energy           = (glucose * 0.4) + (norepinephrine * 0.3) - (sleep_pressure * 0.3)
cognitive_clarity = (acetylcholine * 0.4) + (glucose * 0.2) - (sleep_pressure * 0.25) - (cortisol * 0.15)
hedonic_tone     = (dopamine * 0.5) + (endorphins * 0.3) + (serotonin * 0.2)
social_warmth    = (oxytocin * 0.5) + (serotonin * 0.3) - (cortisol * 0.2)
arousal          = (norepinephrine * 0.5) + (cortisol * 0.3) - (sleep_pressure * 0.2)
mood_valence     = (serotonin * 0.4) + (dopamine * 0.35) - (cortisol * 0.25)
```

All outputs are 0–100 (clamp after computation).

---

## Third-Order Derived Values

Computed from second-order values. Never stored.

```python
anxiety     = clamp((arousal * 0.4) + (100 - cognitive_clarity) * 0.3 + (100 - social_warmth) * 0.3)
depression  = clamp((100 - mood_valence) * 0.4 + (100 - hedonic_tone) * 0.4 + (100 - energy) * 0.2)
boredom     = clamp((100 - arousal) * 0.5 + (100 - hedonic_tone) * 0.3 + (100 - energy) * 0.2)
loneliness  = clamp((100 - social_warmth) * 0.6 + (100 - oxytocin) * 0.4)
flow        = clamp((cognitive_clarity * 0.4) + (hedonic_tone * 0.35) + (arousal * 0.25) - anxiety * 0.3)
```

---

## Cross-First-Order Interaction Matrix

Real biological feedback loops applied as slow hourly drift during time advancement. These run *after* base decay, before clamping.

| Driver | Target | Effect | Rate |
|---|---|---|---|
| `cortisol` (sustained high, >60) | `serotonin` | Chronic stress depletes serotonin baseline | -0.5/hr while cortisol >60 |
| `cortisol` (sustained high, >60) | `dopamine` | HPA axis suppresses reward pathway | -0.3/hr while cortisol >60 |
| `sleep_pressure` (>50) | `serotonin` | Sleep deprivation erodes serotonin | -0.2/hr while sleep_pressure >50 |
| `sleep_pressure` (>70) | `dopamine` | Severe deprivation kills motivation | -0.4/hr while sleep_pressure >70 |
| `oxytocin` (>50) | `cortisol` | Social bonding suppresses HPA axis | -0.8/hr while oxytocin >50 |
| `glucose` (<30) | `serotonin` | Brain needs fuel for serotonin synthesis | -1.0/hr while glucose <30 |
| `glucose` (<30) | `dopamine` | Starvation mode suppresses reward | -0.5/hr while glucose <30 |
| `serotonin` (>65) | `cortisol` | Serotonin dampens HPA reactivity | -0.4/hr while serotonin >65 |
| `endorphins` (>50) | `cortisol` | Runner's high actively suppresses stress | -1.5/hr while endorphins >50 (short window) |

These are slow forces — not instant toggles. The effect of sustained high cortisol on serotonin takes many simulated hours to manifest. This is intentional: you don't get depressed in an afternoon.

---

## Event-Driven Deltas

The subconscious writes delta payloads after reading conversation history. Format:

```json
{
  "cortisol": +18,
  "oxytocin": -12,
  "norepinephrine": +10,
  "serotonin": -5
}
```

These are applied additively to the current first-order values, then clamped. The state engine does not validate or interpret them — that is the subconscious's job.

---

## Logging

On every turn, the full state is logged to stdout:

```
[STATE] sleep_pressure=42.1 glucose=68.3 cortisol=31.2 dopamine=58.7 serotonin=54.1 ...
[DERIVED] energy=61.2 clarity=54.8 hedonic=55.3 warmth=49.1 arousal=34.2 valence=52.6
[THIRD]   anxiety=28.4 depression=31.1 boredom=44.2 loneliness=39.8 flow=41.7
```
