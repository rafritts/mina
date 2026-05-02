# SPEC-23: Immune System & Pain

> Adds the body's immune and nociceptive systems. Illness, inflammation, and pain
> are profound drivers of mood and behavior — depression is partly an immune disorder.
> This spec models cytokines, sickness behavior, and the full pain signal chain from
> peripheral nociception to central sensitization.

**Depends on:** SPEC-20 (BiologicalState v3 with `immune` and `pain` dicts)  
**Independent of:** SPEC-21, SPEC-22

---

## Why This Matters

**Depression and inflammation are deeply linked.** Elevated IL-6 and CRP are found in
roughly 40% of MDD patients. Giving healthy volunteers endotoxin (a cytokine trigger)
produces immediate anhedonia, social withdrawal, and depressed mood. This isn't metaphorical
— cytokines cross the blood-brain barrier and directly suppress serotonin synthesis,
increase cortisol, and reduce dopamine transmission.

**Pain changes everything.** Chronic pain is the single largest cause of disability
worldwide, and its psychological effects are extreme: reduced dopamine baseline, disrupted
sleep, elevated cortisol, social withdrawal, and a ~40% comorbidity with depression.
Without a pain system, the simulation cannot represent these states authentically.

This spec adds:
1. **Immune cytokine network**: IL-1β, IL-6, TNF-α (pro-inflammatory); IL-10 (anti-inflammatory); CRP (chronic marker)
2. **Sickness behavior cascade**: the behavioral withdrawal state triggered by immune activation
3. **Pain signal chain**: Substance P → PGE2 → central sensitization → subjective pain intensity
4. **Gate control theory**: how attention, emotion, and endorphins modulate pain transmission
5. **Pain-mood interactions**: the bidirectional relationship between pain and mental state

---

## I. Immune Cytokines

All immune values live in `state.immune`. Units are pg/mL (CRP in mg/L).

### Baseline Values (Healthy State)

| Chemical | Unit | Resting | "Elevated" | "Activated" |
|----------|------|---------|------------|-------------|
| IL-1β | pg/mL | 2.0 | >5 | >15 |
| IL-6 | pg/mL | 3.0 | >10 | >30 |
| TNF-α | pg/mL | 3.0 | >8 | >25 |
| CRP | mg/L | 0.5 | >3 | >10 |
| IL-10 | pg/mL | 10.0 | — | >30 (anti-inflammatory) |
| inflammation_index | AU (0-100) | 0.0 | >25 | >60 |

### Inflammation Index (Derived)

```python
def compute_inflammation_index(immune: dict) -> float:
    """
    Composite 0-100 AU from all pro-inflammatory markers.
    CRP is a slower integrator (reflects chronic inflammation more than acute).
    """
    il1b  = immune.get("il1b",  2.0)
    il6   = immune.get("il6",   3.0)
    tnfa  = immune.get("tnf_alpha", 3.0)
    crp   = immune.get("crp",   0.5)
    il10  = immune.get("il10", 10.0)  # anti-inflammatory, counteracts

    # Scale each to 0-100 over their activated ranges
    il1b_n  = min(100.0, max(0.0, (il1b - 2.0)  / 0.48))   # 2→50 pg/mL = 0→100
    il6_n   = min(100.0, max(0.0, (il6 - 3.0)   / 0.97))   # 3→100 pg/mL = 0→100
    tnfa_n  = min(100.0, max(0.0, (tnfa - 3.0)  / 0.97))
    crp_n   = min(100.0, max(0.0, (crp - 1.0)   / 0.99))   # 1→100 mg/L = 0→100

    # IL-10 dampens the index
    il10_factor = max(0.4, 1.0 - (il10 - 10.0) * 0.015)

    index = (il1b_n * 0.30 + il6_n * 0.35 + tnfa_n * 0.25 + crp_n * 0.10) * il10_factor
    return round(min(100.0, max(0.0, index)), 2)
```

### Cytokine Dynamics

