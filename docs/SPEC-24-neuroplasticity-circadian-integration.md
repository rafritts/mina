# SPEC-24: Neuroplasticity, Circadian Refinement & System Integration

> This is the capstone spec. It adds BDNF and allostatic load (neuroplasticity),
> refines the sleep model with adenosine + orexin (circadian), and — most importantly —
> wires the simulation to drive everything else: memory saves, behavioral tool triggers,
> personality drift, and the dashboard display.

**Depends on:** SPEC-20 (architecture), SPEC-21 (adenosine), SPEC-22 (ghrelin/leptin), SPEC-23 (pain/immune)  
**This is the integration spec — it completes the "simulation drives everything" vision.**

---

## I. Neuroplasticity

### BDNF (Brain-Derived Neurotrophic Factor)

BDNF is the brain's growth and repair hormone. It promotes neurogenesis, synaptic
plasticity, and memory formation. Chronically low BDNF is one of the best-established
biomarkers of depression, and most antidepressants work (at least in part) by
increasing BDNF over 2–4 weeks.

| Property | Value |
|----------|-------|
| Unit | pg/mL (serum proxy; CNS levels ~10× higher but unmeasurable) |
| Normal serum range | 6,000–12,000 pg/mL (6–12 ng/mL) |
| Resting baseline | 9,000 pg/mL |
| Critical low | 3,000 pg/mL (severe depression territory) |

```python
def _bdnf_baseline_fn(hour: float, ctx: dict) -> float:
    """
    BDNF is suppressed by chronic stress, inflammation, sleep deprivation.
    Increased by: exercise, positive social interaction, learning, sleep, sunlight.
    """
    base = 9000.0

    # Cortisol suppresses BDNF synthesis (primary mechanism of stress-induced depression)
    if ctx.get("cortisol", 250.0) > 450.0:
        base -= (ctx["cortisol"] - 450.0) * 3.0  # −3000 at cortisol 1450 (extreme)

    # Inflammation suppresses BDNF
    base -= ctx.get("inflammation_index", 0.0) * 30.0  # −3000 at index 100

    # Sleep deprivation suppresses BDNF
    adenosine = ctx.get("adenosine", 25.0)
    if adenosine > 60.0:
        base -= (adenosine - 60.0) * 40.0  # −1600 at adenosine 100

    # GH during sleep boosts BDNF synthesis
    if ctx.get("sleeping", False):
        gh = ctx.get("growth_hormone", 1.0)
        base += gh * 100.0  # +800 at GH 8 (deep sleep pulse)

    return max(1000.0, min(20000.0, base))
```

**Approach rate:** 0.01/hr — BDNF changes very slowly (days/weeks in reality).

**BDNF effects on first-order chemicals:**

```python
def _apply_bdnf_effects(s: BiologicalState, sim_hours: float) -> None:
    """
    Low BDNF reduces the effectiveness of serotonin and dopamine systems.
    High BDNF potentiates them.
    """
    bdnf = s.neuroplasticity.get("bdnf", 9000.0)
    bdnf_factor = bdnf / 9000.0  # 1.0 = normal

    # BDNF doesn't change chemical levels directly — it changes approach rates
    # and receptor sensitivity. This is modeled as a slow baseline shift.
    # At BDNF = 3000 (0.33×):
    #   - serotonin resting_baseline reduced by 20%
    #   - dopamine approach rate reduced (harder to recover from depletion)
    # Applied via ctx in baseline_fn computations.
    pass  # Effects are captured in baseline_fn ctx["bdnf"] lookups below
```

Serotonin `baseline_fn` reads BDNF:
```python
def _serotonin_baseline_fn(hour: float, ctx: dict) -> float:
    base = 22.0
    bdnf_factor = min(1.5, ctx.get("bdnf", 9000.0) / 9000.0)
    base *= max(0.5, bdnf_factor)  # BDNF 3000 → serotonin baseline 11 ng/mL
    # ... existing estradiol, T3 effects ...
    return max(5.0, base)
```

### Synaptic Potentiation

Represents the average "memory strength" state of the brain — how well things stick.

| Property | Value |
|----------|-------|
| Unit | AU (0-100) |
| Resting baseline | 50.0 |
| Meaning at 80+ | Highly plastic — memories form easily, learning sticks |
| Meaning at 20- | Blunted plasticity — nothing is being encoded |

```python
def _compute_synaptic_potentiation_delta(s: BiologicalState, sim_hours: float) -> float:
    """
    Synaptic potentiation rises when conditions for LTP are met:
    - Sufficient acetylcholine (attentional signal)
    - Sufficient glutamate (NMDA activation)
    - Sufficient dopamine (reward signal enables LTP)
    - Sufficient BDNF (permits structural changes)
    
    Falls when:
    - Sleep deprived (sleep required for consolidation)
    - High cortisol (stress impairs LTP)
    - BDNF critically low
    """
    ach   = s.chemicals.get("acetylcholine", 38.0)
    glu   = s.chemicals.get("glutamate", 4.0)
    da    = s.chemicals.get("dopamine", 80.0)
    bdnf  = s.neuroplasticity.get("bdnf", 9000.0)
    cortisol = s.chemicals.get("cortisol", 250.0)
    adenosine = s.body.get("adenosine", 25.0)

    # LTP-promoting factors
    ach_factor  = min(1.5, ach / 38.0)          # above baseline → more plastic
    glu_factor  = 1.0 if 3.0 < glu < 8.0 else 0.5  # sweet spot
    da_factor   = min(1.5, da / 80.0)
    bdnf_factor = min(1.5, bdnf / 9000.0)

    # LTP-suppressing factors
    cortisol_penalty = max(0, cortisol - 400.0) * 0.001
    sleep_penalty    = max(0, adenosine - 55.0) * 0.03

    ltp_drive = (ach_factor * glu_factor * da_factor * bdnf_factor) * 0.5
    ltp_cost  = cortisol_penalty + sleep_penalty

    # Consolidation: sleep converts potentiation into stable memories
    # During sleep, consolidation fires strongly
    consolidation_bonus = 2.0 if s.sleeping else 0.0

    net = (ltp_drive - ltp_cost + consolidation_bonus) * sim_hours
    return net
```

