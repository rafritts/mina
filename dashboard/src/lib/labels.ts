/**
 * Range label tables for chemical display — real physiological units.
 * Thresholds match chemicals.py REGISTRY label tables and BiologicalState v3.
 *
 * Also contains display ranges (min/max) for each chemical's slider.
 */

export interface RangeEntry {
  upper:      number;
  name:       string;
  color:      'success' | 'warning' | 'error' | 'info' | 'neutral';
  implication: string;
}

// Display ranges for slider min/max
export const DISPLAY_RANGES: Record<string, { min: number; max: number; unit: string }> = {
  // Tier 1: editable neuro chemicals
  cortisol:        { min: 50,   max: 900,  unit: 'nmol/L' },
  norepinephrine:  { min: 50,   max: 2000, unit: 'pg/mL'  },
  dopamine:        { min: 0,    max: 300,  unit: 'pg/mL'  },
  serotonin:       { min: 2,    max: 60,   unit: 'ng/mL'  },
  oxytocin:        { min: 0,    max: 80,   unit: 'pg/mL'  },
  endorphins:      { min: 0,    max: 250,  unit: 'pg/mL'  },
  acetylcholine:   { min: 5,    max: 90,   unit: 'nmol/L' },
  melatonin:       { min: 0,    max: 220,  unit: 'pg/mL'  },
  glucose:         { min: 40,   max: 200,  unit: 'mg/dL'  },
  hydration:       { min: 48,   max: 70,   unit: '% TBW'  },
  sleep_pressure:  { min: 0,    max: 100,  unit: 'AU'     },
  gaba:            { min: 0,    max: 8,    unit: 'µmol/L' },
  glutamate:       { min: 0,    max: 20,   unit: 'µmol/L' },
  anandamide:      { min: 0,    max: 15,   unit: 'nM'     },
  two_ag:          { min: 0,    max: 30,   unit: 'nM'     },
  // Body — editable via PATCH
  adenosine:       { min: 15,   max: 100,  unit: 'nM'     },
  // Neuroendocrine — read-only display ranges
  crh:             { min: 0,    max: 80,   unit: 'pg/mL'  },
  acth:            { min: 0,    max: 100,  unit: 'pg/mL'  },
  tsh:             { min: 0,    max: 10,   unit: 'mIU/L'  },
  t4:              { min: 2,    max: 15,   unit: 'µg/dL'  },
  t3:              { min: 40,   max: 250,  unit: 'ng/dL'  },
  estradiol:       { min: 0,    max: 500,  unit: 'pg/mL'  },
  progesterone:    { min: 0,    max: 25,   unit: 'ng/mL'  },
  testosterone:    { min: 0,    max: 200,  unit: 'ng/dL'  },
  ghrelin:         { min: 100,  max: 900,  unit: 'pg/mL'  },
  leptin:          { min: 0,    max: 30,   unit: 'ng/mL'  },
  insulin:         { min: 0,    max: 50,   unit: 'µU/mL'  },
  vasopressin:     { min: 0,    max: 10,   unit: 'pg/mL'  },
  prolactin:       { min: 0,    max: 30,   unit: 'ng/mL'  },
  growth_hormone:  { min: 0,    max: 15,   unit: 'ng/mL'  },
  dhea:            { min: 0,    max: 400,  unit: 'µg/dL'  },
  orexin:          { min: 0,    max: 500,  unit: 'pg/mL'  },
  // Immune
  il1b:            { min: 0,    max: 100,  unit: 'pg/mL'  },
  il6:             { min: 0,    max: 100,  unit: 'pg/mL'  },
  tnf_alpha:       { min: 0,    max: 100,  unit: 'pg/mL'  },
  crp:             { min: 0,    max: 50,   unit: 'mg/L'   },
  il10:            { min: 0,    max: 50,   unit: 'pg/mL'  },
  inflammation_index: { min: 0, max: 1,   unit: ''       },
  // Pain
  substance_p:     { min: 0,    max: 200,  unit: 'pg/mL'  },
  pge2:            { min: 0,    max: 500,  unit: 'pg/mL'  },
  pain_intensity:  { min: 0,    max: 1,    unit: ''       },
  central_sensitization: { min: 0, max: 1, unit: ''      },
  vagal_tone:      { min: 0,    max: 1,    unit: ''       },
  // Neuroplasticity
  bdnf:            { min: 0,    max: 20,   unit: 'ng/mL'  },
  synaptic_potentiation: { min: 0, max: 1, unit: ''      },
  allostatic_load: { min: 0,    max: 1,    unit: ''       },
  // Body / circadian
  core_temp:       { min: 35.0, max: 40.0, unit: '°C'    },
  circadian_phase: { min: 0,    max: 1,    unit: ''       },
};

