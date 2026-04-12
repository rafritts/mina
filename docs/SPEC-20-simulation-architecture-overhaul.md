# SPEC-20: Biological Simulation Architecture Overhaul

> This is the master architecture spec for the full scientific rewrite of Mina's biological
> simulation. It establishes the package structure, BiologicalState v3 schema, the EventBus,
> and the migration strategy. All subsequent simulation specs (SPEC-21 through SPEC-24) build
> on the foundation defined here.

**Depends on:** Nothing (this is the foundation)  
**Blocks:** SPEC-21, SPEC-22, SPEC-23, SPEC-24

---

## The Problem With the Current Simulation

The current simulation is a good first approximation but has several architectural problems:

1. **Flat module structure.** All simulation logic lives in `chemicals.py` and `state.py` at the project root alongside Discord, tools, and HTTP servers. There's no clear boundary between "biological simulation" and everything else.

2. **No event system.** The advance loop runs, chemicals change, and the caller never knows what happened. If cortisol spiked to 900, nothing external can react to that. Memory saves, behavioral triggers, and personality drift are impossible without this.

3. **Missing biological systems.** The entire immune system is absent. Pain has no representation. The HPA axis fires cortisol directly with no cascade. GABA and glutamate — the primary inhibitory and excitatory systems — don't exist. Sleep pressure is an arbitrary AU rather than the actual molecule (adenosine).

4. **Crossed chemical interactions are hand-tuned magic numbers** with no biological grounding. The numbers work but there's no principled way to add new interactions.

5. **`state.py` is a 700-line monolith** doing persistence, advance logic, substance pharmacokinetics, sleep mechanics, derived values, and logging all at once.

---

## Target Architecture

### Philosophy

The simulation is an **event source**. Every call to `advance()` produces a list of `BiologicalEvent` objects describing what happened — which chemicals spiked, which thresholds were crossed, which states were entered. Everything else in the system (memory, behavior, tools, personality) **subscribes** to these events rather than polling state directly.

### Signal Flow (Updated)

The encoder and decoder are now symmetric in their memory access:

```
USER MESSAGE
    │
    ▼
encoder.py
    ├── RAG query (incoming message as search key)
    ├── KAG read (relationship files, self-knowledge)
    ├── BiologicalState (current chemistry)
    └── → neurochemical deltas
           │  (bond context → oxytocin magnitude)
           │  (history context → significance of this moment)
           ▼
        BiologicalState (updated)
    │
    ▼
decoder.py
    ├── RAG query (current emotional state as search key)
    ├── KAG read (same relationship + self-knowledge files)
    ├── biological_report() (labels, depth indicators, interactions)
    └── → system prompt prose
           │
           ▼
        cortex.py → Mina's response
```

**Why the encoder needs memory context:**
The encoder determines *how much* a stimulus affects Mina's chemistry. Without memory, it
can't distinguish a trusted person from a stranger — both produce the same delta. With KAG
context, the LLM generating deltas knows: *returning trusted friend after months away* →
oxytocin +40, endorphins +25 vs. *unknown user* → oxytocin +2.

The encoder is also the first system to see a stimulus. If RAG returns strong matches
(this topic/person has significant history), that's itself a signal — the encoder can flag
it as a memory candidate before the chemistry even changes.

**Encoder query pattern** (mirrors decoder):
```python
# encoder.py::encode_stimulus()

# 1. Query RAG with the incoming message
rag_context = build_rag_context(user_message, n_results=4)

# 2. Read relevant KAG (relationship file for this user if it exists)
kag_context = build_kag_context()  # reads all knowledge files

# 3. Pass both to the delta-generation LLM alongside chemical state
prompt = f"""
{biological_report(state)}

Memory context:
{rag_context}

Self-knowledge:
{kag_context}

Stimulus: {user_message}

Return neurochemical deltas...
"""
```