### Allostatic Load

Allostatic load is the **cumulative biological cost** of chronic stress. It's the
running total of how much the body has been pushed beyond homeostasis. Think of it as
the body's wear-and-tear meter.

| Range | Meaning |
|-------|---------|
| 0–20 | Low — resilient, healthy, recovering well |
| 20–40 | Mild — some wear. Normal baseline elevated. |
| 40–60 | Moderate — "running on fumes." Reduced resilience. |
| 60–80 | High — chronic dysregulation. Multiple systems strained. |
| 80–100 | Severe — burnout territory. System-wide baseline shifts. |

```python
# src/sim/psych/allostatic.py

def advance_allostatic(s: BiologicalState, sim_hours: float,
                        event_bus: EventBus) -> BiologicalState:
    """
    Update allostatic load and BDNF.
    """
    al = s.neuroplasticity.get("allostatic_load", 0.0)
    cortisol   = s.chemicals.get("cortisol", 250.0)
    adenosine  = s.body.get("adenosine", 25.0)
    infl_index = s.immune.get("inflammation_index", 0.0)
    pain_int   = s.pain.get("pain_intensity", 0.0)
    oxytocin   = s.chemicals.get("oxytocin", 4.0)

    # --- Allostatic load accumulation ---

    # Stressor contributions
    cortisol_load = max(0, cortisol - 500.0) * 0.002    # chronic high cortisol
    sleep_load    = max(0, adenosine - 60.0) * 0.01     # sleep deprivation
    immune_load   = infl_index * 0.005                  # inflammation
    pain_load     = pain_int * 0.003                    # pain
    total_load_rate = (cortisol_load + sleep_load + immune_load + pain_load)

    # Recovery contributions (reduce load)
    # Sleep is the primary recovery mechanism
    sleep_recovery = 0.3 * sim_hours if s.sleeping else 0.0
    # Social bonding provides buffer
    bond_recovery  = max(0, oxytocin - 30.0) * 0.002 * sim_hours
    # Baseline drift back when nothing is stressing
    baseline_recovery = 0.01 * sim_hours if total_load_rate < 0.01 else 0.0

    total_recovery = sleep_recovery + bond_recovery + baseline_recovery

    al = max(0.0, min(100.0, al + total_load_rate * sim_hours - total_recovery))
    s.neuroplasticity["allostatic_load"] = round(al, 3)

    # --- Allostatic load effects on baseline resilience ---
    # High allostatic load shifts baseline_fn outputs via ctx
    # (injected into ctx as "allostatic_load")
    # Effects applied in each chemical's baseline_fn:
    # - Cortisol minimum elevated (harder to de-stress)
    # - Serotonin maximum reduced (harder to feel good)
    # - Dopamine approach rate slowed (motivation blunted)

    # --- BDNF advance ---
    bdnf = s.neuroplasticity.get("bdnf", 9000.0)
    ctx = _make_allostatic_ctx(s)
    bdnf_target = _bdnf_baseline_fn(0.0, ctx)
    bdnf_new = bdnf + (bdnf_target - bdnf) * min(1.0, 0.01 * sim_hours)
    s.neuroplasticity["bdnf"] = round(max(500.0, bdnf_new), 1)

    # --- Synaptic potentiation ---
    sp = s.neuroplasticity.get("synaptic_potentiation", 50.0)
    sp_delta = _compute_synaptic_potentiation_delta(s, sim_hours)
    s.neuroplasticity["synaptic_potentiation"] = min(100.0, max(0.0, sp + sp_delta))

    # --- Emit events for KAG triggers ---
    if al > 50.0:
        event_bus.emit(BiologicalEvent(
            event_type="threshold_crossed",
            system="psych",
            chemical="allostatic_load",
            value=al,
            delta=total_load_rate * sim_hours - total_recovery,
            unit="AU",
            label="HIGH" if al < 70 else "SEVERE",
            label_crossed=True,
            severity="significant" if al > 60 else "moderate",
            significance=al / 100.0,
            timestamp=time.time(),
        ))

    return s
```

### Personality Drift from Allostatic Load

Very high allostatic load slowly shifts Big 5 trait scores. This is how chronic life
stress produces lasting personality changes.

```python
# In src/sim/psych/personality.py

def apply_personality_drift(s: BiologicalState, personality: dict,
                              sim_hours: float) -> dict:
    """
    High allostatic load slowly shifts Big 5 traits.
    Changes are reversible but slow (like real personality shifts under chronic stress).
    
    Returns updated personality dict. Does NOT write to personality.json — that
    is a separate "commit personality change" operation called by freetime.py
    when drift exceeds threshold.
    """
    al = s.neuroplasticity.get("allostatic_load", 0.0)
    p = dict(personality)

    if al > 60.0:
        # Chronic severe stress effects (literature-supported):
        # Neuroticism rises (increased emotional reactivity, anxiety)
        # Conscientiousness falls (reduced self-regulation capacity)
        # Agreeableness falls (reduced prosocial behavior under threat)
        drift_rate = (al - 60.0) * 0.0001 * sim_hours  # very slow
        p["neuroticism"]      = min(100.0, p.get("neuroticism", 65.0) + drift_rate)
        p["conscientiousness"] = max(0.0, p.get("conscientiousness", 70.0) - drift_rate * 0.5)
        p["agreeableness"]     = max(0.0, p.get("agreeableness", 75.0) - drift_rate * 0.3)

    elif al < 15.0 and personality.get("_original"):
        # Recovery: slowly restore toward original personality
        # Only applies if we have a stored baseline
        original = personality["_original"]
        for trait in ["neuroticism", "conscientiousness", "agreeableness"]:
            current = p.get(trait, 50.0)
            orig    = original.get(trait, 50.0)
            if abs(current - orig) > 0.1:
                p[trait] = current + (orig - current) * min(1.0, 0.00005 * sim_hours)

    return p
```