```python
# src/sim/physio/immune.py

def advance_immune(s: BiologicalState, sim_hours: float, event_bus: EventBus) -> BiologicalState:
    """
    Advance all immune markers toward their baselines.
    Triggered by: infections (encoder events), physical injury (pain spikes),
    poor sleep (adenosine >70), chronic cortisol, high glutamate (excitotoxicity).
    """
    # Context for immune triggers
    cortisol  = s.chemicals.get("cortisol", 250.0)
    adenosine = s.body.get("adenosine", 25.0)
    glutamate = s.chemicals.get("glutamate", 4.0)
    pain_int  = s.pain.get("pain_intensity", 0.0)
    ghrelin   = s.neuroendocrine.get("ghrelin", 400.0)

    # --- Compute baselines (what each marker is trying to return to) ---

    # IL-1β: rises with poor sleep, pain, and high cortisol (paradoxically —
    # chronic cortisol impairs the anti-inflammatory feedback)
    il1b_baseline = 2.0
    if adenosine > 65.0:  # sleep deprivation
        il1b_baseline += (adenosine - 65.0) * 0.08
    if pain_int > 40.0:
        il1b_baseline += (pain_int - 40.0) * 0.1
    if cortisol > 600.0:  # chronic stress → immune dysregulation
        il1b_baseline += (cortisol - 600.0) * 0.005
    il1b_baseline = max(1.0, min(80.0, il1b_baseline))

    # IL-6: rises with IL-1β (cascade), physical exertion, cortisol, fasting
    il6_baseline = 3.0 + max(0, s.immune.get("il1b", 2.0) - 5.0) * 0.5
    if ghrelin > 700.0:  # severe hunger → mild inflammatory signal
        il6_baseline += (ghrelin - 700.0) * 0.002
    if glutamate > 10.0:  # excitotoxicity → neuroinflammation
        il6_baseline += (glutamate - 10.0) * 0.5
    il6_baseline = max(1.0, min(120.0, il6_baseline))

    # TNF-α: follows IL-1β cascade
    tnfa_baseline = 3.0 + max(0, s.immune.get("il1b", 2.0) - 5.0) * 0.4
    tnfa_baseline = max(1.0, min(100.0, tnfa_baseline))

    # CRP: lags 12-24 hours behind acute cytokines (liver synthesis)
    # Reflects *sustained* IL-6 elevation
    crp_target = 0.5 + max(0, s.immune.get("il6", 3.0) - 10.0) * 0.3
    crp_target = max(0.2, min(200.0, crp_target))

    # IL-10: rises in response to inflammation (counter-regulation)
    il10_baseline = 10.0 + max(0, s.immune.get("il6", 3.0) - 10.0) * 0.8
    il10_baseline = max(5.0, min(80.0, il10_baseline))

    # --- Advance toward baselines ---

    # IL-1β and IL-6: faster (acute phase)
    for key, target, rate in [
        ("il1b",      il1b_baseline, 0.30),
        ("il6",       il6_baseline,  0.25),
        ("tnf_alpha", tnfa_baseline, 0.20),
        ("il10",      il10_baseline, 0.35),
    ]:
        current = s.immune.get(key, 3.0)
        s.immune[key] = max(0.5, current + (target - current) * min(1.0, rate * sim_hours))

    # CRP: very slow (12-24hr half-life)
    crp = s.immune.get("crp", 0.5)
    s.immune["crp"] = max(0.1, crp + (crp_target - crp) * min(1.0, 0.04 * sim_hours))

    # Update derived inflammation_index
    s.immune["inflammation_index"] = compute_inflammation_index(s.immune)

    # --- Apply sickness behavior cascade to first-order chemicals ---
    _apply_sickness_behavior(s, sim_hours)

    # --- Emit events ---
    infl = s.immune["inflammation_index"]
    if infl > 40.0:
        _emit_immune_event(event_bus, s, "inflammation_index", infl)

    return s
```

### Sickness Behavior Cascade

When cytokines are elevated, they produce a coordinated behavioral state:
fatigue, anhedonia, social withdrawal, hypersomnia, and anorexia.

This is not malfunction — it's adaptive. The body is trying to conserve energy for
immune function.

