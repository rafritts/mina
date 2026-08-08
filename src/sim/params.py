"""
chemistry_params.py — centralized, data-only parameter table for the chemistry sim.

Structure per chemical:
  class              : 1 (fast NT), 2 (slow peptide), 3 (hormonal), 4 (scaffold)
  tonic_setpoint     : resting baseline in working nM units
  normalization_max  : nM corresponding to 10 on the decoder 0-10 scale
  phasic_half_life_s : phasic decay half-life in seconds (Class 1/2 only)
  tonic_decay_rate   : per-tick fraction by which tonic approaches setpoint
  setpoint_adapt_rate: per-tick fraction of (tonic - setpoint) absorbed into setpoint
  feedback_ceiling   : normalized headroom ceiling for source-side autoreceptor limit
  pfc_regulation     : "none" | "weak" | "moderate" | "strong" (frontend regulation strength)
  axis_weights       : {axis: weight} — Class 1 only; absent for Class 2/3/4

No logic lives here. The chemistry function and tick are thin loops over this table.
All concentration values are in working nM units grounded in published neuroscience ranges.

Decoder normalization anchors (what "10" means per chemical):
  dopamine        — peak extrasynaptic tonic during intense sustained reward
  serotonin       — elevated tonic during prolonged positive affect
  norepinephrine  — intense arousal/stress tonic peak
  epinephrine     — near-maximal peripheral response during acute fight-flight
  cortisol        — acute trauma HPA peak
  oxytocin        — childbirth/sustained bonding peak
  endorphins      — marathon finish / severe injury peak
  substance_p     — intense acute pain / grief peak
  vasopressin     — peak during acute social stress / pair bond formation
  crh             — acute HPA activation peak
  orexin          — wakefulness peak in active, food-deprived state
  adenosine       — maximal sleep pressure before involuntary sleep
  estradiol       — ovulatory LH surge peak (cycle)
  testosterone    — upper natural female range (activated/aroused)
  progesterone    — mid-luteal peak
  melatonin       — peak nocturnal secretion
  bdnf            — after sustained positive social/exercise experience
  prolactin       — post-peak refractory peak
  ghrelin         — fasting peak before meal
  anandamide      — runner's high / sustained exercise peak
  npy             — intense stress activation peak
  dynorphin       — peak dysphoric/opponent crash
  glutamate       — scaffold max
  gaba            — scaffold max
  acetylcholine   — scaffold max
"""

# ── Stability / control constants ─────────────────────────────────────────────
# Tuned so a 24/7 wall-clock daemon does not walk into a death spiral.

# Global scale on encoder→Class-1 deltas. Architecture target: one warm turn ≈ 0.5–1.5
# norm units of DA, not a full-scale spike. Unscaled weights were ~6 DA norm / turn.
EVENT_GAIN: float = 0.18

# Adenosine accumulation per 10s tick while awake (nM into phasic reservoir).
# ~0.07 → ≈16h from resting (norm≈2) to ceiling (norm≈10). Old value 0.5 maxed in ~4h.
ADENOSINE_ACCUM_PER_TICK: float = 0.07

# Auto-sleep thresholds (decoder 0–10 normalized).
SLEEP_ENTER_ADENOSINE: float = 8.0   # fall asleep at/above this
SLEEP_WAKE_ADENOSINE: float = 3.0    # wake at/below this after min sleep
SLEEP_MIN_DURATION_S: float = 4 * 3600  # minimum continuous sleep (sim time via dt)

# Setpoint adaptation: downward rate is this fraction of upward rate.
# Stops transient opponent drag (e.g. adenosine) from ratcheting baselines permanently.
SETPOINT_DOWN_SCALE: float = 0.10

# Tonic cannot be opponent-drained below this fraction of the chemical's natural
# tonic_setpoint. Old floor was 0.25 and became a sticky dead state.
OPPONENT_TONIC_FLOOR_FRAC: float = 0.70

# Setpoint hard floor as fraction of natural tonic_setpoint.
SETPOINT_FLOOR_FRAC: float = 0.70

# Total (tonic+phasic) hard cap as multiple of normalization_max. 1.0 = phys max.
CHEMICAL_TOTAL_CAP_MULT: float = 1.0


# ── Opponent processes (run each tick) ────────────────────────────────────────
#
# Format: (source_chemical, normalized_threshold, target_chemical, drag_per_tick_nM)
# "If source normalized >= threshold, increase target's decay by drag_per_tick_nM per tick."
# Drag is additive to normal phasic decay — pulls the target down continuously.
# Opponents hit phasic first; tonic only down to OPPONENT_TONIC_FLOOR_FRAC.