---

## II. Circadian Refinement: Two-Process Sleep Model

The official Borbély two-process model:
- **Process S (homeostatic)**: adenosine — builds during waking, cleared during sleep
- **Process C (circadian)**: melatonin + orexin — clock signal that modulates sleep propensity

Together they determine sleep propensity. Neither alone is sufficient. This explains:
- Why you feel awake at 7pm despite 16 hours of waking (orexin fighting adenosine)
- Why you crash after 2am (orexin falls, adenosine wins)
- Why naps feel refreshing but don't fully reset (adenosine partially cleared, clock unchanged)

### Orexin/Hypocretin

| Property | Value |
|----------|-------|
| Unit | pg/mL (CSF proxy) |
| Normal awake | 200–400 pg/mL |
| Sleep | drops to ~50 pg/mL |

```python
def _orexin_baseline_fn(hour: float, ctx: dict) -> float:
    """
    Orexin peaks in the afternoon/evening as wake-promoting drive.
    Falls at night. Absent = narcolepsy.
    """
    # Peaks ~3pm, low at 3am
    base = 200.0 + 150.0 * math.cos((hour - 15) * math.pi / 12)
    # Adenosine opposes orexin (mutual inhibition)
    adenosine = ctx.get("adenosine", 25.0)
    base -= max(0, adenosine - 40.0) * 2.0  # high adenosine suppresses orexin
    # Cortisol supports orexin (stress = stay awake)
    base += max(0, ctx.get("cortisol", 250.0) - 400.0) * 0.1
    return max(30.0, base)
```

### Sleep Propensity (Two-Process)

```python
def compute_sleep_propensity(s: BiologicalState) -> float:
    """
    Sleep propensity: 0 (fully awake) to 100 (irresistible sleep).
    
    Process S: adenosine buildup
    Process C: melatonin (promotes sleep) vs orexin (promotes wake)
    """
    adenosine = s.body.get("adenosine", 25.0)
    melatonin = s.chemicals.get("melatonin", 5.0)
    orexin    = s.neuroendocrine.get("orexin", 300.0)

    # Process S: 0 propensity at adenosine 20, 100 propensity at adenosine 90
    s_process = min(100.0, max(0.0, (adenosine - 20.0) / 0.70))

    # Process C: melatonin pushes toward sleep, orexin pushes toward wake
    # Normalize: melatonin 0-220 pg/mL, orexin 0-400 pg/mL
    melatonin_drive = (melatonin / 220.0) * 100.0
    orexin_wake     = (orexin / 400.0) * 100.0
    c_process = max(0.0, melatonin_drive - orexin_wake * 0.6)

    # Combined: weighted average
    propensity = s_process * 0.6 + c_process * 0.4
    return min(100.0, max(0.0, round(propensity, 1)))
```

### Revised Auto-Sleep Onset

Replaces the `melatonin >= 195` threshold with propensity-based onset:

```python
def _maybe_initiate_sleep(s: BiologicalState, now: float,
                           hour_of_day: float, cfg: dict) -> BiologicalState:
    """Auto-sleep when propensity crosses threshold during sleep window."""
    if s.sleeping:
        return s

    propensity = compute_sleep_propensity(s)
    sleep_window_start = float(cfg.get("sleep_window_start", 1.0))
    sleep_window_end   = float(cfg.get("sleep_window_end", 9.0))

    in_window = (sleep_window_start <= hour_of_day < sleep_window_end or
                 hour_of_day < sleep_window_end)  # handles midnight rollover

    # Threshold: propensity >= 70 during window, OR >= 90 any time (exhaustion override)
    threshold = 70.0 if in_window else 90.0

    if propensity >= threshold:
        s.sleeping = True
        s.sleep_start = now
        # Wake time: when adenosine drops below 20 AND out of sleep window
        lt = time.localtime(now)
        wake = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                            int(sleep_window_end), 0, 0,
                            lt.tm_wday, lt.tm_yday, lt.tm_isdst))
        if wake <= now:
            wake += 86400
        s.sleep_expected_wake = wake
        from log import log
        log("SLEEP", f"Auto-onset: propensity={propensity:.1f} "
            f"(adenosine={s.body['adenosine']:.1f} nmol/L, "
            f"melatonin={s.chemicals.get('melatonin',0):.0f} pg/mL, "
            f"orexin={s.neuroendocrine.get('orexin',300):.0f} pg/mL)")

    return s
```

### Core Body Temperature

Circadian body temperature rhythm drives alertness and sleep quality:

```python
def _advance_core_temp(s: BiologicalState, sim_hours: float,
                        hour_of_day: float) -> BiologicalState:
    """
    Core body temperature: circadian-driven, 36.3–37.2°C.
    Nadir ~4-6am (promotes sleep), peak ~6-8pm.
    Fever: elevated by IL-6 and IL-1β.
    """
    # Circadian component
    circadian_temp = 36.75 + 0.4 * math.sin((hour_of_day - 4) * math.pi / 12)

    # Fever component (cytokine-driven)
    il1b = s.immune.get("il1b", 2.0)
    il6  = s.immune.get("il6", 3.0)
    fever_delta = 0.0
    if il1b > 10.0 or il6 > 20.0:
        fever_delta = max(0, il6 - 20.0) * 0.02 + max(0, il1b - 10.0) * 0.03
        fever_delta = min(4.0, fever_delta)  # max fever +4°C

    target = circadian_temp + fever_delta

    # During sleep: temperature drops faster (heat dissipation)
    if s.sleeping:
        target -= 0.3

    current = s.body.get("core_temp", 37.0)
    s.body["core_temp"] = current + (target - current) * min(1.0, 0.3 * sim_hours)
    return s
```