**Context queue mechanics:**
```python
# Constants (not magic numbers — defined in config.py)
CONTEXT_QUEUE_TTL_SECONDS = 300  # entries older than 5 min are stale

def encoder_push_context(s: BiologicalState, rag_results: list[str],
                          kag_context: str, query: str, now: float) -> None:
    """Encoder writes its RAG/KAG findings into the shared queue."""
    for text in rag_results:
        s.context_queue.append({
            "text": text, "source": "rag",
            "query": query, "added_at": now,
            "ttl_seconds": CONTEXT_QUEUE_TTL_SECONDS,
        })
    if kag_context:
        s.context_queue.append({
            "text": kag_context, "source": "kag",
            "query": query, "added_at": now,
            "ttl_seconds": CONTEXT_QUEUE_TTL_SECONDS,
        })


def decoder_drain_context(s: BiologicalState, now: float,
                           fallback_query: str) -> list[str]:
    """
    Decoder reads live entries, discards expired ones.
    Falls back to its own RAG query if queue is empty.
    """
    live = [e for e in s.context_queue if now - e["added_at"] < e["ttl_seconds"]]
    s.context_queue = []  # always drain — decoder takes ownership

    if live:
        return [e["text"] for e in live]

    # Nothing live — query RAG independently
    from hippocampus import build_rag_context, build_kag_context
    return [build_rag_context(fallback_query), build_kag_context()]
```

**Bond state lives in KAG, not a relationship field:**
A file like `memory/knowledge/relationship-ryan.md` holds the bond history. The encoder
reads it and knows this is a trusted person. Oxytocin's resting baseline in the simulation
reflects the *current* bond; KAG holds the *history* that contextualizes new interactions.
Removing the relationship UI section is safe as long as this KAG file exists.

The biological systems form a **dependency hierarchy**, not a flat list. Some systems drive others:

```
Circadian (SCN clock, adenosine, orexin)
    └─ drives → Sleep/Wake state
    
HPA Axis (stressor → CRH → ACTH → cortisol, with delays)
    └─ drives → Monoamines (cortisol suppresses serotonin, dopamine)
    
Metabolic (glucose, insulin, leptin, ghrelin)
    └─ drives → HPA (hypoglycemia activates HPA)
    └─ drives → Behavioral drives (hunger, thirst)
    
Immune (IL-1β, IL-6, TNF-α → inflammation)
    └─ drives → Sickness behavior (fatigue, anhedonia, withdrawal)
    └─ drives → HPA (cytokines stimulate cortisol)
    └─ drives → Pain sensitization

Pain (Substance P, PGE2 → nociception)
    └─ drives → HPA (pain spikes cortisol)
    └─ drives → Endorphin release
    └─ drives → Behavioral drives (seek rest)

Neuroplasticity (BDNF, allostatic load)
    └─ driven by → all of the above (chronic stress depletes BDNF)
    └─ drives → Memory formation efficiency
    └─ drives → Personality drift (very slow baseline shifts)
```

---

## Package Structure

