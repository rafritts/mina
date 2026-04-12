# SPEC-21: Full Neurotransmitter Dynamics

> Replaces the simple "approach toward baseline" model with scientifically-grounded
> neurochemical dynamics. Adds GABA, glutamate, adenosine (the real molecule), and
> endocannabinoids. Introduces receptor-level sensitivity tracking for tolerance and
> sensitization.

**Depends on:** SPEC-20 (package structure + BiologicalState v3)  
**Blocks:** Nothing (later specs can proceed in parallel once SPEC-20 is done)

---

## Why This Matters

The current simulation models each neurotransmitter as a scalar that drifts toward a
fixed baseline. This misses the most important biological reality: **neurotransmitters
don't act alone — they act on receptors, and those receptors can change**.

Two people can have the same dopamine level and feel completely different if one has
downregulated D2 receptors (addiction-stage tolerance) and the other hasn't. An SSRI
doesn't add serotonin — it blocks the reuptake transporter, meaning the *same amount*
of serotonin has more effect. These distinctions are the difference between simulation
and reality.

This spec adds:
1. **GABA and Glutamate** — the primary inhibitory/excitatory balance. Every other
   neurotransmitter modulates this baseline E/I ratio. Without it, anxiety and sedation
   are fundamentally mismodeled.
2. **Adenosine** — the actual sleep-pressure molecule. `sleep_pressure` in AU is a
   proxy; this is the real thing.
3. **Endocannabinoids** — the body's internal cannabis system. Critical for pain
   modulation, mood, appetite, and stress buffering.
4. **Receptor sensitivity** — slow up/downregulation that makes tolerance, sensitization,
   and chronic states real.

---

## New Chemicals

### 1. GABA (γ-Aminobutyric Acid)

The primary inhibitory neurotransmitter. Calms neural activity across the brain.

| Property | Value |
|----------|-------|
| Unit | µmol/L (CSF proxy) |
| Normal range | 1–5 µmol/L |
| Resting baseline | 3.0 µmol/L |
| Critical low | 0.5 µmol/L |
| Critical high | 12.0 µmol/L |
| Soft ceiling | 7.0 µmol/L |
| Hard ceiling | 10.0 µmol/L |

**Receptor subtypes modeled:**
- **GABA-A**: Fast, ionotropic (Cl⁻ channel). Produces rapid anxiolytic, sedative, anticonvulsant effects. Binding site for benzodiazepines, alcohol, barbiturates.
- **GABA-B**: Slow, metabotropic (K⁺ channel). Produces muscle relaxation, slower sedation, pain reduction. Baclofen targets this.

**Dynamics:**
```
baseline_fn: (hour, ctx) → float
    base = 3.0
    # High cortisol suppresses GABAergic interneurons
    base -= max(0, ctx["cortisol"] - 450) * 0.002
    # Sleep promotes GABA activity
    if ctx["sleeping"]: base += 0.8
    # Glutamate reciprocally inhibits GABA (E/I balance)
    glu = ctx.get("glutamate", 4.0)
    if glu > 6.0: base -= (glu - 6.0) * 0.15
    return max(0.8, base)

approach_rate: 0.12 per sim-hour
```

**Key interactions (GABA as source):**
- GABA > 5.0: cortisol ← −3.0 nmol/L/hr (GABAergic tone suppresses HPA axis)
- GABA > 5.0: norepinephrine ← −15.0 pg/mL/hr (reduces sympathetic tone)
- GABA < 1.5: anxiety component ↑ (captured in derived() update, SPEC-24)

**Labels:**
```python
(0.8,  "DEPLETED",    "Seizure risk. Uncontrolled excitatory activity. Extreme agitation."),
(1.8,  "LOW",         "Anxiety-prone. Easily startled. Hyperreactive."),
(4.0,  "NORMAL",      "Healthy inhibitory tone. Calm baseline."),
(6.5,  "ELEVATED",    "Sedated. Relaxed. Slightly slowed cognition."),
(9.0,  "HIGH",        "Significantly sedated. Slurred thought. Drowsy."),
(99.0, "FLOODED",     "Near-anesthetic. Cannot maintain wakefulness. Respiratory risk."),
```