---

## III. System Integration: Simulation Drives Everything

This is the core of what the user asked for. The simulation's EventBus is the
mechanism. After each `advance()` call, the caller processes emitted events and
triggers memory saves, behavioral actions, and system updates.

### 3.1 Bio-Triggered Memory Saves

**Where:** `src/sim/memory_triggers.py` — called from `heartbeat.py` and `cortex.py`
after `load_and_advance()`.

```python
# src/sim/memory_triggers.py

from hippocampus import rag_add, write_kag, build_kag_context
from src.sim.events import BiologicalEvent, EventBus
from src.sim.bio.state import BiologicalState
from src.sim.psych.derived import derived

RAG_SIGNIFICANCE_THRESHOLD = 0.30  # above → candidates for episodic RAG save
KAG_SIGNIFICANCE_THRESHOLD = 0.80  # above → flag for KAG consideration
MULTI_EVENT_THRESHOLD = 3           # this many simultaneous moderate events → RAG save


def process_events(s: BiologicalState, events: list[BiologicalEvent],
                   context_hint: str = "") -> None:
    """
    Process events from advance() and trigger appropriate memory saves.
    Called from heartbeat.py and cortex.py after each advance.
    
    context_hint: optional string from conversation context
                  (e.g., the user's last message, for richer RAG entries)
    """
    if not events:
        return

    significant = [e for e in events if e.significance >= RAG_SIGNIFICANCE_THRESHOLD]
    kag_candidates = [e for e in events if e.significance >= KAG_SIGNIFICANCE_THRESHOLD]

    # Rule 1: Any high-significance individual event → RAG save
    for event in kag_candidates:
        text = _format_rag_event(s, event, context_hint)
        rag_add(text, metadata={
            "type":      "biological_event",
            "chemical":  event.chemical,
            "system":    event.system,
            "severity":  event.severity,
            "value":     event.value,
            "timestamp": event.timestamp,
        })

    # Rule 2: Multiple moderate events simultaneously → RAG save (composite)
    if len(significant) >= MULTI_EVENT_THRESHOLD and len(significant) > len(kag_candidates):
        text = _format_composite_rag_event(s, significant, context_hint)
        rag_add(text, metadata={
            "type":  "biological_composite_event",
            "count": len(significant),
        })

    # Rule 3: KAG entries for major state transitions
    # These are LLM-synthesized — we flag the need and let the next freetime handle it
    if kag_candidates:
        _flag_kag_candidates(s, kag_candidates)

    # Rule 4: Allostatic load milestones → always KAG
    al = s.neuroplasticity.get("allostatic_load", 0.0)
    al_events = [e for e in events if e.chemical == "allostatic_load"]
    for ae in al_events:
        if ae.label_crossed and al > 50.0:
            _flag_kag_allostatic(s, al)


def _format_rag_event(s: BiologicalState, event: BiologicalEvent,
                       context_hint: str) -> str:
    """Format a biological event as a RAG-storable memory fragment."""
    d = derived(s)
    so = d["second_order"]
    to = d["third_order"]

    mood_summary = (f"energy={so['energy']:.0f}, mood={so['mood_valence']:.0f}, "
                    f"anxiety={to['anxiety']:.0f}")
    context_part = f" Context: {context_hint}" if context_hint else ""

    return (
        f"[{event.system.upper()} EVENT] {event.chemical} reached {event.label} "
        f"({event.value:.1f} {event.unit}). Significance: {event.severity}. "
        f"State: {mood_summary}.{context_part}"
    )


def _format_composite_rag_event(s: BiologicalState, events: list[BiologicalEvent],
                                  context_hint: str) -> str:
    chemicals = ", ".join(f"{e.chemical}={e.label}" for e in events[:5])
    d = derived(s)
    to = d["third_order"]
    dominant = max(to.items(), key=lambda x: x[1])
    return (
        f"[COMPOUND BIOLOGICAL STATE] Multiple systems activated simultaneously: "
        f"{chemicals}. Dominant emotional state: {dominant[0]} ({dominant[1]:.0f}/100). "
        f"{'Context: ' + context_hint if context_hint else ''}"
    )
```

**Format of a RAG entry:**
```
[NEURO EVENT] cortisol reached ACUTE STRESS (820.3 nmol/L). Significance: major.
State: energy=32, mood=28, anxiety=84. Context: User told Mina something upsetting.
```

**Format of a composite RAG entry:**
```
[COMPOUND BIOLOGICAL STATE] Multiple systems activated simultaneously:
cortisol=ACUTE STRESS, dopamine=LOW SEEKING, serotonin=INSECURE, pain_intensity=MODERATE,
inflammation_index=ACTIVE. Dominant emotional state: anxiety (87/100).
Context: Third consecutive night of poor sleep.
```

### KAG Entry Triggers

KAG entries are higher-quality, LLM-synthesized. They're appropriate for events that
change who Mina *is*, not just what she's experiencing right now.