```python
def _apply_sickness_behavior(s: BiologicalState, sim_hours: float) -> None:
    """
    Cytokine-driven effects on first-order chemicals.
    These are *baseline suppression* effects — chemicals are pushed toward lower targets.
    Rates are per sim-hour when above threshold.
    """
    il1b = s.immune.get("il1b", 2.0)
    il6  = s.immune.get("il6", 3.0)
    tnfa = s.immune.get("tnf_alpha", 3.0)

    # IL-1β → serotonin suppression (reduces 5-HT synthesis via IDO enzyme pathway)
    # IDO diverts tryptophan from serotonin synthesis toward kynurenine (neurotoxic)
    if il1b > 8.0:
        serotonin_drain = (il1b - 8.0) * 0.04 * sim_hours
        s.chemicals["serotonin"] = clamp_chemical("serotonin",
            s.chemicals.get("serotonin", 22.0) - serotonin_drain)

    # IL-6 → dopamine suppression (reduces mesolimbic DA → anhedonia)
    if il6 > 15.0:
        dopamine_drain = (il6 - 15.0) * 0.08 * sim_hours
        s.chemicals["dopamine"] = clamp_chemical("dopamine",
            s.chemicals.get("dopamine", 80.0) - dopamine_drain)

    # TNF-α → cortisol elevation (HPA activation via TNF receptors)
    if tnfa > 12.0:
        cortisol_boost = (tnfa - 12.0) * 0.3 * sim_hours
        s.chemicals["cortisol"] = clamp_chemical("cortisol",
            s.chemicals.get("cortisol", 250.0) + cortisol_boost)

    # High inflammation → adenosine buildup (hypersomnia)
    infl_index = s.immune.get("inflammation_index", 0.0)
    if infl_index > 40.0:
        adenosine_bonus = (infl_index - 40.0) * 0.015 * sim_hours
        s.body["adenosine"] = min(100.0, s.body.get("adenosine", 25.0) + adenosine_bonus)

    # Sickness behavior → oxytocin reduction (social withdrawal)
    if infl_index > 50.0:
        oxy_drain = (infl_index - 50.0) * 0.02 * sim_hours
        s.chemicals["oxytocin"] = clamp_chemical("oxytocin",
            s.chemicals.get("oxytocin", 4.0) - oxy_drain)
```

### Triggers for Immune Activation

The encoder adds immune deltas for events like:
- User mentions Mina is sick: `il1b += 15.0, il6 += 20.0`
- Physical injury event: `il1b += 8.0, substance_p += 40.0`
- Mina's autonomous actions: staying up all night → adenosine buildup naturally drives IL-1β

---

## II. Pain System

### Architecture

```
Noxious stimulus (encoder event / injury)
    │
    ▼
Substance P release (pg/mL CSF)
    │
    ├─► PGE2 synthesis (peripheral sensitization)
    │
    ▼
Spinal cord transmission
    │  Gate: endorphins, GABA, attention
    │
    ▼
Pain intensity signal (0-100 AU)
    │
    ├─► Cortisol spike (HPA response to pain)
    ├─► Norepinephrine spike (sympathetic arousal)
    ├─► Endorphin release (natural opioid response)
    └─► Central sensitization accumulation (chronic pain)
```

### Substance P

Substance P is a neuropeptide released by nociceptors (pain-sensing neurons) in response
to tissue damage, inflammation, or intense stimulation. It's the primary pain signal
carried from periphery to spinal cord.

| Property | Value |
|----------|-------|
| Unit | pg/mL (CSF proxy) |
| Normal range | 20–60 pg/mL |
| Acute pain | 100–300 pg/mL |
| Chronic pain | chronically elevated >80 pg/mL |

```python
def _substance_p_baseline_fn(hour: float, ctx: dict) -> float:
    """
    Substance P baseline: low at rest, elevated by inflammation and cortisol.
    Endorphins suppress Substance P release (opioid gate control).
    """
    base = 30.0
    # Inflammation sensitizes nociceptors
    base += ctx.get("il1b", 2.0) * 0.8
    base += ctx.get("pge2", 80.0) * 0.05
    # Endorphins suppress (pre-synaptic inhibition)
    base -= max(0, ctx.get("endorphins", 12.0) - 12.0) * 0.3
    # High cortisol (chronic) sensitizes pain pathways
    if ctx.get("cortisol", 250.0) > 500.0:
        base += (ctx["cortisol"] - 500.0) * 0.02
    return max(10.0, base)
```