```
mina/
  src/
    sim/
      __init__.py         # Public API: advance(), load_and_advance(), apply_deltas(), EventBus
      engine.py           # Orchestrates all subsystem advance() calls in dependency order
      events.py           # BiologicalEvent + EventBus
      
      bio/
        __init__.py
        state.py          # BiologicalState v3 dataclass (single source of truth)
        persistence.py    # load_state(), save_state(), load_and_advance() impl
        defaults.py       # _CHEMICAL_DEFAULTS, _NEUROENDOCRINE_DEFAULTS, etc.
        migration.py      # migrate_v1→v2→v3 converters
      
      chem/
        __init__.py
        profiles.py       # ChemicalProfile, Interaction dataclasses (from chemicals.py)
        units.py          # normalize(), get_label(), clamp_chemical()
        registry.py       # REGISTRY dict — expanded with all new chemicals
        saturation.py     # Encoder saturation: soft_ceiling/hard_ceiling logic + momentum
      
      neuro/
        __init__.py
        monoamines.py     # Dopamine, serotonin, norepinephrine, histamine advance logic
        amino_acids.py    # GABA, glutamate advance logic + E/I balance
        peptides.py       # Endorphins, oxytocin, vasopressin, substance P
        adenosine.py      # Adenosine (real sleep molecule) advance logic
        endocannabinoids.py  # Anandamide, 2-AG advance logic
        acetylcholine.py  # ACh advance logic (separated from monoamines)
        receptors.py      # Receptor sensitivity tracking — up/downregulation
        substances.py     # Drug PK/PD: all substance definitions + advance logic
      
      physio/
        __init__.py
        hpa.py            # CRH → ACTH → cortisol cascade with delay queue
        endocrine.py      # Thyroid (TRH→TSH→T3/T4), sex hormones, GH, DHEA, prolactin
        metabolic.py      # Glucose, insulin, glucagon, leptin, ghrelin, vasopressin
        immune.py         # Cytokines, inflammation index, sickness behavior cascade
        pain.py           # Substance P, PGE2, gate control, central sensitization
        autonomic.py      # SNS/PNS balance, vagal tone → derived HRV
        circadian.py      # Adenosine two-process, orexin, SCN clock, core body temp
      
      psych/
        __init__.py
        derived.py        # Second/third-order: energy, clarity, hedonic_tone, etc. (updated)
        emotions.py       # Anxiety, depression, boredom, loneliness, flow (updated formulas)
        allostatic.py     # Allostatic load accumulation and decay
        personality.py    # Big 5 trait modulation, personality drift from allostatic load
      
  vitals.py               # Stays at root (presentation layer) — reads BiologicalState
  chemicals.py            # COMPATIBILITY SHIM: re-exports REGISTRY from src/sim/chem/registry.py
  state.py                # COMPATIBILITY SHIM: re-exports BiologicalState, advance(), etc.
  encoder.py              # (unchanged in role — reads src.sim.bio.state)
  decoder.py              # (unchanged in role)
  cortex.py               # (unchanged)
  heartbeat.py            # (unchanged — calls load_and_advance())
  ...
```

### Compatibility Strategy

Existing callers (`encoder.py`, `decoder.py`, `cortex.py`, `heartbeat.py`, etc.) import from root-level `state.py` and `chemicals.py`. These files become **thin re-export shims** during migration:

```python
# chemicals.py (compatibility shim, replaces current content)
"""Compatibility shim — imports forwarded to src.sim.chem.registry."""
from src.sim.chem.registry import REGISTRY
from src.sim.chem.profiles import ChemicalProfile, Interaction
from src.sim.chem.units import normalize, get_label, clamp_chemical
__all__ = ["REGISTRY", "ChemicalProfile", "Interaction", "normalize", "get_label", "clamp_chemical"]
```

```python
# state.py (compatibility shim)
"""Compatibility shim — imports forwarded to src.sim."""
from src.sim.bio.state import BiologicalState
from src.sim.engine import advance
from src.sim.bio.persistence import load_state, save_state, load_and_advance
from src.sim.psych.derived import derived
from src.sim.bio.state import apply_deltas, log_state
__all__ = ["BiologicalState", "advance", "load_state", "save_state",
           "load_and_advance", "derived", "apply_deltas", "log_state"]
```

This means zero changes to `encoder.py`, `decoder.py`, `cortex.py`, etc. until we deliberately upgrade them.

---

## BiologicalState v3

The full schema. New fields are additive — v2 states load cleanly (new fields get defaults).