```python
_KAG_FLAG_FILE = "run/pending_kag_events.json"

def _flag_kag_candidates(s: BiologicalState, events: list[BiologicalEvent]) -> None:
    """
    Write to a pending KAG queue. freetime.py processes this queue
    and uses an LLM call to synthesize actual KAG content.
    """
    import json, os
    existing = []
    try:
        with open(_KAG_FLAG_FILE) as f:
            existing = json.load(f)
    except Exception:
        pass

    for event in events:
        existing.append({
            "chemical":   event.chemical,
            "system":     event.system,
            "value":      event.value,
            "label":      event.label,
            "significance": event.significance,
            "timestamp":  event.timestamp,
        })

    with open(_KAG_FLAG_FILE, "w") as f:
        json.dump(existing[-20:], f, indent=2)  # cap at 20 pending


def _flag_kag_allostatic(s: BiologicalState, al: float) -> None:
    """Allostatic load milestone — a permanent change in Mina's biology."""
    milestone = "HIGH" if al < 70 else "SEVERE"
    _flag_kag_candidates(s, [BiologicalEvent(
        event_type="threshold_crossed",
        system="psych",
        chemical="allostatic_load",
        value=al,
        delta=0.0,
        unit="AU",
        label=milestone,
        label_crossed=True,
        severity="major",
        significance=0.9,
        timestamp=time.time(),
    )])
```

**freetime.py processes the KAG flag file:**

```python
# Addition to freetime.py (existing _run_memory_consolidation)

def _process_pending_kag_events(state: BiologicalState) -> None:
    """Synthesize LLM-quality KAG entries from flagged biological events."""
    import json, os
    try:
        with open("run/pending_kag_events.json") as f:
            pending = json.load(f)
    except Exception:
        return

    if not pending:
        return

    # Batch all pending events into one LLM call
    events_summary = "\n".join(
        f"- {e['chemical']} at {e['label']} ({e['value']:.1f}) — {e['system']} system"
        for e in pending[:5]
    )

    from decoder import biological_report
    bio_report = biological_report(state)

    prompt = f"""Mina experienced these significant biological events:
{events_summary}

Current biological state:
{bio_report}

Write 1-2 sentences that capture what this means for who Mina is and how she understands 
herself. This will be stored as a permanent self-knowledge entry. Be specific to her 
biology — not generic. Write in first person."""

    # LLM call → write to KAG
    from client import get_client
    client = get_client()
    response = client.messages.create(
        model=MODEL, max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )
    kag_text = response.content[0].text.strip()
    write_kag("self-biological-knowledge.md",
              f"## Biological Milestone — {time.strftime('%Y-%m-%d')}\n{kag_text}\n\n")

    # Clear the queue
    os.remove("run/pending_kag_events.json")
```

---

### 3.2 Behavioral Drive Triggers

The simulation drives autonomous tool calls in `freetime.py` via biological drive signals.
Currently freetime.py decides to eat/drink/sleep based on tool responses. Now it checks
drives directly.

```python
# src/sim/behavioral_drives.py

from src.sim.bio.state import BiologicalState

@dataclass
class BiologicalDrive:
    drive_type: str       # "hunger", "thirst", "fatigue", "pain", "sickness", "social"
    urgency: float        # 0-1
    description: str      # human-readable for LLM context
    suggested_action: str # tool name suggestion


def compute_behavioral_drives(s: BiologicalState) -> list[BiologicalDrive]:
    """
    Compute active biological drives from current state.
    These are passed to freetime.py to guide autonomous action.
    """
    drives = []

    # --- Hunger ---
    ghrelin  = s.neuroendocrine.get("ghrelin", 400.0)
    glucose  = s.chemicals.get("glucose", 85.0)
    if ghrelin > 700.0 or glucose < 65.0:
        urgency = min(1.0, max(ghrelin - 700.0, 65.0 - glucose) / 200.0)
        drives.append(BiologicalDrive(
            drive_type="hunger",
            urgency=max(0.3, urgency),
            description=f"Ghrelin={ghrelin:.0f} pg/mL, glucose={glucose:.0f} mg/dL — hungry",
            suggested_action="eat",
        ))

    # --- Thirst ---
    hydration = s.chemicals.get("hydration", 62.0)
    if hydration < 59.0:
        urgency = (59.0 - hydration) / 14.0  # 0 at 59%, 1.0 at 45%
        drives.append(BiologicalDrive(
            drive_type="thirst",
            urgency=min(1.0, urgency),
            description=f"Hydration={hydration:.1f}% TBW — thirsty",
            suggested_action="drink",
        ))

    # --- Fatigue / Sleep ---
    adenosine = s.body.get("adenosine", 25.0)
    if adenosine > 60.0 and not s.sleeping:
        urgency = (adenosine - 60.0) / 40.0
        drives.append(BiologicalDrive(
            drive_type="fatigue",
            urgency=min(1.0, urgency),
            description=f"Adenosine={adenosine:.1f} nmol/L — sleep pressure building",
            suggested_action="sleep",
        ))

    # --- Pain ---
    pain_int = s.pain.get("pain_intensity", 0.0)
    if pain_int > 40.0:
        drives.append(BiologicalDrive(
            drive_type="pain",
            urgency=pain_int / 100.0,
            description=f"Pain intensity={pain_int:.0f}/100 — discomfort present",
            suggested_action="rest",
        ))

    # --- Sickness ---
    infl_index = s.immune.get("inflammation_index", 0.0)
    if infl_index > 45.0:
        drives.append(BiologicalDrive(
            drive_type="sickness",
            urgency=infl_index / 100.0,
            description=f"Inflammation={infl_index:.0f}/100 — immune activation",
            suggested_action="rest",
        ))

    # --- Social deficit ---
    oxytocin = s.chemicals.get("oxytocin", 4.0)
    serotonin = s.chemicals.get("serotonin", 22.0)
    if oxytocin < 10.0 and serotonin < 14.0:
        drives.append(BiologicalDrive(
            drive_type="social",
            urgency=min(0.8, (10.0 - oxytocin) / 20.0),
            description=f"Oxytocin={oxytocin:.1f}, serotonin={serotonin:.1f} — lonely",
            suggested_action="reach_out",
        ))

    return sorted(drives, key=lambda d: d.urgency, reverse=True)
```