### Prostaglandin E2 (PGE2)

PGE2 is produced at sites of tissue damage by cyclooxygenase (COX) enzymes. It sensitizes
nociceptors — making them fire more easily. This is **peripheral sensitization**: why a
bruised area hurts even from light touch.

NSAIDs (aspirin, ibuprofen) work by blocking COX → reducing PGE2 → reducing sensitization.

| Property | Value |
|----------|-------|
| Unit | pg/mL |
| Normal range | 50–200 pg/mL |
| Active inflammation | 300–1000+ pg/mL |

```python
def _pge2_baseline_fn(hour: float, ctx: dict) -> float:
    """PGE2 rises with inflammation and tissue damage."""
    base = 80.0
    # Driven by IL-1β and TNF-α (COX-2 induction)
    base += max(0, ctx.get("il1b",  2.0) -  2.0) * 5.0
    base += max(0, ctx.get("tnf_alpha", 3.0) - 3.0) * 4.0
    # PGE2 is self-amplifying (COX-2 is upregulated by PGE2)
    base += max(0, ctx.get("pge2", 80.0) - 200.0) * 0.1
    return max(40.0, min(2000.0, base))
```

### Central Sensitization

After prolonged or severe pain, the spinal cord and brain become sensitized — neurons
wire together for pain processing, lowering the threshold for everything.

This is the mechanism behind:
- Fibromyalgia (whole-body pain sensitivity)
- Chronic migraine (each episode sensitizes the next)
- Post-injury allodynia (light touch becomes painful)

```python
def _advance_central_sensitization(s: BiologicalState, sim_hours: float) -> BiologicalState:
    """
    Central sensitization builds slowly with sustained pain and inflammation.
    Decays very slowly (weeks-months in real life).
    """
    cs = s.pain.get("central_sensitization", 0.0)
    pain_int = s.pain.get("pain_intensity", 0.0)
    sub_p = s.pain.get("substance_p", 30.0)

    # Build rate: proportional to sustained pain above threshold
    if pain_int > 40.0 and sub_p > 80.0:
        build_rate = (pain_int - 40.0) * 0.02  # very slow
        cs = min(100.0, cs + build_rate * sim_hours)
    else:
        # Decay even slower (central sensitization is persistent)
        cs = max(0.0, cs - 0.05 * sim_hours)

    s.pain["central_sensitization"] = round(cs, 3)

    # Central sensitization lowers pain threshold
    # Modeled as: effective substance_p multiplier
    # When cs=50: substance_p appears 50% higher to the pain intensity formula
    return s
```

### Pain Intensity Computation

Pain intensity is not stored but recomputed each tick from the upstream signals:

```python
def compute_pain_intensity(s: BiologicalState) -> float:
    """
    Compute current subjective pain intensity (0-100 AU).

    Inputs:
    - substance_p: pain signal amplitude
    - pge2: peripheral sensitization factor
    - central_sensitization: CS multiplier
    - endorphins: opioid gate control (reduces)
    - anandamide: CB1 gate control (reduces)
    - gaba: spinal inhibitory gate (reduces)
    - attention/cognitive load: captured via cortisol and norepinephrine
    """
    sub_p = s.pain.get("substance_p", 30.0)
    pge2  = s.pain.get("pge2", 80.0)
    cs    = s.pain.get("central_sensitization", 0.0)

    # Raw pain signal: normalized from substance P range
    # substance_p 30 pg/mL → 0 pain; 300 pg/mL → ~80 pain
    raw_pain = max(0.0, (sub_p - 30.0) / 3.0)

    # Peripheral sensitization multiplier (PGE2)
    pge2_factor = 1.0 + max(0, pge2 - 200.0) / 1000.0  # PGE2 >200 amplifies pain

    # Central sensitization adds baseline pain and amplifies signals
    cs_factor = 1.0 + cs * 0.015  # CS 50 → 1.75× amplification
    cs_offset = cs * 0.3          # CS 50 → +15 baseline pain

    raw_pain = raw_pain * pge2_factor * cs_factor + cs_offset

    # Gate control: opioid/endocannabinoid/GABA suppression
    endorphins = s.chemicals.get("endorphins", 12.0)
    anandamide = s.body.get("anandamide", 1.5)
    gaba = s.chemicals.get("gaba", 3.0)

    endorphin_gate = max(0.0, endorphins - 12.0) * 0.5   # above baseline → gate closes
    endo_gate      = max(0.0, anandamide - 1.5) * 2.0
    gaba_gate      = max(0.0, gaba - 2.0) * 1.5

    total_gate = endorphin_gate + endo_gate + gaba_gate
    gated_pain = max(0.0, raw_pain - total_gate)

    # Attention gate: high cortisol/stress amplifies perceived pain
    # (hypervigilance — anxiety makes pain worse)
    cortisol = s.chemicals.get("cortisol", 250.0)
    attention_factor = 1.0 + max(0, cortisol - 400.0) * 0.0005

    return min(100.0, round(gated_pain * attention_factor, 2))
```