OPPONENT_PROCESSES: list[tuple[str, float, str, float]] = [
    # Cortisol suppresses bonding chemicals during sustained stress
    ("cortisol",    4.0, "oxytocin",   0.008),
    ("cortisol",    5.0, "serotonin",  0.020),
    ("cortisol",    4.0, "endorphins", 0.015),
    # 5-HT ↔ DA mutual regulation (bidirectional, asymmetric)
    ("serotonin",   6.0, "dopamine",   0.010),
    ("dopamine",    7.0, "serotonin",  0.008),
    # Endorphin/dynorphin opponent (kappa-opioid rebound)
    ("endorphins",  5.0, "dynorphin",  0.020),
    ("dynorphin",   4.0, "endorphins", 0.015),
    # Substance P drives cortisol and suppresses endorphins
    ("substance_p", 4.0, "endorphins", 0.012),
    # Adenosine suppresses dopamine and NE during sleep pressure buildup
    # (milder than original — suppression is felt, not baseline-erasing)
    ("adenosine",   6.0, "dopamine",   0.006),
    ("adenosine",   7.0, "norepinephrine", 0.005),
    # Orexin suppresses adenosine (wakefulness opposes sleep pressure)
    ("orexin",      5.0, "adenosine",  0.015),
]


# ── Class 2 accumulation — sustained Class 1 → slow peptide buildup ───────────
#
# Format: {target_chemical: {"drivers": {source: weight}, "threshold": float, "rate_nM_per_tick": float}}
# Each tick: if weighted sum of driver normalized values > threshold, accumulate at rate.
# Totals are hard-capped at normalization_max (see tick).

CLASS2_ACCUMULATION: dict[str, dict] = {
    "oxytocin": {
        # Warm/rewarding Class 1 elevation → OT buildup over many messages.
        # Threshold 3.5 so chatbot-scale Class 1 (post EVENT_GAIN) still accumulates;
        # hard cap at normalization_max prevents the old OT→120 runaway.
        "drivers": {"dopamine": 0.40, "serotonin": 0.30, "norepinephrine": 0.10},
        "threshold": 3.5,
        "rate_nM_per_tick": 0.0025,
    },
    "endorphins": {
        # Reward + bonding Class 1 → endorphin accumulation
        "drivers": {"dopamine": 0.35, "serotonin": 0.25, "norepinephrine": 0.20},
        "threshold": 4.0,
        "rate_nM_per_tick": 0.020,
    },
    "substance_p": {
        # Threat + social pain axis (proxied by NE and CRH levels) → substance P
        "drivers": {"norepinephrine": 0.40, "epinephrine": 0.30, "cortisol": 0.15},
        "threshold": 4.0,
        "rate_nM_per_tick": 0.010,
    },
    "vasopressin": {
        # Deep bonding + oxytocin co-release → vasopressin (pair bonding signal)
        "drivers": {"oxytocin": 0.50, "dopamine": 0.20},
        "threshold": 4.0,
        "rate_nM_per_tick": 0.002,
    },
    "dynorphin": {
        # High endorphin states → dynorphin opponent process buildup
        "drivers": {"endorphins": 0.70},
        "threshold": 5.5,
        "rate_nM_per_tick": 0.015,
    },
    "npy": {
        # Stress-induced neuropeptide Y (resilience buffer) — rises under sustained cortisol
        "drivers": {"cortisol": 0.50, "norepinephrine": 0.30},
        "threshold": 4.5,
        "rate_nM_per_tick": 0.010,
    },
}


# ── HPA cascade parameters ─────────────────────────────────────────────────────
# CRH accumulates from sustained NE/epinephrine (threat axis).
# Cortisol rises from sustained CRH elevation (30-min lag modeled as slow rate).

HPA: dict = {
    # Compared against *normalized* NE + 0.5*epi (0–10 scale), not raw nM.
    "crh_driver_threshold_normalized": 6.0,
    "crh_accumulation_nM_per_s": 0.005,  # per second when NE above threshold
    "crh_decay_half_life_s":     600,    # CRH clears in ~10 min without sustained drive
    "cortisol_driver_threshold_normalized": 3.5,  # CRH normalized level → cortisol rise
    "cortisol_rise_nM_per_s":    0.08,   # slow cortisol rise rate (30-min to peak)
}