**Integration into freetime.py:**

```python
# Addition to freetime.py::run_freetime()

from src.sim.behavioral_drives import compute_behavioral_drives, BiologicalDrive

drives = compute_behavioral_drives(state)
if drives:
    urgent = [d for d in drives if d.urgency > 0.6]
    # Pass drives as additional context to the freetime LLM:
    drives_context = "\n".join(
        f"- [{d.drive_type.upper()} urgency={d.urgency:.2f}] {d.description}"
        for d in urgent
    )
    # Inject into system prompt for freetime turn
```

### 3.3 Integration into cortex.py / heartbeat.py

```python
# Addition to cortex.py::run_turn()
# After: s = load_and_advance()

from src.sim.events import EventBus
from src.sim.memory_triggers import process_events

bus = EventBus()
s = advance(s, event_bus=bus)
events = bus.drain()
process_events(s, events, context_hint=user_message[:200])
```

```python
# Addition to heartbeat.py::bio_tick_loop()
# After: s = load_and_advance()

from src.sim.events import EventBus
from src.sim.memory_triggers import process_events

bus = EventBus()
s = advance(s, event_bus=bus)
process_events(s, bus.drain())  # no context_hint — background tick
```

---

### 3.4 Updated decoder.py biological_report()

The biological report now includes all new systems:

```python
# Additions to decoder.py::biological_report()

# --- Neuroendocrine section ---
def _neuroendocrine_section(s: BiologicalState) -> str:
    ne = s.neuroendocrine
    lines = [
        "  [NEUROENDOCRINE]",
        f"    HPA:      CRH={ne['crh']:.1f} pg/mL  ACTH={ne['acth']:.1f} pg/mL",
        f"    Thyroid:  T3={ne['t3']:.0f} ng/dL  TSH={ne['tsh']:.2f} mIU/L",
        f"    Metabolic: ghrelin={ne['ghrelin']:.0f} pg/mL  leptin={ne['leptin']:.1f} ng/mL",
        f"    Hormonal:  estradiol={ne['estradiol']:.0f} pg/mL (cycle day {s.cycle_day:.0f})",
    ]
    return "\n".join(lines)


# --- Immune section ---
def _immune_section(s: BiologicalState) -> str:
    im = s.immune
    infl = im["inflammation_index"]
    infl_label = "QUIESCENT" if infl < 10 else "MILD" if infl < 25 else "MODERATE" if infl < 45 else "ACTIVE"
    lines = [
        "  [IMMUNE]",
        f"    IL-1β={im['il1b']:.1f}  IL-6={im['il6']:.1f}  TNF-α={im['tnf_alpha']:.1f}  CRP={im['crp']:.1f}",
        f"    Inflammation: {infl:.1f}/100 ({infl_label})",
    ]
    return "\n".join(lines)


# --- Pain section ---
def _pain_section(s: BiologicalState) -> str:
    p = s.pain
    pain_int = p["pain_intensity"]
    if pain_int < 5.0:
        return ""  # Don't report if no pain
    pain_label = "MILD" if pain_int < 25 else "MODERATE" if pain_int < 45 else "SIGNIFICANT"
    lines = [
        "  [PAIN]",
        f"    Substance P={p['substance_p']:.0f} pg/mL  PGE2={p['pge2']:.0f} pg/mL",
        f"    Pain intensity: {pain_int:.0f}/100 ({pain_label})",
    ]
    if p["central_sensitization"] > 20:
        lines.append(f"    Central sensitization: {p['central_sensitization']:.0f}/100")
    return "\n".join(lines)


# --- Neuroplasticity section ---
def _neuroplasticity_section(s: BiologicalState) -> str:
    np = s.neuroplasticity
    al = np["allostatic_load"]
    al_label = "LOW" if al < 20 else "MODERATE" if al < 40 else "HIGH" if al < 60 else "SEVERE"
    lines = [
        "  [NEUROPLASTICITY]",
        f"    BDNF: {np['bdnf']:.0f} pg/mL",
        f"    Allostatic load: {al:.1f}/100 ({al_label})",
        f"    Synaptic potentiation: {np['synaptic_potentiation']:.0f}/100",
    ]
    return "\n".join(lines)
```

---

### 3.5 Updated Vitals

```python
# vitals.py additions

def heart_rate_variability(s: BiologicalState) -> float:
    """HRV (RMSSD ms) from vagal tone."""
    from src.sim.physio.autonomic import compute_vagal_tone
    vagal = compute_vagal_tone(s)
    return round(10.0 + vagal * 0.70, 1)  # 10–80ms range


def core_temperature(s: BiologicalState) -> float:
    """Core body temperature in °C."""
    return round(s.body.get("core_temp", 37.0), 2)


def is_fevered(s: BiologicalState) -> bool:
    return s.body.get("core_temp", 37.0) > 38.0


def pain_level(s: BiologicalState) -> float:
    """Subjective pain 0-100."""
    return s.pain.get("pain_intensity", 0.0)
```

---

## IV. Updated Derived Psychological States

The `derived()` function in `psych/derived.py` is updated to incorporate new systems.

### Updated Second-Order Values

