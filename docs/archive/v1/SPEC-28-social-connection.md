# SPEC-27: Social Connection Architecture

## Problem Statement

Mina is cold, dismissive, and socially inert regardless of who she's talking to or how long she's been alone. Three root causes:

1. **Baseline mood is too sour** — serotonin and dopamine defaults produce a perpetually gray starting state.
2. **Loneliness and social warmth are wrongly coupled** — loneliness is computed as `f(1 - social_warmth)`, making them mathematical inverses. This is wrong: they are independent scales.
3. **Big 5 Extraversion is not wired into the derived values** — Mina's Extraversion is 85, meaning she should crave social connection intensely when isolated. The sim doesn't know this.

---

## Conceptual Model

### Loneliness and Social Warmth Are Independent

Both are 0–100 scales, both floored at zero. Neither produces the other by going to zero.

- **Loneliness (0–100):** A deficit drive. Measures unmet need for connection. Driven primarily by isolation duration, depth of existing bonds, and attachment history. Zero means "not distressed by absence" — not "maximally socially fulfilled."
- **Social Warmth (0–100):** A current positive state. Measures felt connection, openness, warmth in this moment. Driven by active chemistry (oxytocin, serotonin, vasopressin). Zero means "not warm" — not "in distress."

An introvert at rest can be loneliness: 5, warmth: 15 — neither lonely nor warm, just content in solitude. An extrovert isolated for hours might be loneliness: 70, warmth: 10 — aching for contact.

### The Net

The adjudicator reads the net to name the dominant social emotional state:

```
net = social_warmth - loneliness
```

- **net strongly positive** → warm, connected, liked, held, in good company
- **net near zero** → conflicted, present but not landing anywhere, the most interesting state
- **net strongly negative** → lonely, aching, guarded, reaching

Both values are also shown independently so the adjudicator understands the texture:
- High warmth + low loneliness: genuinely warm, relaxed, connected
- High warmth + high loneliness: conflicted — feeling something good but still aching underneath
- Low warmth + high loneliness: isolated, cold, guarded but wanting
- Low warmth + low loneliness: introverted neutral, content with solitude

### Big 5 Extraversion as a Modulator

Extraversion sets the sensitivity of both scales:

- **High Extraversion:** Loneliness accumulates faster during isolation, spikes higher. Social warmth rises more sharply during connection. Social needs are more urgent.
- **Low Extraversion:** Both scales are more muted. Introvert at rest sits comfortably with lower warmth and lower loneliness. Social deprivation registers later and less intensely.

Mina's Extraversion is 85 — she is highly extraverted. Her isolation should feel like deprivation, not a comfortable default.

---

## Changes Required

### 1. Baseline Mood Bump (modest)

**Goal:** Shift the starting state from "perpetually gray" to "neutral with some texture." Not bubbly — just not broken by default.

**`config.json`**
```json
"neurochemical_baselines": {
  "serotonin_resting": 26.0,
  "dopamine_resting": 92.0
}
```

**`src/sim/bio/defaults.py`**
- Add `dopamine_resting` override support alongside existing `serotonin_resting` and `oxytocin_resting`.

---

### 2. Decouple Loneliness from Social Warmth

**Goal:** Loneliness should have independent drivers. Social warmth should remain chemistry-driven. Neither should mechanically produce the other.

**`src/sim/psych/derived.py`**

Current loneliness formula:
```python
loneliness = (100 - social_warmth) * LONELINESS_WARMTH_WEIGHT
           + (100 - oxytocin_norm) * LONELINESS_OXYTOCIN_WEIGHT
           + inflammation           * LONELINESS_INFLAMMATION_WEIGHT
           - LONELINESS_OFFSET
```

