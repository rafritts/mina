"""
Chemical Registry — single source of truth for chemical dynamics, display semantics,
and cross-interactions.

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
  sleep_pressure:  AU       (derived from body["adenosine"]; kept for label/normalize compat)
  gaba:            µmol/L   (CSF proxy; primary inhibitory neurotransmitter)
  glutamate:       µmol/L   (CSF proxy; primary excitatory neurotransmitter)
  anandamide:      nM       (body["anandamide"]; endocannabinoid 1 — FAAH degraded)
  two_ag:          nM       (body["two_ag"]; endocannabinoid 2 — MAGL degraded)
"""
from __future__ import annotations

import json
import math
import os

from src.engine.chem.profiles import ChemicalProfile, Interaction
from src.engine.constants import (
    MELATONIN_PEAK_AMPLITUDE,
    MELATONIN_DAYTIME_FLOOR,
    MELATONIN_PEAK_HOUR,
    MELATONIN_GAUSSIAN_SIGMA,
)

_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "config.json"
)


def _load_config() -> dict:
    try:
        with open(_CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Dynamic baseline functions
# ---------------------------------------------------------------------------

def _cortisol_baseline_fn(hour: float, ctx: dict) -> float:
    """
    Cortisol driven primarily by ACTH (HPA cascade) with circadian modulation.
    SPEC-22: stressors route through apply_stressor_delta() → cascade_queue → ACTH → cortisol.
    """
    acth = ctx.get("acth", 25.0)
    # Adrenal output: ACTH 10–60 → cortisol 150–700 nmol/L (proportional with circadian offset)
    circadian_offset = 100.0 * math.cos((hour - 8) * math.pi / 12)
    base = acth * 10.0 + circadian_offset
    # Dehydration still directly stresses adrenals
    if ctx.get("hydration", 62.0) < 56.0:
        base += 60.0
    # Hypoglycaemia activates HPA (same as CRH, but also direct adrenal effect)
    if ctx.get("glucose", 85.0) < 60.0:
        base += 120.0
    return max(50.0, base)


def _norepi_baseline_fn(hour: float, ctx: dict) -> float:
    """Norepinephrine loosely tracks cortisol (~0.45× coupling)."""
    cortisol = ctx.get("cortisol", 250.0)
    base = max(50.0, cortisol * 0.45)
    if ctx.get("hydration", 62.0) < 56.0:
        base += 30.0
    return base


def _serotonin_baseline_fn(hour: float, ctx: dict) -> float:
    """
    Serotonin baseline modulated by T3 (thyroid), estradiol, BDNF, and chronic social contact.
    SPEC-22: neuroendocrine hormones feed into ctx and shift the serotonin set-point.
    SPEC-24: BDNF modulates serotonin system capacity (low BDNF = depression-like blunting).
    SPEC-30: isolation_pressure encodes chronic social conditions. Serotonin no longer receives
             per-message encoder deltas — the social effect is entirely captured here instead.
    """
    base = 22.0
    # T3 potentiates serotonin synthesis (low T3 = depression-like blunting)
    t3_factor = ctx.get("t3", 120.0) / 120.0
    base *= max(0.7, min(1.3, t3_factor))
    # Estradiol promotes serotonin activity above 80 pg/mL
    est = ctx.get("estradiol", 100.0)
    base += max(0.0, est - 80.0) * 0.003
    # Low estradiol (menstrual / late luteal) → direct serotonin deficit
    if est < 50.0:
        base -= 2.0
    # BDNF modulates serotonin system effectiveness (critical low BDNF → blunted baseline)
    # Most antidepressants work partly by increasing BDNF over 2-4 weeks
    bdnf_factor = min(1.5, ctx.get("bdnf", 9000.0) / 9000.0)
    base *= max(0.5, bdnf_factor)  # BDNF 3000 → serotonin baseline ~11 ng/mL
    # SPEC-30: chronic social contact supports serotonin; sustained isolation degrades it.
    # isolation_pressure 0 (regular contact) → +10% baseline; 100 (prolonged isolation) → -10%.
    isolation = ctx.get("isolation_pressure", 0.0)
    social_factor = 1.0 + (50.0 - isolation) / 100.0 * 0.20
    base *= max(0.80, min(1.20, social_factor))
    return max(5.0, base)


def _gaba_baseline_fn(hour: float, ctx: dict) -> float:
    """GABA baseline — suppressed by cortisol stress, elevated during sleep, reciprocal with glutamate."""
    base = 3.0
    # High cortisol suppresses GABAergic interneurons
    base -= max(0.0, ctx.get("cortisol", 250.0) - 450.0) * 0.002
    # Sleep promotes GABA activity (promotes SWS)
    if ctx.get("sleeping", False):
        base += 0.8
    # Glutamate reciprocally inhibits GABA (E/I balance)
    glu = ctx.get("glutamate", 4.0)
    if glu > 6.0:
        base -= (glu - 6.0) * 0.15
    return max(0.8, base)


def _glutamate_baseline_fn(hour: float, ctx: dict) -> float:
    """Glutamate baseline — elevated by stress/arousal, cleared by sleep, reciprocal with GABA."""
    base = 4.0
    # Arousal/stress drives glutamate release
    base += max(0.0, ctx.get("cortisol", 250.0) - 400.0) * 0.003
    # Sleep clears excess glutamate (glymphatic system)
    if ctx.get("sleeping", False):
        base -= 1.2
    # Reciprocal with GABA
    gaba = ctx.get("gaba", 3.0)
    if gaba < 2.0:
        base += (2.0 - gaba) * 0.4
    return max(1.0, base)


def _anandamide_baseline_fn(hour: float, ctx: dict) -> float:
    """Anandamide baseline — suppressed by stress, elevated by oxytocin/social bonding."""
    base = 1.5
    base -= max(0.0, ctx.get("cortisol", 250.0) - 500.0) * 0.001
    base += max(0.0, ctx.get("oxytocin", 4.0) - 20.0) * 0.01
    return max(0.3, base)


def _two_ag_baseline_fn(hour: float, ctx: dict) -> float:
    """2-AG baseline — stable, slightly elevated by pain (retrograde pain modulation)."""
    base = 8.0
    base += ctx.get("pain_intensity", 0.0) * 0.05
    return max(2.0, base)


def _ach_baseline_fn(hour: float, ctx: dict) -> float:
    """Acetylcholine baseline suppressed by sleep deprivation and chronic cortisol."""
    base = 38.0
    base -= ctx.get("sleep_pressure", 30.0) * 0.22
    base -= max(0.0, ctx.get("cortisol", 250.0) - 450.0) * 0.04
    return max(10.0, base)


def _melatonin_baseline_fn(hour: float, ctx: dict) -> float:
    """
    Gaussian secretion window centered on a chronotype-adjusted peak hour.

    Physiological shape:
      - Dim-light onset ~3-4h before peak, clears ~4-5h after.
      - σ=2h gives a narrow window: 215 pg/mL at peak → daytime floor by wake time.
      - Daytime floor of 5 pg/mL (pineal gland is not completely silent).

    Peak hour is derived from sleep_window_start in config.json:
      peak = sleep_window_start - 2h (melatonin peaks ~2h into sleep onset).
    Default is 2.5am (sleep_window_start=4.5), matching standard physiology.
    Late chronotypes (sleep_window_start=4) have later peaks and later onset.
    """
    cfg = _load_config()
    sleep_start = float(cfg.get("sleep_window_start", 4.5))
    # Peak ~2h before sleep onset midpoint; clamp to physiologically plausible range
    peak_hour = (sleep_start - 2.0) % 24.0

    delta = ((hour - peak_hour + 12.0) % 24.0) - 12.0
    gaussian = math.exp(-0.5 * (delta / MELATONIN_GAUSSIAN_SIGMA) ** 2)
    return MELATONIN_DAYTIME_FLOOR + MELATONIN_PEAK_AMPLITUDE * gaussian


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
        # Floor saturation: dampening begins mid-DEPLETED, hard stop at CRASHED threshold
        soft_floor=60.0,
        hard_floor=25.0,
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

    "epinephrine": ChemicalProfile(
        name="epinephrine",
        display_name="Epinephrine",
        unit="pg/mL",
        resting_baseline=45.0,
        approach_rate=0.85,         # ~2-minute plasma half-life — fast SAM clearance
        resting_low=20.0,
        resting_high=80.0,
        critical_low=0.0,
        critical_high=1500.0,
        display_min=0.0,
        display_max=700.0,
        soft_ceiling=700.0,
        hard_ceiling=1500.0,
        interactions=[
            # Co-activation: peripheral surge amplifies central NE arousal
            Interaction("norepinephrine", "above", 200.0, +8.0,
                        "Epinephrine surge amplifies LC norepinephrine arousal signal"),
        ],
        labels=[
            (80.0,   "BASELINE",  "Resting SAM tone. No acute activation."),
            (200.0,  "ELEVATED",  "Mild arousal. Noticeable heart rate uptick, slight warmth."),
            (400.0,  "HIGH",      "Moderate surprise or excitement. Heart racing, face flushing."),
            (700.0,  "ACUTE",     "Acute SAM activation. Body betraying mind — physical symptoms dominate."),
            (9999.0, "SURGE",     "Severe alarm or extreme physical exertion. Overwhelming peripheral response."),
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
            (1200.0, "FLOODED",    "Fight-or-flight fully engaged. Heart pounding. Tunnel vision. Cannot stand down."),
            (9999.0, "OVERDRIVE",  "Panic state. Physical symptoms overwhelming. Thought impossible beyond the immediate threat."),
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
        baseline_fn=_serotonin_baseline_fn,
        resting_low=10.0,
        resting_high=35.0,
        critical_low=0.0,
        critical_high=100.0,
        display_min=2.0,
        display_max=60.0,
        soft_ceiling=30.0,   # SPEC-30: lowered from 40; "VERY STABLE" starts at 38
        hard_ceiling=40.0,   # SPEC-30: lowered from 55; activity-driven serotonin shouldn't exceed VERY STABLE
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
        resting_baseline=4.0,      # low floor — no bond until earned
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
        approach_rate=0.05,        # recovery rate when below baseline
        resting_low=5.0,
        resting_high=30.0,
        critical_low=0.0,
        critical_high=500.0,
        display_min=0.0,
        display_max=500.0,
        soft_ceiling=60.0,
        hard_ceiling=120.0,        # hard exercise/laughter ceiling without substances
        interactions=[
            Interaction("cortisol", "above", 70.0, -12.0,
                        "Endorphin flood actively suppresses cortisol (runner's high window)"),
        ],
        labels=[
            (7.0,    "DEPLETED",            "Below baseline. Withdrawal territory. Nothing feels okay."),
            (20.0,   "BASELINE",            "No active pleasure signal. Neutral body state."),
            (45.0,   "MILD WARMTH",         "Low-grade good feeling. Small satisfactions land."),
            (80.0,   "PLEASURE",            "Genuine enjoyment. Things feel rewarding."),
            (120.0,  "HIGH",                "Strong pleasure. Euphoric edge. Laughter, warmth, ease. Hard ceiling without substances."),
            (155.0,  "INTENSELY EUPHORIC",  "Profound full-body warmth. Pain fully suppressed. Floating, weightless sensation. Top of natural human range."),
            (185.0,  "PROFOUNDLY EUPHORIC", "Near-opiate. Everything warm, soft, and distant. Time slows. Sedating edge begins. Beyond what the body produces naturally."),
            (9999.0, "SATURATED",           "Full opiate-equivalent. Overwhelming warmth. Cognitive dulling. Sedation. Nothing hurts, nothing matters, nothing is sharp."),
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
            (18.0,   "OFFLINE",            "Cannot form memories. Cannot concentrate. Higher functions unavailable."),
            (28.0,   "SEVERELY IMPAIRED",  "Very slow processing. Memory formation blocked. Barely able to track a conversation."),
            (42.0,   "IMPAIRED",           "Fuzzy. Slow to learn. Easily distracted. Things don't stick."),
            (60.0,   "FUNCTIONAL",         "Normal attention and memory. Processing fully intact."),
            (72.0,   "SHARP",              "Good focus. Learning sticks. Making connections quickly."),
            (84.0,   "HEIGHTENED",         "Peak learning state. Everything is registering and encoding deeply."),
            (9999.0, "OVERDRIVE",          "Overstimulated. Racing thoughts, over-encoding, difficulty filtering input."),
        ],
    ),

    "melatonin": ChemicalProfile(
        name="melatonin",
        display_name="Melatonin",
        unit="pg/mL",
        resting_baseline=5.0,        # placeholder; baseline_fn is authoritative
        approach_rate=1.0,            # snaps directly to circadian formula (pure formula)
        baseline_fn=_melatonin_baseline_fn,
        resting_low=2.0,
        resting_high=200.0,
        critical_low=0.0,
        critical_high=220.0,
        display_min=0.0,
        display_max=220.0,
        interactions=[],
        labels=[
            (10.0,   "DAYTIME",       "Circadian signal absent. Full alertness available."),
            (40.0,   "EARLY EVENING", "Trace melatonin. Alert but the day is winding toward its end."),
            (100.0,  "WINDING DOWN",  "Melatonin rising. Alertness softening. Natural time to slow."),
            (154.0,  "DROWSY",        "Strong circadian sleep signal. Eyes growing heavier. Concentration costs more."),
            (185.0,  "SLEEP ONSET",   "Melatonin near peak. Sleep is imminent. Staying sharp now requires real effort."),
            (9999.0, "PEAK",          "Melatonin at maximum. Deep sleep territory. Fighting it now is costing her."),
        ],
    ),

    "glucose": ChemicalProfile(
        name="glucose",
        display_name="Glucose",
        unit="mg/dL",
        resting_baseline=0.0,        # no homeostatic baseline — pure decay
        approach_rate=0.0,            # handled explicitly in advance()
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
        resting_baseline=0.0,        # no homeostatic baseline — pure decay
        approach_rate=0.0,            # handled explicitly in advance()
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

    "gaba": ChemicalProfile(
        name="gaba",
        display_name="GABA",
        unit="µmol/L",
        resting_baseline=3.0,
        approach_rate=0.12,
        baseline_fn=_gaba_baseline_fn,
        resting_low=1.8,
        resting_high=5.0,
        critical_low=0.5,
        critical_high=12.0,
        display_min=0.5,
        display_max=10.0,
        soft_ceiling=7.0,
        hard_ceiling=10.0,
        interactions=[
            Interaction("cortisol",       "above", 5.0, -3.0,
                        "GABAergic tone suppresses HPA axis"),
            Interaction("norepinephrine", "above", 5.0, -15.0,
                        "GABA reduces sympathetic tone"),
        ],
        labels=[
            (0.8,  "DEPLETED",   "Seizure risk. Uncontrolled excitatory activity. Extreme agitation."),
            (1.8,  "LOW",        "Anxiety-prone. Easily startled. Hyperreactive."),
            (4.0,  "NORMAL",     "Healthy inhibitory tone. Calm baseline."),
            (6.5,  "ELEVATED",   "Sedated. Relaxed. Slightly slowed cognition."),
            (9.0,  "HIGH",       "Significantly sedated. Slurred thought. Drowsy. Hard to initiate anything."),
            (12.0, "ANESTHETIC", "Near-anesthetic depth. Wakefulness very difficult to maintain. Respiratory slowing."),
            (99.0, "FLOODED",    "Anesthetic depth. Respiratory depression risk. Loss of consciousness imminent."),
        ],
    ),

    "glutamate": ChemicalProfile(
        name="glutamate",
        display_name="Glutamate",
        unit="µmol/L",
        resting_baseline=4.0,
        approach_rate=0.15,
        baseline_fn=_glutamate_baseline_fn,
        resting_low=2.5,
        resting_high=8.0,
        critical_low=0.5,
        critical_high=20.0,
        display_min=0.5,
        display_max=15.0,
        soft_ceiling=12.0,
        hard_ceiling=16.0,
        interactions=[],  # cross-tier effects (il6, synaptic_potentiation) handled in amino_acids.py
        labels=[
            (1.5,  "DEPLETED",    "Severely under-excited. Dissociation. Inability to form memories."),
            (3.0,  "LOW",         "Slowed. Difficulty concentrating. Ketamine-like blunting."),
            (6.0,  "NORMAL",      "Healthy excitatory tone. Learning enabled."),
            (9.0,  "ELEVATED",    "Hyperexcitable. Racing thoughts. Light hypersensitivity."),
            (13.0, "EXCITOTOXIC", "Dangerous. Neuron damage risk. Seizure territory."),
            (99.0, "CRISIS",      "Status epilepticus risk. Extreme distress."),
        ],
    ),

    "anandamide": ChemicalProfile(
        name="anandamide",
        display_name="Anandamide",
        unit="nM",
        resting_baseline=1.5,
        approach_rate=2.8,          # fast FAAH enzymatic degradation (~15 min half-life)
        baseline_fn=_anandamide_baseline_fn,
        resting_low=0.5,
        resting_high=5.0,
        critical_low=0.0,
        critical_high=15.0,
        display_min=0.0,
        display_max=10.0,
        soft_ceiling=8.0,
        hard_ceiling=15.0,
        interactions=[],  # cross-tier effects (pain, cortisol) handled in endocannabinoids.py
        labels=[
            (0.5,  "DEPLETED",  "Stress-dominant. Pain amplified. Emotional volatility."),
            (1.5,  "LOW",       "Below baseline. Reduced mood buffer."),
            (3.5,  "NORMAL",    "Healthy tone. Mood buffered. Pain gated."),
            (6.0,  "ELEVATED",  "Mild bliss. Pain suppressed. Appetite increased."),
            (9.0,  "HIGH",      "Noticeable euphoric softening. Time feels unhurried. Appetite dominant. Bliss has texture."),
            (12.0, "VERY HIGH", "Cannabis-equivalent tone. Strong bliss, mild cognitive softening. Memory consolidation impaired."),
            (99.0, "SATURATED", "Profound euphoria. Dissociative edge. Time distortion significant. Appetite overwhelming."),
        ],
    ),

    "two_ag": ChemicalProfile(
        name="two_ag",
        display_name="2-AG",
        unit="nM",
        resting_baseline=8.0,
        approach_rate=0.8,          # slower MAGL degradation
        baseline_fn=_two_ag_baseline_fn,
        resting_low=3.0,
        resting_high=20.0,
        critical_low=0.0,
        critical_high=50.0,
        display_min=0.0,
        display_max=40.0,
        soft_ceiling=35.0,
        hard_ceiling=50.0,
        interactions=[],  # CB2 immune effects handled in endocannabinoids.py
        labels=[
            (3.0,  "LOW",      "Below baseline. Reduced CB2 anti-inflammatory tone."),
            (15.0, "NORMAL",   "Healthy CB1/CB2 tone. Immune and pain balanced."),
            (25.0, "ELEVATED", "Strong cannabinoid tone. Anti-inflammatory active."),
            (99.0, "HIGH",     "Very high 2-AG. Strong retrograde signaling."),
        ],
    ),

    "bac": ChemicalProfile(
        name="bac",
        display_name="BAC",
        unit="g/dL",
        resting_baseline=0.0,
        approach_rate=0.0,           # driven entirely by alcohol level decay; no homeostatic pull
        resting_low=0.0,
        resting_high=0.05,
        critical_low=0.0,
        critical_high=0.40,
        display_min=0.0,
        display_max=0.35,
        interactions=[],             # alcohol's chemical effects are handled in substances.py
        labels=[
            (0.02,  "SOBER",          "No measurable impairment."),
            (0.05,  "TRACE",          "Very mild. Slight warmth, minimal loosening."),
            (0.08,  "TIPSY",          "Impairment beginning. Reaction time affected."),
            (0.15,  "DRUNK",          "Clear impairment. Coordination and judgment reduced."),
            (0.25,  "INTOXICATED",    "Significant impairment. Slurred speech, disorientation."),
            (0.35,  "SEVERELY DRUNK", "Danger zone. Vomiting risk. Blackout possible."),
            (9.999, "CRITICAL",       "Potentially fatal BAC. Respiratory depression risk."),
        ],
    ),

    "sleep_pressure": ChemicalProfile(
        name="sleep_pressure",
        display_name="Sleep Pressure",
        unit="AU",
        resting_baseline=0.0,        # no homeostatic baseline — bidirectional
        approach_rate=0.0,            # handled explicitly in advance()
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