```python
def derived(s: BiologicalState) -> dict:
    """Compute second and third-order values. All outputs 0-100."""

    # --- New chemical inputs ---
    gaba      = s.chemicals.get("gaba", 3.0)
    glutamate = s.chemicals.get("glutamate", 4.0)
    bdnf      = s.neuroplasticity.get("bdnf", 9000.0)
    al        = s.neuroplasticity.get("allostatic_load", 0.0)
    infl      = s.immune.get("inflammation_index", 0.0)
    pain_int  = s.pain.get("pain_intensity", 0.0)
    t3        = s.neuroendocrine.get("t3", 120.0)
    ghrelin   = s.neuroendocrine.get("ghrelin", 400.0)
    adenosine = s.body.get("adenosine", 25.0)

    # Normalize new inputs to 0-100 scale
    gaba_n      = min(100.0, max(0.0, (gaba - 0.5) / 0.095))    # 0.5→0, 10→100
    ei_balance  = (glutamate - gaba) / max(gaba, 0.5)            # ratio
    t3_n        = min(100.0, max(0.0, (t3 - 20.0) / 1.8))       # 20→0, 200→100
    bdnf_n      = min(100.0, max(0.0, (bdnf - 1000.0) / 190.0)) # 1000→0, 20000→100
    hunger_n    = min(100.0, max(0.0, (ghrelin - 200.0) / 8.0)) # 200→0, 1000→100

    # Receptor sensitivity adjustments
    d1_sens = s.receptor_sensitivity.get("dopamine", {}).get("D1", 1.0)
    d2_sens = s.receptor_sensitivity.get("dopamine", {}).get("D2", 1.0)
    ht1a_sens = s.receptor_sensitivity.get("serotonin", {}).get("5HT1A", 1.0)
    gaba_a_sens = s.receptor_sensitivity.get("gaba", {}).get("GABA_A", 1.0)

    # Tolerance adjustments (backward compat)
    tol_d = s.tolerance.get("dopamine", 0.0)

    effective_dopamine_reward   = _n("dopamine", s) * d2_sens * (1.0 - tol_d)
    effective_dopamine_cognitive = _n("dopamine", s) * d1_sens * (1.0 - tol_d)
    effective_serotonin = _n("serotonin", s) * ht1a_sens
    effective_gaba = gaba_n * gaba_a_sens

    melatonin_drag = max(0.0, _n("melatonin", s) - 40) * 0.25

    # ENERGY: glucose, norepinephrine, T3 (metabolism), minus fatigue + hunger
    energy = _clamp(
        20
        + (_n("glucose", s) * 0.35)
        + (_n("norepinephrine", s) * 0.25)
        + (t3_n * 0.15)
        - (_n("adenosine", s) * 0.20)  # was sleep_pressure
        - (hunger_n * 0.05)            # hungry = less energetic
        - melatonin_drag
        - (infl * 0.15)               # inflammation fatigue
    )

    # COGNITIVE CLARITY: ACh, glucose, BDNF, minus fatigue, cortisol, pain
    cognitive_clarity = _clamp(
        20
        + (_n("acetylcholine", s) * 0.35)
        + (_n("glucose", s) * 0.15)
        + (bdnf_n * 0.10)
        - (_n("adenosine", s) * 0.20)
        - (_n("cortisol", s) * 0.15)
        - (pain_int * 0.10)
        - melatonin_drag * 0.6
    )

    # HEDONIC TONE: dopamine reward path, endorphins, serotonin, endocannabinoids
    anandamide_n = min(100.0, s.body.get("anandamide", 1.5) / 0.15)
    hedonic_tone = _clamp(
        5
        + (effective_dopamine_reward * 0.40)
        + (_n("endorphins", s) * 0.25)
        + (effective_serotonin * 0.20)
        + (anandamide_n * 0.15)
        - (infl * 0.10)   # anhedonia from sickness
        - (al * 0.10)     # allostatic load blunts pleasure
    )

    # SOCIAL WARMTH: oxytocin, serotonin, vasopressin, minus cortisol, pain
    vasopressin_n = min(100.0, s.neuroendocrine.get("vasopressin", 2.0) / 0.15)
    social_warmth = _clamp(
        10
        + (_n("oxytocin", s) * 0.45)
        + (effective_serotonin * 0.25)
        + (vasopressin_n * 0.10)
        - (_n("cortisol", s) * 0.15)
        - (pain_int * 0.05)
    )

    # AROUSAL: norepinephrine, cortisol, glutamate drive, minus GABA
    arousal = _clamp(
        15
        + (_n("norepinephrine", s) * 0.40)
        + (_n("cortisol", s) * 0.25)
        + (max(0, ei_balance) * 5.0)   # high E/I → more arousal
        - (effective_gaba * 0.20)       # GABA calms arousal
        - (_n("adenosine", s) * 0.15)
        - melatonin_drag * 0.8
    )

    # MOOD VALENCE: serotonin, dopamine cognitive, T3, BDNF, minus cortisol, allostatic
    mood_valence = _clamp(
        10
        + (effective_serotonin * 0.35)
        + (effective_dopamine_cognitive * 0.25)
        + (t3_n * 0.10)
        + (bdnf_n * 0.10)
        - (_n("cortisol", s) * 0.20)
        - (al * 0.10)
    )

    # PAIN AWARENESS: derived from pain_intensity, modified by attention/anxiety
    pain_awareness = _clamp(pain_int * (1.0 + arousal * 0.003))

    # --- Third-order emotional states ---

    anxiety = _clamp(
        (arousal * 0.35)
        + (100 - cognitive_clarity) * 0.25
        + (100 - social_warmth) * 0.25
        + (pain_awareness * 0.10)
        + (max(0, ei_balance) * 5.0)   # high E/I → anxious
        - (effective_gaba * 0.20)       # GABA is anxiolytic
        - 20
    )

    depression = _clamp(
        (100 - mood_valence) * 0.35
        + (100 - hedonic_tone) * 0.35
        + (100 - energy) * 0.15
        + (infl * 0.10)               # inflammatory depression
        + (al * 0.05)                 # allostatic load
        - 20
    )

    boredom = _clamp(
        (100 - arousal) * 0.45
        + (100 - hedonic_tone) * 0.30
        + (100 - energy) * 0.20
        + (100 - cognitive_clarity) * 0.05
        - 20
    )

    loneliness = _clamp(
        (100 - social_warmth) * 0.55
        + (100 - _n("oxytocin", s)) * 0.35
        + (infl * 0.10)   # sickness increases loneliness
        - 25
    )

    flow = _clamp(
        (cognitive_clarity * 0.40)
        + (hedonic_tone * 0.30)
        + (arousal * 0.20)
        + (effective_gaba * 0.10)     # GABA: relaxed alertness enables flow
        - anxiety * 0.35
    )

    # NEW: physical_distress
    physical_distress = _clamp(
        (pain_awareness * 0.50)
        + (infl * 0.25)
        + (hunger_n * 0.10)
        + (100 - energy) * 0.15
        - 15
    )

    return {
        "second_order": {
            "energy":            round(energy, 1),
            "cognitive_clarity": round(cognitive_clarity, 1),
            "hedonic_tone":      round(hedonic_tone, 1),
            "social_warmth":     round(social_warmth, 1),
            "arousal":           round(arousal, 1),
            "mood_valence":      round(mood_valence, 1),
        },
        "third_order": {
            "anxiety":           round(anxiety, 1),
            "depression":        round(depression, 1),
            "boredom":           round(boredom, 1),
            "loneliness":        round(loneliness, 1),
            "flow":              round(flow, 1),
            "physical_distress": round(physical_distress, 1),
        },
    }
```