# ── Circadian amplitudes (used in tick for time-of-day modulation) ─────────────
# Format: {chemical: {"peak_hour": float, "amplitude_nM": float}}
# Adds a sinusoidal offset to tonic level based on hour of day.

CIRCADIAN: dict[str, dict] = {
    "cortisol": {
        "peak_hour": 8.0,       # CAR (cortisol awakening response) peaks ~8am
        "amplitude_nM": 200.0,  # morning vs evening swing
    },
    "melatonin": {
        "peak_hour": 2.0,       # nocturnal peak ~2am
        "amplitude_nM": 80.0,
    },
    "orexin": {
        "peak_hour": 14.0,      # wakefulness peak in early afternoon
        "amplitude_nM": 80.0,
    },
    "serotonin": {
        "peak_hour": 12.0,      # mild diurnal rhythm, peaks midday
        "amplitude_nM": 1.0,
    },
}


# ── Big 5 → setpoint multipliers ──────────────────────────────────────────────
# Applied at sim init to compute effective tonic_setpoint for each chemical.
# Format: {trait: {chemical: {param: scale_factor}}}
# scale_factor is applied as: effective = base * (1 + trait_fraction * scale_factor)
# where trait_fraction = (trait_value - 50) / 50  (centered at 50, range -1 to +1)

BIG5_SETPOINT_BIAS: dict[str, dict[str, float]] = {
    # Neuroticism — high N → lower 5-HT baseline, higher cortisol, more NE reactivity
    "neuroticism": {
        "serotonin":      -0.30,   # high N → depressed 5-HT setpoint
        "cortisol":       +0.25,   # high N → elevated cortisol setpoint
        "norepinephrine": +0.15,   # high N → slightly elevated NE setpoint
        "dopamine":       -0.10,   # high N → slightly lower DA setpoint
    },
    # Extraversion — high E → higher DA and oxytocin setpoints
    "extraversion": {
        "dopamine":   +0.25,   # high E → higher tonic DA
        "serotonin":  +0.10,
        "oxytocin":   +0.15,   # high E → higher OT (social reward baseline)
    },
    # Agreeableness — high A → higher OT, lower substance P
    "agreeableness": {
        "oxytocin":    +0.20,
        "substance_p": -0.15,
        "serotonin":   +0.10,
    },
    # Conscientiousness — high C → more stable setpoints (model as slightly higher 5-HT)
    "conscientiousness": {
        "serotonin":  +0.15,
        "cortisol":   -0.10,   # high C → slightly lower chronic cortisol
    },
    # Openness — high O → higher DA novelty response (encoded in axis weights below)
    "openness": {
        "dopamine":  +0.10,
        "anandamide": +0.10,
    },
}

# Per-chemical gain multiplier from neuroticism (higher N → larger phasic spikes)
BIG5_GAIN_BIAS: dict[str, dict[str, float]] = {
    "neuroticism": {
        "norepinephrine": +0.30,  # high N → NE overreacts
        "epinephrine":    +0.25,
        "serotonin":      -0.15,  # high N → 5-HT less able to dampen spikes
        "cortisol":       +0.20,
    },
    "openness": {
        "dopamine":       +0.20,  # high O → bigger DA novelty spikes
    },
}

# Axis weight scaling from Big 5 (applied to novelty/bonding/etc. weights)
BIG5_AXIS_BIAS: dict[str, dict[str, dict[str, float]]] = {
    "openness": {
        "dopamine": {"novelty": +0.20},
    },
    "neuroticism": {
        "norepinephrine": {"threat": +0.15, "social_threat": +0.15},
        "epinephrine":    {"threat": +0.20},
    },
    "agreeableness": {
        "oxytocin":       {"bonding": +0.15},
        "substance_p":    {"social_threat": -0.15},
    },
}


# ── PFC frontend regulation strength → multiplier ─────────────────────────────
# raw_delta * pfc_factor (0-1; lower = more regulation)
# Neuroticism scales this DOWN (weaker regulation at high N).

PFC_REGULATION_BASE: dict[str, float] = {
    "none":     1.00,   # no regulation
    "weak":     0.85,   # DA — lightly modulated
    "moderate": 0.65,   # 5-HT — moderate dampening
    "strong":   0.45,   # NE, epinephrine — heavy top-down control
}


# ── Main chemical parameter table ─────────────────────────────────────────────
#
# Class 1 — fast neurotransmitters (encoder deltas applied directly)
# Class 2 — slow peptides (tick-only accumulation)
# Class 3 — hormonal / very slow (tick-only, cascade-driven)
# Class 4 — scaffolds (named scalar only, minimal dynamics)