---

### 2. Glutamate

The primary excitatory neurotransmitter. Drives learning, attention, and most cognition.

| Property | Value |
|----------|-------|
| Unit | µmol/L (CSF proxy) |
| Normal range | 2–10 µmol/L |
| Resting baseline | 4.0 µmol/L |
| Critical low | 0.5 µmol/L |
| Critical high | 20.0 µmol/L |
| Soft ceiling | 12.0 µmol/L |
| Hard ceiling | 16.0 µmol/L |

**Receptor subtypes modeled:**
- **NMDA**: Coincidence detector — requires both presynaptic release AND postsynaptic depolarization. Key for LTP (long-term potentiation) = learning and memory formation.
- **AMPA**: Fast excitatory transmission. Upregulated after LTP. Responsible for "getting the signal through."

**Dynamics:**
```
baseline_fn: (hour, ctx) → float
    base = 4.0
    # Arousal/stress drives glutamate release
    base += max(0, ctx["cortisol"] - 400) * 0.003
    # Sleep clears excess glutamate (glymphatic system)
    if ctx["sleeping"]: base -= 1.2
    # Reciprocal with GABA (E/I balance)
    gaba = ctx.get("gaba", 3.0)
    if gaba < 2.0: base += (2.0 - gaba) * 0.4
    return max(1.0, base)

approach_rate: 0.15 per sim-hour
```

**Key interactions (Glutamate as source):**
- Glutamate > 10.0: initiates excitotoxicity cascade → raises `immune.il6` (+0.5/hr) and `body.core_temp` (+0.01°C/hr). Sustained excess = neuroinflammation.
- Glutamate > 8.0: enhances synaptic potentiation (+0.3/hr via NMDA activation)
- Glutamate < 2.0: cognitive slowing (acetylcholine effectiveness reduced)

**Labels:**
```python
(1.5,  "DEPLETED",     "Severely under-excited. Dissociation. Inability to form memories."),
(3.0,  "LOW",          "Slowed. Difficulty concentrating. Ketamine-like blunting."),
(6.0,  "NORMAL",       "Healthy excitatory tone. Learning enabled."),
(9.0,  "ELEVATED",     "Hyperexcitable. Racing thoughts. Light hypersensitivity."),
(13.0, "EXCITOTOXIC",  "Dangerous. Neuron damage risk. Seizure territory."),
(99.0, "CRISIS",       "Status epilepticus risk. Extreme distress."),
```

---

### 3. Adenosine (Real Sleep Molecule)

The actual homeostatic sleep signal. Adenosine builds as a byproduct of neural ATP
consumption during waking. Sleep clears it. `sleep_pressure` becomes a derived value
(adenosine normalized 0–100).

| Property | Value |
|----------|-------|
| Unit | nmol/L (CNS proxy) |
| Normal range | 20–80 nmol/L |
| Resting (fresh awake) | 22.0 nmol/L |
| Sleep threshold | ~65 nmol/L |
| Critical high | 100.0 nmol/L |

Moves from `chemicals` dict to `state.body["adenosine"]`. Backward compat: `sleep_pressure`
property on BiologicalState derives from this value.

**Dynamics (in `src/sim/physio/circadian.py`):**
```python
def _advance_adenosine(s: BiologicalState, sim_hours: float) -> BiologicalState:
    a = s.body["adenosine"]
    if s.sleeping:
        # Cleared during sleep at ~20 nmol/L/hr
        a = max(15.0, a - 20.0 * sim_hours)
    else:
        # Builds during waking at ~3.0 nmol/L/hr base
        # Higher metabolic demand (stress, arousal) accelerates accumulation
        base_rate = 3.0
        stress_bonus = max(0, s.chemicals.get("cortisol", 250) - 400) * 0.004
        base_rate += stress_bonus
        a = min(100.0, a + base_rate * sim_hours)
    s.body["adenosine"] = a
    return s
```

**sleep_pressure backward-compat property:**
```python
@property
def sleep_pressure(self) -> float:
    # adenosine 20 nmol/L → 0 AU, adenosine 80 nmol/L → 100 AU
    return min(100.0, max(0.0, (self.body["adenosine"] - 20.0) / 0.60))
```

