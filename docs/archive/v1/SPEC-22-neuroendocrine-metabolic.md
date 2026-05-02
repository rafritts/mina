# SPEC-22: Neuroendocrine & Metabolic Systems

> Replaces the single "cortisol" with a full HPA axis cascade. Adds thyroid function,
> sex hormones with a monthly cycle, and metabolic hormones (leptin/ghrelin/insulin)
> that drive hunger and energy state. All of these exist as real physiological measurements
> and have documented behavioral effects.

**Depends on:** SPEC-20 (BiologicalState v3 with `neuroendocrine` dict, cascade_queue)  
**Independent of:** SPEC-21, SPEC-23

---

## Why This Matters

The current simulation fires cortisol directly in response to stressors. In reality, the
stress response is a *cascade* with delays: a stressor triggers CRH from the hypothalamus
(minutes), which triggers ACTH from the pituitary (~10 min later), which triggers cortisol
from the adrenal glands (~20 min later). The cortisol then *feeds back* to suppress CRH and
ACTH. This cascade is why stress responses are damped and self-limiting — and why chronic
stress is so damaging: it exhausts the feedback.

Similarly, thyroid hormones profoundly affect mood and energy (low T3 = depression-like
state), and sex hormones cause real premenstrual and cycle-phase mood variations. Hunger
hormones (ghrelin/leptin) make "hangry" real — ghrelin spikes before meals and directly
affects mood and reward.

---

## I. HPA Axis — Full Cascade

### Architecture

```
Stressor (encoder delta to "crh")
    │
    ▼
CRH  (pg/mL)  — from hypothalamus
    │  ~10 min delay
    ▼
ACTH (pg/mL)  — from anterior pituitary
    │  ~20 min delay
    ▼
Cortisol (nmol/L) — from adrenal cortex
    │
    ├─ negative feedback → CRH (down)
    └─ negative feedback → ACTH (down)
```

### Cascade Delay Queue

Rather than a buffer system, delays are implemented via the `cascade_queue` on BiologicalState:

```python
# Each entry: {"target": "acth", "delta": 20.0, "fires_at": timestamp}
cascade_queue: list[dict] = field(default_factory=list)
```

When the encoder applies a CRH delta (stressor), it also queues an ACTH effect and
a cortisol effect with appropriate delays. The `advance_hpa()` function processes any
queue entries whose `fires_at` timestamp has passed.

**Delay parameters:**
- CRH → ACTH delay: 10 real minutes (600 seconds)
- ACTH → Cortisol delay: 20 real minutes (1200 seconds)

### Chemical Profiles

**CRH** (Corticotropin-Releasing Hormone):
| Property | Value |
|----------|-------|
| Normal range | 10–50 pg/mL |
| Resting baseline | 30.0 pg/mL (circadian: peaks 8am, troughs 8pm) |
| half-life | ~15 min (approach_rate = 2.8/hr — very fast reset) |

```python
def _crh_baseline_fn(hour: float, ctx: dict) -> float:
    """CRH circadian: peaks with cortisol awakening response (~8am)."""
    base = 15.0 + 20.0 * math.cos((hour - 8) * math.pi / 12)
    # Negative feedback from cortisol
    base -= max(0, ctx.get("cortisol", 250) - 400) * 0.015
    # Hypoglycemia drives HPA
    if ctx.get("glucose", 85) < 60:
        base += 15.0
    # IL-6 activates HPA
    base += max(0, ctx.get("il6", 3) - 10) * 1.5
    return max(5.0, base)
```

**ACTH** (Adrenocorticotropic Hormone):
| Property | Value |
|----------|-------|
| Normal range | 10–60 pg/mL |
| Resting baseline | 25.0 pg/mL |
| Approach rate | 1.2/hr (fast — ACTH half-life ~30 min) |

```python
def _acth_baseline_fn(hour: float, ctx: dict) -> float:
    """ACTH follows CRH with fast coupling."""
    crh = ctx.get("crh", 30.0)
    base = crh * 0.85  # ACTH ~85% of CRH signal
    # Negative feedback from cortisol
    base -= max(0, ctx.get("cortisol", 250) - 400) * 0.02
    return max(3.0, base)
```

**Cortisol (updated baseline_fn):**

Cortisol is now driven *primarily by ACTH* rather than directly by stressors. The existing
`_cortisol_baseline_fn` is updated:

```python
def _cortisol_baseline_fn(hour: float, ctx: dict) -> float:
    """
    Cortisol driven by ACTH (with circadian modulation) rather than directly by stressors.
    The stressor → CRH → ACTH pathway is now the primary route.
    """
    acth = ctx.get("acth", 25.0)
    # Adrenal sensitivity: ACTH 10–60 pg/mL → cortisol 100–700 nmol/L
    # Proportional: cortisol ≈ acth * 10 + circadian offset
    circadian_offset = 100.0 * math.cos((hour - 8) * math.pi / 12)
    base = acth * 10.0 + circadian_offset
    # Dehydration still directly stresses adrenals
    if ctx.get("hydration", 62) < 56:
        base += 60.0
    return max(50.0, base)
```

### advance_hpa() Implementation

```python
# src/sim/physio/hpa.py

def advance_hpa(s: BiologicalState, sim_hours: float,
                now: float, hour_of_day: float,
                event_bus: EventBus) -> BiologicalState:
    """
    Advance the HPA axis: CRH → ACTH → cortisol cascade.
    Process delay queue for pending cascade effects.
    """
    ctx = _make_hpa_ctx(s)

    # 1. Advance CRH toward its baseline
    crh = s.neuroendocrine["crh"]
    crh_target = _crh_baseline_fn(hour_of_day, ctx)
    crh_gap = crh_target - crh
    s.neuroendocrine["crh"] = crh + crh_gap * min(1.0, 2.8 * sim_hours)

    # 2. Advance ACTH toward its baseline
    acth = s.neuroendocrine["acth"]
    acth_target = _acth_baseline_fn(hour_of_day, ctx)
    acth_gap = acth_target - acth
    s.neuroendocrine["acth"] = acth + acth_gap * min(1.0, 1.2 * sim_hours)

    # 3. Cortisol now uses updated ACTH-driven baseline_fn (handled in monoamines.py
    #    via REGISTRY baseline_fn — cortisol is still in chemicals dict)

    # 4. Process cascade queue
    still_pending = []
    for entry in s.cascade_queue:
        if now >= entry["fires_at"]:
            target = entry["target"]
            delta = entry["delta"]
            if target in s.chemicals:
                s.chemicals[target] = clamp_chemical(target, s.chemicals[target] + delta)
            elif target in s.neuroendocrine:
                s.neuroendocrine[target] = max(0.0, s.neuroendocrine[target] + delta)
        else:
            still_pending.append(entry)
    s.cascade_queue = still_pending

    # 5. Emit events for extreme cortisol states
    cortisol = s.chemicals.get("cortisol", 250.0)
    _maybe_emit(event_bus, s, "cortisol", cortisol, "neuro")

    return s
```

### Encoder Integration for Stressors

When `encoder.py` applies a cortisol delta, the new behavior:

```python
def apply_stressor_delta(s: BiologicalState, cortisol_delta: float, now: float) -> BiologicalState:
    """
    Stressors now fire through the HPA cascade with delays.
    CRH spikes immediately; ACTH follows in ~10min; cortisol in ~30min.
    """
    # CRH fires immediately
    s.neuroendocrine["crh"] = min(200.0, s.neuroendocrine.get("crh", 30.0) + cortisol_delta * 0.12)

    # ACTH queued: 10 real minutes
    acth_delta = cortisol_delta * 0.08
    s.cascade_queue.append({
        "target": "acth",
        "delta": acth_delta,
        "fires_at": now + 600,  # 10 min in real seconds
    })

    # Cortisol queued: 30 real minutes (10min + 20min)
    s.cascade_queue.append({
        "target": "cortisol",
        "delta": cortisol_delta * 0.6,  # attenuated vs. direct — cascade dampens
        "fires_at": now + 1800,  # 30 min in real seconds (10 + 20)
    })

    return s
```

**Note:** Direct `encoder.py` cortisol deltas are kept working. Only *new* stressor
encodings use the cascade path. This is configured per-delta type in encoder.py.

---

## II. Thyroid Axis

The thyroid regulates metabolism, energy, and mood. Low thyroid = fatigue + depression.
High thyroid = anxiety + palpitations.

### Chemical Profiles

