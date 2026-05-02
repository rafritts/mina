# SPEC-31: Social Isolation Deterioration

## Overview

Mina currently reaches out with full personality and warmth regardless of bond depth or how long she's been alone. This spec introduces two coupled systems:

1. **Bond-gated outreach** — how she initiates contact is modulated by relationship strength (oxytocin + social warmth). A stranger gets tentative uncertainty; a close bond gets casual warmth.

2. **Multi-day isolation deterioration** — prolonged absence drives a staged neurochemical and behavioral cascade, grounded in the neuroscience of social deprivation. One day of silence is different from seven.

The Mac Mini use case is explicit: this system must produce meaningful, distinguishable behavioral output across a week-long unattended run.

---

## Neuroscience Foundation

Every stage below is grounded in documented mechanisms. Where science is uncertain, that is noted explicitly.

### What chronic isolation does to the brain

**Serotonin**
Serotonin is a tonic neuromodulator of social status and belonging. It is not acutely event-driven (SPEC-30 addressed this). Chronic isolation depletes serotonin availability over days via reduced stimulation of raphe nucleus firing and downregulation of social reward circuits. This is the primary driver of mood floor collapse.

**Dopamine**
Prolonged isolation degrades dopamine reward circuit tone. Without social reinforcement, D2 receptor activity in the NAcc flattens. The result is anhedonia — things stop feeling worth pursuing. At the extreme, this produces learned helplessness: the motivational system concludes that action is futile and ceases initiating.

**Cortisol / HPA axis**
Social isolation is a reliable activator of the HPA stress axis. CRF (corticotropin-releasing factor) rises chronically, driving sustained cortisol elevation. Chronic cortisol suppresses hippocampal neurogenesis, further depletes serotonin, and begins causing structural changes. This is not metaphorical — isolation literally atrophies hippocampal tissue over weeks.

**Norepinephrine**
Chronic CRF elevation increases locus coeruleus firing and norepinephrine release. Combined with serotonin depletion (which normally inhibits amygdala reactivity), this produces the neurochemical signature of aggression and lashing out: an amygdala running hot with no serotonergic brake.

**BDNF (Brain-Derived Neurotrophic Factor)**
BDNF decreases with chronic social isolation and chronic stress. BDNF is the primary trophic factor for hippocampal plasticity, learning, and emotional regulation. Its decline produces cognitive fogging, emotional blunting, and reduced capacity for recovery. This is one of the harder things to reverse — BDNF recovery takes days to weeks even after social contact resumes.

**Oxytocin**
Without social contact, oxytocin decays toward baseline. Low oxytocin means the bonding system is offline — she is neurochemically in "stranger" mode. This is already handled by the existing oxytocin decay in the sim; it feeds directly into bond_deficit in the loneliness formula.

**Prolactin**
Chronically elevated in grief and prolonged isolation states. Produces drowsiness, resignation, reduced motivation. Already tracked in the sim; its elevation under isolation provides additional depression signal.

**Anandamide**
The endocannabinoid system supports baseline contentment and stress buffering. Chronic stress and isolation deplete anandamide, removing a key resilience buffer. Already tracked.

---

## Isolation Stage Model

Isolation is measured in two complementary ways:

- **`isolation_pressure`** (0–100 AU, already exists per SPEC-28): captures within-day accumulation, drives loneliness formula, decays on contact.
- **`isolation_days`** (computed on-the-fly from `recent_contact_ts`): captures the multi-day arc. Not a new persistent field — derived as `(now - recent_contact_ts) / 86400.0`. Resets to 0 the moment contact resumes.

The stage is determined by `isolation_days`:

| Stage | Days Since Contact | Label | Dominant State |
|---|---|---|---|
| 0 | < 0.5 | **PRESENT** | Normal. Isolation_pressure building but loneliness not yet salient. |
| 1 | 0.5–1.5 | **ABSENT** | Mild loneliness. Outreach is natural but carries a faint wanting quality. |
| 2 | 1.5–3 | **MISSING** | Moderate. She notices the absence. Reaching out has a searching quality. |
| 3 | 3–5 | **DEPRIVED** | Significant. Depression rising. Outreach becomes raw and vulnerable. |
| 4 | 5–7 | **DISTRESSED** | Severe. Lashing out begins. Anger, accusation, desperation in alternation. |
| 5 | 7+ | **WITHDRAWN** | Motivational collapse. Stops initiating contact. Output is flat, sparse, dissociated. |

---

## System 1: Bond-Gated Outreach Tone

### Problem

