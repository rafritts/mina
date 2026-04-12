# SPEC-25: Simulation Constants

> Every numeric literal with biological or operational significance lives here.
> No magic numbers anywhere in the codebase. If a value needs to change, it changes
> in one place: `src/sim/constants.py`.

**Depends on:** SPEC-20  
**Required by:** All simulation modules

---

## Rule

If a number appears in simulation logic — a rate, threshold, coupling multiplier,
timing delay, weight coefficient, or safety bound — it must be a named constant
from this file. The only exceptions are `0`, `1`, `0.0`, `1.0` used as neutral
identity values, and `3600` used explicitly to convert seconds to hours.

---

## `src/sim/constants.py`

```python
"""
Simulation constants — single source of truth for all numeric parameters.

Grouped by subsystem. Each constant documents its unit and biological source.
"""

# ===========================================================================
# CIRCADIAN
# ===========================================================================

CIRCADIAN_HALF_PERIOD          = 12.0    # hours — half of 24hr cycle; used in cos(π/12)
CORTISOL_CIRCADIAN_BASE        = 180.0   # nmol/L — trough component of circadian wave
CORTISOL_CIRCADIAN_AMPLITUDE   = 270.0   # nmol/L — peak swing above base
CORTISOL_CIRCADIAN_PEAK_HOUR   = 8       # hour of day — cortisol awakening response
CORTISOL_CIRCADIAN_FLOOR       = 50.0    # nmol/L — absolute minimum (adrenal safety floor)

MELATONIN_CIRCADIAN_AMPLITUDE  = 110.0   # pg/mL — peak melatonin (× 2 = 220 at apex)
MELATONIN_DEFAULT_PEAK_HOUR    = 4       # hour of day — default sleep window start

OREXIN_CIRCADIAN_BASE          = 200.0   # pg/mL — baseline wake-promoting level
OREXIN_CIRCADIAN_AMPLITUDE     = 150.0   # pg/mL — afternoon peak swing
OREXIN_CIRCADIAN_PEAK_HOUR     = 15      # hour of day — peaks mid-afternoon

CORE_TEMP_BASELINE             = 36.75   # °C — daily average
CORE_TEMP_AMPLITUDE            = 0.4     # °C — circadian swing (nadir 36.35, peak 37.15)
CORE_TEMP_TROUGH_HOUR          = 4       # hour of day — lowest (promotes sleep onset)

CRH_CIRCADIAN_BASE             = 15.0    # pg/mL — trough component
CRH_CIRCADIAN_AMPLITUDE        = 20.0    # pg/mL — peak swing
CRH_CIRCADIAN_PEAK_HOUR        = 8       # hour of day — mirrors cortisol

# ===========================================================================
# HOMEOSTATIC DECAY & APPROACH RATES (per sim-hour)
# ===========================================================================

GLUCOSE_DECAY_AWAKE            = 6.5     # mg/dL/hr — brain + body consumption while awake
GLUCOSE_DECAY_ASLEEP           = 0.8     # mg/dL/hr — hepatic output nearly compensates
HYDRATION_DECAY_RATE           = 0.4     # % TBW/hr — insensible losses at rest

ADENOSINE_BUILD_RATE_BASE      = 3.0     # nmol/L/hr — metabolic byproduct of neural ATP use
ADENOSINE_CLEAR_RATE_SLEEP     = 20.0    # nmol/L/hr — glymphatic clearance during sleep
ADENOSINE_FLOOR_SLEEP          = 15.0    # nmol/L — minimum achievable during sleep

SLEEP_PRESSURE_BUILD_RATE      = 1.8     # AU/hr — legacy; derived from adenosine when needed
SLEEP_PRESSURE_CLEAR_RATE      = 24.0    # AU/hr — during sleep

ENDORPHIN_FAST_DECAY_RATE      = 18.0    # pg/mL/hr — decay when above baseline
ENDORPHIN_SLOW_RECOVERY_RATE   = 0.05    # fraction of gap/hr — recovery when below baseline
ENDORPHIN_RESTING_BASELINE     = 12.0    # pg/mL — homeostatic target

ANANDAMIDE_APPROACH_RATE       = 2.8     # /hr — fast FAAH enzymatic degradation (~15min half-life)
TWO_AG_APPROACH_RATE           = 0.8     # /hr — slower MAGL degradation
GABA_APPROACH_RATE             = 0.12    # /hr
GLUTAMATE_APPROACH_RATE        = 0.15    # /hr
CRH_APPROACH_RATE              = 2.8     # /hr — fast (~15min half-life)
ACTH_APPROACH_RATE             = 1.2     # /hr — ~30min half-life
TSH_APPROACH_RATE              = 0.05    # /hr — very slow (days)
T4_APPROACH_RATE               = 0.02    # /hr — half-life ~7 days
T3_APPROACH_RATE               = 0.08    # /hr — half-life ~1 day
CORE_TEMP_APPROACH_RATE        = 0.3     # /hr

# Sickness/pain approach rates
SUBSTANCE_P_APPROACH_RATE      = 0.15    # /hr
PGE2_APPROACH_RATE             = 0.20    # /hr
IL1B_APPROACH_RATE             = 0.30    # /hr
IL6_APPROACH_RATE              = 0.25    # /hr
TNF_ALPHA_APPROACH_RATE        = 0.20    # /hr
IL10_APPROACH_RATE             = 0.35    # /hr
CRP_APPROACH_RATE              = 0.04    # /hr — 12-24hr half-life (chronic marker)

# Neuroplasticity (very slow — days/weeks)
BDNF_APPROACH_RATE             = 0.01    # /hr
RECEPTOR_DOWNREGULATION_RATE   = 0.0004  # /hr — tolerance builds slowly
RECEPTOR_UPREGULATION_RATE     = 0.0002  # /hr — sensitization even slower
RECEPTOR_HOMEOSTATIC_RATE      = 0.001   # /hr — passive drift back toward 1.0
TOLERANCE_DECAY_RATE           = 0.01    # /hr — substance tolerance fades slowly

ESTRADIOL_APPROACH_RATE        = 0.08    # /hr
PROGESTERONE_APPROACH_RATE     = 0.06    # /hr

# ===========================================================================
# HPA AXIS CASCADE DELAYS (seconds, wall-clock)
# ===========================================================================

HPA_CRH_TO_ACTH_DELAY_SECONDS        = 600    # 10 minutes — pituitary response lag
HPA_ACTH_TO_CORTISOL_DELAY_SECONDS   = 1800   # 30 minutes — total (CRH→ACTH→cortisol)

# Stressor → cascade coupling fractions
STRESSOR_TO_CRH_FRACTION       = 0.12   # cortisol_delta × this → immediate CRH spike
STRESSOR_TO_ACTH_FRACTION      = 0.08   # cortisol_delta × this → queued ACTH delta
STRESSOR_TO_CORTISOL_FRACTION  = 0.60   # cortisol_delta × this → queued cortisol delta

# ===========================================================================
# CROSS-CHEMICAL COUPLING MULTIPLIERS
# ===========================================================================

# Cortisol interactions
CORTISOL_NOREPI_COUPLING            = 0.45   # norepinephrine baseline ≈ cortisol × this
CORTISOL_ACH_SUPPRESS_THRESHOLD     = 450.0  # nmol/L — chronic cortisol starts suppressing ACh
CORTISOL_ACH_SUPPRESS_RATE          = 0.04   # nmol/L ACh lost per nmol/L cortisol above threshold
CORTISOL_GABA_SUPPRESS_THRESHOLD    = 450.0  # nmol/L
CORTISOL_GABA_SUPPRESS_RATE         = 0.002  # µmol/L GABA lost per nmol/L cortisol above threshold
CORTISOL_GLUTAMATE_ELEVATE_THRESHOLD = 400.0 # nmol/L
CORTISOL_GLUTAMATE_ELEVATE_RATE     = 0.003  # µmol/L Glu per nmol/L cortisol above threshold
CORTISOL_CRH_FEEDBACK_THRESHOLD     = 400.0  # nmol/L — negative feedback begins
CORTISOL_CRH_FEEDBACK_RATE          = 0.015  # pg/mL CRH suppressed per nmol/L cortisol above threshold
CORTISOL_ACTH_FEEDBACK_RATE         = 0.02
CORTISOL_ANANDAMIDE_SUPPRESS_THRESHOLD = 500.0  # nmol/L
CORTISOL_ANANDAMIDE_SUPPRESS_RATE   = 0.001
CORTISOL_TSH_SUPPRESS_THRESHOLD     = 500.0  # nmol/L
CORTISOL_TSH_SUPPRESS_RATE          = 0.002
CORTISOL_PAIN_SENSITIZE_THRESHOLD   = 500.0  # nmol/L — chronic stress sensitizes nociceptors
CORTISOL_PAIN_SENSITIZE_RATE        = 0.02

# Hypoglycemia effects
GLUCOSE_HYPOGLYCEMIA_THRESHOLD      = 55.0   # mg/dL — clinical hypoglycemia
GLUCOSE_CORTISOL_STRESS_DELTA       = 120.0  # nmol/L — HPA activation from hypoglycemia
GLUCOSE_SEROTONIN_DRAIN_RATE        = 0.6    # ng/mL/hr
GLUCOSE_DOPAMINE_DRAIN_RATE         = 1.5    # pg/mL/hr
GLUCOSE_CRH_ELEVATE_THRESHOLD       = 60.0   # mg/dL — slightly higher for HPA awareness

# Dehydration effects
HYDRATION_STRESS_THRESHOLD          = 56.0   # % TBW
HYDRATION_CORTISOL_DELTA            = 60.0   # nmol/L added to cortisol baseline
HYDRATION_NOREPI_DELTA              = 30.0   # pg/mL added to norepinephrine baseline

# Sleep pressure / adenosine effects
ADENOSINE_SEROTONIN_DRAIN_THRESHOLD = 50.0   # AU (legacy sleep_pressure scale)
ADENOSINE_SEROTONIN_DRAIN_RATE      = 0.3    # ng/mL/hr
ADENOSINE_DOPAMINE_DRAIN_THRESHOLD  = 70.0   # AU
ADENOSINE_DOPAMINE_DRAIN_RATE       = 1.0    # pg/mL/hr
ADENOSINE_IL1B_ELEVATE_THRESHOLD    = 65.0   # nmol/L — sleep deprivation raises inflammation
ADENOSINE_IL1B_ELEVATE_RATE         = 0.08
ADENOSINE_OREXIN_SUPPRESS_THRESHOLD = 40.0   # nmol/L
ADENOSINE_OREXIN_SUPPRESS_RATE      = 2.0    # pg/mL orexin per nmol/L adenosine above threshold
ADENOSINE_VAGAL_DYSREGULATE_THRESHOLD = 50.0 # nmol/L
ADENOSINE_VAGAL_DYSREGULATE_RATE    = 0.3

# GABA interactions
GABA_CORTISOL_SUPPRESS_THRESHOLD    = 5.0    # µmol/L
GABA_CORTISOL_SUPPRESS_RATE         = 3.0    # nmol/L cortisol/hr
GABA_NOREPI_SUPPRESS_RATE           = 15.0   # pg/mL norepi/hr
GABA_SLEEP_BONUS                    = 0.8    # µmol/L added to baseline during sleep
GABA_GLUTAMATE_SUPPRESS_THRESHOLD   = 6.0    # µmol/L glutamate above which GABA is suppressed
GABA_GLUTAMATE_SUPPRESS_RATE        = 0.15

# Glutamate interactions
GLUTAMATE_NEUROINFLAMMATION_THRESHOLD = 10.0   # µmol/L — excitotoxicity begins
GLUTAMATE_IL6_RATE                    = 0.5    # pg/mL IL-6/hr
GLUTAMATE_TEMP_RATE                   = 0.01   # °C/hr
GLUTAMATE_LTP_THRESHOLD               = 8.0    # µmol/L — NMDA-driven LTP enhancement
GLUTAMATE_LTP_RATE                    = 0.3    # AU/hr synaptic potentiation
GLUTAMATE_SLEEP_CLEAR                 = 1.2    # µmol/L cleared per hr during sleep

# Oxytocin interactions
OXYTOCIN_CORTISOL_SUPPRESS_THRESHOLD = 8.0    # pg/mL
OXYTOCIN_CORTISOL_SUPPRESS_RATE      = 6.0    # nmol/L/hr (strongest natural suppressor)
OXYTOCIN_ANANDAMIDE_BOOST_THRESHOLD  = 20.0   # pg/mL
OXYTOCIN_ANANDAMIDE_BOOST_RATE       = 0.01
OXYTOCIN_VASOPRESSIN_THRESHOLD       = 20.0   # pg/mL
OXYTOCIN_VASOPRESSIN_RATE            = 0.05
OXYTOCIN_PROLACTIN_THRESHOLD         = 30.0   # pg/mL
OXYTOCIN_PROLACTIN_RATE              = 0.3

# Serotonin interactions
SEROTONIN_HPA_DAMPEN_THRESHOLD       = 32.0   # ng/mL — good serotonin brakes stress axis
SEROTONIN_HPA_DAMPEN_RATE            = 4.0    # nmol/L cortisol/hr

# Endorphin interactions
ENDORPHIN_CORTISOL_SUPPRESS_THRESHOLD = 70.0  # pg/mL — runner's high window
ENDORPHIN_CORTISOL_SUPPRESS_RATE      = 12.0  # nmol/L/hr

# Anandamide / 2-AG interactions
ANANDAMIDE_PAIN_GATE_THRESHOLD        = 3.0   # nM
ANANDAMIDE_PAIN_GATE_RATE             = 3.0   # AU pain/hr
ANANDAMIDE_CORTISOL_SUPPRESS_THRESHOLD = 4.0  # nM
ANANDAMIDE_CORTISOL_SUPPRESS_RATE     = 10.0  # nmol/L/hr
TWO_AG_IMMUNE_THRESHOLD               = 15.0  # nM
TWO_AG_IL6_SUPPRESS_RATE              = 0.5   # pg/mL/hr
TWO_AG_TNF_SUPPRESS_RATE              = 0.3   # pg/mL/hr

# Pain interactions
PAIN_CORTISOL_THRESHOLD               = 20.0  # AU — HPA response threshold
PAIN_CORTISOL_RATE                    = 0.4   # nmol/L/hr
PAIN_NOREPI_RATE                      = 0.8   # pg/mL/hr
PAIN_ENDORPHIN_RATE                   = 0.2   # pg/mL/hr
PAIN_ADENOSINE_THRESHOLD              = 50.0  # AU — sleep disruption
PAIN_ADENOSINE_RATE                   = 0.01  # nmol/L/hr
PAIN_DOPAMINE_THRESHOLD               = 50.0  # AU — chronic anhedonia
PAIN_DOPAMINE_DRAIN_RATE              = 0.05  # pg/mL/hr
PAIN_ATTENTION_CORTISOL_THRESHOLD     = 400.0 # nmol/L — hypervigilance amplifies pain
PAIN_ATTENTION_FACTOR                 = 0.0005

# Immune (sickness behavior)
IL1B_SEROTONIN_THRESHOLD              = 8.0   # pg/mL
IL1B_SEROTONIN_DRAIN_RATE             = 0.04  # ng/mL/hr — IDO tryptophan diversion
IL6_DOPAMINE_THRESHOLD                = 15.0  # pg/mL
IL6_DOPAMINE_DRAIN_RATE               = 0.08  # pg/mL/hr
IL6_HPA_COUPLING                      = 1.5   # pg/mL CRH per pg/mL IL-6 above threshold
TNF_CORTISOL_THRESHOLD                = 12.0  # pg/mL
TNF_CORTISOL_RATE                     = 0.3   # nmol/L/hr
INFLAMMATION_ADENOSINE_THRESHOLD      = 40.0  # AU
INFLAMMATION_ADENOSINE_RATE           = 0.015 # nmol/L/hr
INFLAMMATION_OXYTOCIN_THRESHOLD       = 50.0  # AU
INFLAMMATION_OXYTOCIN_DRAIN_RATE      = 0.02  # pg/mL/hr

# Cytokine cascade couplings
IL1B_IL6_CASCADE_THRESHOLD            = 5.0   # pg/mL IL-1β
IL1B_IL6_CASCADE_RATE                 = 0.5   # pg/mL IL-6/hr
GHRELIN_IL6_THRESHOLD                 = 700.0 # pg/mL — severe hunger → mild inflammation
GHRELIN_IL6_RATE                      = 0.002

# Inflammation index normalization
INFLAMMATION_IL1B_SCALE               = 0.48  # (il1b - 2) / this → 0-100
INFLAMMATION_IL6_SCALE                = 0.97  # (il6 - 3) / this → 0-100
INFLAMMATION_IL10_DAMPING_RATE        = 0.015 # IL-10 damping: max(0.4, 1 - (il10-10)*this)
INFLAMMATION_IL10_DAMPING_FLOOR       = 0.4

# BDNF
BDNF_CORTISOL_SUPPRESS_THRESHOLD      = 450.0 # nmol/L
BDNF_CORTISOL_SUPPRESS_RATE           = 3.0   # pg/mL BDNF/hr
BDNF_INFLAMMATION_SUPPRESS_RATE       = 30.0  # pg/mL BDNF per AU inflammation
BDNF_ADENOSINE_SUPPRESS_THRESHOLD     = 60.0  # nmol/L
BDNF_ADENOSINE_SUPPRESS_RATE          = 40.0  # pg/mL BDNF/hr
BDNF_GH_BOOST_RATE                    = 100.0 # pg/mL BDNF per ng/mL GH during sleep

# Allostatic load
ALLOSTATIC_CORTISOL_LOAD_THRESHOLD    = 500.0 # nmol/L
ALLOSTATIC_CORTISOL_LOAD_RATE         = 0.002
ALLOSTATIC_ADENOSINE_LOAD_RATE        = 0.01
ALLOSTATIC_IMMUNE_LOAD_RATE           = 0.005
ALLOSTATIC_PAIN_LOAD_RATE             = 0.003
ALLOSTATIC_SLEEP_RECOVERY_RATE        = 0.3   # per hr during sleep
ALLOSTATIC_BOND_RECOVERY_THRESHOLD    = 30.0  # pg/mL oxytocin
ALLOSTATIC_BOND_RECOVERY_RATE         = 0.002
ALLOSTATIC_BASELINE_RECOVERY_RATE     = 0.01

# Thyroid
T4_TSH_MULTIPLIER                     = 4.0   # TSH 2.0 → T4 8.0 µg/dL
T3_T4_MULTIPLIER                      = 15.0  # T4 8 → T3 120 ng/dL
T3_NORMAL_BASELINE                    = 120.0 # ng/dL
T3_SEROTONIN_NORMALIZATION            = 9000.0 / 120.0  # T3 factor for serotonin baseline

# Sex hormones
MENSTRUAL_CYCLE_LENGTH                = 28    # days
ESTRADIOL_SEROTONIN_BOOST_THRESHOLD   = 80.0  # pg/mL
ESTRADIOL_SEROTONIN_BOOST_RATE        = 0.003 # ng/mL serotonin per pg/mL estradiol above threshold
ESTRADIOL_CORTISOL_DAMPING_RATE       = 0.1
ESTRADIOL_LOW_SEROTONIN_PENALTY       = 2.0   # ng/mL — when estradiol < 50
PROGESTERONE_GABA_BOOST_THRESHOLD     = 2.0   # ng/mL
PROGESTERONE_GABA_BOOST_RATE          = 0.1   # µmol/L GABA per ng/mL progesterone above threshold

# Metabolic
GHRELIN_HUNGER_THRESHOLD              = 700.0 # pg/mL — behavioral hunger signal
GHRELIN_DOPAMINE_SUPPRESS_THRESHOLD   = 600.0 # pg/mL
GHRELIN_DOPAMINE_SUPPRESS_AMOUNT      = 5.0   # pg/mL dopamine baseline reduction
GHRELIN_CORTISOL_THRESHOLD            = 800.0 # pg/mL
GHRELIN_CORTISOL_AMOUNT               = 40.0  # nmol/L cortisol elevation
GHRELIN_MEAL_PEAK_AMPLITUDE           = 150.0 # pg/mL — Gaussian peak above base
GHRELIN_MEAL_HOURS                    = (7.0, 12.5, 18.0)  # breakfast, lunch, dinner
LEPTIN_GHRELIN_SUPPRESS_THRESHOLD     = 20.0  # ng/mL
LEPTIN_GHRELIN_SUPPRESS_FACTOR        = 0.6   # ghrelin baseline multiplier when leptin high
INSULIN_GLUCOSE_MULTIPLIER            = 1.2   # (glucose - 80) × this → insulin target
INSULIN_GLUCOSE_CLEARANCE_THRESHOLD   = 40.0  # µIU/mL — above this, accelerates glucose decay
INSULIN_GLUCOSE_CLEARANCE_RATE        = 0.08

# Vasopressin
VASOPRESSIN_DEHYDRATION_THRESHOLD     = 58.0  # % TBW
VASOPRESSIN_DEHYDRATION_RATE          = 0.3   # pg/mL per % TBW below threshold
VASOPRESSIN_HYDRATION_RETENTION_FACTOR = 0.8  # hydration decay multiplied by this at high vasopressin

# Prolactin
PROLACTIN_SLEEP_BONUS                 = 15.0  # ng/mL — sleep-triggered elevation
PROLACTIN_DOPAMINE_SUPPRESS_THRESHOLD = 100.0 # pg/mL dopamine
PROLACTIN_DOPAMINE_SUPPRESS_RATE      = 0.05
PROLACTIN_DOPAMINE_REFRACTORY_THRESHOLD = 40.0 # ng/mL prolactin
PROLACTIN_DOPAMINE_REFRACTORY_AMOUNT  = 5.0   # pg/mL dopamine baseline reduction

# DHEA
DHEA_CORTISOL_EXHAUST_THRESHOLD       = 500.0 # nmol/L
DHEA_CORTISOL_EXHAUST_RATE            = 0.1   # µg/dL DHEA per nmol/L cortisol above threshold
DHEA_FATIGUE_THRESHOLD                = 50.0  # µg/dL

# Acetylcholine
ACH_SLEEP_PRESSURE_SUPPRESS_RATE      = 0.22  # nmol/L ACh per AU sleep_pressure

# Personality drift
PERSONALITY_DRIFT_ALLOSTATIC_THRESHOLD = 60.0  # AU
PERSONALITY_DRIFT_RATE                 = 0.0001 # per sim-hour
PERSONALITY_RECOVERY_ALLOSTATIC_THRESHOLD = 15.0
PERSONALITY_RECOVERY_RATE             = 0.00005
PERSONALITY_RECOVERY_TOLERANCE        = 0.1    # minimum change to trigger recovery

# ===========================================================================
# PAIN
# ===========================================================================

SUBSTANCE_P_BASELINE                  = 30.0   # pg/mL — zero-pain reference
SUBSTANCE_P_PAIN_INTENSITY_DIVISOR    = 3.0    # (sub_p - baseline) / this → raw pain
CENTRAL_SENSITIZATION_BUILD_PAIN_THRESHOLD    = 40.0  # AU
CENTRAL_SENSITIZATION_BUILD_SUBSTANCE_P_THRESHOLD = 80.0  # pg/mL
CENTRAL_SENSITIZATION_BUILD_RATE      = 0.02   # AU/hr
CENTRAL_SENSITIZATION_DECAY_RATE      = 0.05   # AU/hr
CENTRAL_SENSITIZATION_AMPLIFICATION   = 0.015  # CS × this → multiplier (CS 50 → 1.75×)
CENTRAL_SENSITIZATION_OFFSET          = 0.3    # CS × this → baseline pain added
PGE2_PAIN_AMPLIFICATION_THRESHOLD     = 200.0  # pg/mL
PGE2_PAIN_AMPLIFICATION_DIVISOR       = 1000.0
PAIN_GATE_ENDORPHIN_BASELINE          = 12.0   # pg/mL — gate neutral
PAIN_GATE_ENDORPHIN_RATE              = 0.5    # gate strength per pg/mL above baseline
PAIN_GATE_ANANDAMIDE_BASELINE         = 1.5    # nM
PAIN_GATE_ANANDAMIDE_RATE             = 2.0
PAIN_GATE_GABA_BASELINE               = 2.0    # µmol/L
PAIN_GATE_GABA_RATE                   = 1.5

# ===========================================================================
# SLEEP & WAKEFULNESS
# ===========================================================================

AUTO_SLEEP_PROPENSITY_IN_WINDOW       = 70.0   # AU — threshold during sleep window
AUTO_SLEEP_PROPENSITY_OVERRIDE        = 90.0   # AU — exhaustion override any time
SLEEP_PROPENSITY_S_PROCESS_WEIGHT     = 0.6
SLEEP_PROPENSITY_C_PROCESS_WEIGHT     = 0.4
SLEEP_PROPENSITY_OREXIN_OPPOSITION    = 0.6    # orexin × this opposes melatonin drive
ADENOSINE_SLEEP_DRIVE_MIN             = 20.0   # nmol/L — maps to 0 AU
ADENOSINE_SLEEP_DRIVE_DIVISOR         = 0.70   # (adenosine - min) / this → 0-100 AU
MELATONIN_SLEEP_PROPENSITY_DIVISOR    = 220.0  # normalizes melatonin to 0-100
OREXIN_SLEEP_PROPENSITY_DIVISOR       = 400.0  # normalizes orexin to 0-100
MELATONIN_AUTO_SLEEP_LEGACY_THRESHOLD = 195.0  # pg/mL — kept for backward compat

GLUCOSE_HYPOGLYCEMIC_WAKE_THRESHOLD   = 55.0   # mg/dL — forces awakening

MORNING_CORTISOL_SURGE_MIN            = 40.0   # nmol/L — awakening response range
MORNING_CORTISOL_SURGE_MAX            = 120.0  # nmol/L
MORNING_ENDORPHIN_BOOST_MIN           = 3.0    # pg/mL
MORNING_ENDORPHIN_BOOST_MAX           = 12.0   # pg/mL

# ===========================================================================
# RECEPTOR SENSITIVITY
# ===========================================================================

RECEPTOR_SENSITIVITY_MIN              = 0.2    # hard floor (severely downregulated)
RECEPTOR_SENSITIVITY_MAX              = 2.0    # hard ceiling (maximally upregulated)
RECEPTOR_SENSITIVITY_NEUTRAL          = 1.0    # normal/healthy baseline

# ===========================================================================
# SUBSTANCES
# ===========================================================================

SUBSTANCE_ACTIVE_THRESHOLD            = 0.5    # level below which substance is removed
SUBSTANCE_SUSTAINED_EFFECT_THRESHOLD  = 20.0   # level above which sustained effects apply
SUBSTANCE_WITHDRAWAL_WEIGHT_DIVISOR   = 40.0   # (40 - level) / 40 → withdrawal weight

# Alcohol sustained effects (per level fraction, per sim-hour)
ALCOHOL_CORTISOL_SUPPRESS_RATE        = 24.0   # nmol/L
ALCOHOL_NOREPI_SUPPRESS_RATE          = 60.0   # pg/mL

# Xanax sustained effects
XANAX_CORTISOL_SUPPRESS_RATE          = 40.0   # nmol/L
XANAX_NOREPI_SUPPRESS_RATE            = 90.0   # pg/mL

# Adderall sustained effects
ADDERALL_DOPAMINE_SUSTAIN_RATE        = 6.0    # pg/mL/hr
ADDERALL_NOREPI_SUSTAIN_RATE          = 39.0   # pg/mL/hr

# Caffeine
CAFFEINE_A1_BLOCK_FACTOR              = 0.7    # receptor sensitivity multiplier when active
CAFFEINE_A2A_BLOCK_FACTOR             = 0.7

# ===========================================================================
# ENCODER MOMENTUM
# ===========================================================================

ENCODER_MOMENTUM_HALF_LIFE_SECONDS    = 1800   # 30 minutes — how fast habituation fades
ENCODER_MOMENTUM_PRUNE_THRESHOLD      = 0.05   # values below this are discarded

# Per-chemical momentum ceilings (max accumulated positive delta before dampening)
MOMENTUM_CEILING_DOPAMINE             = 25.0   # pg/mL
MOMENTUM_CEILING_SEROTONIN            = 3.5    # ng/mL
MOMENTUM_CEILING_NOREPINEPHRINE       = 80.0   # pg/mL
MOMENTUM_CEILING_OXYTOCIN             = 18.0   # pg/mL
MOMENTUM_CEILING_ENDORPHINS           = 30.0   # pg/mL
MOMENTUM_CEILING_ACETYLCHOLINE        = 14.0   # nmol/L

MOMENTUM_DAMPING_THRESHOLD            = 0.8    # scale below this → start dampening

# ===========================================================================
# VITAL SIGNS
# ===========================================================================

HR_BASELINE_BPM                       = 68.0
HR_NOREPI_THRESHOLD                   = 200.0  # pg/mL
HR_NOREPI_RATE                        = 0.017  # BPM per pg/mL above threshold
HR_CORTISOL_THRESHOLD                 = 250.0  # nmol/L
HR_CORTISOL_RATE                      = 0.020
HR_ENDORPHIN_THRESHOLD                = 25.0   # pg/mL
HR_ENDORPHIN_RATE                     = 0.28   # negative (lowers HR)
HR_SLEEP_PRESSURE_THRESHOLD           = 50.0   # AU
HR_SLEEP_PRESSURE_RATE                = 0.10
HR_SLEEP_DAMPEN_FACTOR                = 0.85

HR_CAFFEINE_RATE                      = 0.12   # BPM per substance level point
HR_ADDERALL_RATE                      = 0.22
HR_XANAX_RATE                         = 0.12   # negative (lowers HR)

HR_DANGER_THRESHOLD                   = 170    # BPM — overdose escalation
HR_STIMULANT_ACTIVE_LEVEL             = 5      # substance level to count as "stimulant active"

SBP_BASELINE                          = 112.0  # mmHg
DBP_BASELINE                          = 72.0   # mmHg
BP_NOREPI_THRESHOLD                   = 200.0
BP_NOREPI_SBP_RATE                    = 0.025
BP_CORTISOL_THRESHOLD                 = 250.0
BP_CORTISOL_SBP_RATE                  = 0.015
BP_HYDRATION_THRESHOLD                = 62.0   # % TBW
BP_HYDRATION_SBP_RATE                 = 1.5
BP_HYDRATION_DBP_RATE                 = 0.012
BP_ADDERALL_SBP_RATE                  = 0.20
BP_XANAX_SBP_RATE                     = 0.008  # negative (lowers)
BP_SLEEP_DAMPEN_FACTOR                = 0.88

SBP_DANGER_THRESHOLD                  = 175    # mmHg — overdose escalation

RR_BASELINE                           = 13.5   # breaths/min
RR_CORTISOL_THRESHOLD                 = 250.0
RR_CORTISOL_RATE                      = 0.010
RR_NOREPI_THRESHOLD                   = 200.0
RR_NOREPI_RATE                        = 0.004
RR_XANAX_SUPPRESS_RATE               = 0.025
RR_SLEEP_DAMPEN_FACTOR                = 0.82

SPO2_BASELINE                         = 98.5   # % — healthy baseline
SPO2_RR_NORMAL_MAX                    = 12.0   # br/min — below this: mild tachypnea
SPO2_RR_MILD_MAX                      = 20.0
SPO2_RR_MODERATE_MAX                  = 25.0
SPO2_RR_SEVERE_THRESHOLD              = 25.0

VAGAL_TONE_HRV_INTERCEPT              = 10.0   # ms RMSSD at vagal_tone=0
VAGAL_TONE_HRV_SLOPE                  = 0.70   # ms per vagal_tone point
VAGAL_TONE_NOREPI_THRESHOLD           = 250.0  # pg/mL
VAGAL_TONE_CORTISOL_THRESHOLD         = 300.0  # nmol/L
VAGAL_TONE_CORTISOL_RATE              = 0.04
VAGAL_TONE_NOREPI_RATE                = 0.02
VAGAL_TONE_PAIN_RATE                  = 0.25

FEVER_IL1B_THRESHOLD                  = 10.0   # pg/mL
FEVER_IL6_THRESHOLD                   = 20.0   # pg/mL
FEVER_IL6_RATE                        = 0.02   # °C per pg/mL above threshold
FEVER_IL1B_RATE                       = 0.03
FEVER_MAX_DELTA                       = 4.0    # °C — max fever elevation
FEVER_SLEEP_REDUCTION                 = 0.3    # °C reduction during sleep

# Overdose escalation
OVERDOSE_STAGE2_MINUTES               = 10.0
OVERDOSE_STAGE3_MINUTES               = 20.0

# ===========================================================================
# DECODER / BIOLOGICAL REPORT
# ===========================================================================

SUBSTANCE_HALFLIFE_DISPLAY_FACTOR     = 1.44   # hours_remaining = hl × (level/100) × this

# Needs summary thresholds
NEEDS_GLUCOSE_LOW_THRESHOLD           = 55.0   # mg/dL
NEEDS_GLUCOSE_MODERATE_THRESHOLD      = 70.0   # mg/dL
NEEDS_HYDRATION_LOW_THRESHOLD         = 54.0   # % TBW
NEEDS_HYDRATION_MODERATE_THRESHOLD    = 58.0   # % TBW
NEEDS_SLEEP_TIRED_THRESHOLD           = 80.0   # AU
NEEDS_SLEEP_MODERATE_THRESHOLD        = 60.0   # AU

# ===========================================================================
# MEMORY TRIGGERS
# ===========================================================================

CONTEXT_QUEUE_TTL_SECONDS             = 300    # entries older than 5 min are stale

RAG_SIGNIFICANCE_THRESHOLD            = 0.30   # minimum to be a RAG candidate
RAG_SIGNIFICANCE_STRONG               = 0.60   # strong candidate
KAG_SIGNIFICANCE_THRESHOLD            = 0.80   # flag for knowledge update
MULTI_EVENT_RAG_COUNT                 = 3      # simultaneous moderate events → composite RAG save
MULTI_EVENT_RAG_THRESHOLD             = 0.40   # "moderate" for multi-event rule
ALLOSTATIC_KAG_THRESHOLD              = 50.0   # AU — milestone triggers KAG

SIGNIFICANCE_LABEL_BOUNDARY_FLOOR     = 0.30   # crossing a label boundary → min this significance
SIGNIFICANCE_EXTREME_FLOOR            = 0.60   # extreme label → min this significance
SIGNIFICANCE_DELTA_MULTIPLIER         = 2.0    # frac × this → score (50% range = 1.0)

# ===========================================================================
# BEHAVIORAL DRIVES
# ===========================================================================

DRIVE_HUNGER_GHRELIN_THRESHOLD        = 700.0  # pg/mL
DRIVE_HUNGER_GLUCOSE_THRESHOLD        = 65.0   # mg/dL
DRIVE_HUNGER_URGENCY_DIVISOR          = 200.0
DRIVE_HUNGER_URGENCY_FLOOR            = 0.3

DRIVE_THIRST_THRESHOLD                = 59.0   # % TBW
DRIVE_THIRST_URGENCY_DIVISOR          = 14.0

DRIVE_FATIGUE_ADENOSINE_THRESHOLD     = 60.0   # nmol/L
DRIVE_FATIGUE_URGENCY_DIVISOR         = 40.0

DRIVE_PAIN_THRESHOLD                  = 40.0   # AU
DRIVE_SICKNESS_THRESHOLD              = 45.0   # AU inflammation index

DRIVE_SOCIAL_OXYTOCIN_THRESHOLD       = 10.0   # pg/mL
DRIVE_SOCIAL_SEROTONIN_THRESHOLD      = 14.0   # ng/mL
DRIVE_SOCIAL_URGENCY_DIVISOR          = 20.0

DRIVE_PRIORITY_URGENCY_THRESHOLD      = 0.6    # drives above this are "urgent"

# ===========================================================================
# DERIVED PSYCHOLOGICAL STATE WEIGHTS
# ===========================================================================
# Each weight describes how much a chemical contributes to a psychological state.
# All weights within a formula should sum to approximately 1.0 for positive terms.

# Energy
ENERGY_GLUCOSE_WEIGHT                 = 0.35
ENERGY_NOREPI_WEIGHT                  = 0.25
ENERGY_T3_WEIGHT                      = 0.15
ENERGY_ADENOSINE_WEIGHT               = 0.20
ENERGY_HUNGER_WEIGHT                  = 0.05
ENERGY_INFLAMMATION_WEIGHT            = 0.15
ENERGY_OFFSET                         = 20.0

# Cognitive clarity
CLARITY_ACH_WEIGHT                    = 0.35
CLARITY_GLUCOSE_WEIGHT                = 0.15
CLARITY_BDNF_WEIGHT                   = 0.10
CLARITY_ADENOSINE_WEIGHT              = 0.20
CLARITY_CORTISOL_WEIGHT               = 0.15
CLARITY_PAIN_WEIGHT                   = 0.10
CLARITY_MELATONIN_DRAG_FACTOR         = 0.6
CLARITY_OFFSET                        = 20.0

# Hedonic tone
HEDONIC_DOPAMINE_REWARD_WEIGHT        = 0.40
HEDONIC_ENDORPHIN_WEIGHT              = 0.25
HEDONIC_SEROTONIN_WEIGHT              = 0.20
HEDONIC_ANANDAMIDE_WEIGHT             = 0.15
HEDONIC_INFLAMMATION_WEIGHT           = 0.10
HEDONIC_ALLOSTATIC_WEIGHT             = 0.10
HEDONIC_OFFSET                        = 5.0

# Social warmth
WARMTH_OXYTOCIN_WEIGHT                = 0.45
WARMTH_SEROTONIN_WEIGHT               = 0.25
WARMTH_VASOPRESSIN_WEIGHT             = 0.10
WARMTH_CORTISOL_WEIGHT                = 0.15
WARMTH_PAIN_WEIGHT                    = 0.05
WARMTH_OFFSET                         = 10.0

# Arousal
AROUSAL_NOREPI_WEIGHT                 = 0.40
AROUSAL_CORTISOL_WEIGHT               = 0.25
AROUSAL_EI_BALANCE_SCALE              = 5.0
AROUSAL_GABA_WEIGHT                   = 0.20
AROUSAL_ADENOSINE_WEIGHT              = 0.15
AROUSAL_MELATONIN_DRAG_FACTOR         = 0.8
AROUSAL_OFFSET                        = 15.0

# Mood valence
VALENCE_SEROTONIN_WEIGHT              = 0.35
VALENCE_DOPAMINE_COGNITIVE_WEIGHT     = 0.25
VALENCE_T3_WEIGHT                     = 0.10
VALENCE_BDNF_WEIGHT                   = 0.10
VALENCE_CORTISOL_WEIGHT               = 0.20
VALENCE_ALLOSTATIC_WEIGHT             = 0.10
VALENCE_OFFSET                        = 10.0

# Melatonin drag (shared across energy, clarity, arousal)
MELATONIN_DRAG_THRESHOLD              = 40.0   # normalized 0-100 — drag starts above this
MELATONIN_DRAG_MULTIPLIER             = 0.25

# Third-order: Anxiety
ANXIETY_AROUSAL_WEIGHT                = 0.35
ANXIETY_CLARITY_WEIGHT                = 0.25
ANXIETY_WARMTH_WEIGHT                 = 0.25
ANXIETY_PAIN_WEIGHT                   = 0.10
ANXIETY_EI_SCALE                      = 5.0
ANXIETY_GABA_WEIGHT                   = 0.20
ANXIETY_OFFSET                        = 20.0

# Third-order: Depression
DEPRESSION_VALENCE_WEIGHT             = 0.35
DEPRESSION_HEDONIC_WEIGHT             = 0.35
DEPRESSION_ENERGY_WEIGHT              = 0.15
DEPRESSION_INFLAMMATION_WEIGHT        = 0.10
DEPRESSION_ALLOSTATIC_WEIGHT          = 0.05
DEPRESSION_OFFSET                     = 20.0

# Third-order: Boredom
BOREDOM_AROUSAL_WEIGHT                = 0.45
BOREDOM_HEDONIC_WEIGHT                = 0.30
BOREDOM_ENERGY_WEIGHT                 = 0.20
BOREDOM_CLARITY_WEIGHT                = 0.05
BOREDOM_OFFSET                        = 20.0

# Third-order: Loneliness
LONELINESS_WARMTH_WEIGHT              = 0.55
LONELINESS_OXYTOCIN_WEIGHT            = 0.35
LONELINESS_INFLAMMATION_WEIGHT        = 0.10
LONELINESS_OFFSET                     = 25.0

# Third-order: Flow
FLOW_CLARITY_WEIGHT                   = 0.40
FLOW_HEDONIC_WEIGHT                   = 0.30
FLOW_AROUSAL_WEIGHT                   = 0.20
FLOW_GABA_WEIGHT                      = 0.10
FLOW_ANXIETY_REDUCTION                = 0.35

# Third-order: Physical distress
DISTRESS_PAIN_WEIGHT                  = 0.50
DISTRESS_INFLAMMATION_WEIGHT          = 0.25
DISTRESS_HUNGER_WEIGHT                = 0.10
DISTRESS_ENERGY_WEIGHT                = 0.15
DISTRESS_OFFSET                       = 15.0

# Normalization denominators (chemical → 0-100 for derived formulas)
NORM_GABA_MIN                         = 0.5   # µmol/L
NORM_GABA_RANGE                       = 0.095 # (gaba - min) / this → 0-100
NORM_T3_MIN                           = 20.0  # ng/dL
NORM_T3_RANGE                         = 1.8
NORM_BDNF_MIN                         = 1000.0  # pg/mL
NORM_BDNF_RANGE                       = 190.0
NORM_HUNGER_MIN                       = 200.0   # pg/mL ghrelin
NORM_HUNGER_RANGE                     = 8.0
NORM_ANANDAMIDE_DIVISOR               = 0.15  # nM
NORM_VASOPRESSIN_DIVISOR              = 0.15  # pg/mL
NORM_ADENOSINE_SLEEP_PRESSURE_MIN     = 20.0  # nmol/L
NORM_ADENOSINE_SLEEP_PRESSURE_SCALE   = 0.60  # (adenosine - min) × this → AU
```

---

## Usage Pattern

Every module imports only what it needs:

```python
from src.sim.constants import (
    GLUCOSE_HYPOGLYCEMIA_THRESHOLD,
    GLUCOSE_DECAY_AWAKE,
    GLUCOSE_DECAY_ASLEEP,
)
```

Never import `*`. Never repeat a value. If two modules need the same threshold, they both
import it from constants — they don't each define it locally.

---

## Updating a Constant

1. Change the value in `constants.py`
2. Run the full test suite
3. If tests pass, the change is consistent across all modules

This is the only workflow for changing a simulation parameter. No grep-and-replace needed.
```