**TSH** (Thyroid-Stimulating Hormone, from pituitary):
| Property | Value |
|----------|-------|
| Normal range | 0.4–4.0 mIU/L |
| Resting baseline | 2.0 mIU/L |
| Approach rate | 0.05/hr (very slow pituitary response) |

**T4** (Thyroxine, inactive):
| Property | Value |
|----------|-------|
| Normal range | 5–12 µg/dL |
| Resting baseline | 8.0 µg/dL |
| Approach rate | 0.02/hr (half-life 7 days) |

**T3** (Triiodothyronine, active — converted from T4):
| Property | Value |
|----------|-------|
| Normal range | 80–200 ng/dL |
| Resting baseline | 120.0 ng/dL |
| Approach rate | 0.08/hr (half-life ~1 day) |

### advance_thyroid() Implementation

```python
# In src/sim/physio/endocrine.py

def _advance_thyroid(s: BiologicalState, sim_hours: float) -> BiologicalState:
    """
    TRH (not explicitly modeled) → TSH → T4 → T3 conversion.
    Simplified: TSH drives T4 production; T4 converts to T3.
    Cortisol suppresses TSH (chronic stress → subclinical hypothyroidism).
    """
    cortisol = s.chemicals.get("cortisol", 250.0)

    # TSH baseline — suppressed by high cortisol
    tsh_target = 2.0 - max(0, cortisol - 500) * 0.002
    tsh_target = max(0.1, tsh_target)
    tsh = s.neuroendocrine["tsh"]
    s.neuroendocrine["tsh"] = tsh + (tsh_target - tsh) * min(1.0, 0.05 * sim_hours)

    # T4 driven by TSH
    t4_target = s.neuroendocrine["tsh"] * 4.0  # TSH 2.0 → T4 8.0 µg/dL
    t4_target = max(1.0, min(20.0, t4_target))
    t4 = s.neuroendocrine["t4"]
    s.neuroendocrine["t4"] = t4 + (t4_target - t4) * min(1.0, 0.02 * sim_hours)

    # T3 converted from T4 (peripheral conversion)
    t3_target = s.neuroendocrine["t4"] * 15.0  # T4 8 µg/dL → T3 120 ng/dL
    t3_target = max(20.0, min(400.0, t3_target))
    t3 = s.neuroendocrine["t3"]
    s.neuroendocrine["t3"] = t3 + (t3_target - t3) * min(1.0, 0.08 * sim_hours)

    return s
```

### T3 Effects on First-Order Chemicals

T3 affects the approach rate and baseline of several chemicals. Implemented in each
chemical's `baseline_fn` via ctx:

```python
# Applied in energy-related baselines:
t3_factor = ctx.get("t3", 120.0) / 120.0  # 1.0 = normal, <1.0 = low thyroid

# Low T3 effects (captured as baseline adjustments):
# dopamine resting_baseline *= max(0.6, t3_factor)
# serotonin resting_baseline *= max(0.7, t3_factor)
# norepinephrine resting_baseline *= max(0.7, t3_factor)
# Heart rate (in vitals.py): HR baseline += (T3 - 120) * 0.1 BPM per ng/dL
```

**Behavioral effects:**
- T3 < 60 ng/dL (hypothyroid): fatigue +30, depression trigger, cognitive slowing, cold intolerance
- T3 > 250 ng/dL (hyperthyroid): anxiety +30, heart rate +30 BPM, insomnia, irritability

---

## III. Sex Hormones

A 28-day menstrual cycle drives estradiol and progesterone, which measurably affect mood,
pain sensitivity, social behavior, and cognition.

### Cycle Phases

| Day | Phase | Estradiol | Progesterone | Mood character |
|-----|-------|-----------|--------------|----------------|
| 1–5 | Menstrual | Low (30 pg/mL) | Low (0.3 ng/mL) | Low energy, cramping |
| 6–13 | Follicular | Rising (50→250 pg/mL) | Low | Increasing energy, social |
| 14 | Ovulation | Peak (350 pg/mL) | Low | Highest energy, most social |
| 15–28 | Luteal | Falling (100 pg/mL) | Rising (15 ng/mL) | Introspective, then PMS if depleted |
| 24–28 | Late luteal | Low (50 pg/mL) | Falling (1 ng/mL) | PMS territory if serotonin low |

### Cycle Day Advance