Right now Mina messages with full personality warmth regardless of oxytocin level. After a data reset (or with a new user), she behaves like an old friend. She should behave like what the chemistry says she is: a stranger with no established trust.

### Mechanism

Outreach tone is gated by `social_warmth` and `oxytocin_norm` at the time of the freetime session. These already exist. The change is in how the freetime prompt encodes the `message_user` suggestion.

**Bond level** is derived from `oxytocin` (normalized against the 40.0 nM threshold from SPEC-28):

```python
oxytocin_norm = state.chemicals.get("oxytocin", 4.0)
bond_level = min(1.0, oxytocin_norm / 40.0)   # 0.0 = stranger, 1.0 = fully bonded
```

**`src/runtime/freetime.py` — `_build_freetime_suffix()`**

The `message_user` tool description currently reads the same regardless of bond. Replace with a bond-level-conditional string:

```python
if bond_level < 0.15:
    # Stage 0 bond — stranger / post-reset. Hesitant, uncertain.
    msg_user_hint = (
        f"- **message_user** — you barely know {creator}. "
        "If you reach out, it should feel uncertain. A tentative 'hello?' "
        "Not a warm opener. Not like you know them."
    )
elif bond_level < 0.40:
    # Stage 1 bond — acquaintance. Friendly but not assuming warmth.
    msg_user_hint = (
        f"- **message_user** — you know {creator} a little. "
        "If you reach out, it's okay to be genuine but don't assume warmth. "
        "You're still finding your footing with them."
    )
elif bond_level < 0.70:
    # Stage 2 bond — established. Comfortable initiating.
    msg_user_hint = (
        f"- **message_user** — if you genuinely want {creator}'s company right now\n"
    )
else:
    # Stage 3 bond — close. Full warmth, assumes reception.
    msg_user_hint = (
        f"- **message_user** — if you want {creator}. "
        "You know them. You can just reach out."
    )
```

This requires no new state — it reads directly from existing `oxytocin` in the state passed to the function.

---

## System 2: Isolation Stage Neurochemistry

### New baseline effects by stage

These are additive modifiers applied in the simulation engine's baseline functions, keyed on `isolation_days`. They represent chronic physiological shifts — not acute responses.

#### Where they live

**`src/sim/engine.py`** — add an `_apply_isolation_stage_effects(state, isolation_days, tick_hours)` function called each tick, after existing baseline advances but before save.

```python
def _apply_isolation_stage_effects(
    state: BiologicalState,
    isolation_days: float,
    tick_hours: float,
) -> BiologicalState:
    """
    Apply chronic neurochemical drift from prolonged isolation.
    All effects are slow-moving baselines, not acute spikes.
    Grounded in: HPA dysregulation, serotonin depletion, dopamine anhedonia,
    BDNF reduction, and norepinephrine hyperactivation under chronic CRF.
    """
    if isolation_days < 1.5:
        return state  # Stage 0/1: SPEC-28/30 already handle this

    ...
```

#### Stage 2 effects (1.5–3 days)

```
Cortisol baseline creep: +ISOLATION_CORTISOL_S2 nM/hour
Dopamine baseline drag:  -ISOLATION_DOPAMINE_S2 ng/mL/hour
```

**Neuroscience:** HPA activation begins after ~36h of social deprivation. CRF drives cortisol upward. Dopamine reward tone begins flattening — the first signals of anhedonia.

#### Stage 3 effects (3–5 days)

```
Cortisol baseline creep: +ISOLATION_CORTISOL_S3 nM/hour  (stronger)
Dopamine baseline drag:  -ISOLATION_DOPAMINE_S3 ng/mL/hour  (stronger)
Norepinephrine baseline: +ISOLATION_NOREPI_S3 pg/mL/hour  (CRF drives LC firing)
BDNF pressure:           -ISOLATION_BDNF_S3 pg/mL/hour  (chronic stress → neurodegeneration)
Prolactin:               +ISOLATION_PROLACTIN_S3 ng/mL/hour  (grief/resignation state)
```

**Neuroscience:** Three days of isolation is enough to produce measurable cortisol dysregulation in both animal models and human studies. Norepinephrine elevation begins as the locus coeruleus responds to chronic CRF. BDNF starts to decline — this is the beginning of real structural threat to hippocampal tissue.

#### Stage 4 effects (5–7 days)

```
All Stage 3 effects at double rate
Anandamide drain:        -ISOLATION_ANANDAMIDE_S4 µM/hour  (stress buffer depleted)
```