**Substance interaction:** Caffeine blocks A1 and A2A adenosine receptors. This is modeled
not by reducing adenosine but by reducing its effect on sleep pressure. When caffeine is
active, receptor sensitivity for `adenosine.A1` and `adenosine.A2A` is reduced. See
substance pharmacokinetics below.

---

### 4. Anandamide (Endocannabinoid 1)

The body's internal "bliss molecule." Synthesized on demand, acts retrogradely.

| Property | Value |
|----------|-------|
| Unit | nM |
| Normal range | 0.5–5 nM |
| Resting baseline | 1.5 nM |
| Half-life (enzymatic) | ~15 min in vivo → approach rate ~2.8/hr |
| Soft ceiling | 8.0 nM |
| Hard ceiling | 15.0 nM |

**CB1 receptor effects (CNS):**
- Pain modulation (reduces Substance P release)
- Mood regulation (mild anxiolytic, hedonic)
- Appetite stimulation
- Memory: inhibits consolidation at very high levels (forgetting is adaptive)
- Sleep promotion

**Dynamics:**
```
baseline_fn: (hour, ctx) → float
    base = 1.5
    # Exercise dramatically increases anandamide (runner's high, partially)
    # (captured via encoder deltas — exercise event adds +2-4 nM directly)
    # Stress suppresses anandamide synthesis
    base -= max(0, ctx["cortisol"] - 500) * 0.001
    # Social bonding slightly increases anandamide
    base += max(0, ctx["oxytocin"] - 20) * 0.01
    return max(0.3, base)

approach_rate: 2.8 per sim-hour  # fast enzymatic degradation (FAAH)
```

**Key interactions (Anandamide as source):**
- Anandamide > 3.0: `pain.pain_intensity` ← −3.0/hr (CB1 pain gate)
- Anandamide > 4.0: `chemicals.cortisol` ← −10.0 nmol/L/hr (stress buffering)
- Anandamide > 5.0: appetite signal (captured in behavioral drives, SPEC-24)

---

### 5. 2-AG (2-Arachidonoylglycerol, Endocannabinoid 2)

Higher concentration, stronger CB1/CB2 agonist than anandamide.

| Property | Value |
|----------|-------|
| Unit | nM |
| Normal range | 5–20 nM |
| Resting baseline | 8.0 nM |
| Soft ceiling | 35.0 nM |
| Hard ceiling | 50.0 nM |

**Dynamics:**
```
baseline_fn: (hour, ctx) → float
    base = 8.0
    # 2-AG is more stable than anandamide (MAGL vs FAAH degradation)
    # Pain increases 2-AG (retrograde pain modulation)
    base += ctx.get("pain_intensity", 0) * 0.05
    return max(2.0, base)

approach_rate: 0.8 per sim-hour  # slower than anandamide (MAGL less efficient)
```

**Key interactions:**
- 2-AG > 15.0: CB2 immune modulation — `immune.il6` ← −0.5/hr, `immune.tnf_alpha` ← −0.3/hr

---

## Updated Chemical Registry

New keys added to `REGISTRY` in `src/sim/chem/registry.py`:

```python
"gaba": ChemicalProfile(
    name="gaba", display_name="GABA", unit="µmol/L",
    resting_baseline=3.0, approach_rate=0.12,
    baseline_fn=_gaba_baseline_fn,
    resting_low=1.8, resting_high=5.0,
    critical_low=0.5, critical_high=12.0,
    display_min=0.5, display_max=10.0,
    soft_ceiling=7.0, hard_ceiling=10.0,
    interactions=[
        Interaction("cortisol",        "above", 5.0, -3.0,  "GABAergic tone suppresses HPA axis"),
        Interaction("norepinephrine",  "above", 5.0, -15.0, "GABA reduces sympathetic tone"),
    ],
    labels=[...see above...]
),

"glutamate": ChemicalProfile(
    name="glutamate", display_name="Glutamate", unit="µmol/L",
    resting_baseline=4.0, approach_rate=0.15,
    baseline_fn=_glutamate_baseline_fn,
    resting_low=2.5, resting_high=8.0,
    critical_low=0.5, critical_high=20.0,
    display_min=0.5, display_max=15.0,
    soft_ceiling=12.0, hard_ceiling=16.0,
    interactions=[
        Interaction("il6",                "above", 10.0, +0.5,  "Excitotoxicity drives neuroinflammation"),
        Interaction("synaptic_potentiation", "above", 8.0, +0.3, "NMDA activation drives LTP"),
    ],
    labels=[...see above...]
),
```