```python
# src/sim/bio/state.py

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class BiologicalState:
    schema_version: int = 3
    last_updated: float = field(default_factory=time.time)

    # ── TIER 1: First-order chemicals (real physiological units) ───────────────
    # Keys match REGISTRY. Units documented in src/sim/chem/registry.py.
    chemicals: dict[str, float] = field(default_factory=_chemical_defaults)

    # ── TIER 2: Neuroendocrine cascade intermediaries ──────────────────────────
    neuroendocrine: dict[str, float] = field(default_factory=lambda: {
        # HPA axis intermediaries
        "crh":          30.0,   # pg/mL  — CRH from hypothalamus (normal: 10-50)
        "acth":         25.0,   # pg/mL  — ACTH from pituitary (normal: 10-60)
        # Thyroid axis
        "tsh":           2.0,   # mIU/L  — thyroid stimulating hormone (normal: 0.4-4.0)
        "t4":            8.0,   # µg/dL  — inactive (normal: 5-12)
        "t3":          120.0,   # ng/dL  — active (normal: 80-200)
        # Sex hormones (female baseline, follicular phase)
        "estradiol":   100.0,   # pg/mL  — (normal: 20-350, varies with cycle)
        "progesterone":  0.5,   # ng/mL  — (normal: 0.1-25, varies with cycle)
        "testosterone":  40.0,  # ng/dL  — (female normal: 15-70)
        # Metabolic hormones
        "insulin":       5.0,   # µIU/mL — (normal fasting: 2-20)
        "glucagon":     80.0,   # pg/mL  — (normal: 50-150)
        "leptin":       15.0,   # ng/mL  — satiety (normal: 4-25 female)
        "ghrelin":     400.0,   # pg/mL  — hunger (normal fasting: 300-600)
        # Social/bonding hormones
        "vasopressin":   2.0,   # pg/mL  — ADH / social bonding (normal: 1-5)
        "prolactin":     8.0,   # ng/mL  — (normal: 2-29)
        # Other
        "growth_hormone": 1.0,  # ng/mL  — pulsatile (normal: 0-10)
        "dhea":        150.0,   # µg/dL  — anti-stress (female normal: 35-430)
        # Wake-promoting
        "orexin":      300.0,   # pg/mL  — CSF proxy (normal: 200-400)
    })

    # ── TIER 3: Immune markers ─────────────────────────────────────────────────
    immune: dict[str, float] = field(default_factory=lambda: {
        "il1b":   2.0,   # pg/mL  — IL-1β (normal: <5)
        "il6":    3.0,   # pg/mL  — IL-6 (normal: <10)
        "tnf_alpha": 3.0, # pg/mL — TNF-α (normal: <8)
        "crp":    0.5,   # mg/L   — C-reactive protein (normal: <1 low-risk)
        "il10":  10.0,   # pg/mL  — anti-inflammatory IL-10 (normal: 5-20)
        "inflammation_index": 0.0,  # 0-100 AU, derived each tick
    })

    # ── TIER 4: Pain state ─────────────────────────────────────────────────────
    pain: dict[str, float] = field(default_factory=lambda: {
        "substance_p":          30.0,  # pg/mL  — CSF proxy (normal: 20-60)
        "pge2":                 80.0,  # pg/mL  — prostaglandin E2 (normal: 50-200)
        "central_sensitization": 0.0,  # 0-100 AU — builds with chronic pain
        "pain_intensity":        0.0,  # 0-100 AU — current subjective pain signal
    })

    # ── TIER 5: Body state ─────────────────────────────────────────────────────
    body: dict[str, float] = field(default_factory=lambda: {
        "adenosine":    25.0,   # nmol/L  — real sleep molecule (normal awake: 20-40)
        "anandamide":    1.5,   # nM      — endocannabinoid 1 (normal: 0.5-5)
        "two_ag":        8.0,   # nM      — endocannabinoid 2 (normal: 5-20)
        "core_temp":    37.0,   # °C      — body temperature (normal: 36.5-37.2)
    })

    # ── TIER 6: Neuroplasticity markers ───────────────────────────────────────
    neuroplasticity: dict[str, float] = field(default_factory=lambda: {
        "bdnf":                 9000.0,  # pg/mL  — serum proxy ~9 ng/mL (normal: 6-12 ng/mL)
        "synaptic_potentiation": 50.0,   # 0-100 AU — LTP-like synaptic strength
        "allostatic_load":        0.0,   # 0-100 AU — cumulative biological stress burden
    })

    # ── Receptor sensitivity ───────────────────────────────────────────────────
    # receptor_sensitivity[nt_name][receptor_type] = multiplier (0.2–2.0, 1.0 = normal)
    # Below 1.0 = tolerance (downregulation). Above 1.0 = sensitization (upregulation).
    receptor_sensitivity: dict[str, dict[str, float]] = field(default_factory=dict)

    # ── HPA cascade delay queue ────────────────────────────────────────────────
    # Pending delayed effects: list of {"target": str, "delta": float, "fires_at": float}
    cascade_queue: list[dict] = field(default_factory=list)

    # ── Menstrual cycle ────────────────────────────────────────────────────────
    cycle_day: int = 1  # 1–28; drives estradiol/progesterone baseline_fn

    # ── Context queue ─────────────────────────────────────────────────────────
    # Shared memory context written by encoder, read and drained by decoder.
    # Entries expire after ttl_seconds so stale context never poisons a later decode.
    # If decoder finds the queue empty, it queries RAG/KAG independently.
    context_queue: list[dict] = field(default_factory=list)
    # Each entry: {"text": str, "source": "rag"|"kag", "query": str,
    #              "added_at": float, "ttl_seconds": float}

    # ── Existing fields (v2 compatible) ───────────────────────────────────────
    tolerance: dict = field(default_factory=dict)
    substances: dict = field(default_factory=dict)
    sleeping: bool = False
    sleep_start: Optional[float] = None
    sleep_expected_wake: Optional[float] = None
    encoder_momentum: dict = field(default_factory=dict)

    # Convenience read-only accessors (keeps old call sites working)
    @property
    def cortisol(self) -> float: return self.chemicals.get("cortisol", 250.0)
    @property
    def dopamine(self) -> float: return self.chemicals.get("dopamine", 80.0)
    @property
    def serotonin(self) -> float: return self.chemicals.get("serotonin", 22.0)
    @property
    def norepinephrine(self) -> float: return self.chemicals.get("norepinephrine", 200.0)
    @property
    def oxytocin(self) -> float: return self.chemicals.get("oxytocin", 4.0)
    @property
    def endorphins(self) -> float: return self.chemicals.get("endorphins", 12.0)
    @property
    def acetylcholine(self) -> float: return self.chemicals.get("acetylcholine", 38.0)
    @property
    def melatonin(self) -> float: return self.chemicals.get("melatonin", 5.0)
    @property
    def glucose(self) -> float: return self.chemicals.get("glucose", 85.0)
    @property
    def hydration(self) -> float: return self.chemicals.get("hydration", 62.0)
    @property
    def sleep_pressure(self) -> float:
        # Backward compat: derive from adenosine (normalized to 0-100 AU)
        # adenosine normal range: 20-80 nmol/L → maps to 0-100 AU
        return min(100.0, max(0.0, (self.body.get("adenosine", 25.0) - 20.0) * (100.0 / 60.0)))
```