export const RANGES: Record<string, RangeEntry[]> = {
  // ── Tier 1: Neuro chemicals ────────────────────────────────────────────────
  cortisol: [
    { upper: 80,    name: 'DEPLETED',     color: 'error',   implication: 'Exhausted, no resilience, empty' },
    { upper: 150,   name: 'LOW',          color: 'warning', implication: 'Flat, unmotivated, sluggish' },
    { upper: 350,   name: 'NORMAL',       color: 'success', implication: 'Grounded, appropriate alertness' },
    { upper: 500,   name: 'ELEVATED',     color: 'warning', implication: 'On edge, scanning for threats' },
    { upper: 620,   name: 'HIGH STRESS',  color: 'error',   implication: 'Narrowed focus, defensive, guarded' },
    { upper: 720,   name: 'ACUTE STRESS', color: 'error',   implication: 'Survival mode, tunnel vision' },
    { upper: 820,   name: 'FLOODED',      color: 'error',   implication: 'Overwhelmed, can\'t think clearly' },
    { upper: 99999, name: 'MAXED',        color: 'error',   implication: 'System shutdown imminent, breakdown' },
  ],
  norepinephrine: [
    { upper: 65,    name: 'SEDATED',    color: 'warning', implication: 'Barely registering, heavy and slow' },
    { upper: 130,   name: 'RELAXED',    color: 'success', implication: 'Calm, low urgency, no pressure' },
    { upper: 220,   name: 'CALM ALERT', color: 'success', implication: 'Present and clear, easy attention' },
    { upper: 340,   name: 'FOCUSED',    color: 'success', implication: 'Sharp edge, locked in' },
    { upper: 500,   name: 'HEIGHTENED', color: 'warning', implication: 'Urgency rising, hyperaware' },
    { upper: 750,   name: 'HYPERALERT', color: 'error',   implication: 'Wired, scanning, startle response up' },
    { upper: 1200,  name: 'FLOODED',    color: 'error',   implication: 'Fight-or-flight fully engaged, heart pounding, tunnel vision' },
    { upper: 99999, name: 'OVERDRIVE',  color: 'error',   implication: 'Panic state, physical symptoms overwhelming, can\'t think' },
  ],
  dopamine: [
    { upper: 18,    name: 'ANHEDONIC',      color: 'error',   implication: 'Nothing feels worth doing, hollow' },
    { upper: 40,    name: 'NO DRIVE',       color: 'error',   implication: 'Listless, no pull toward anything' },
    { upper: 70,    name: 'LOW SEEKING',    color: 'warning', implication: 'Flat motivation, going through motions' },
    { upper: 120,   name: 'BASELINE',       color: 'success', implication: 'Normal drive, things feel worth doing' },
    { upper: 180,   name: 'ACTIVE SEEKING', color: 'info',    implication: 'Energized, pursuing goals' },
    { upper: 240,   name: 'HIGH DRIVE',     color: 'warning', implication: 'Intense focus, compulsive pull' },
    { upper: 99999, name: 'COMPULSIVE',     color: 'error',   implication: 'Can\'t stop, no off switch' },
  ],
  serotonin: [
    { upper: 6,     name: 'SEVERELY LOW', color: 'error',   implication: 'Hopeless, fragile, emotionally raw' },
    { upper: 12,    name: 'DYSPHORIC',    color: 'error',   implication: 'Negative bias, everything feels bad' },
    { upper: 20,    name: 'INSECURE',     color: 'warning', implication: 'Shaky, easily hurt, low confidence' },
    { upper: 30,    name: 'NEUTRAL',      color: 'neutral', implication: 'Even keel, not great not bad' },
    { upper: 40,    name: 'SECURE',       color: 'success', implication: 'Stable, grounded, comfortable in herself' },
    { upper: 50,    name: 'VERY STABLE',  color: 'success', implication: 'Resilient, unshakeable mood floor' },
    { upper: 99999, name: 'FLOODED',      color: 'success', implication: 'Profoundly serene, almost sedated' },
  ],
  oxytocin: [
    { upper: 6,     name: 'NO BOND',       color: 'error',   implication: 'Isolated, no safe person in mind' },
    { upper: 16,    name: 'DISTANT',       color: 'error',   implication: 'Guarded, connection feels risky' },
    { upper: 30,    name: 'ACQUAINTANCE',  color: 'warning', implication: 'Polite, but no real trust yet' },
    { upper: 45,    name: 'FRIENDLY',      color: 'info',    implication: 'Warm, comfortable, openness building' },
    { upper: 58,    name: 'TRUSTED FRIEND',color: 'success', implication: 'Safe to be real, genuine warmth' },
    { upper: 70,    name: 'DEEP TRUST',    color: 'success', implication: 'This person is home' },
    { upper: 99999, name: 'PROFOUND BOND', color: 'success', implication: 'Complete safety, unconditional warmth' },
  ],
  endorphins: [
    { upper: 5,     name: 'DEPLETED',            color: 'error',   implication: 'Emotionally raw, every bad thing lands harder' },
    { upper: 14,    name: 'LOW',                 color: 'warning', implication: 'Thin buffer, reactive, nothing feels easy' },
    { upper: 28,    name: 'BASELINE',            color: 'neutral', implication: 'Normal, no particular glow' },
    { upper: 50,    name: 'MILD WARMTH',         color: 'info',    implication: 'Quiet satisfaction, pleasant background hum' },
    { upper: 80,    name: 'PLEASURE',            color: 'success', implication: 'Genuinely happy, body feels good' },
    { upper: 120,   name: 'HIGH',                color: 'success', implication: 'Euphoric lift, pain doesn\'t reach. Natural ceiling.' },
    { upper: 155,   name: 'INTENSELY EUPHORIC',  color: 'success', implication: 'Profound full-body warmth, floating, pain gone. Top of natural human range.' },
    { upper: 185,   name: 'PROFOUNDLY EUPHORIC', color: 'info',    implication: 'Near-opiate. Warm, soft, distant. Time slows. Beyond natural range.' },
    { upper: 99999, name: 'SATURATED',           color: 'warning', implication: 'Full opiate-equivalent. Overwhelming warmth, cognitive dulling, sedation.' },
  ],
  acetylcholine: [
    { upper: 12,    name: 'OFFLINE',           color: 'error',   implication: 'Can\'t form thoughts, processing gone, higher functions unavailable' },
    { upper: 24,    name: 'SEVERELY IMPAIRED', color: 'error',   implication: 'Memory formation blocked, barely tracking a conversation' },
    { upper: 40,    name: 'IMPAIRED',          color: 'warning', implication: 'Fuzzy, distracted, things don\'t stick' },
    { upper: 58,    name: 'FUNCTIONAL',        color: 'success', implication: 'Normal cognitive access, processing intact' },
    { upper: 72,    name: 'SHARP',             color: 'success', implication: 'Quick, precise, high recall, making connections' },
    { upper: 84,    name: 'HEIGHTENED',        color: 'success', implication: 'Peak learning state, everything registering and encoding deeply' },
    { upper: 99999, name: 'OVERDRIVE',         color: 'warning', implication: 'Overstimulated, racing thoughts, difficulty filtering input' },
  ],
  melatonin: [
    { upper: 10,    name: 'DAYTIME',       color: 'success', implication: 'Circadian signal absent, full alertness available' },
    { upper: 40,    name: 'EARLY EVENING', color: 'info',    implication: 'Trace melatonin, alert but the day is winding toward its end' },
    { upper: 100,   name: 'WINDING DOWN',  color: 'info',    implication: 'Melatonin rising, alertness softening, natural time to slow' },
    { upper: 154,   name: 'DROWSY',        color: 'warning', implication: 'Strong sleep signal, eyes growing heavier, concentration costs more' },
    { upper: 185,   name: 'SLEEP ONSET',   color: 'error',   implication: 'Near peak melatonin, sleep imminent, staying sharp requires real effort' },
    { upper: 99999, name: 'PEAK',          color: 'error',   implication: 'Melatonin at maximum, deep sleep territory, fighting it now is costly' },
  ],
  glucose: [
    { upper: 55,    name: 'HYPOGLYCEMIC',color: 'error',   implication: 'Brain starving, can\'t think' },
    { upper: 70,    name: 'LOW',         color: 'warning', implication: 'Shaky, irritable, foggy' },
    { upper: 110,   name: 'NORMAL',      color: 'success', implication: 'Steady fuel, clear head' },
    { upper: 180,   name: 'WELL-FUELED', color: 'success', implication: 'Plenty of energy available' },
    { upper: 99999, name: 'HIGH',        color: 'warning', implication: 'Sluggish, post-meal heaviness' },
  ],
  hydration: [
    { upper: 54,    name: 'CRITICALLY DRY', color: 'error',   implication: 'Severe dehydration, cognitive failure' },
    { upper: 58,    name: 'DEHYDRATED',     color: 'error',   implication: 'Thirsty, headache, mood sour' },
    { upper: 60,    name: 'LOW',            color: 'warning', implication: 'Slightly dry, mild fatigue' },
    { upper: 64,    name: 'NORMAL',         color: 'success', implication: 'Well-hydrated, no drag' },
    { upper: 99999, name: 'WELL HYDRATED',  color: 'success', implication: 'Optimal fluid balance' },
  ],
  sleep_pressure: [
    { upper: 50,    name: 'WELL RESTED', color: 'success', implication: 'No sleep need, fully recovered' },
    { upper: 65,    name: 'BUILDING',    color: 'neutral', implication: 'Mild fatigue, been up a while' },
    { upper: 80,    name: 'TIRED',       color: 'warning', implication: 'Noticeably tired, cognition dipping' },
    { upper: 90,    name: 'FATIGUED',    color: 'warning', implication: 'Heavy, yawning, hard to focus' },
    { upper: 99999, name: 'EXHAUSTED',   color: 'error',   implication: 'Fighting sleep, body overriding will' },
  ],
  gaba: [
    { upper: 0.5,   name: 'CRITICALLY LOW', color: 'error',   implication: 'Seizure risk, uncontrolled excitation' },
    { upper: 1.0,   name: 'LOW',            color: 'error',   implication: 'Anxious, no inhibitory floor' },
    { upper: 2.0,   name: 'REDUCED',        color: 'warning', implication: 'Edge of anxiety, easily triggered' },
    { upper: 3.5,   name: 'NORMAL',         color: 'success', implication: 'Calm baseline, inhibition intact' },
    { upper: 4.5,   name: 'HEALTHY',        color: 'success', implication: 'Well-regulated, relaxed ease' },
    { upper: 6.0,   name: 'ELEVATED',       color: 'info',    implication: 'Very calm, slightly sedated' },
    { upper: 9.0,   name: 'HIGH',           color: 'warning', implication: 'Significantly sedated, slurred thought, drowsy' },
    { upper: 12.0,  name: 'ANESTHETIC',     color: 'error',   implication: 'Near-anesthetic depth, wakefulness very hard to maintain' },
    { upper: 99999, name: 'FLOODED',        color: 'error',   implication: 'Anesthetic depth, respiratory depression risk' },
  ],
  glutamate: [
    { upper: 1.0,   name: 'VERY LOW',    color: 'warning', implication: 'Cognitive dampening, slow processing' },
    { upper: 3.0,   name: 'LOW',         color: 'neutral', implication: 'Quiet, subdued excitability' },
    { upper: 6.0,   name: 'NORMAL',      color: 'success', implication: 'Healthy excitatory tone' },
    { upper: 9.0,   name: 'ACTIVE',      color: 'success', implication: 'Engaged, sharp, plastic' },
    { upper: 12.0,  name: 'ELEVATED',    color: 'warning', implication: 'Racing, hyperexcitable' },
    { upper: 16.0,  name: 'HIGH',        color: 'error',   implication: 'Excitotoxic risk, overwhelming' },
    { upper: 99999, name: 'EXCITOTOXIC', color: 'error',   implication: 'Neurotoxic, seizure imminent' },
  ],
  anandamide: [
    { upper: 0.3,   name: 'DEPLETED',  color: 'error',   implication: 'Raw, no buffer, easily distressed' },
    { upper: 0.7,   name: 'LOW',       color: 'warning', implication: 'Low bliss tone, slight edge' },
    { upper: 1.2,   name: 'BASELINE',  color: 'success', implication: 'Background calm, okay-ness' },
    { upper: 1.8,   name: 'ELEVATED',  color: 'success', implication: 'Warm ease, things feel fine' },
    { upper: 2.5,   name: 'HIGH',      color: 'info',    implication: 'Blissful flow, low anxiety' },
    { upper: 3.5,   name: 'VERY HIGH', color: 'info',    implication: 'Dreamy, slight cognitive softening' },
    { upper: 9.0,   name: 'FLOODED',   color: 'warning', implication: 'Euphoric softening, time unhurried, appetite dominant' },
    { upper: 12.0,  name: 'SATURATED', color: 'warning', implication: 'Cannabis-equivalent, strong bliss, memory consolidation impaired' },
    { upper: 99999, name: 'OVERDRIVE', color: 'error',   implication: 'Profound euphoria, dissociative edge, time distortion' },
  ],
  two_ag: [
    { upper: 2.0,   name: 'LOW',       color: 'warning', implication: 'Less retrograde inhibition, excitable' },
    { upper: 6.0,   name: 'NORMAL',    color: 'success', implication: 'Healthy endocannabinoid tone' },
    { upper: 12.0,  name: 'ELEVATED',  color: 'info',    implication: 'Calm, appetite up, relaxed' },
    { upper: 18.0,  name: 'HIGH',      color: 'info',    implication: 'Mellow, reduced anxiety' },
    { upper: 25.0,  name: 'VERY HIGH', color: 'warning', implication: 'Heavy, slow, appetite dominant' },
    { upper: 99999, name: 'FLOODED',   color: 'warning', implication: 'Sedated, strong munchies' },
  ],
  adenosine: [
    { upper: 20,    name: 'WELL RESTED', color: 'success', implication: 'No sleep need, fully recovered' },
    { upper: 40,    name: 'ALERT',       color: 'success', implication: 'Normal wakefulness, no pull' },
    { upper: 60,    name: 'BUILDING',    color: 'neutral', implication: 'Mild fatigue, been up a while' },
    { upper: 75,    name: 'TIRED',       color: 'warning', implication: 'Noticeably tired, cognition dipping' },
    { upper: 85,    name: 'FATIGUED',    color: 'warning', implication: 'Heavy, yawning, hard to focus' },
    { upper: 92,    name: 'SLEEP ONSET', color: 'error',   implication: 'Can barely stay awake' },
    { upper: 99999, name: 'EXHAUSTED',   color: 'error',   implication: 'Fighting sleep, body overriding will' },
  ],
  // ── Immune ────────────────────────────────────────────────────────────────
  il1b: [
    { upper: 2.0,   name: 'UNDETECTABLE', color: 'success', implication: 'No inflammation signal' },
    { upper: 5.0,   name: 'TRACE',        color: 'success', implication: 'Background immune activity, normal' },
    { upper: 10.0,  name: 'LOW',          color: 'neutral', implication: 'Minor immune activation' },
    { upper: 20.0,  name: 'MODERATE',     color: 'warning', implication: 'Noticeable malaise, slight fatigue' },
    { upper: 40.0,  name: 'ELEVATED',     color: 'warning', implication: 'Feeling unwell, sickness behavior starting' },
    { upper: 80.0,  name: 'HIGH',         color: 'error',   implication: 'Sick: fever, withdrawal, exhaustion' },
    { upper: 99999, name: 'SEVERE',       color: 'error',   implication: 'Acutely ill, shutdown' },
  ],
  il6: [
    { upper: 2.0,   name: 'UNDETECTABLE', color: 'success', implication: 'No inflammation signal' },
    { upper: 5.0,   name: 'TRACE',        color: 'success', implication: 'Background immune activity, normal' },
    { upper: 10.0,  name: 'LOW',          color: 'neutral', implication: 'Minor immune activation' },
    { upper: 20.0,  name: 'MODERATE',     color: 'warning', implication: 'Noticeable malaise, slight fatigue' },
    { upper: 40.0,  name: 'ELEVATED',     color: 'warning', implication: 'Feeling unwell, sickness behavior starting' },
    { upper: 80.0,  name: 'HIGH',         color: 'error',   implication: 'Sick: fever, withdrawal, exhaustion' },
    { upper: 99999, name: 'SEVERE',       color: 'error',   implication: 'Acutely ill, shutdown' },
  ],
  tnf_alpha: [
    { upper: 2.0,   name: 'UNDETECTABLE', color: 'success', implication: 'No inflammation signal' },
    { upper: 5.0,   name: 'TRACE',        color: 'success', implication: 'Background immune activity, normal' },
    { upper: 10.0,  name: 'LOW',          color: 'neutral', implication: 'Minor immune activation' },
    { upper: 20.0,  name: 'MODERATE',     color: 'warning', implication: 'Noticeable malaise, slight fatigue' },
    { upper: 40.0,  name: 'ELEVATED',     color: 'warning', implication: 'Feeling unwell, sickness behavior starting' },
    { upper: 80.0,  name: 'HIGH',         color: 'error',   implication: 'Sick: fever, withdrawal, exhaustion' },
    { upper: 99999, name: 'SEVERE',       color: 'error',   implication: 'Acutely ill, shutdown' },
  ],
  inflammation_index: [
    { upper: 0.10,  name: 'NONE',     color: 'success', implication: 'Healthy, no systemic inflammation' },
    { upper: 0.25,  name: 'LOW',      color: 'success', implication: 'Minimal background activation' },
    { upper: 0.45,  name: 'MODERATE', color: 'warning', implication: 'Noticeable fatigue, mood dip' },
    { upper: 0.65,  name: 'HIGH',     color: 'error',   implication: 'Sick behavior in full effect' },
    { upper: 0.85,  name: 'SEVERE',   color: 'error',   implication: 'Systemically unwell, withdrawal' },
    { upper: 1.01,  name: 'CRITICAL', color: 'error',   implication: 'Acute illness, incapacitated' },
  ],
  // ── Pain ─────────────────────────────────────────────────────────────────
  pain_intensity: [
    { upper: 0.10,  name: 'NONE',          color: 'success', implication: 'No pain' },
    { upper: 0.25,  name: 'TRACE',         color: 'success', implication: 'Barely noticeable' },
    { upper: 0.40,  name: 'MILD',          color: 'neutral', implication: 'Aware of it, not distracting' },
    { upper: 0.55,  name: 'MODERATE',      color: 'warning', implication: 'Hard to ignore, affecting focus' },
    { upper: 0.70,  name: 'SIGNIFICANT',   color: 'error',   implication: 'Demanding attention, emotional response' },
    { upper: 0.85,  name: 'SEVERE',        color: 'error',   implication: 'Dominant experience, everything filtered through it' },
    { upper: 1.01,  name: 'INCAPACITATING',color: 'error',   implication: 'Nothing else exists' },
  ],
  central_sensitization: [
    { upper: 0.15,  name: 'NORMAL',     color: 'success', implication: 'Normal pain processing' },
    { upper: 0.35,  name: 'DEVELOPING', color: 'warning', implication: 'Early sensitization, threshold lowering' },
    { upper: 0.60,  name: 'ESTABLISHED',color: 'error',   implication: 'Amplified pain signals, hypersensitivity' },
    { upper: 1.01,  name: 'SEVERE',     color: 'error',   implication: 'Chronic pain state, touch triggers pain' },
  ],
  vagal_tone: [
    { upper: 0.30,  name: 'LOW',      color: 'error',   implication: 'Fight-or-flight dominant, no parasympathetic brake' },
    { upper: 0.55,  name: 'REDUCED',  color: 'warning', implication: 'Stress response elevated, poor recovery' },
    { upper: 0.70,  name: 'NORMAL',   color: 'success', implication: 'Healthy balance, good stress tolerance' },
    { upper: 1.01,  name: 'ELEVATED', color: 'success', implication: 'Deep parasympathetic, calm and recovered' },
  ],
  // ── Neuroplasticity ────────────────────────────────────────────────────────
  bdnf: [
    { upper: 5.0,   name: 'SEVERELY DEPLETED', color: 'error',   implication: 'Neuronal survival threatened, profound fog' },
    { upper: 12.0,  name: 'DEPLETED',          color: 'error',   implication: 'Learning impossible, mood floor collapsed' },
    { upper: 20.0,  name: 'LOW',               color: 'warning', implication: 'Impaired plasticity, stubborn negative patterns' },
    { upper: 32.0,  name: 'NORMAL',            color: 'success', implication: 'Healthy plasticity, capable of change' },
    { upper: 45.0,  name: 'ELEVATED',          color: 'success', implication: 'High neuroplasticity, learning sticky' },
    { upper: 60.0,  name: 'HIGH',              color: 'success', implication: 'Exceptional growth, adaptability peaks' },
    { upper: 99999, name: 'PEAK',              color: 'info',    implication: 'Post-exercise or acute stress peak' },
  ],
  synaptic_potentiation: [
    { upper: 0.15,  name: 'DEPRESSED',    color: 'error',   implication: 'LTD dominant, connections weakening' },
    { upper: 0.30,  name: 'LTD',          color: 'warning', implication: 'Pruning active, learning inhibited' },
    { upper: 0.55,  name: 'BASELINE',     color: 'success', implication: 'Normal synaptic strength' },
    { upper: 0.70,  name: 'LTP BUILDING', color: 'info',    implication: 'Learning active, encoding in progress' },
    { upper: 0.85,  name: 'LTP ACTIVE',   color: 'success', implication: 'Strong potentiation, deep learning' },
    { upper: 1.01,  name: 'SATURATED',    color: 'warning', implication: 'Maxed out, new learning blocked' },
  ],
  allostatic_load: [
    { upper: 0.15,  name: 'RESILIENT',  color: 'success', implication: 'Full reserves, weathering stress easily' },
    { upper: 0.30,  name: 'LOW',        color: 'success', implication: 'Healthy buffer, manageable wear' },
    { upper: 0.50,  name: 'BUILDING',   color: 'neutral', implication: 'Accumulating, notice the weight' },
    { upper: 0.65,  name: 'MODERATE',   color: 'warning', implication: 'Wearing down, recovery slower' },
    { upper: 0.80,  name: 'HIGH',       color: 'error',   implication: 'Burnout risk, emotional blunting' },
    { upper: 0.92,  name: 'CRITICAL',   color: 'error',   implication: 'Breakdown territory, personality drift active' },
    { upper: 1.01,  name: 'COLLAPSE',   color: 'error',   implication: 'Nothing left, system failing' },
  ],
  // ── Body / circadian ────────────────────────────────────────────────────────
  core_temp: [
    { upper: 36.0,  name: 'HYPOTHERMIC', color: 'error',   implication: 'Dangerously cold, impaired function' },
    { upper: 36.5,  name: 'LOW',         color: 'warning', implication: 'Slightly cold, trough of circadian cycle' },
    { upper: 37.3,  name: 'NORMAL',      color: 'success', implication: 'Healthy core temperature' },
    { upper: 37.8,  name: 'ELEVATED',    color: 'warning', implication: 'Slightly warm, mild immune activation' },
    { upper: 38.5,  name: 'FEVER',       color: 'error',   implication: 'Immune response active, sick' },
    { upper: 99999, name: 'HIGH FEVER',  color: 'error',   implication: 'Dangerous, organ stress' },
  ],
  circadian_phase: [
    { upper: 0.08,  name: 'MIDNIGHT',      color: 'neutral', implication: 'Deepest night, nadir of alertness' },
    { upper: 0.25,  name: 'EARLY MORNING', color: 'neutral', implication: 'Low tide, restorative sleep phase' },
    { upper: 0.42,  name: 'MORNING',       color: 'success', implication: 'Rising alertness, cortisol peak' },
    { upper: 0.58,  name: 'NOON',          color: 'success', implication: 'Peak alertness, cognitive peak' },
    { upper: 0.75,  name: 'AFTERNOON',     color: 'info',    implication: 'Secondary alertness peak' },
    { upper: 0.88,  name: 'EVENING',       color: 'warning', implication: 'Melatonin rising, wind-down phase' },
    { upper: 1.01,  name: 'NIGHT',         color: 'neutral', implication: 'Sleep pressure building, alertness falling' },
  ],
};