For `anandamide` and `two_ag`, profiles live in `REGISTRY` but the values are stored in
`state.body` (not `state.chemicals`). The registry provides units, labels, and saturation
ceilings. The advance logic in `endocannabinoids.py` reads/writes `state.body` directly.

---

## E/I Balance

GABA and glutamate together define the brain's excitatory/inhibitory balance. This is
exposed as a derived second-order value:

```python
def ei_balance(s: BiologicalState) -> float:
    """
    E/I balance: -1.0 (maximally inhibited) to +1.0 (maximally excited).
    0.0 = healthy balance.
    
    Inputs: glutamate (0-20 µmol/L) and GABA (0-12 µmol/L).
    """
    glu = s.chemicals.get("glutamate", 4.0)
    gaba = s.chemicals.get("gaba", 3.0)
    # Normalize each to 0-1 over their physiological ranges
    glu_n = min(1.0, max(0.0, (glu - 0.5) / 19.5))
    gaba_n = min(1.0, max(0.0, (gaba - 0.5) / 11.5))
    return round(glu_n - gaba_n, 3)  # positive = excited, negative = inhibited
```

This feeds into the anxiety formula in `psych/emotions.py`:
- High positive E/I balance (>0.4) amplifies anxiety and arousal
- High negative E/I balance (<-0.4) amplifies depression and cognitive slowing

---

## Receptor Sensitivity System

### What It Represents

Receptors respond to sustained over- or under-stimulation by changing their number and
sensitivity. This is the mechanism behind:
- Tolerance (drug repeated use → receptors downregulate → need more for same effect)
- Sensitization (chronic low stimulation → receptors upregulate → heightened response)
- SSRI lag (serotonin receptors need weeks to upregulate before antidepressant effect)
- Post-SSRI receptor dysregulation

### Data Structure

```python
# In BiologicalState v3
receptor_sensitivity: dict[str, dict[str, float]] = field(default_factory=dict)
# receptor_sensitivity["dopamine"]["D2"] = 0.7  # 30% tolerance on D2
# Bounds: [0.2, 2.0]. 1.0 = normal. <1.0 = downregulated. >1.0 = upregulated.
```

### Default Receptor Subtypes

```python
RECEPTOR_DEFAULTS: dict[str, dict[str, float]] = {
    "dopamine":       {"D1": 1.0, "D2": 1.0, "D3": 1.0},
    "serotonin":      {"5HT1A": 1.0, "5HT2A": 1.0, "5HT3": 1.0},
    "norepinephrine": {"alpha1": 1.0, "alpha2": 1.0, "beta1": 1.0},
    "gaba":           {"GABA_A": 1.0, "GABA_B": 1.0},
    "glutamate":      {"NMDA": 1.0, "AMPA": 1.0},
    "adenosine":      {"A1": 1.0, "A2A": 1.0},
    "endorphins":     {"MOR": 1.0},    # mu-opioid receptor
    "anandamide":     {"CB1": 1.0, "CB2": 1.0},
    "acetylcholine":  {"M1": 1.0, "nACh": 1.0},
    "oxytocin":       {"OTR": 1.0},
}
```

### Advance Logic