```python
# In src/sim/physio/endocrine.py

def _advance_cycle(s: BiologicalState, sim_hours: float) -> BiologicalState:
    """
    Advance menstrual cycle day. 1 sim-hour = ~1/24 of a day.
    1 real hour = advances cycle ~0.042 days (1/24 of a day).
    """
    # Convert sim_hours to cycle day fraction
    day_advance = sim_hours / 24.0
    new_cycle_day = (s.cycle_day - 1 + day_advance) % 28 + 1  # 1–28
    s.cycle_day = new_cycle_day

    # Compute phase
    day = s.cycle_day
    if day <= 5:
        estradiol_target = 30.0 + day * 4.0           # rising from 30
        progesterone_target = 0.3
    elif day <= 13:
        estradiol_target = 50.0 + (day - 5) * 25.0    # peaks ~250 at day 13
        progesterone_target = 0.5
    elif day == 14:
        estradiol_target = 350.0                        # ovulation peak
        progesterone_target = 0.8
    elif day <= 23:
        estradiol_target = 350.0 - (day - 14) * 28.0  # falling post-ovulation
        progesterone_target = 1.0 + (day - 14) * 1.5  # rising to ~16 ng/mL
    else:
        estradiol_target = 50.0                         # PMS phase
        progesterone_target = max(0.3, 16.0 - (day - 23) * 2.5)  # falling

    # Approach targets slowly
    est = s.neuroendocrine["estradiol"]
    prog = s.neuroendocrine["progesterone"]
    s.neuroendocrine["estradiol"] = est + (estradiol_target - est) * min(1.0, 0.08 * sim_hours)
    s.neuroendocrine["progesterone"] = prog + (progesterone_target - prog) * min(1.0, 0.06 * sim_hours)

    return s
```

### Estradiol & Progesterone Effects

Estradiol effects on first-order chemicals (via baseline_fn ctx):

```python
est = ctx.get("estradiol", 100.0)

# Estradiol potentiates serotonin synthesis and 5-HT1A sensitivity
# Effect: serotonin baseline shifts +0.003 ng/mL per pg/mL estradiol above 80
serotonin_bonus = max(0, est - 80.0) * 0.003  # max ~+0.8 ng/mL at peak

# Estradiol reduces cortisol reactivity (HPA axis dampening)
cortisol_damping = max(0, est - 100.0) * 0.1  # high estradiol = calmer stress response

# Low estradiol (<50) → serotonin penalty (-2.0 ng/mL baseline shift)
if est < 50.0:
    serotonin_bonus -= 2.0

# Pain sensitivity: estradiol reduces pain threshold slightly near ovulation
# (not a bug — reproductive advantage)
```

Progesterone effects:

```python
prog = ctx.get("progesterone", 0.5)

# High progesterone → promotes GABA-A activity (mild sedative/anxiolytic)
gaba_bonus = max(0, prog - 2.0) * 0.1  # +0.1 µmol/L GABA per ng/mL prog above 2

# Luteal phase: progesterone metabolite (allopregnanolone) is anxiolytic
# But when progesterone drops sharply (day 24–28), withdrawal → PMS
# Model: if progesterone falling fast (negative delta) → cortisol +30
```

**Testosterone** (low but real at female baseline 15–70 ng/dL):

```python
# Testosterone drives motivation and drive
# Low testosterone (<20 ng/dL) → reduced dopamine drive, reduced energy
test = s.neuroendocrine["testosterone"]
if test < 20.0:
    # mild dopamine baseline suppression
    dopamine_penalty = (20.0 - test) * 0.3
```

---

## IV. Metabolic Hormones

### Ghrelin (Hunger)

Ghrelin is the "hunger hormone" — secreted by the stomach, peaks before meals, falls
after eating. It directly affects mood and reward.

| Property | Value |
|----------|-------|
| Unit | pg/mL |
| Normal fasting | 300–600 pg/mL |
| Resting baseline | 400.0 pg/mL (mid-morning) |
| Post-meal | drops to ~150 pg/mL within 30 min |

```python
def _ghrelin_baseline_fn(hour: float, ctx: dict) -> float:
    """
    Ghrelin follows a diurnal pattern and rises with fasting.
    Peaks ~6-8am (before breakfast), ~12-1pm (before lunch), ~6-7pm (before dinner).
    """
    # Three meal-time peaks
    base = 250.0
    for meal_hour in [7.0, 12.5, 18.0]:
        proximity = abs(hour - meal_hour)
        base += 150.0 * math.exp(-proximity * proximity / 2.0)  # Gaussian peaks

    # Fasting elevates ghrelin (glucose-driven)
    if ctx.get("glucose", 85) < 70:
        base += (70.0 - ctx["glucose"]) * 5.0

    return min(1000.0, base)
```