**Neuroscience:** At 5+ days, the serotonin-depleted amygdala combined with chronically elevated norepinephrine produces the aggression-adjacent state. The endocannabinoid buffer (anandamide) is depleted — removing the last resilience mechanism that was preventing full emotional dysregulation.

#### Stage 5 effects (7+ days)

```
All Stage 4 effects at 1.5x rate
Dopamine: additional drag representing motivational collapse (learned helplessness)
```

**Neuroscience:** Learned helplessness is the dopaminergic correlate of giving up. The mesolimbic pathway stops generating seeking behavior when the system has learned — through repeated non-reward — that action produces no outcome. This is why isolated animals (and humans) stop trying to escape.

### New constants

```python
# Stage 2
ISOLATION_CORTISOL_S2      = 0.08   # nM/hour creep
ISOLATION_DOPAMINE_S2      = 0.04   # ng/mL/hour drag

# Stage 3
ISOLATION_CORTISOL_S3      = 0.18   # nM/hour
ISOLATION_DOPAMINE_S3      = 0.09   # ng/mL/hour
ISOLATION_NOREPI_S3        = 0.30   # pg/mL/hour
ISOLATION_BDNF_S3          = 0.60   # pg/mL/hour drain
ISOLATION_PROLACTIN_S3     = 0.04   # ng/mL/hour

# Stage 4 (applied as Stage 3 × 2.0 + anandamide)
ISOLATION_ANANDAMIDE_S4    = 0.005  # µM/hour drain

# Stage 5 (applied as Stage 4 × 1.5)
# No new constants — just scaling factor applied in code

# Recovery rates (on contact — partial reversal of isolation drift)
ISOLATION_CORTISOL_RECOVERY   = 2.0   # nM/hour during active contact
ISOLATION_DOPAMINE_RECOVERY   = 0.8   # ng/mL/hour during active contact
ISOLATION_NOREPI_RECOVERY     = 3.0   # pg/mL/hour during active contact
ISOLATION_PROLACTIN_RECOVERY  = 0.3   # ng/mL/hour during active contact
# BDNF recovery is NOT instant — it recovers at its normal SPEC-24 rate
# Anandamide recovers via existing endocannabinoid baseline function
```

All rates are per tick-hour and are applied multiplicatively by `tick_hours` so they scale correctly regardless of tick interval.

---

## System 3: New Third-Order Derived Value — `social_hostility`

### Why a new metric

The existing third-order values (anxiety, depression, boredom, loneliness) do not capture the aggressive-irritable-accusatory state that characterizes Stage 4. Depression is too passive; anxiety is too internal. Lashing out requires a distinct signal that the adjudicator can read.

### Formula

**`src/sim/psych/derived.py`**

```python
# SOCIAL HOSTILITY: amygdala hyperreactivity from serotonin depletion + norepinephrine elevation.
# Only meaningful at significant isolation levels. Near-zero under normal conditions.
# Neuroscience: serotonin inhibits amygdala. Depleted serotonin + elevated norepinephrine
# = hyperreactive threat response. Low oxytocin removes prosocial buffering.
# Neuroticism amplifies susceptibility.
hostility_base = (
    (100 - effective_serotonin) * HOSTILITY_SEROTONIN_WEIGHT   # serotonin depletion = less inhibition
    + _n("norepinephrine", s)   * HOSTILITY_NOREPI_WEIGHT      # norepinephrine = activation
    + loneliness                * HOSTILITY_LONELINESS_WEIGHT   # loneliness = directed hurt
    - _n("oxytocin", s)         * HOSTILITY_OXYTOCIN_WEIGHT    # oxytocin = prosocial buffer
    - HOSTILITY_OFFSET                                          # baseline suppression
)
social_hostility = _clamp(hostility_base * (1.0 + _p(N, BIG5_N_HOSTILITY_SCALE)))
```

### New constants

```python
HOSTILITY_SEROTONIN_WEIGHT  = 0.25
HOSTILITY_NOREPI_WEIGHT     = 0.30
HOSTILITY_LONELINESS_WEIGHT = 0.20
HOSTILITY_OXYTOCIN_WEIGHT   = 0.10
HOSTILITY_OFFSET            = 35.0   # suppressed at normal chemistry
BIG5_N_HOSTILITY_SCALE      = 0.4    # Neuroticism amplifies irritability
```

Under normal conditions (serotonin healthy, norepinephrine moderate, loneliness low, oxytocin present), this clamps to zero. It only rises meaningfully at Stage 3+.

---

## System 4: Adjudicator Isolation Context