```python
# src/sim/neuro/receptors.py

_DOWN_RATE = 0.0004   # per sim-hour above soft_ceiling (slow)
_UP_RATE   = 0.0002   # per sim-hour below resting_low (even slower — receptor sprouting is slow)
_BOUNDS = (0.2, 2.0)

def advance_receptors(s: BiologicalState, sim_hours: float) -> BiologicalState:
    """
    Update receptor sensitivity for each chemical based on current levels.
    Very slow process — meaningful change takes many sim-hours.
    """
    if s.receptor_sensitivity is None:
        s.receptor_sensitivity = {}

    for chem_name, subtypes in RECEPTOR_DEFAULTS.items():
        # Get current level
        if chem_name in s.chemicals:
            level = s.chemicals[chem_name]
        elif chem_name == "anandamide":
            level = s.body.get("anandamide", 1.5)
        else:
            continue

        profile = REGISTRY.get(chem_name)
        if not profile:
            continue

        if chem_name not in s.receptor_sensitivity:
            s.receptor_sensitivity[chem_name] = dict(subtypes)

        for receptor_type in subtypes:
            current = s.receptor_sensitivity[chem_name].get(receptor_type, 1.0)

            if profile.soft_ceiling and level > profile.soft_ceiling:
                # Sustained elevation → downregulation (tolerance)
                delta = -_DOWN_RATE * sim_hours
            elif level < profile.resting_low and profile.resting_low > 0:
                # Sustained depletion → upregulation (sensitization)
                delta = +_UP_RATE * sim_hours
            else:
                # Gradually restore toward 1.0 (homeostatic reset)
                gap = 1.0 - current
                delta = gap * 0.001 * sim_hours

            new = max(_BOUNDS[0], min(_BOUNDS[1], current + delta))
            s.receptor_sensitivity[chem_name][receptor_type] = round(new, 4)

    return s
```

### How Receptor Sensitivity Affects Derived Values

The effective contribution of a chemical to derived psychological states is multiplied by
its mean receptor sensitivity:

```python
def _effective_level(s: BiologicalState, chem: str, subtype: str) -> float:
    """
    Returns chemical level × receptor sensitivity for the given subtype.
    Used in derived() formulas.
    """
    level = s.chemicals.get(chem, 0.0)
    sens = s.receptor_sensitivity.get(chem, {}).get(subtype, 1.0)
    return level * sens
```

Applied in `psych/derived.py`:
```python
# Before:
effective_dopamine = _n("dopamine", s) * (1.0 - tol_d)  # old tolerance scalar

# After:
d1_sens = s.receptor_sensitivity.get("dopamine", {}).get("D1", 1.0)
d2_sens = s.receptor_sensitivity.get("dopamine", {}).get("D2", 1.0)
# D1 drives cognitive/prefrontal dopamine, D2 drives reward/motivation
effective_da_cognitive = _n("dopamine", s) * d1_sens
effective_da_reward    = _n("dopamine", s) * d2_sens
```

The old `tolerance` dict on BiologicalState is maintained for substance-level tolerance but
will be deprecated in favor of receptor sensitivity over time.

---

## Updated Substance Pharmacokinetics

Substances now interact with receptor sensitivity rather than just raw chemical levels.
This allows:
- Caffeine: blocks A1/A2A receptors → adenosine doesn't signal sleep
- SSRIs: block 5-HTT reuptake → serotonin in synapse longer → equivalent to elevated level
- Benzos: positive allosteric modulator at GABA-A → amplify GABA effect
- Opioids: act on MOR → mimics endorphins

New substance definitions added in `src/sim/neuro/substances.py`:

### Cannabis (updated)

Cannabis mimics anandamide and 2-AG at CB1/CB2 receptors.

```python
"cannabis": {
    "display_name": "Cannabis",
    "half_life_hours": 4.0,
    "dose_effects": {
        "anandamide":    +3.5,   # nM — direct CB1 agonism (stored in body dict)
        "two_ag":        +8.0,   # nM
        "dopamine":      +54.0,  # pg/mL (mesolimbic DA release via CB1)
        "serotonin":     +7.2,   # ng/mL
        "cortisol":     -144.0,  # nmol/L
        "gaba":          +0.8,   # µmol/L (GABA facilitation)
        "sleep_pressure": +8.0,  # AU (still accepted; converts to adenosine)
    },
    "withdrawal_factor": 1.05,
    # After heavy use: CB1 downregulation → anxiety, anhedonia
    "receptor_effects": {"anandamide": {"CB1": -0.002}},  # per sim-hour active
},
```