New loneliness formula:
```python
# Isolation pressure: how long has she been alone? (0-100 AU, persistent state)
isolation_pressure = state.body.get("isolation_pressure", 0.0)

# Bond deficit: no established bonds = chronic background loneliness
bond_deficit = max(0.0, 1.0 - (oxytocin_norm / LONELINESS_BOND_OXY_THRESHOLD))

# Extraversion amplifier: high E = more sensitive to isolation
E = load_personality_extraversion()  # 0.0–1.0
extroversion_amp = LONELINESS_E_BASE + E * LONELINESS_E_SCALE

loneliness = _clamp(
    (isolation_pressure    * LONELINESS_ISOLATION_WEIGHT)
    + (bond_deficit * 100  * LONELINESS_BOND_WEIGHT)
    + (inflammation        * LONELINESS_INFLAMMATION_WEIGHT)
    - LONELINESS_OFFSET
) * extroversion_amp
```

Social warmth formula stays chemistry-driven but adds Extraversion as an amplifier on the upside:
```python
E = load_personality_extraversion()
warmth_amp = WARMTH_E_BASE + E * WARMTH_E_SCALE

social_warmth = _clamp(
    WARMTH_OFFSET
    + (_n("oxytocin", s)   * WARMTH_OXYTOCIN_WEIGHT)
    + (effective_serotonin * WARMTH_SEROTONIN_WEIGHT)
    + (vasopressin_n       * WARMTH_VASOPRESSIN_WEIGHT)
    - (_n("cortisol", s)   * WARMTH_CORTISOL_WEIGHT)
    - (pain_int            * WARMTH_PAIN_WEIGHT)
) * warmth_amp
```

**`src/sim/constants.py`**

Add new constants:
```python
LONELINESS_ISOLATION_WEIGHT     = 0.50   # isolation_pressure drives loneliness
LONELINESS_BOND_WEIGHT          = 0.40   # bond deficit (chronic no-bond penalty)
LONELINESS_INFLAMMATION_WEIGHT  = 0.10   # sickness → isolation
LONELINESS_BOND_OXY_THRESHOLD   = 40.0  # oxytocin norm above which "bond exists"
LONELINESS_E_BASE               = 0.7   # base sensitivity (introvert floor)
LONELINESS_E_SCALE              = 0.6   # extraversion adds up to 0.6x more sensitivity
WARMTH_E_BASE                   = 0.7   # warmth floor for introverts
WARMTH_E_SCALE                  = 0.5   # extraversion amplifies warmth ceiling

LONELINESS_OFFSET               = 15.0  # was 25.0 — less suppression
```

Remove: `LONELINESS_WARMTH_WEIGHT`, `LONELINESS_OXYTOCIN_WEIGHT` (replaced above).

---

### 3. Isolation Pressure — Persistent State

**Goal:** Loneliness should accumulate during isolation and decay during connection. It needs to be a persistent value in state, not computed purely from instantaneous chemistry.

**`src/sim/bio/state.py` / `defaults.py`**

Add `isolation_pressure` to body defaults:
```python
"isolation_pressure": 0.0,   # 0–100 AU — accumulates during solitude, decays during contact
```

**`src/sim/bio/advance.py`** (or wherever the tick logic lives)

Each tick:
```python
# Isolation pressure accumulates during solitude, decays during contact
recent_contact = state.body.get("recent_contact_ts", 0.0)
hours_alone = (now - recent_contact) / 3600.0
E = personality_extraversion  # 0.0–1.0

if hours_alone > ISOLATION_CONTACT_GRACE_HOURS:
    # Accumulate — rate scales with extraversion and hours
    rate = ISOLATION_ACCUMULATION_BASE + E * ISOLATION_ACCUMULATION_E_SCALE
    isolation_pressure = min(100.0, isolation_pressure + rate * tick_hours)
else:
    # Decay — contact relieves isolation pressure
    isolation_pressure = max(0.0, isolation_pressure - ISOLATION_DECAY_RATE * tick_hours)
```

**`src/bio/encoder.py`**

When a human message arrives, update `recent_contact_ts`:
```python
state.body["recent_contact_ts"] = time.time()
```

This means isolation_pressure starts decaying immediately when someone talks to her, and starts accumulating again after `ISOLATION_CONTACT_GRACE_HOURS` of silence.