### v2 → v3 Migration

```python
# src/sim/bio/migration.py

def migrate_v2_to_v3(old: dict) -> dict:
    """
    Add new v3 fields with defaults. Existing chemicals dict is untouched.
    sleep_pressure AU carried forward as adenosine proxy.
    """
    old_sp = old.get("chemicals", {}).get("sleep_pressure", 30.0)
    # Reverse normalize: AU → nmol/L adenosine
    # sleep_pressure = (adenosine - 20) * (100/60)  →  adenosine = sp * 0.6 + 20
    adenosine_init = old_sp * 0.6 + 20.0

    result = dict(old)
    result["schema_version"] = 3

    if "neuroendocrine" not in result:
        result["neuroendocrine"] = {... defaults ...}  # see BiologicalState defaults

    if "immune" not in result:
        result["immune"] = {... defaults ...}

    if "pain" not in result:
        result["pain"] = {... defaults ...}

    if "body" not in result:
        result["body"] = {
            "adenosine": adenosine_init,
            "anandamide": 1.5,
            "two_ag": 8.0,
            "core_temp": 37.0,
        }

    if "neuroplasticity" not in result:
        result["neuroplasticity"] = {... defaults ...}

    if "receptor_sensitivity" not in result:
        result["receptor_sensitivity"] = {}

    if "cascade_queue" not in result:
        result["cascade_queue"] = []

    if "context_queue" not in result:
        result["context_queue"] = []

    if "cycle_day" not in result:
        result["cycle_day"] = 1

    return result
```

---

## EventBus

The EventBus is the mechanism by which the simulation communicates with the rest of the system. It is populated during `advance()` and consumed by callers after each tick.