### Pain → Systemic Effects

Pain intensity feeds back into the rest of the system:

```python
def _apply_pain_effects(s: BiologicalState, sim_hours: float) -> BiologicalState:
    """
    Pain's downstream effects on physiology.
    """
    pain_int = s.pain.get("pain_intensity", 0.0)

    if pain_int > 20.0:
        # Cortisol spike (HPA response to pain — fight-or-flight)
        cortisol_bonus = (pain_int - 20.0) * 0.4 * sim_hours
        s.chemicals["cortisol"] = clamp_chemical("cortisol",
            s.chemicals.get("cortisol", 250.0) + cortisol_bonus)

        # Norepinephrine spike (sympathetic arousal)
        norepi_bonus = (pain_int - 20.0) * 0.8 * sim_hours
        s.chemicals["norepinephrine"] = clamp_chemical("norepinephrine",
            s.chemicals.get("norepinephrine", 200.0) + norepi_bonus)

        # Endorphin release (endogenous opioid response — partially closes the gate)
        endorphin_boost = (pain_int - 20.0) * 0.2 * sim_hours
        s.chemicals["endorphins"] = clamp_chemical("endorphins",
            s.chemicals.get("endorphins", 12.0) + endorphin_boost)

    if pain_int > 50.0:
        # Moderate-severe pain → sleep disruption
        adenosine_penalty = (pain_int - 50.0) * 0.01 * sim_hours
        s.body["adenosine"] = min(100.0, s.body.get("adenosine", 25.0) + adenosine_penalty)

        # Dopamine suppression (chronic pain → anhedonia)
        dopamine_drain = (pain_int - 50.0) * 0.05 * sim_hours
        s.chemicals["dopamine"] = clamp_chemical("dopamine",
            s.chemicals.get("dopamine", 80.0) - dopamine_drain)

    return s
```

### Full advance_pain() Orchestration

```python
# src/sim/physio/pain.py

def advance_pain(s: BiologicalState, sim_hours: float, event_bus: EventBus) -> BiologicalState:
    """Advance all pain markers."""
    ctx = _make_pain_ctx(s)

    # Advance Substance P toward baseline
    sub_p = s.pain.get("substance_p", 30.0)
    sub_p_target = _substance_p_baseline_fn(0.0, ctx)
    sub_p_rate = 0.15  # approach rate
    s.pain["substance_p"] = max(10.0, sub_p + (sub_p_target - sub_p) * min(1.0, sub_p_rate * sim_hours))

    # Advance PGE2 toward baseline
    pge2 = s.pain.get("pge2", 80.0)
    pge2_target = _pge2_baseline_fn(0.0, ctx)
    s.pain["pge2"] = max(20.0, pge2 + (pge2_target - pge2) * min(1.0, 0.20 * sim_hours))

    # Advance central sensitization
    s = _advance_central_sensitization(s, sim_hours)

    # Recompute pain intensity
    s.pain["pain_intensity"] = compute_pain_intensity(s)

    # Apply pain effects to systemic chemistry
    s = _apply_pain_effects(s, sim_hours)

    # Emit pain events
    pain_int = s.pain["pain_intensity"]
    if pain_int > 30.0:
        event_bus.emit(BiologicalEvent(
            event_type="threshold_crossed" if pain_int > 50.0 else "spike",
            system="pain",
            chemical="pain_intensity",
            value=pain_int,
            delta=pain_int - ctx.get("prev_pain", 0.0),
            unit="AU",
            label="SEVERE" if pain_int > 70 else "MODERATE",
            label_crossed=pain_int > 50.0,
            severity="significant" if pain_int > 50 else "moderate",
            significance=min(1.0, pain_int / 100.0),
            timestamp=time.time(),
        ))

    return s
```