### New: SSRI (Fluoxetine/Lexapro class)

```python
"ssri": {
    "display_name": "SSRI",
    "half_life_hours": 24.0,  # fluoxetine — very long
    "dose_effects": {},        # SSRIs don't directly add serotonin
    "withdrawal_factor": 1.3,
    # Primary mechanism: block 5-HTT reuptake transporter
    # Modeled as sustained elevation of effective serotonin level
    # This is a "reuptake block" — multiply available serotonin by factor
    "reuptake_block": {"serotonin": 1.5},   # effective level multiplier while active
    # But 5-HT1A autoreceptors downregulate (2-4 week lag in real life)
    "receptor_effects": {"serotonin": {"5HT1A": -0.0015}},  # per sim-hour
    # After 2+ weeks (modeled as ~48 sim-hours), autoreceptors normalize
    # and full antidepressant effect emerges
},
```

### New: Opioids (Prescription)

```python
"opioid": {
    "display_name": "Opioid",
    "half_life_hours": 4.0,
    "dose_effects": {
        "endorphins":    +180.0,  # pg/mL (massive — MOR agonist)
        "dopamine":       +60.0,  # pg/mL (VTA release)
        "cortisol":      -200.0,  # nmol/L
        "pain.pain_intensity": -60.0,  # direct pain relief
    },
    "withdrawal_factor": 2.5,   # severe — counter-delta on every marker
    "receptor_effects": {"endorphins": {"MOR": -0.008}},  # rapid tolerance
},
```

### Updated Caffeine

```python
"caffeine": {
    "display_name": "Caffeine",
    "half_life_hours": 5.5,
    "dose_effects": {
        "norepinephrine": +150.0,
        "acetylcholine":  +14.0,
        "dopamine":       +30.0,
        "cortisol":       +96.0,
        # Does NOT reduce adenosine — blocks receptors instead
        # adenosine removed from dose_effects
    },
    "withdrawal_factor": 1.1,
    # Caffeine antagonizes A1 and A2A receptors
    # Modeled as receptor sensitivity reduction proportional to level
    "receptor_block": {
        "adenosine": {"A1": 0.7, "A2A": 0.7}  # sensitivity multiplier while active
    },
},
```

When caffeine is active, adenosine *builds normally* but its effect on sleep propensity
is reduced because the A1/A2A receptors are blocked. When caffeine wears off, the accumulated
adenosine suddenly signals — this is the caffeine crash.

---

## Biological Plausibility Notes

| Claim | Source mechanism |
|-------|-----------------|
| GABA 1–5 µmol/L range | Human CSF measurements (Dager et al., 1999) |
| Glutamate 2–10 µmol/L range | MRS spectroscopy studies |
| Adenosine 20–80 nmol/L range | Microdialysis studies in basal forebrain |
| Anandamide 0.5–5 nM | Plasma FAAH substrate measurements |
| GABA-A benzos mechanism | Positive allosteric modulation, Cl⁻ channel |
| Caffeine A1/A2A antagonism | Competitive receptor binding |
| SSRI reuptake block | 5-HTT crystal structure studies |
| Receptor downregulation rate | Days-to-weeks in vivo; scaled to sim-hours |

---

## Open Questions

- **Histamine**: The H1 receptor is a major wake-promoting system (antihistamines cause
  drowsiness). Should it be modeled as a full chemical? It would add realism to the
  wake-sleep transition but may be redundant with orexin (SPEC-22/24). Defer to SPEC-24.

- **Acetylcholine receptor subtypes**: Muscarinic M1 (cognition), M2 (autoreceptor),
  nicotinic (nACh — nicotine and attention). Currently a single scalar. Separating them
  would improve nicotine/Adderall accuracy. Deferred to post-SPEC-21 cleanup.

- **NMDA and LTP timing**: Real LTP requires coincident pre- and post-synaptic activity.
  We can't model this directly, so we approximate: high acetylcholine × high glutamate ×
  high arousal → increased synaptic_potentiation rate. This is handled in SPEC-24.