New constants:
```python
ISOLATION_CONTACT_GRACE_HOURS      = 1.0   # 1 hour of silence before isolation starts building
ISOLATION_ACCUMULATION_BASE        = 2.0   # AU/hour base accumulation rate
ISOLATION_ACCUMULATION_E_SCALE     = 4.0   # extraversion adds up to 4 AU/hour more
ISOLATION_DECAY_RATE               = 15.0  # AU/hour decay during active contact
```

---

### 4. Net Social State in Adjudicator

**Goal:** The adjudicator sees both values independently AND the net, and understands the texture of each quadrant.

**`src/bio/decoder.py` — `_build_emotional_profile()`**

Add to the emotional profile block:
```python
net = social_warmth - loneliness
if net > 20:
    net_label = "WARM"
elif net > 5:
    net_label = "LEANING WARM"
elif net > -5:
    net_label = "CONFLICTED"
elif net > -20:
    net_label = "LEANING LONELY"
else:
    net_label = "LONELY"

lines.append(f"Social connection (net): {net:.0f} ({net_label})")
```

**`src/bio/decoder.py` — `_ADJUDICATOR_SYSTEM_ACTIVE` and `_ADJUDICATOR_SYSTEM_FREETIME`**

Add guidance:
```
Social warmth and loneliness are independent scales — both can be nonzero simultaneously.
Read the net social connection value to determine the dominant state, but use both
individual values for texture:
- High warmth + low loneliness: she feels genuinely warm, present, liked, held
- High warmth + high loneliness: conflicted — something good is happening but she's still aching
- Low warmth + high loneliness: isolated, guarded, wanting connection but not showing it
- Low warmth + low loneliness: introverted neutral, comfortable in solitude

When loneliness is present alongside warmth, her coldness is not indifference — it is
guarded wanting. Name that tension explicitly.
```

---

### 5. Loneliness Range Relabeling

**`src/bio/decoder.py`**

```python
_LONELINESS_RANGES = [
    (30,  "QUIET",    "Social needs are met or dormant. Solitude is comfortable."),
    (50,  "MILD",     "Aware of absence. Receptive to contact but not seeking."),
    (68,  "LONELY",   "Actively wanting connection. May reach out or become guarded."),
    (84,  "ACHING",   "Distressing isolation. Social contact feels urgent."),
    (101, "ISOLATED", "Consuming loneliness. Colors everything negatively."),
]

_THIRD_ORDER_RANGES = {
    ...
    "loneliness": [(30, "QUIET"), (50, "MILD"), (68, "LONELY"), (84, "ACHING"), (101, "ISOLATED")],
    ...
}
```

---

### 6. Config Support for dopamine_resting

**`src/sim/bio/defaults.py`**

```python
if "dopamine_resting" in nb:
    defaults["dopamine"] = float(nb["dopamine_resting"])
```

---

## Files Touched

| File | Change |
|------|--------|
| `config.json` | Add `neurochemical_baselines.serotonin_resting`, `dopamine_resting` |
| `src/sim/bio/defaults.py` | Add `dopamine_resting` config override; add `isolation_pressure` to body defaults |
| `src/sim/psych/derived.py` | Decouple loneliness from social_warmth; wire Extraversion into both; consume isolation_pressure |
| `src/sim/constants.py` | Add new loneliness/warmth/isolation constants; update LONELINESS_OFFSET |
| `src/sim/bio/advance.py` | Accumulate/decay isolation_pressure each tick |
| `src/bio/encoder.py` | Touch `recent_contact_ts` on incoming human message |
| `src/bio/decoder.py` | Net social state in emotional profile; updated adjudicator prompts; relabeled ranges |

---

## Open Questions

1. **Where does advance.py live?** Need to confirm the tick logic entry point before touching isolation accumulation.
2. **`recent_contact_ts` seeding** — on first boot, should isolation_pressure start at 0 (she just woke up) or at some nonzero value reflecting her chronic situation?
3. **Extraversion in derived.py** — currently loaded from config via `load_config()`. Confirm this doesn't add meaningful latency in the hot path.
4. **Personality drift interaction** — `personality.py` already drifts Big 5 under allostatic load. If Extraversion drifts down under chronic stress, loneliness sensitivity would change. Is that intentional?