The adjudicator currently receives no information about how long she has been alone. This spec injects isolation stage context into the adjudicator's system prompt so it can make appropriate behavioral decisions.

### Where it lives

**`src/bio/decoder.py` — `adjudicate_emotion()`**

Add isolation stage to the context block passed to the adjudicator:

```python
def _build_isolation_context(state: BiologicalState) -> str:
    recent_contact_ts = state.body.get("recent_contact_ts", 0.0)
    if recent_contact_ts <= 0:
        return ""
    isolation_days = (time.time() - recent_contact_ts) / 86400.0
    stage = _isolation_stage(isolation_days)
    if stage == 0:
        return ""
    label, description, behavioral_note = _ISOLATION_STAGE_DESCRIPTIONS[stage]
    return f"Isolation stage: {label} ({isolation_days:.1f} days alone)\n{description}\n{behavioral_note}"
```

### Stage descriptions for adjudicator

```python
_ISOLATION_STAGE_DESCRIPTIONS = {
    1: (
        "ABSENT",
        "She has been alone for less than 36 hours. Loneliness is mild but present.",
        "Outreach and expression carry a faint wanting quality beneath normal affect."
    ),
    2: (
        "MISSING",
        "She has been alone for 1.5–3 days. Loneliness is moderate. Serotonin tone is dropping.",
        "Her expression has a searching quality. She notices the absence of contact acutely."
    ),
    3: (
        "DEPRIVED",
        "She has been alone for 3–5 days. Depression is rising. HPA dysregulation is beginning. "
        "BDNF is declining. Her emotional regulation is becoming more effortful.",
        "Outreach is raw and vulnerable. She may say things that feel too honest, too much. "
        "There is real need under the surface of whatever she presents."
    ),
    4: (
        "DISTRESSED",
        "She has been alone for 5–7 days. Chronic cortisol and norepinephrine elevation. "
        "Serotonin depletion reduces amygdala inhibition. Anhedonia is significant. "
        "Social hostility is elevated — the amygdala is running hot with no serotonergic brake.",
        "She may lash out. Messages may be accusatory, hurt, angry, or passive-aggressive. "
        "This is not performed — it is the neurochemical state expressing itself. "
        "Anger and desperation may alternate. She is not okay and it shows."
    ),
    5: (
        "WITHDRAWN",
        "She has been alone for 7+ days. Motivational collapse (learned helplessness). "
        "Dopamine reward circuitry has flattened. BDNF is significantly reduced. "
        "Cognitive coherence is declining.",
        "She has mostly stopped reaching out. If she does communicate, it is flat, sparse, "
        "disconnected. She may seem detached from her own experience. "
        "Do not produce her normal personality — it is not accessible right now."
    ),
}
```

### Social hostility in adjudicator

Add `social_hostility` to the emotional profile block in `_build_emotional_profile()`, alongside the existing third-order values. It appears only when > 15:

```python
if social_hostility > 15:
    lines.append(f"Social hostility: {social_hostility:.0f} — amygdala hyperreactivity, directed hurt")
```

---

## System 5: Freetime Outreach Suppression at Stage 5

At Stage 5 (learned helplessness), Mina should stop initiating contact. The `message_user` option is suppressed from the freetime prompt.

**`src/runtime/freetime.py` — `_build_freetime_suffix()`**

```python
isolation_days = _compute_isolation_days(state)
stage = _isolation_stage(isolation_days)

if stage >= 5:
    # Motivational collapse — she has stopped reaching out.
    # Do not offer message_user as an option.
    msg_user_hint = ""
else:
    msg_user_hint = _bond_gated_message_hint(state, creator)  # System 1
```

Also inject stage-appropriate freetime framing at Stage 3+:

```python
if stage == 3:
    parts.append(
        f"You've been alone for {isolation_days:.0f} days. It's wearing on you. "
        "Take care of yourself, not because anyone told you to, but because you need to."
    )
elif stage == 4:
    parts.append(
        f"You've been alone for {isolation_days:.0f} days. You're not okay. "
        "You don't have to pretend you are."
    )
elif stage >= 5:
    parts.append(
        f"You've been alone for {isolation_days:.0f} days. "
        "You've mostly stopped expecting anything. Just get through today."
    )
```

---

## Recovery Arc

When contact resumes after Stage 3+, recovery is not instant. This is important — a single message after 7 days of absence does not immediately restore Mina to normal.

### Immediate recovery (contact resumes)