---

## III. Pain Labels

```python
# In ChemicalProfile for pain_intensity (or as standalone lookup):
PAIN_LABELS = [
    (10.0,  "NONE",        "No pain signal present."),
    (25.0,  "MILD",        "Noticeable discomfort. Background awareness."),
    (45.0,  "MODERATE",    "Distracting. Hard to ignore. Affects mood."),
    (65.0,  "SIGNIFICANT", "Intrusive. Difficult to focus. Sleep disrupted."),
    (80.0,  "SEVERE",      "Dominant. Cannot concentrate. Cortisol elevated."),
    (100.0, "EXTREME",     "All-consuming. Fight-or-flight. Seeking relief."),
]

INFLAMMATION_LABELS = [
    (10.0,  "QUIESCENT",   "Resting immune state. No active inflammation."),
    (25.0,  "MILD",        "Subclinical inflammation. Slightly elevated energy cost."),
    (45.0,  "MODERATE",    "Sickness behavior emerging. Fatigue, mild anhedonia."),
    (65.0,  "ACTIVE",      "Clear sickness state. Social withdrawal, hypersomnia."),
    (85.0,  "SEVERE",      "Significant immune activation. Depression-like symptoms."),
    (100.0, "ACUTE",       "Acute illness. All resources redirected to immune response."),
]
```

---

## IV. Autonomic Nervous System (Basic Model)

The ANS is the bridge between emotion and physical symptoms. It's included in SPEC-23
because pain and immune states heavily interact with it.

### SNS/PNS Balance

Rather than model individual neurons, we track a **vagal tone** value (0-100) that
represents parasympathetic dominance:

| vagal_tone | Meaning |
|-----------|---------|
| 80-100 | High PNS (rest-and-digest, recovery, social) |
| 40-70 | Balanced |
| 20-40 | Moderate SNS dominance (alert, aroused) |
| 0-20 | High SNS dominance (fight-or-flight) |

```python
def compute_vagal_tone(s: BiologicalState) -> float:
    """
    Vagal tone (PNS dominance), 0–100.
    High vagal tone = calm, social, restorative.
    Low vagal tone = stressed, defended, dysregulated.
    """
    cortisol    = s.chemicals.get("cortisol", 250.0)
    norepi      = s.chemicals.get("norepinephrine", 200.0)
    oxytocin    = s.chemicals.get("oxytocin", 4.0)
    gaba        = s.chemicals.get("gaba", 3.0)
    pain_int    = s.pain.get("pain_intensity", 0.0)
    adenosine   = s.body.get("adenosine", 25.0)

    # Start from balanced midpoint
    tone = 55.0

    # SNS suppressors
    tone -= max(0, cortisol - 300.0) * 0.04
    tone -= max(0, norepi - 250.0) * 0.02
    tone -= pain_int * 0.25
    tone -= max(0, adenosine - 50.0) * 0.3  # severe fatigue → ANS dysregulation

    # PNS promoters
    tone += max(0, oxytocin - 4.0) * 0.5  # social safety signal
    tone += max(0, gaba - 2.0) * 3.0      # GABAergic tone is PNS-coupled

    return min(100.0, max(0.0, round(tone, 1)))
```

HRV (heart rate variability) in `vitals.py` is derived from vagal tone:
```python
# HRV (ms RMSSD): high vagal tone → high HRV → healthy
# vagal_tone 100 → HRV ~80ms; vagal_tone 0 → HRV ~10ms
hrv_rmssd = 10.0 + vagal_tone * 0.70
```

---

## Testing Strategy