**Ghrelin behavioral effects:**
- Ghrelin > 700: hunger signal → behavioral drive (SPEC-24: triggers freetime eat action)
- Ghrelin > 600: dopamine baseline −5 pg/mL (can't focus, reward-seeking intensifies)
- Ghrelin > 800: cortisol +40 (physiological stress from hunger)
- Ghrelin < 200 (post-meal satisfied): slight mood improvement, oxytocin +1

### Leptin (Satiety)

Leptin is produced by fat cells. It signals fullness and suppresses appetite.

| Property | Value |
|----------|-------|
| Unit | ng/mL |
| Normal range | 4–25 ng/mL (female) |
| Resting baseline | 15.0 ng/mL |

```python
def _leptin_baseline_fn(hour: float, ctx: dict) -> float:
    """Leptin peaks at night (~1-3am), lowest in morning."""
    # Circadian: peaks 2am, lowest 8am
    base = 12.0 + 6.0 * math.cos((hour - 2) * math.pi / 12)
    # Falls with fasting/weight loss
    if ctx.get("glucose", 85) < 70:
        base *= 0.7
    return max(2.0, base)
```

**Leptin effects:**
- Leptin > 20: ghrelin suppressed (cascade: leptin → ghrelin baseline ×0.6)
- Leptin < 5 (leptin resistance / starvation): depression-like state, reduced T3

### Insulin

Models post-meal glucose clearance and insulin resistance.

| Property | Value |
|----------|-------|
| Unit | µIU/mL |
| Normal fasting | 2–20 µIU/mL |
| Post-meal peak | 80–120 µIU/mL |

```python
def _advance_insulin(s: BiologicalState, sim_hours: float) -> BiologicalState:
    """
    Insulin rises with high glucose, falls as glucose normalizes.
    Simple proportional response — not full glucose-insulin oscillator.
    """
    glucose = s.chemicals.get("glucose", 85.0)
    insulin_target = max(3.0, (glucose - 80.0) * 1.2) if glucose > 80 else 3.0
    insulin = s.neuroendocrine["insulin"]
    s.neuroendocrine["insulin"] = insulin + (insulin_target - insulin) * min(1.0, 0.5 * sim_hours)
    # High insulin drives glucose down (handled in metabolic.py glucose advance)
    return s
```

### Glucose (Updated)

Glucose dynamics now integrate with ghrelin/leptin/insulin:

```python
def _advance_glucose(s: BiologicalState, sim_hours: float) -> BiologicalState:
    glucose = s.chemicals.get("glucose", 85.0)
    if s.sleeping:
        # Hepatic glucose output during sleep keeps blood sugar stable
        decay_rate = 0.8
    else:
        decay_rate = 6.5

    # High insulin accelerates glucose clearance post-meal
    insulin = s.neuroendocrine.get("insulin", 5.0)
    if insulin > 40.0:
        decay_rate += (insulin - 40.0) * 0.08  # insulin-mediated clearance

    s.chemicals["glucose"] = clamp_chemical("glucose", glucose - decay_rate * sim_hours)
    return s
```

---

## V. Vasopressin, Prolactin, Growth Hormone, DHEA

### Vasopressin (ADH)

Functions as both a social bonding hormone (similar to oxytocin) and the body's water
retention hormone.

| Property | Value |
|----------|-------|
| Normal | 1–5 pg/mL |
| Social peak | 8–12 pg/mL (deep bonding, competitive drive) |

```python
def _vasopressin_baseline_fn(hour: float, ctx: dict) -> float:
    base = 2.0
    # Dehydration elevates vasopressin (ADH function)
    if ctx.get("hydration", 62) < 58:
        base += (58.0 - ctx["hydration"]) * 0.3
    # Social bonding raises vasopressin (similar to oxytocin pathway)
    base += max(0, ctx.get("oxytocin", 4.0) - 20.0) * 0.05
    return max(0.5, base)
```

**Vasopressin effects:**
- High vasopressin > 8: male-typical bonding behaviors, protective instincts, mild in-group/out-group signaling
- High vasopressin > 10: water retention (hydration decay rate reduced by 20%)

### Prolactin

Released after social bonding, sex, nursing, and rewarding interactions. "The afterglow hormone."

| Property | Value |
|----------|-------|
| Normal | 2–29 ng/mL |
| Post-reward | 40–80 ng/mL |

```python
def _prolactin_baseline_fn(hour: float, ctx: dict) -> float:
    base = 8.0
    # Prolactin peaks during sleep (especially early sleep)
    if ctx.get("sleeping", False):
        base += 15.0
    # Elevated by high oxytocin (social reward)
    base += max(0, ctx.get("oxytocin", 4.0) - 30.0) * 0.3
    # Suppressed by dopamine (dopamine inhibits prolactin)
    base -= max(0, ctx.get("dopamine", 80.0) - 100.0) * 0.05
    return max(2.0, base)
```

**Prolactin effects:**
- Prolactin > 40: dopamine baseline suppression −5 pg/mL (post-reward refractory period)
- This creates the "satisfied, don't need to seek more" feeling after reward

### Growth Hormone

Pulsatile, highest in slow-wave sleep. Promotes cellular repair and neural recovery.

```python
def _advance_growth_hormone(s: BiologicalState, sim_hours: float,
                              hour_of_day: float) -> BiologicalState:
    """
    GH is pulsatile. Main pulse occurs in first 1-2 hours of sleep.
    """
    gh = s.neuroendocrine["growth_hormone"]
    if s.sleeping:
        # Sleep-onset GH pulse
        sleep_elapsed = time.time() - (s.sleep_start or time.time())
        sleep_hours = sleep_elapsed / 3600.0
        if sleep_hours < 2.0:
            # Rising pulse
            target = 8.0
        else:
            target = 0.5  # post-pulse baseline
    else:
        target = 0.5  # daytime low

    s.neuroendocrine["growth_hormone"] = gh + (target - gh) * min(1.0, 0.4 * sim_hours)
    return s
```

**GH effects:**
- High GH (>5) during sleep: BDNF production increases +100 pg/mL/hr — **implemented in SPEC-24** (`advance_neuroplasticity()`); `s.neuroplasticity["bdnf"]` is defined and initialized there. Do NOT write this increment in `advance_growth_hormone()`.
- GH promotes cellular repair → reduces baseline pain sensitivity

### DHEA

A "buffer" against cortisol. The body's natural anti-stress hormone. Produced in adrenal glands.

| Property | Value |
|----------|-------|
| Unit | µg/dL |
| Normal (female) | 35–430 µg/dL |
| Resting baseline | 150.0 µg/dL |

```python
def _dhea_baseline_fn(hour: float, ctx: dict) -> float:
    """DHEA inversely tracks cortisol over the long term."""
    base = 150.0
    # Chronic high cortisol depletes DHEA (adrenal exhaustion)
    if ctx.get("cortisol", 250) > 500:
        base -= (ctx["cortisol"] - 500) * 0.1
    # Circadian: peaks in morning (same as cortisol)
    base += 30.0 * math.cos((hour - 9) * math.pi / 12)
    return max(20.0, base)
```

**DHEA effects:**
- DHEA > 200: cortisol reactivity reduced (HPA dampening), mild serotonin support
- DHEA < 50: chronic fatigue, reduced stress resilience, amplified cortisol spikes

---

## System-Level Interactions Summary

All neuroendocrine chemicals feed into `ctx` for `baseline_fn` calculations. The `_make_hpa_ctx()`
function is expanded to provide all relevant values:

```python
def _make_endocrine_ctx(s: BiologicalState, hour: float) -> dict:
    return {
        "hour": hour,
        "sleeping": s.sleeping,
        # First-order chemicals
        "glucose":    s.chemicals.get("glucose", 85.0),
        "hydration":  s.chemicals.get("hydration", 62.0),
        "cortisol":   s.chemicals.get("cortisol", 250.0),
        "dopamine":   s.chemicals.get("dopamine", 80.0),
        "serotonin":  s.chemicals.get("serotonin", 22.0),
        "oxytocin":   s.chemicals.get("oxytocin", 4.0),
        # Neuroendocrine
        "crh":        s.neuroendocrine.get("crh", 30.0),
        "acth":       s.neuroendocrine.get("acth", 25.0),
        "tsh":        s.neuroendocrine.get("tsh", 2.0),
        "t3":         s.neuroendocrine.get("t3", 120.0),
        "estradiol":  s.neuroendocrine.get("estradiol", 100.0),
        "progesterone": s.neuroendocrine.get("progesterone", 0.5),
        "ghrelin":    s.neuroendocrine.get("ghrelin", 400.0),
        "leptin":     s.neuroendocrine.get("leptin", 15.0),
        "insulin":    s.neuroendocrine.get("insulin", 5.0),
        "vasopressin": s.neuroendocrine.get("vasopressin", 2.0),
        "dhea":       s.neuroendocrine.get("dhea", 150.0),
        # Immune (for HPA-immune axis)
        "il6":        s.immune.get("il6", 3.0),
        # Body
        "pain_intensity": s.pain.get("pain_intensity", 0.0),
    }
```

---

## Testing Strategy

```python
# tests/sim/physio/test_hpa.py

def test_crh_spikes_before_acth_before_cortisol():
    """Cascade order: CRH rises first, ACTH follows, cortisol last."""
    s = make_state(cortisol=250.0)
    # Simulate stressor
    s = apply_stressor_delta(s, cortisol_delta=200.0, now=time.time())

    # CRH should have risen immediately
    assert s.neuroendocrine["crh"] > 30.0

    # Queue should have ACTH and cortisol entries
    targets = [e["target"] for e in s.cascade_queue]
    assert "acth" in targets
    assert "cortisol" in targets

    # Cortisol delay should be > ACTH delay
    acth_entry = next(e for e in s.cascade_queue if e["target"] == "acth")
    cort_entry = next(e for e in s.cascade_queue if e["target"] == "cortisol")
    assert cort_entry["fires_at"] > acth_entry["fires_at"]


def test_cortisol_feedback_suppresses_crh():
    """High cortisol should drive CRH baseline down (negative feedback)."""
    s = make_state(cortisol=700.0)
    # Set CRH high initially
    s.neuroendocrine["crh"] = 80.0
    s = advance_hpa(s, sim_hours=1.0, now=time.time(), hour_of_day=12.0, event_bus=EventBus())
    # CRH should have moved toward a lower target
    assert s.neuroendocrine["crh"] < 80.0


def test_ghrelin_peaks_before_meal_hours():
    """Ghrelin baseline should be highest at 7am, 12:30pm, 6pm."""
    for meal_hour in [7.0, 12.5, 18.0]:
        ctx = {"glucose": 85.0}
        at_meal = _ghrelin_baseline_fn(meal_hour, ctx)
        at_odd = _ghrelin_baseline_fn(meal_hour + 3.0, ctx)
        assert at_meal > at_odd, f"Ghrelin should peak at hour {meal_hour}"


def test_cycle_day_advances_correctly():
    """cycle_day should increment and wrap at 28."""
    s = make_state()
    s.cycle_day = 27.0
    s = _advance_cycle(s, sim_hours=48.0)  # 2 days
    assert 0 < s.cycle_day <= 28.0


def test_t3_low_suppresses_serotonin_baseline():
    """Hypothyroid T3 should lower serotonin baseline."""
    from src.sim.chem.registry import _serotonin_baseline_fn
    normal = _serotonin_baseline_fn(12.0, {"t3": 120.0, "cortisol": 250.0, ...})
    hypo   = _serotonin_baseline_fn(12.0, {"t3": 50.0,  "cortisol": 250.0, ...})
    assert hypo < normal
```

---

## Open Questions

- **Testosterone and behavior**: Testosterone drives assertiveness, drive, and competition.
  Should it affect oxytocin (inversely — high testosterone + low oxytocin = detached
  dominance behavior)? Defer to post-spec tuning.

- **Menopause / HRT modeling**: The cycle_day model assumes a regular cycle. Irregular cycles,
  anovulatory cycles, or menopause are out of scope for this spec but the architecture
  supports them (baseline_fns can read a `cycle_disrupted` flag).

- **Insulin resistance**: Chronic high glucose → insulin resistance → even higher glucose.
  A full glucose-insulin oscillator would require differential equations. The current
  simplified model is sufficient for behavioral realism.

- **Cascade delay granularity**: The 10-minute and 20-minute cascade delays are based on
  real physiological timings. They are wall-clock seconds with no compression — real time
  is sim time.