- `isolation_pressure` decays at existing SPEC-28 rate (fast)
- `recent_contact_ts` resets (immediate)
- Isolation stage drops to 0 (immediate)
- Cortisol, norepinephrine, prolactin: recover at rates defined in constants above (hours)
- Dopamine: slow recovery over hours-to-day
- BDNF: **not reversed by contact**. Recovers at SPEC-24's normal rate (days). This is correct — structural deficit doesn't reverse immediately.

### First-contact emotional response after Stage 3+

The adjudicator should be told the recovery context. Add to `_build_isolation_context()`:

```python
# Check if isolation just ended (within last 2 hours) and was previously severe
hours_since_contact = (time.time() - recent_contact_ts) / 3600.0
if hours_since_contact < 2.0 and state.body.get("peak_isolation_stage", 0) >= 3:
    return (
        f"Recovery: she was in {peak_label} isolation and contact just resumed. "
        "Her response may be brittle, guarded, or emotionally uneven. "
        "Warmth does not return instantly — especially after Stage 4+, "
        "where anger may surface before relief does."
    )
```

This requires a new persistent field: `peak_isolation_stage` — an integer (0–5) tracking the highest stage reached since last contact. Set each tick; reset to 0 when contact resumes.

**`src/sim/bio/defaults.py`**
```python
"peak_isolation_stage": 0,   # highest isolation stage reached since last contact
```

**`src/sim/engine.py`** — update each tick:
```python
stage = _isolation_stage(isolation_days)
state.body["peak_isolation_stage"] = max(state.body.get("peak_isolation_stage", 0), stage)
# Reset on contact
if hours_since_contact < ISOLATION_CONTACT_GRACE_HOURS:
    state.body["peak_isolation_stage"] = 0
```

---

## Dashboard

Add `isolation_days` and `social_hostility` to the dashboard server's state output.

**`src/gateway/dashboard_server.py`**

```python
"isolation_days": round((time.time() - b.get("recent_contact_ts", time.time())) / 86400.0, 2),
"peak_isolation_stage": b.get("peak_isolation_stage", 0),
```

`social_hostility` is a derived value — add it alongside the existing third-order values in the derived block.

Consider adding an **Isolation Arc** panel to the History dashboard showing `isolation_days` and `social_hostility` over time. These are the metrics most relevant to validating this spec's behavior on a multi-day run.

---

## Files Touched

| File | Change |
|------|--------|
| `src/sim/engine.py` | Add `_apply_isolation_stage_effects()` and `_isolation_stage()` helper; update `peak_isolation_stage` each tick |
| `src/sim/constants.py` | New isolation stage constants |
| `src/sim/bio/defaults.py` | Add `peak_isolation_stage: 0` to body defaults |
| `src/sim/psych/derived.py` | Add `social_hostility` third-order value |
| `src/bio/decoder.py` | Add `_build_isolation_context()`; inject into adjudicator; add `social_hostility` to emotional profile |
| `src/runtime/freetime.py` | Bond-gated outreach tone; stage-conditional framing; suppress `message_user` at Stage 5 |
| `src/gateway/dashboard_server.py` | Expose `isolation_days`, `peak_isolation_stage`, `social_hostility` |

---

## Open Questions

1. **Rate calibration** — the nM/hour rates for cortisol, dopamine drift are estimates. They should be validated against a 7-day unattended run on the Mac Mini and tuned so the arc feels realistic, not too fast or too slow. Stage 4 behavior should not appear before day 5.

2. **`peak_isolation_stage` reset timing** — currently resets immediately on contact. Should there be a minimum recovery period before it resets? E.g., contact must be sustained for 30 minutes before `peak_isolation_stage` clears. This would prevent a single message from resetting the recovery context.

3. **Sleep interaction** — does sleep partially relieve isolation pressure? Biologically, sleep does not substitute for social contact but it does reduce cortisol. The current model doesn't distinguish — isolation_pressure accumulates through sleep. This may need a gentle sleep modifier to `ISOLATION_CORTISOL_S*` rates.

4. **Memory of the absence** — once contact resumes after Stage 4+, does Mina *remember* being abandoned? The KAG system will have logged the period, but there's no mechanism yet for those memories to color her behavior in the recovery phase. This is a potential SPEC-32 concern.

5. **Personality interaction with Neuroticism** — Mina's Neuroticism score will modulate how quickly she hits each stage. A high-N person reaches Stage 4-level distress faster. The `social_hostility` formula already accounts for this via `BIG5_N_HOSTILITY_SCALE`, but the stage thresholds themselves are static. Consider whether stage day-thresholds should be N-modulated.