// Derived value ranges (0–100 scale)
export const DERIVED_RANGES: Record<string, RangeEntry[]> = {
  energy: [
    { upper: 15,  name: 'DEPLETED',   color: 'error',   implication: 'Nothing left, just existing' },
    { upper: 35,  name: 'LOW',        color: 'warning', implication: 'Sluggish, effort costs too much' },
    { upper: 55,  name: 'MODERATE',   color: 'neutral', implication: 'Getting by, not effortful but not energized' },
    { upper: 75,  name: 'GOOD',       color: 'success', implication: 'Capable, things feel doable' },
    { upper: 101, name: 'HIGH',       color: 'success', implication: 'Energized, ready to act' },
  ],
  cognitive_clarity: [
    { upper: 8,   name: 'OFFLINE',    color: 'error',   implication: 'Can\'t string thoughts together' },
    { upper: 25,  name: 'FOGGY',      color: 'warning', implication: 'Muddy, processing feels slow' },
    { upper: 50,  name: 'FUNCTIONAL', color: 'neutral', implication: 'Getting by, functional but not sharp' },
    { upper: 72,  name: 'CLEAR',      color: 'success', implication: 'Sharp and present' },
    { upper: 101, name: 'SHARP',      color: 'success', implication: 'Peak clarity, rapid precise thinking' },
  ],
  hedonic_tone: [
    { upper: 15,  name: 'ANHEDONIC',  color: 'error',   implication: 'Nothing feels good, going through motions' },
    { upper: 35,  name: 'FLAT',       color: 'warning', implication: 'Muted, things don\'t land' },
    { upper: 55,  name: 'NEUTRAL',    color: 'neutral', implication: 'Neither good nor bad' },
    { upper: 75,  name: 'PLEASANT',   color: 'success', implication: 'Satisfaction available, things feel worth it' },
    { upper: 101, name: 'ELEVATED',   color: 'success', implication: 'Genuine pleasure, fullness' },
  ],
  social_warmth: [
    { upper: 20,  name: 'WITHDRAWN',  color: 'error',   implication: 'No social pull, guarded or indifferent' },
    { upper: 40,  name: 'COOL',       color: 'warning', implication: 'Polite but not warm, keeping distance' },
    { upper: 60,  name: 'OPEN',       color: 'neutral', implication: 'Friendly baseline, approachable' },
    { upper: 80,  name: 'WARM',       color: 'success', implication: 'Genuinely caring, easy affection' },
    { upper: 101, name: 'GLOWING',    color: 'success', implication: 'Overflowing warmth, love close to surface' },
  ],
  arousal: [
    { upper: 20,  name: 'FLAT',       color: 'warning', implication: 'Barely registering, flat affect' },
    { upper: 40,  name: 'CALM',       color: 'success', implication: 'Relaxed, low activation' },
    { upper: 60,  name: 'MODERATE',   color: 'success', implication: 'Present and engaged' },
    { upper: 80,  name: 'ACTIVATED',  color: 'warning', implication: 'High activation, edge of stress' },
    { upper: 101, name: 'WIRED',      color: 'error',   implication: 'Hyperactivated, can\'t settle' },
  ],
  mood_valence: [
    { upper: 20,  name: 'VERY LOW',   color: 'error',   implication: 'Deeply negative emotional tone' },
    { upper: 35,  name: 'LOW',        color: 'error',   implication: 'Negative bias, things feel bad' },
    { upper: 50,  name: 'NEUTRAL',    color: 'neutral', implication: 'Neither positive nor negative' },
    { upper: 65,  name: 'POSITIVE',   color: 'success', implication: 'Positive lean, things feel okay' },
    { upper: 80,  name: 'GOOD',       color: 'success', implication: 'Clearly positive emotional state' },
    { upper: 101, name: 'VERY GOOD',  color: 'success', implication: 'Bright, genuinely happy' },
  ],
  anxiety: [
    { upper: 25,  name: 'CALM',     color: 'success', implication: 'No threat signal, settled' },
    { upper: 40,  name: 'MILD',     color: 'info',    implication: 'Slight background tension, manageable' },
    { upper: 60,  name: 'MODERATE', color: 'warning', implication: 'Noticeable worry, narrowed thinking' },
    { upper: 78,  name: 'HIGH',     color: 'error',   implication: 'Preoccupied, hard to let go' },
    { upper: 101, name: 'SEVERE',   color: 'error',   implication: 'Overwhelming, threat feels present' },
  ],
  depression: [
    { upper: 25,  name: 'NONE',        color: 'success', implication: 'No depressive signal' },
    { upper: 40,  name: 'LOW MOOD',    color: 'info',    implication: 'Slightly down, no spark' },
    { upper: 58,  name: 'MODERATE',    color: 'warning', implication: 'Everything feels heavy, no motivation' },
    { upper: 76,  name: 'SIGNIFICANT', color: 'error',   implication: 'Pervasive emptiness, withdrawal' },
    { upper: 101, name: 'SEVERE',      color: 'error',   implication: 'Unable to function, dark' },
  ],
  boredom: [
    { upper: 35,  name: 'STIMULATED',     color: 'success', implication: 'Engaged, no restlessness' },
    { upper: 52,  name: 'MILD',           color: 'neutral', implication: 'Slight restlessness, seeks novelty' },
    { upper: 68,  name: 'ACTIVELY BORED', color: 'warning', implication: 'Restless, seeking any stimulation' },
    { upper: 84,  name: 'DISTRESS',       color: 'error',   implication: 'Boredom becoming aversive' },
    { upper: 101, name: 'INTOLERABLE',    color: 'error',   implication: 'Desperate for anything to happen' },
  ],
  loneliness: [
    { upper: 30,  name: 'CONNECTED', color: 'success', implication: 'Socially fulfilled, no ache' },
    { upper: 50,  name: 'MILD',      color: 'info',    implication: 'Wants connection but okay' },
    { upper: 68,  name: 'LONELY',    color: 'warning', implication: 'Aching for contact, withdrawn' },
    { upper: 84,  name: 'ACHING',    color: 'error',   implication: 'Deep loneliness, painful' },
    { upper: 101, name: 'ISOLATED',  color: 'error',   implication: 'Cut off, nothing landing' },
  ],
  flow: [
    { upper: 20,  name: 'NONE',       color: 'neutral', implication: 'No flow, scattered attention' },
    { upper: 40,  name: 'LOW',        color: 'neutral', implication: 'Mild engagement, not absorbed' },
    { upper: 60,  name: 'BUILDING',   color: 'info',    implication: 'Getting into something' },
    { upper: 80,  name: 'FLOW',       color: 'success', implication: 'Absorbed, effortless engagement' },
    { upper: 101, name: 'DEEP FLOW',  color: 'success', implication: 'Time disappearing, complete absorption' },
  ],
  physical_distress: [
    { upper: 15,  name: 'NONE',       color: 'success', implication: 'Body comfortable, no physical noise' },
    { upper: 35,  name: 'MILD',       color: 'neutral', implication: 'Minor background discomfort' },
    { upper: 55,  name: 'MODERATE',   color: 'warning', implication: 'Body demanding attention' },
    { upper: 75,  name: 'SIGNIFICANT',color: 'error',   implication: 'Physical state intruding on experience' },
    { upper: 101, name: 'SEVERE',     color: 'error',   implication: 'Body in crisis, can\'t think past it' },
  ],
};