CHEMICAL_PARAMS: dict[str, dict] = {

    # ── CLASS 1: Fast neurotransmitters ────────────────────────────────────

    "dopamine": {
        "class": 1,
        "grade": "A",
        "tonic_setpoint": 8.0,       # nM; NAc/striatum extracellular tonic (dark cycle mean)
        "normalization_max": 20.0,    # nM → 10; intense reward tonic peak
        "phasic_half_life_s": 60,     # DAT reuptake; seconds-to-minutes
        "tonic_decay_rate": 0.025,    # per-tick fraction toward setpoint
        "setpoint_adapt_rate": 0.0005,
        "feedback_ceiling": 0.85,
        "pfc_regulation": "weak",
        "axis_weights": {
            "reward":       0.65,
            "novelty":      0.45,
            "bonding":      0.15,
            "arousal":      0.10,
            "romance":       0.30,
            "loss":        -0.20,
            "threat":      -0.05,
            "aversion":    -0.10,
        },
    },

    "serotonin": {
        "class": 1,
        "grade": "A",
        "tonic_setpoint": 6.0,        # nM; dorsal raphe projection areas
        "normalization_max": 15.0,
        "phasic_half_life_s": 90,      # SERT reuptake; slightly slower than DA
        "tonic_decay_rate": 0.020,
        "setpoint_adapt_rate": 0.0003, # 5-HT1A autoreceptor adaptation is slow
        "feedback_ceiling": 0.80,
        "pfc_regulation": "moderate",
        "axis_weights": {
            "reward":        0.40,
            "bonding":       0.30,
            "arousal":      -0.05,  # 5-HT mildly opposes NE arousal
            "loss":         -0.30,
            "aversion":     -0.20,
            "shame":        -0.15,
            "social_threat":-0.20,
        },
    },

    "norepinephrine": {
        "class": 1,
        "grade": "A",
        "tonic_setpoint": 3.0,        # nM; LC projection areas
        "normalization_max": 20.0,    # peak during intense arousal/stress
        "phasic_half_life_s": 45,     # NET reuptake; fast
        "tonic_decay_rate": 0.030,
        "setpoint_adapt_rate": 0.0005,
        "feedback_ceiling": 0.80,
        "pfc_regulation": "strong",
        "axis_weights": {
            "threat":        0.60,
            "social_threat": 0.35,
            "arousal":       0.70,
            "novelty":       0.20,
            "romance":        0.15,
            "loss":          0.15,  # NE also rises with loss/grief
        },
    },

    "epinephrine": {
        "class": 1,
        "grade": "B",
        "tonic_setpoint": 0.3,        # nM; resting plasma (~160 pg/mL ≈ 0.87 nM, but CNS tonic is lower)
        "normalization_max": 5.0,     # acute panic / near-death; ~2750 pg/mL
        "phasic_half_life_s": 120,    # plasma clearance; slower than CNS monoamines
        "tonic_decay_rate": 0.040,
        "setpoint_adapt_rate": 0.0008,
        "feedback_ceiling": 0.75,
        "pfc_regulation": "strong",
        "axis_weights": {
            "threat":        0.80,
            "arousal":       0.40,
            "social_threat": 0.20,
            "romance":        0.20,
            "loss":          0.15,
        },
    },

    # ── CLASS 2: Slow peptides ────────────────────────────────────────────

    "oxytocin": {
        "class": 2,
        "grade": "A",
        "tonic_setpoint": 0.015,     # nM; CSF resting (~17 pg/mL ≈ 0.017 nM)
        "normalization_max": 0.30,   # nM; childbirth/sustained bonding peak
        "phasic_half_life_s": 600,   # slower degradation than monoamines
        "tonic_decay_rate": 0.010,
        "setpoint_adapt_rate": 0.0002,
        "feedback_ceiling": 0.80,
        "pfc_regulation": "none",    # OT does not receive PFC frontend regulation
    },

    "endorphins": {
        "class": 2,
        "grade": "A",
        "tonic_setpoint": 2.5,       # nM; resting CSF β-endorphin
        "normalization_max": 40.0,   # nM; marathon finish / severe pain (CNS endorphin estimate)
        "phasic_half_life_s": 900,   # slow peptidase degradation
        "tonic_decay_rate": 0.008,
        "setpoint_adapt_rate": 0.0001,
        "feedback_ceiling": 0.75,
        "pfc_regulation": "none",
    },

    "substance_p": {
        "class": 2,
        "grade": "B",
        "tonic_setpoint": 0.10,      # nM; resting CSF substance P
        "normalization_max": 3.0,    # nM; intense acute pain / social grief peak
        "phasic_half_life_s": 600,
        "tonic_decay_rate": 0.012,
        "setpoint_adapt_rate": 0.0005,
        "feedback_ceiling": 0.70,
        "pfc_regulation": "none",
    },

    "vasopressin": {
        "class": 2,
        "grade": "B",
        "tonic_setpoint": 0.8,       # nM; CSF AVP resting
        "normalization_max": 12.0,   # nM; acute social stress / pair bond peak
        "phasic_half_life_s": 1200,
        "tonic_decay_rate": 0.008,
        "setpoint_adapt_rate": 0.0001,
        "feedback_ceiling": 0.80,
        "pfc_regulation": "none",
    },

    "dynorphin": {
        "class": 2,
        "grade": "C",
        "tonic_setpoint": 0.5,       # nM
        "normalization_max": 5.0,
        "phasic_half_life_s": 600,
        "tonic_decay_rate": 0.012,
        "setpoint_adapt_rate": 0.0005,
        "feedback_ceiling": 0.75,
        "pfc_regulation": "none",
    },

    "npy": {
        "class": 2,
        "grade": "C",
        "tonic_setpoint": 10.0,      # nM; CSF NPY resting range
        "normalization_max": 50.0,
        "phasic_half_life_s": 3600,
        "tonic_decay_rate": 0.005,
        "setpoint_adapt_rate": 0.0001,
        "feedback_ceiling": 0.80,
        "pfc_regulation": "none",
    },

    "orexin": {
        "class": 2,
        "grade": "B",
        "tonic_setpoint": 300.0,     # pg/mL (used directly; ~0.09 nM but kept in pg/mL for interpretability)
        "normalization_max": 600.0,
        "phasic_half_life_s": 3600,
        "tonic_decay_rate": 0.005,
        "setpoint_adapt_rate": 0.00005,
        "feedback_ceiling": 0.85,
        "pfc_regulation": "none",
        "circadian_driven": True,
    },

    "adenosine": {
        "class": 2,
        "grade": "B",
        # Sleep-pressure model scale (SPEC-63 Phase 2): not literal CSF
        # microdialysis. Tonic ~100 is the resting floor; phasic is the wake
        # reservoir that climbs toward normalization_max (~500) over ~16h awake.
        "tonic_setpoint": 100.0,
        "normalization_max": 500.0,  # forced-sleep ceiling on the model scale
        "phasic_half_life_s": 7200,  # clears slowly during wakefulness; fast during sleep
        "tonic_decay_rate": 0.003,   # slow approach during wakefulness
        "setpoint_adapt_rate": 0.00005,
        "feedback_ceiling": 0.90,
        "pfc_regulation": "none",
        "sleep_pressure": True,      # tick accumulates with wakefulness
    },

    "anandamide": {
        "class": 2,
        "grade": "C",
        "tonic_setpoint": 1.5,       # nM; plasma resting (brain is higher but unmeasured)
        "normalization_max": 8.0,    # runner's high / sustained exercise
        "phasic_half_life_s": 1800,
        "tonic_decay_rate": 0.008,
        "setpoint_adapt_rate": 0.0001,
        "feedback_ceiling": 0.80,
        "pfc_regulation": "none",
    },

    "ghrelin": {
        "class": 2,
        "grade": "C",
        "tonic_setpoint": 400.0,     # pg/mL; fasted baseline
        "normalization_max": 1200.0, # pre-meal peak during extended fast
        "phasic_half_life_s": 1800,
        "tonic_decay_rate": 0.010,
        "setpoint_adapt_rate": 0.0002,
        "feedback_ceiling": 0.85,
        "pfc_regulation": "none",
        "hunger_driven": True,
    },

    # ── CLASS 3: Hormonal / very slow ────────────────────────────────────

    "cortisol": {
        "class": 3,
        "grade": "A",
        "tonic_setpoint": 250.0,     # nM; diurnal mean (morning ~400, evening ~100)
        "normalization_max": 1200.0, # nM; acute trauma HPA peak
        "phasic_half_life_s": 5400,  # ~90 min plasma half-life
        "tonic_decay_rate": 0.003,
        "setpoint_adapt_rate": 0.00005,
        "feedback_ceiling": 0.65,    # strong GR negative feedback
        "pfc_regulation": "none",    # cortisol is not directly regulated by PFC frontend
        "circadian_driven": True,
        "hpa_target": True,          # rises from CRH cascade (tick handles)
    },

    "crh": {
        "class": 3,
        "grade": "B",
        "tonic_setpoint": 30.0,      # pg/mL; resting CSF CRH
        "normalization_max": 200.0,  # acute HPA activation
        "phasic_half_life_s": 600,
        "tonic_decay_rate": 0.015,
        "setpoint_adapt_rate": 0.0005,
        "feedback_ceiling": 0.70,
        "pfc_regulation": "none",
        "hpa_cascade": True,         # drives cortisol rise (tick handles)
    },

    "estradiol": {
        "class": 3,
        "grade": "B",
        "tonic_setpoint": 0.18,      # nM; follicular phase mean
        "normalization_max": 1.5,    # nM; ovulatory LH surge peak
        "phasic_half_life_s": 86400, # days-long dynamics
        "tonic_decay_rate": 0.0002,
        "setpoint_adapt_rate": 0.00001,
        "feedback_ceiling": 0.90,
        "pfc_regulation": "none",
        "circadian_driven": False,
    },

    "testosterone": {
        "class": 3,
        "grade": "B",
        "tonic_setpoint": 0.5,       # nM; typical female range
        "normalization_max": 2.5,    # nM; upper natural female range (activated)
        "phasic_half_life_s": 7200,
        "tonic_decay_rate": 0.0005,
        "setpoint_adapt_rate": 0.00005,
        "feedback_ceiling": 0.85,
        "pfc_regulation": "none",
    },

    "progesterone": {
        "class": 3,
        "grade": "C",
        "tonic_setpoint": 2.0,       # nM; luteal baseline
        "normalization_max": 50.0,   # nM; mid-luteal peak
        "phasic_half_life_s": 86400,
        "tonic_decay_rate": 0.0002,
        "setpoint_adapt_rate": 0.00001,
        "feedback_ceiling": 0.90,
        "pfc_regulation": "none",
    },

    "melatonin": {
        "class": 3,
        "grade": "C",
        # Working concentration units (displayed as nM). Historical comments
        # said pg/mL; dynamics share one unit space with the rest of the sim.
        "tonic_setpoint": 5.0,       # daytime low on the working scale
        "normalization_max": 250.0,  # nocturnal peak on the working scale
        "phasic_half_life_s": 1800,
        "tonic_decay_rate": 0.005,
        "setpoint_adapt_rate": 0.00005,
        "feedback_ceiling": 0.90,
        "pfc_regulation": "none",
        "circadian_driven": True,
    },

    "bdnf": {
        "class": 3,
        "grade": "C",
        "tonic_setpoint": 9.0,       # ng/mL; serum resting
        "normalization_max": 25.0,
        "phasic_half_life_s": 172800, # days
        "tonic_decay_rate": 0.0001,
        "setpoint_adapt_rate": 0.000001,
        "feedback_ceiling": 0.90,
        "pfc_regulation": "none",
    },

    "prolactin": {
        "class": 3,
        "grade": "C",
        "tonic_setpoint": 8.0,       # ng/mL; resting female
        "normalization_max": 80.0,   # post-peak peak
        "phasic_half_life_s": 3600,
        "tonic_decay_rate": 0.003,
        "setpoint_adapt_rate": 0.0001,
        "feedback_ceiling": 0.80,
        "pfc_regulation": "none",
    },

    # ── CLASS 4: Scaffolds ──────────────────────────────────────────────

    "glutamate": {
        "class": 4,
        "grade": "D",
        "tonic_setpoint": 2000.0,
        "normalization_max": 8000.0,
        "phasic_half_life_s": 5,
        "tonic_decay_rate": 0.10,
        "setpoint_adapt_rate": 0.001,
        "feedback_ceiling": 0.90,
        "pfc_regulation": "none",
    },

    "gaba": {
        "class": 4,
        "grade": "D",
        "tonic_setpoint": 200.0,
        "normalization_max": 800.0,
        "phasic_half_life_s": 5,
        "tonic_decay_rate": 0.10,
        "setpoint_adapt_rate": 0.001,
        "feedback_ceiling": 0.90,
        "pfc_regulation": "none",
    },

    "acetylcholine": {
        "class": 4,
        "grade": "D",
        "tonic_setpoint": 0.10,
        "normalization_max": 2.0,
        "phasic_half_life_s": 5,
        "tonic_decay_rate": 0.10,
        "setpoint_adapt_rate": 0.001,
        "feedback_ceiling": 0.90,
        "pfc_regulation": "none",
    },
}