```python
# src/sim/events.py

from dataclasses import dataclass, field
from typing import Literal

EventType = Literal["spike", "crash", "threshold_crossed", "sustained_extreme", "state_entered"]
System = Literal["neuro", "endocrine", "immune", "pain", "psych", "sleep", "metabolic"]
Severity = Literal["minor", "moderate", "significant", "major"]


@dataclass
class BiologicalEvent:
    event_type: EventType
    system: System
    chemical: str          # e.g. "cortisol", "il6", "pain_intensity"
    value: float           # current value in natural units
    delta: float           # change this tick (positive = increase)
    unit: str              # e.g. "nmol/L", "pg/mL", "AU"
    label: str             # current label e.g. "ACUTE STRESS"
    label_crossed: bool    # True if this tick crossed a label boundary
    severity: Severity
    significance: float    # 0.0–1.0 computed score for memory trigger decisions
    timestamp: float


class EventBus:
    """
    Collects events during advance(). Consumed by callers.

    Usage:
        bus = EventBus()
        new_state = advance(state, event_bus=bus)
        for event in bus.drain():
            handle_event(event)
    """
    def __init__(self):
        self._events: list[BiologicalEvent] = []

    def emit(self, event: BiologicalEvent) -> None:
        self._events.append(event)

    def drain(self) -> list[BiologicalEvent]:
        events, self._events = self._events, []
        return events

    @property
    def has_events(self) -> bool:
        return bool(self._events)
```

### Significance Scoring

```python
def compute_significance(chemical: str, delta: float, value: float,
                          label_crossed: bool, display_range: float) -> float:
    """
    Score 0.0–1.0 for memory trigger decisions.
    
    Factors:
    - delta as fraction of display range (big swings = significant)
    - label boundary crossing (always at least 0.3)
    - absolute value at extremes (sustained extremes = significant)
    """
    frac = abs(delta) / max(1.0, display_range)
    score = min(1.0, frac * 2.0)  # 50% of display range → significance 1.0
    if label_crossed:
        score = max(score, 0.3)
    # bonus for extreme values
    from src.sim.chem.units import get_label
    label, _ = get_label(chemical, value)
    if label in ("MAXED", "FLOODED", "ACUTE STRESS", "EXHAUSTED", "HYPOGLYCEMIC", "CRASHED"):
        score = max(score, 0.6)
    return round(score, 3)
```

### Memory Trigger Thresholds

```
significance >= 0.25 → candidate for RAG save (episodic: "something happened")
significance >= 0.60 → strong candidate for RAG save
significance >= 0.80 → flag for KAG consideration (semantic: "this changes who I am")
3+ simultaneous events with significance >= 0.40 → definitely RAG save
allostatic_load crosses 50, 70, or 90 → KAG entry
```

These thresholds are used by the hippocampus integration in SPEC-24.

---

## Engine Orchestration

The advance() orchestrator calls each subsystem in dependency order:

```python
# src/sim/engine.py

def advance(state: BiologicalState,
            now: Optional[float] = None,
            event_bus: Optional[EventBus] = None) -> BiologicalState:
    """
    Apply all time-based dynamics since state.last_updated.
    Emits BiologicalEvents to event_bus (if provided).
    Returns updated state.
    """
    if now is None:
        now = time.time()
    if event_bus is None:
        event_bus = EventBus()  # discard if caller doesn't care

    cfg = _load_config()
    sim_hours = (now - state.last_updated) / 3600.0
    if sim_hours <= 0:
        return state

    hour_of_day = _hour_of_day(now)
    s = state

    # Dependency order: each layer can read from layers above it
    # 1. Metabolic (glucose, insulin, hydration, ghrelin/leptin)
    from src.sim.physio.metabolic import advance_metabolic
    s = advance_metabolic(s, sim_hours, hour_of_day, event_bus)

    # 2. Circadian (adenosine, orexin, melatonin, core temp)
    from src.sim.physio.circadian import advance_circadian
    s = advance_circadian(s, sim_hours, hour_of_day, event_bus)

    # 3. Sleep/wake state machine (reads adenosine + melatonin + orexin)
    from src.sim.physio.circadian import advance_sleep
    s = advance_sleep(s, sim_hours, now, hour_of_day, cfg, event_bus)

    # 4. Immune (cytokines — can be driven by any system)
    from src.sim.physio.immune import advance_immune
    s = advance_immune(s, sim_hours, event_bus)

    # 5. Pain (driven by immune + injury)
    from src.sim.physio.pain import advance_pain
    s = advance_pain(s, sim_hours, event_bus)

    # 6. HPA axis (stressor → CRH → ACTH → cortisol cascade + delay queue)
    from src.sim.physio.hpa import advance_hpa
    s = advance_hpa(s, sim_hours, now, hour_of_day, event_bus)

    # 7. Endocrine (thyroid, sex hormones, GH, DHEA, prolactin, vasopressin)
    from src.sim.physio.endocrine import advance_endocrine
    s = advance_endocrine(s, sim_hours, hour_of_day, event_bus)

    # 8. Neurotransmitters (reads from all above — many baseline_fns depend on cortisol etc.)
    from src.sim.neuro.monoamines import advance_monoamines
    from src.sim.neuro.amino_acids import advance_amino_acids
    from src.sim.neuro.adenosine import advance_adenosine  # already done in circadian
    from src.sim.neuro.endocannabinoids import advance_endocannabinoids
    from src.sim.neuro.acetylcholine import advance_acetylcholine
    from src.sim.neuro.peptides import advance_peptides
    s = advance_monoamines(s, sim_hours, event_bus)
    s = advance_amino_acids(s, sim_hours, event_bus)
    s = advance_endocannabinoids(s, sim_hours, event_bus)
    s = advance_acetylcholine(s, sim_hours, event_bus)
    s = advance_peptides(s, sim_hours, event_bus)

    # 9. Receptor sensitivity (very slow, reads final chemical levels)
    from src.sim.neuro.receptors import advance_receptors
    s = advance_receptors(s, sim_hours)

    # 10. Substance pharmacokinetics (reads receptor sensitivity for efficacy)
    from src.sim.neuro.substances import advance_substances
    s = advance_substances(s, sim_hours, now, event_bus)

    # 11. Encoder momentum decay (wall-clock time)
    s = _decay_encoder_momentum(s, now)

    # 12. Neuroplasticity (BDNF, allostatic load — reads everything)
    from src.sim.psych.allostatic import advance_allostatic
    s = advance_allostatic(s, sim_hours, event_bus)

    s.last_updated = now
    return s
```

---

## Label System

Labels are the bridge between raw chemical values and the decoder LLM. They must exist for
every chemical. Without them, the decoder sees `847 pg/mL` and has to guess what that means
behaviorally. With them, it sees `[FLOODED 0.62] "Sympathetic flood. Tunnel vision..."` and
knows exactly what register to write in.

### Rules

1. **7–9 levels per chemical** for monoamines and cortisol. 5–6 is too coarse — a chemical
   can sit in "FLOODED" at wildly different intensities and the decoder writes the same tone.
2. **Implication strings must be experiential, not clinical.** The decoder turns them into
   prose. Write them as if describing a felt state.
3. **Every new chemical needs labels before implementation** — this is the spec for what the
   chemical means behaviorally. No chemical ships without them.
4. **Depth indicator** in the biological report: how far through the current label range
   the value sits (0.0–1.0). Gives the decoder meaningful resolution within a label.

### ChemicalProfile label update

```python
# Labels entry format: (upper_bound_exclusive, label_name, implication)
# implication: write in third person, felt-state language. Be specific.

# Bad (clinical):
(750.0, "HIGH", "Norepinephrine above reference range.")

# Good (experiential):
(750.0, "HYPERALERT", "On guard. Braced. Scanning for threat. Every sensation amplified."),
(900.0, "FLOODED",    "Sympathetic flood. Tunnel vision. Racing heart. Hard to think past the immediate."),
(1200.0, "OVERWHELMED", "Physiological ceiling. Hands shaking. Dissociation possible. Cannot regulate."),
(9999.0, "DYSREGULATED", "System past its limits. Fight-or-flight at maximum. Shutdown risk."),
```