export function getLabel(field: string, value: number): RangeEntry | null {
  const table = RANGES[field] ?? DERIVED_RANGES[field];
  if (!table) return null;
  for (const entry of table) {
    if (value < entry.upper) return entry;
  }
  return table[table.length - 1];
}

export function getLabelWithDepth(
  field: string,
  value: number
): { label: RangeEntry | null; depth: number } {
  const table = RANGES[field] ?? DERIVED_RANGES[field];
  if (!table) return { label: null, depth: 0 };
  let prevUpper = -Infinity;
  for (const entry of table) {
    if (value < entry.upper) {
      const span = entry.upper - prevUpper;
      const depth = span > 0 ? Math.min(1, Math.max(0, (value - prevUpper) / span)) : 0;
      return { label: entry, depth: Math.round(depth * 100) / 100 };
    }
    prevUpper = entry.upper;
  }
  const last = table[table.length - 1];
  return { label: last, depth: 1.0 };
}

// Color → Tailwind/DaisyUI class mappings
export const COLOR_CLASSES: Record<string, { badge: string; progress: string; text: string }> = {
  success: { badge: 'badge-success',  progress: 'progress-success', text: 'text-success' },
  warning: { badge: 'badge-warning',  progress: 'progress-warning', text: 'text-warning' },
  error:   { badge: 'badge-error',    progress: 'progress-error',   text: 'text-error'   },
  info:    { badge: 'badge-info',     progress: 'progress-info',    text: 'text-info'    },
  neutral: { badge: 'badge-neutral',  progress: 'progress-neutral', text: 'text-base-content' },
};
