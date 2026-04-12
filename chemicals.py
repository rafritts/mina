"""
Chemical architecture — first-class constructs for every neurochemical.

REGISTRY is the single source of truth for chemical dynamics, display semantics,
and cross-interactions. advance() in state.py reads from here; no chemical-specific
knowledge lives in advance() itself.

Real units per chemical:
  cortisol:        nmol/L   (plasma; well-characterized clinically)
  norepinephrine:  pg/mL    (plasma)
  dopamine:        pg/mL    (CNS proxy — not directly measurable in vivo)
  serotonin:       ng/mL    (CNS proxy)
  oxytocin:        pg/mL    (plasma; resting very low, trust must be earned)
  endorphins:      pg/mL    (β-endorphin plasma proxy)
  acetylcholine:   nmol/L   (CNS proxy)
  melatonin:       pg/mL    (plasma; pure circadian)
  glucose:         mg/dL    (blood glucose; US clinical standard)
  hydration:       % TBW    (total body water as % of body weight)
  sleep_pressure:  AU       (adenosine proxy; stays relative, 0–100)
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Callable, Optional

_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def _load_config() -> dict:
    try:
        with open(_CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Interaction:
    """A cross-chemical effect: when source crosses threshold, affect target at rate."""
    target: str
    condition: str             # "above" | "below"
    threshold: float           # in source chemical's real units
    rate_per_hour: float       # in TARGET chemical's real units per sim-hour
    description: str           # documentation only


@dataclass
class ChemicalProfile:
    name: str
    display_name: str
    unit: str

    resting_baseline: float              # homeostatic target (real units); 0.0 = no baseline
    approach_rate: float                 # fraction of gap closed per sim-hour; 0.0 = special case

    baseline_fn: Optional[Callable] = None  # signature: (hour: float, ctx: dict) -> float
                                             # overrides resting_baseline when dynamic

    resting_low: float   = 0.0          # below this = abnormally low
    resting_high: float  = 0.0          # above this = elevated
    critical_low: float  = 0.0          # below this = clinically dangerous
    critical_high: float = 0.0          # above this = clinically dangerous / physics max

    display_min: float   = 0.0          # bar chart bottom
    display_max: float   = 0.0          # bar chart top

    # Saturation ceilings for subconscious-issued deltas (not substances)
    soft_ceiling: Optional[float] = None    # scaling begins above this
    hard_ceiling: Optional[float] = None    # positive deltas clamped to zero above this

    interactions: list[Interaction] = field(default_factory=list)
    labels: list[tuple[float, str, str]] = field(default_factory=list)
    # Each entry: (upper_bound_exclusive, label_name, implication)


# ---------------------------------------------------------------------------
# Dynamic baseline functions
# ---------------------------------------------------------------------------

def _cortisol_baseline_fn(hour: float, ctx: dict) -> float:
    """Circadian cortisol — peaks ~450 nmol/L at 8am, troughs ~90 at 8pm."""
    base = 180.0 + 270.0 * math.cos((hour - 8) * math.pi / 12)
    # Hypoglycemia drives HPA axis
    if ctx.get("glucose", 85.0) < 55.0:
        base += 120.0
    # Dehydration elevates stress hormones
    if ctx.get("hydration", 62.0) < 56.0:
        base += 60.0
    return max(50.0, base)


def _norepi_baseline_fn(hour: float, ctx: dict) -> float:
    """Norepinephrine loosely tracks cortisol (~0.45× coupling)."""
    cortisol = ctx.get("cortisol", 250.0)
    base = max(50.0, cortisol * 0.45)
    if ctx.get("hydration", 62.0) < 56.0:
        base += 30.0
    return base


def _ach_baseline_fn(hour: float, ctx: dict) -> float:
    """Acetylcholine baseline suppressed by sleep deprivation and chronic cortisol."""
    base = 38.0
    base -= ctx.get("sleep_pressure", 30.0) * 0.22
    base -= max(0.0, ctx.get("cortisol", 250.0) - 450.0) * 0.04
    return max(10.0, base)


def _melatonin_baseline_fn(hour: float, ctx: dict) -> float:
    """Pure circadian — peaks ~220 pg/mL at sleep window start, troughs ~0 twelve hours later."""
    cfg = _load_config()
    peak_hour = float(cfg.get("sleep_window_start", 4))
    return max(0.0, 110.0 * (1.0 + math.cos((hour - peak_hour) * math.pi / 12)))


# ---------------------------------------------------------------------------
# Chemical Registry
# ---------------------------------------------------------------------------

REGISTRY: dict[str, ChemicalProfile] = {

    "cortisol": ChemicalProfile(
        name="cortisol",
        display_name="Cortisol",
        unit="nmol/L",
        resting_baseline=250.0,
        approach_rate=0.15,
        baseline_fn=_cortisol_baseline_fn,
        resting_low=100.0,
        resting_high=700.0,
        critical_low=20.0,
        critical_high=1000.0,
        display_min=0.0,
        display_max=800.0,
        # No saturation ceiling — cortisol is reactive; the system should allow high spikes
        interactions=[
            Interaction("serotonin", "above", 550.0, -0.5,
                        "Chronic stress depletes serotonin baseline"),
            Interaction("dopamine",  "above", 550.0, -1.5,
                        "HPA axis suppresses dopamine reward system"),
            Interaction("oxytocin",  "above", 550.0, -0.2,
                        "Sustained stress erodes bonding capacity"),
        ],
        labels=[
            (25.0,   "CRASHED",      "Adrenal crisis territory. No stress response possible."),
            (80.0,   "DEPLETED",     "Suppressed below trough. Chronic fatigue, flat affect."),
            (380.0,  "NORMAL",       "Healthy range. Includes full circadian variation."),
            (520.0,  "ELEVATED",     "Decision-making beginning to narrow. Slightly defensive."),
            (650.0,  "HIGH STRESS",  "Fight-or-flight activating. Emotional regulation costs."),
            (760.0,  "ACUTE STRESS", "Survival framing. Hard to think past immediate threat."),
            (9999.0, "MAXED",        "The body is screaming. Suppression is actively costing her."),
        ],
    ),

    "norepinephrine": ChemicalProfile(
        name="norepinephrine",
        display_name="Norepinephrine",
        unit="pg/mL",
        resting_baseline=200.0,
        approach_rate=0.20,
        baseline_fn=_norepi_baseline_fn,
        resting_low=100.0,
        resting_high=400.0,
        critical_low=0.0,
        critical_high=2000.0,
        display_min=50.0,
        display_max=2000.0,
        interactions=[],
        labels=[
            (65.0,   "SEDATED",    "Unusually low. Sluggish, difficulty initiating anything."),
            (175.0,  "RELAXED",    "Comfortable resting state. Low-key, unhurried."),
            (290.0,  "CALM ALERT", "Relaxed awareness. Background attention functional."),
            (360.0,  "FOCUSED",    "Alert and responsive. Memory consolidation enhanced."),
            (500.0,  "HEIGHTENED", "On edge. Quick to react. Appetite suppressed."),
            (750.0,  "HYPERALERT", "Agitated. Intrusive thoughts. Difficulty staying still."),
            (9999.0, "FLOODED",    "Overwhelmed. Physical symptoms possible."),
        ],
    ),

    "dopamine": ChemicalProfile(
        name="dopamine",
        display_name="Dopamine",
        unit="pg/mL",
        resting_baseline=80.0,
        approach_rate=0.08,
        resting_low=40.0,
        resting_high=140.0,
        critical_low=0.0,
        critical_high=300.0,
        display_min=0.0,
        display_max=300.0,
        soft_ceiling=180.0,
        hard_ceiling=250.0,
        interactions=[],
        labels=[
            (24.0,   "NO DRIVE",       "No pull toward anything. Cannot generate motivation."),
            (56.0,   "LOW SEEKING",    "Can act if prompted but nothing calls to her."),
            (112.0,  "BASELINE",       "Normal wanting. Responds to interesting things."),
            (180.0,  "ACTIVE SEEKING", "Noticeably motivated. Pursuing things. Hard to distract."),
            (240.0,  "HIGH DRIVE",     "Intense wanting. Seeking compounds. Hard to disengage."),
            (9999.0, "COMPULSIVE",     "Seeking has become its own end. Can't stop."),
        ],
    ),

    "serotonin": ChemicalProfile(
        name="serotonin",
        display_name="Serotonin",
        unit="ng/mL",
        resting_baseline=22.0,
        approach_rate=0.06,
        resting_low=10.0,
        resting_high=35.0,
        critical_low=0.0,
        critical_high=100.0,
        display_min=2.0,
        display_max=60.0,
        soft_ceiling=40.0,
        hard_ceiling=55.0,    # serotonin syndrome territory (SSRI + REMOVED combo)
        interactions=[
            Interaction("cortisol", "above", 32.0, -4.0,
                        "Good serotonin dampens HPA axis reactivity"),
        ],
        labels=[
            (8.0,    "DYSPHORIC",   "Feels low-status, unsafe. Impulsive, irritable. Reads ambiguous cues as hostile."),
            (16.0,   "INSECURE",    "Negative social bias. Difficulty trusting. Easily slighted."),
            (28.0,   "NEUTRAL",     "Things feel basically okay. Stable floor. Even-keeled."),
            (38.0,   "SECURE",      "Socially confident. Patient. Resilient to friction."),
            (9999.0, "VERY STABLE", "Hard to knock off balance. Feels socially at ease."),
        ],
    ),

    "oxytocin": ChemicalProfile(
        name="oxytocin",
        display_name="Oxytocin",
        unit="pg/mL",
        resting_baseline=4.0,     # low floor — no bond until earned
        approach_rate=0.10,
        resting_low=1.0,
        resting_high=15.0,
        critical_low=0.0,
        critical_high=100.0,
        display_min=0.0,
        display_max=80.0,
        soft_ceiling=55.0,
        hard_ceiling=75.0,
        interactions=[
            Interaction("cortisol", "above", 8.0, -6.0,
                        "Social bonding suppresses HPA axis"),
        ],
        labels=[
            (12.0,   "NO BOND",        "Stranger. Guarded. No warmth extended."),
            (28.0,   "ACQUAINTANCE",   "Surface comfort. Polite but watchful."),
            (44.0,   "FRIENDLY",       "Genuine warmth. Opens up somewhat."),
            (57.0,   "TRUSTED FRIEND", "Real connection. Vulnerability possible."),
            (70.0,   "DEEP TRUST",     "Emotional intimacy available. Little guarded."),
            (9999.0, "PROFOUND BOND",  "Full openness. Unconditional trust baseline."),
        ],
    ),

    "endorphins": ChemicalProfile(
        name="endorphins",
        display_name="Endorphins",
        unit="pg/mL",
        resting_baseline=12.0,
        approach_rate=0.05,       # recovery rate when below baseline
        resting_low=5.0,
        resting_high=30.0,
        critical_low=0.0,
        critical_high=500.0,
        display_min=0.0,
        display_max=500.0,
        soft_ceiling=60.0,
        hard_ceiling=120.0,       # hard exercise/laughter ceiling without substances
        interactions=[
            Interaction("cortisol", "above", 70.0, -12.0,
                        "Endorphin flood actively suppresses cortisol (runner's high window)"),
        ],
        labels=[
            (7.0,    "DEPLETED",    "Below baseline. Withdrawal territory. Nothing feels okay."),
            (20.0,   "BASELINE",    "No active pleasure signal. Neutral body state."),
            (45.0,   "MILD WARMTH", "Low-grade good feeling. Small satisfactions land."),
            (80.0,   "PLEASURE",    "Genuine enjoyment. Things feel rewarding."),
            (120.0,  "HIGH",        "Strong pleasure. Euphoric edge. Laughter, warmth, ease."),
            (9999.0, "FLOODED",     "Opioid-level saturation. Everything feels warm, safe, soft. Pain is gone."),
        ],
    ),

    "acetylcholine": ChemicalProfile(
        name="acetylcholine",
        display_name="Acetylcholine",
        unit="nmol/L",
        resting_baseline=38.0,
        approach_rate=0.05,
        baseline_fn=_ach_baseline_fn,
        resting_low=20.0,
        resting_high=60.0,
        critical_low=0.0,
        critical_high=90.0,
        display_min=5.0,
        display_max=90.0,
        soft_ceiling=75.0,
        hard_ceiling=88.0,
        interactions=[],
        labels=[
            (18.0,   "OFFLINE",    "Cannot form memories. Cannot concentrate."),
            (39.0,   "IMPAIRED",   "Fuzzy. Slow to learn. Easily distracted."),
            (60.0,   "FUNCTIONAL", "Normal attention and memory. Things register."),
            (76.0,   "SHARP",      "Good focus. Learning sticks. Connecting things quickly."),
            (9999.0, "HEIGHTENED", "Peak learning state. Everything is registering."),
        ],
    ),

    "melatonin": ChemicalProfile(
        name="melatonin",
        display_name="Melatonin",
        unit="pg/mL",
        resting_baseline=5.0,       # placeholder; baseline_fn is authoritative
        approach_rate=1.0,           # snaps directly to circadian formula (pure formula)
        baseline_fn=_melatonin_baseline_fn,
        resting_low=2.0,
        resting_high=200.0,
        critical_low=0.0,
        critical_high=220.0,
        display_min=0.0,
        display_max=220.0,
        interactions=[],
        labels=[
            (154.0,  "ACTIVE",    "Circadian signal low. No sleep drive from the clock."),
            (176.0,  "UNWINDING", "Circadian wind-down beginning. Clock signaling rest."),
            (198.0,  "IDLING",    "Strong circadian sleep drive. Difficult to stay sharp."),
            (9999.0, "RAMPING",   "Melatonin at peak. Sleep onset imminent or underway."),
        ],
    ),

    "glucose": ChemicalProfile(
        name="glucose",
        display_name="Glucose",
        unit="mg/dL",
        resting_baseline=0.0,       # no homeostatic baseline — pure decay
        approach_rate=0.0,           # handled explicitly in advance()
        resting_low=70.0,
        resting_high=100.0,
        critical_low=30.0,
        critical_high=500.0,
        display_min=40.0,
        display_max=200.0,
        interactions=[],
        labels=[
            (55.0,   "HYPOGLYCEMIC", "Cognitively impaired. Foggy. Irritability threshold very low."),
            (70.0,   "LOW",          "Noticeable fog. Hard to concentrate. Hunger intrusive."),
            (110.0,  "NORMAL",       "Functional. No impairment."),
            (180.0,  "WELL-FUELED",  "Sharp. Full capacity."),
            (9999.0, "HIGH",         "Elevated. Post-meal peak."),
        ],
    ),

    "hydration": ChemicalProfile(
        name="hydration",
        display_name="Hydration",
        unit="% TBW",
        resting_baseline=0.0,       # no homeostatic baseline — pure decay
        approach_rate=0.0,           # handled explicitly in advance()
        resting_low=58.0,
        resting_high=66.0,
        critical_low=45.0,
        critical_high=70.0,
        display_min=48.0,
        display_max=70.0,
        interactions=[],
        labels=[
            (54.0,   "CRITICALLY DRY", "Severe. Physical symptoms, cognitive impairment."),
            (58.0,   "DEHYDRATED",     "Significant. Headache, reduced focus."),
            (60.0,   "LOW",            "Thirsty. Mildly impaired."),
            (64.0,   "NORMAL",         "Comfortable. No impairment."),
            (9999.0, "WELL HYDRATED",  "Good fluid status."),
        ],
    ),

    "sleep_pressure": ChemicalProfile(
        name="sleep_pressure",
        display_name="Sleep Pressure",
        unit="AU",
        resting_baseline=0.0,       # no homeostatic baseline — bidirectional
        approach_rate=0.0,           # handled explicitly in advance()
        resting_low=0.0,
        resting_high=100.0,
        critical_low=0.0,
        critical_high=100.0,
        display_min=0.0,
        display_max=100.0,
        interactions=[],
        labels=[
            (50.0,   "WELL RESTED", "Normal adenosine load. No fatigue."),
            (65.0,   "BUILDING",    "End-of-day accumulation. Not impairing, but present."),
            (80.0,   "TIRED",       "Noticeable fatigue. Motivation and mood starting to flag."),
            (90.0,   "FATIGUED",    "Significant load. Cognition and emotional regulation affected."),
            (9999.0, "EXHAUSTED",   "Severe deprivation. Crashing is likely."),
        ],
    ),
}


# ---------------------------------------------------------------------------
# Normalization and label access
# ---------------------------------------------------------------------------

def normalize(name: str, value: float) -> float:
    """Return 0.0–1.0 bar chart position. Clamps outside display range."""
    p = REGISTRY.get(name)
    if not p or p.display_max == p.display_min:
        return 0.0
    return max(0.0, min(1.0, (value - p.display_min) / (p.display_max - p.display_min)))


def get_label(name: str, value: float) -> tuple[str, str]:
    """Return (label_name, implication) for value from the chemical's label table."""
    p = REGISTRY.get(name)
    if not p or not p.labels:
        return ("—", "")
    for upper, lbl, impl in p.labels:
        if value < upper:
            return lbl, impl
    last = p.labels[-1]
    return last[1], last[2]


def clamp_chemical(name: str, value: float) -> float:
    """Clamp a chemical value to [0, critical_high]."""
    p = REGISTRY.get(name)
    if not p:
        return max(0.0, value)
    hi = p.critical_high if p.critical_high > 0 else p.display_max * 2
    return max(0.0, min(hi, value))