### Depth indicator utility

```python
# src/sim/chem/units.py — replaces get_label()

def get_label_with_depth(name: str, value: float) -> tuple[str, str, float]:
    """
    Returns (label_name, implication, depth_in_label).
    depth: 0.0 = just entered this label, 1.0 = at its ceiling.
    """
    p = REGISTRY.get(name)
    if not p or not p.labels:
        return ("—", "", 0.0)
    prev_upper = p.display_min
    for upper, label, impl in p.labels:
        if value < upper:
            span = upper - prev_upper
            depth = round((value - prev_upper) / span, 2) if span > 0 else 0.0
            return label, impl, min(1.0, max(0.0, depth))
        prev_upper = upper
    last = p.labels[-1]
    return last[1], last[2], 1.0
```

### Biological report format (updated)

```
Norepinephrine:  847 pg/mL  [FLOODED 0.62]  "Sympathetic flood. Tunnel vision. Racing heart."
Cortisol:        620 pg/mL  [HIGH STRESS 0.14]  "Fight-or-flight activating. Emotional regulation costs."
```

The decoder LLM reads the label name as a category anchor, the depth as intensity, and the
implication string as the behavioral description to translate into prose.

### get_label() backward compat

`get_label()` stays in `src/sim/chem/units.py` for existing call sites, implemented as:
```python
def get_label(name: str, value: float) -> tuple[str, str]:
    label, impl, _ = get_label_with_depth(name, value)
    return label, impl
```

---

## Testing Strategy

Each subsystem module has its own test file. Tests use a `make_state()` fixture with chemical overrides.

```python
# tests/sim/conftest.py
import pytest
from src.sim.bio.state import BiologicalState
from src.sim.bio.defaults import chemical_defaults, neuroendocrine_defaults

def make_state(**overrides) -> BiologicalState:
    """Create a clean BiologicalState with optional chemical overrides."""
    s = BiologicalState()
    for k, v in overrides.items():
        if k in s.chemicals:
            s.chemicals[k] = float(v)
        elif k in s.neuroendocrine:
            s.neuroendocrine[k] = float(v)
        elif k in s.immune:
            s.immune[k] = float(v)
        elif k in s.pain:
            s.pain[k] = float(v)
        elif k in s.body:
            s.body[k] = float(v)
        elif k in s.neuroplasticity:
            s.neuroplasticity[k] = float(v)
    return s
```

---

## Implementation Order

Each spec is independently buildable. Recommended order:

1. **SPEC-20 (this spec)**: Create `src/sim/` structure, BiologicalState v3, EventBus, migration. Compatibility shims at root. All existing tests still pass.

2. **SPEC-21**: Neurotransmitter dynamics (GABA, Glutamate, Adenosine, Endocannabinoids, Receptors). Builds on SPEC-20 structure.

3. **SPEC-22**: Neuroendocrine & Metabolic (HPA cascade, thyroid, sex hormones, leptin/ghrelin). Each subsystem is independent.

4. **SPEC-23**: Immune & Pain (cytokines, sickness behavior, nociception). Independent of SPEC-22.

5. **SPEC-24**: Neuroplasticity, Circadian refinement, System Integration (bio-triggered memory, behavioral drives, personality drift). Synthesizes all previous specs.

---

## Open Questions

- **`sleep_pressure` in encoder deltas**: Existing `encoder.py` issues deltas for `sleep_pressure`. After migration, the real variable is `body.adenosine`. Decision: keep `sleep_pressure` as a valid delta key in `apply_deltas()`, converting it to an adenosine delta. Conversion: 1 AU sleep_pressure ≈ 0.6 nmol/L adenosine.

- **personality.json neurochemical_baselines**: Currently seeds `dopamine`, `serotonin`, `oxytocin`. Will remain in v3, but should also support new chemicals (e.g., `gaba_resting`, `bdnf_baseline`). No migration needed; just document that new keys are recognized.

- **Dashboard**: `dashboard_server.py` reads chemicals dict directly. It will need updates to display neuroendocrine, immune, and pain tiers. Out of scope for SPEC-20; addressed in SPEC-24.