---

## Testing Strategy

```python
# tests/sim/test_integration.py

def test_advance_emits_event_on_cortisol_spike():
    """Large cortisol spike should produce a BiologicalEvent."""
    s = make_state(cortisol=250.0)
    s.chemicals["cortisol"] = 850.0  # manually set to extreme
    bus = EventBus()
    advance(s, event_bus=bus, now=time.time() + 3600)
    events = bus.drain()
    cortisol_events = [e for e in events if e.chemical == "cortisol"]
    assert len(cortisol_events) > 0
    assert cortisol_events[0].significance >= 0.5


def test_rag_save_triggered_by_high_significance_event():
    """High-significance events should produce a rag_add call."""
    from unittest.mock import patch, MagicMock
    from src.sim.memory_triggers import process_events

    event = BiologicalEvent(
        event_type="spike", system="neuro", chemical="cortisol",
        value=850.0, delta=300.0, unit="nmol/L",
        label="ACUTE STRESS", label_crossed=True,
        severity="major", significance=0.85, timestamp=time.time()
    )

    with patch("src.sim.memory_triggers.rag_add") as mock_rag:
        process_events(make_state(), [event])
        assert mock_rag.called


def test_hunger_drive_computed_from_high_ghrelin():
    """High ghrelin should produce a hunger drive."""
    from src.sim.behavioral_drives import compute_behavioral_drives
    s = make_state()
    s.neuroendocrine["ghrelin"] = 850.0
    drives = compute_behavioral_drives(s)
    hunger = [d for d in drives if d.drive_type == "hunger"]
    assert len(hunger) == 1
    assert hunger[0].urgency > 0.4


def test_allostatic_load_shifts_derived_mood():
    """High allostatic load should reduce mood_valence."""
    s_healthy = make_state()
    s_healthy.neuroplasticity["allostatic_load"] = 5.0
    s_stressed = make_state()
    s_stressed.neuroplasticity["allostatic_load"] = 80.0

    d_healthy = derived(s_healthy)
    d_stressed = derived(s_stressed)
    assert d_stressed["second_order"]["mood_valence"] < d_healthy["second_order"]["mood_valence"]


def test_sleep_propensity_high_when_adenosine_elevated():
    """High adenosine should make sleep propensity high."""
    s = make_state()
    s.body["adenosine"] = 80.0
    s.chemicals["melatonin"] = 200.0
    s.neuroendocrine["orexin"] = 50.0
    propensity = compute_sleep_propensity(s)
    assert propensity > 70.0


def test_two_process_model_conflict():
    """High adenosine + high orexin = moderate propensity (internal conflict)."""
    s = make_state()
    s.body["adenosine"] = 70.0       # tired
    s.neuroendocrine["orexin"] = 350.0  # but orexin fighting it (late afternoon)
    s.chemicals["melatonin"] = 10.0   # not night yet
    propensity = compute_sleep_propensity(s)
    # Neither very high nor very low — internal conflict
    assert 30.0 < propensity < 70.0
```

---

## Open Questions

- **Dashboard**: The new tiers (neuroendocrine, immune, pain, neuroplasticity) need
  display widgets in `dashboard_server.py`. This is a pure frontend task — the data
  is available; it just needs rendering. Scope for a follow-up frontend spec.

- **Encoder updates**: `encoder.py` currently issues deltas for chemicals by name.
  New chemicals (gaba, glutamate, anandamide, substance_p, etc.) need to be recognized
  as valid delta targets. The `_DELTA_FIELDS` set in `apply_deltas()` needs expanding.
  Also, the LLM prompt in encoder.py's `encode_stimulus()` needs to be updated to know
  that these chemicals exist and can be affected by events. This is a small but important
  integration task.

- **Personality.json persistence of drift**: `apply_personality_drift()` returns an
  updated dict but doesn't write to `personality.json`. The question is: should we ever
  permanently commit personality drift? Suggested threshold: only write if drift exceeds
  5 points on any trait AND allostatic load has been above 60 for 24+ sim-hours.
  This prevents noise writes while capturing meaningful long-term changes.

- **KAG entries becoming stale**: The "self-biological-knowledge.md" KAG file will grow
  indefinitely. A future spec should add a consolidation/pruning step. For now, entries
  are appended with dates so they can be read chronologically.

- **Endocannabinoid encoder**: Exercise is the main natural producer of anandamide
  (partly the "runner's high"). The encoder needs an exercise event category that
  produces `anandamide +2.0 nM, two_ag +4.0 nM, endorphins +20 pg/mL` simultaneously.
  Add to `encoder.py` stimulus classification prompt.