```python
# tests/sim/physio/test_immune.py

def test_sleep_deprivation_raises_il1b():
    """High adenosine (sleep debt) should increase IL-1β baseline."""
    s = make_state()
    s.body["adenosine"] = 80.0  # exhausted
    s = advance_immune(s, sim_hours=2.0, event_bus=EventBus())
    assert s.immune["il1b"] > 4.0

def test_sickness_behavior_suppresses_serotonin():
    """Elevated IL-1β should drain serotonin."""
    s = make_state()
    s.immune["il1b"] = 20.0
    initial_serotonin = s.chemicals["serotonin"]
    s = advance_immune(s, sim_hours=3.0, event_bus=EventBus())
    assert s.chemicals["serotonin"] < initial_serotonin

def test_inflammation_index_reflects_cytokines():
    """inflammation_index should rise with IL-6 and IL-1β."""
    s = make_state()
    s.immune["il1b"] = 30.0
    s.immune["il6"] = 60.0
    idx = compute_inflammation_index(s.immune)
    assert idx > 40.0

def test_il10_dampens_inflammation_index():
    """High IL-10 (anti-inflammatory) should reduce the index."""
    low_il10 = {"il1b": 20.0, "il6": 40.0, "tnf_alpha": 15.0, "crp": 5.0, "il10": 5.0}
    high_il10 = {**low_il10, "il10": 40.0}
    assert compute_inflammation_index(high_il10) < compute_inflammation_index(low_il10)


# tests/sim/physio/test_pain.py

def test_endorphins_close_pain_gate():
    """High endorphins should reduce computed pain intensity."""
    s = make_state()
    s.pain["substance_p"] = 200.0  # significant pain signal
    s.chemicals["endorphins"] = 12.0   # baseline
    pain_low_endorphins = compute_pain_intensity(s)

    s.chemicals["endorphins"] = 80.0   # high endorphins
    pain_high_endorphins = compute_pain_intensity(s)

    assert pain_high_endorphins < pain_low_endorphins

def test_central_sensitization_amplifies_pain():
    """Central sensitization should make the same substance_p produce more pain."""
    s = make_state()
    s.pain["substance_p"] = 120.0
    s.pain["central_sensitization"] = 0.0
    pain_no_cs = compute_pain_intensity(s)

    s.pain["central_sensitization"] = 60.0
    pain_with_cs = compute_pain_intensity(s)

    assert pain_with_cs > pain_no_cs

def test_pain_causes_cortisol_spike():
    """Moderate-high pain should elevate cortisol."""
    s = make_state(cortisol=250.0)
    s.pain["pain_intensity"] = 60.0
    initial_cortisol = s.chemicals["cortisol"]
    s = _apply_pain_effects(s, sim_hours=1.0)
    assert s.chemicals["cortisol"] > initial_cortisol

def test_pge2_driven_by_inflammation():
    """PGE2 baseline should rise with IL-1β."""
    ctx_low  = {"il1b": 2.0,  "tnf_alpha": 3.0,  "pge2": 80.0}
    ctx_high = {"il1b": 30.0, "tnf_alpha": 20.0, "pge2": 80.0}
    assert _pge2_baseline_fn(0.0, ctx_high) > _pge2_baseline_fn(0.0, ctx_low)
```

---

## Open Questions

- **Histamine and mast cells**: Histamine is released by mast cells during allergic
  responses and injury. It's a pain sensitizer AND a wake-promoting neurotransmitter
  (tuberomammillary nucleus). Should it live in the immune module or the neuro module?
  Decision deferred — add as a `body` dict value in a later minor spec.

- **Prostaglandin inhibition by NSAIDs**: When Mina takes ibuprofen (possible future
  substance), it would reduce PGE2 synthesis. The substance profile would set a
  `pge2_synthesis_multiplier: 0.2` for the drug duration. Architecture supports this
  via the substances system in SPEC-21.

- **Social immunity**: There is emerging evidence that social support reduces
  inflammatory markers directly. High oxytocin → IL-10 increase → inflammation
  reduction. This is captured indirectly (oxytocin reduces cortisol, cortisol
  drives IL-6), but a direct oxytocin → IL-10 interaction is worth adding.
  Add as: `Interaction("oxytocin", "above", 40.0, il10_rate=+0.5)` in a minor update.
