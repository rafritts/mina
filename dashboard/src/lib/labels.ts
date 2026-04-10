/**
 * Range label tables for chemical display — real physiological units.
 * Thresholds match chemicals.py REGISTRY label tables.
 *
 * Also contains display ranges (min/max) for each chemical's slider.
 */

export interface RangeEntry {
  upper: number;
  name: string;
  color: 'success' | 'warning' | 'error' | 'info' | 'neutral';
}

// Display ranges for slider min/max (matches REGISTRY display_min / display_max)
export const DISPLAY_RANGES: Record<string, { min: number; max: number; unit: string }> = {
  cortisol:        { min: 50,   max: 900,  unit: 'nmol/L' },
  norepinephrine:  { min: 50,   max: 2000, unit: 'pg/mL'  },
  dopamine:        { min: 0,    max: 300,  unit: 'pg/mL'  },
  serotonin:       { min: 2,    max: 60,   unit: 'ng/mL'  },
  oxytocin:        { min: 0,    max: 80,   unit: 'pg/mL'  },
  endorphins:      { min: 0,    max: 150,  unit: 'pg/mL'  },
  acetylcholine:   { min: 5,    max: 90,   unit: 'nmol/L' },
  melatonin:       { min: 0,    max: 220,  unit: 'pg/mL'  },
  glucose:         { min: 40,   max: 200,  unit: 'mg/dL'  },
  hydration:       { min: 48,   max: 70,   unit: '% TBW'  },
  sleep_pressure:  { min: 0,    max: 100,  unit: 'AU'     },
};

export const RANGES: Record<string, RangeEntry[]> = {
  cortisol: [
    { upper: 100,   name: 'DEPLETED',     color: 'warning' },
    { upper: 380,   name: 'NORMAL',       color: 'success' },
    { upper: 520,   name: 'ELEVATED',     color: 'warning' },
    { upper: 650,   name: 'HIGH STRESS',  color: 'error'   },
    { upper: 760,   name: 'ACUTE STRESS', color: 'error'   },
    { upper: 99999, name: 'MAXED',        color: 'error'   },
  ],
  norepinephrine: [
    { upper: 65,    name: 'SEDATED',    color: 'warning' },
    { upper: 175,   name: 'RELAXED',    color: 'success' },
    { upper: 290,   name: 'CALM ALERT', color: 'success' },
    { upper: 360,   name: 'FOCUSED',    color: 'success' },
    { upper: 500,   name: 'HEIGHTENED', color: 'warning' },
    { upper: 750,   name: 'HYPERALERT', color: 'error'   },
    { upper: 99999, name: 'FLOODED',    color: 'error'   },
  ],
  dopamine: [
    { upper: 24,    name: 'NO DRIVE',       color: 'error'   },
    { upper: 56,    name: 'LOW SEEKING',    color: 'warning' },
    { upper: 112,   name: 'BASELINE',       color: 'success' },
    { upper: 180,   name: 'ACTIVE SEEKING', color: 'info'    },
    { upper: 240,   name: 'HIGH DRIVE',     color: 'warning' },
    { upper: 99999, name: 'COMPULSIVE',     color: 'error'   },
  ],
  serotonin: [
    { upper: 8,     name: 'DYSPHORIC',   color: 'error'   },
    { upper: 16,    name: 'INSECURE',    color: 'warning' },
    { upper: 28,    name: 'NEUTRAL',     color: 'neutral' },
    { upper: 38,    name: 'SECURE',      color: 'success' },
    { upper: 99999, name: 'VERY STABLE', color: 'success' },
  ],
  oxytocin: [
    { upper: 12,    name: 'NO BOND',        color: 'error'   },
    { upper: 28,    name: 'ACQUAINTANCE',   color: 'warning' },
    { upper: 44,    name: 'FRIENDLY',       color: 'info'    },
    { upper: 57,    name: 'TRUSTED FRIEND', color: 'success' },
    { upper: 70,    name: 'DEEP TRUST',     color: 'success' },
    { upper: 99999, name: 'PROFOUND BOND',  color: 'success' },
  ],
  endorphins: [
    { upper: 7,     name: 'DEPLETED',    color: 'error'   },
    { upper: 20,    name: 'BASELINE',    color: 'neutral' },
    { upper: 45,    name: 'MILD WARMTH', color: 'info'    },
    { upper: 80,    name: 'PLEASURE',    color: 'success' },
    { upper: 120,   name: 'HIGH',        color: 'success' },
    { upper: 99999, name: 'FLOODED',     color: 'success' },
  ],
  acetylcholine: [
    { upper: 18,    name: 'OFFLINE',    color: 'error'   },
    { upper: 39,    name: 'IMPAIRED',   color: 'warning' },
    { upper: 60,    name: 'FUNCTIONAL', color: 'success' },
    { upper: 76,    name: 'SHARP',      color: 'success' },
    { upper: 99999, name: 'HEIGHTENED', color: 'success' },
  ],
  melatonin: [
    { upper: 154,   name: 'ACTIVE',    color: 'success' },
    { upper: 176,   name: 'UNWINDING', color: 'info'    },
    { upper: 198,   name: 'IDLING',    color: 'warning' },
    { upper: 99999, name: 'RAMPING',   color: 'error'   },
  ],
  glucose: [
    { upper: 55,    name: 'HYPOGLYCEMIC', color: 'error'   },
    { upper: 70,    name: 'LOW',          color: 'warning' },
    { upper: 110,   name: 'NORMAL',       color: 'success' },
    { upper: 180,   name: 'WELL-FUELED',  color: 'success' },
    { upper: 99999, name: 'HIGH',         color: 'warning' },
  ],
  hydration: [
    { upper: 54,    name: 'CRITICALLY DRY', color: 'error'   },
    { upper: 58,    name: 'DEHYDRATED',     color: 'error'   },
    { upper: 60,    name: 'LOW',            color: 'warning' },
    { upper: 64,    name: 'NORMAL',         color: 'success' },
    { upper: 99999, name: 'WELL HYDRATED',  color: 'success' },
  ],
  sleep_pressure: [
    { upper: 50,    name: 'WELL RESTED', color: 'success' },
    { upper: 65,    name: 'BUILDING',    color: 'neutral' },
    { upper: 80,    name: 'TIRED',       color: 'warning' },
    { upper: 90,    name: 'FATIGUED',    color: 'warning' },
    { upper: 99999, name: 'EXHAUSTED',   color: 'error'   },
  ],
};

// Derived value ranges (0–100 scale, unchanged)
export const DERIVED_RANGES: Record<string, RangeEntry[]> = {
  cognitive_clarity: [
    { upper: 8,   name: 'OFFLINE',    color: 'error'   },
    { upper: 25,  name: 'FOGGY',      color: 'warning' },
    { upper: 50,  name: 'FUNCTIONAL', color: 'neutral' },
    { upper: 72,  name: 'CLEAR',      color: 'success' },
    { upper: 101, name: 'SHARP',      color: 'success' },
  ],
  anxiety: [
    { upper: 35,  name: 'CALM',     color: 'success' },
    { upper: 52,  name: 'MILD',     color: 'info'    },
    { upper: 68,  name: 'MODERATE', color: 'warning' },
    { upper: 84,  name: 'HIGH',     color: 'error'   },
    { upper: 101, name: 'SEVERE',   color: 'error'   },
  ],
  boredom: [
    { upper: 45,  name: 'STIMULATED',     color: 'success' },
    { upper: 60,  name: 'MILD',           color: 'neutral' },
    { upper: 74,  name: 'ACTIVELY BORED', color: 'warning' },
    { upper: 88,  name: 'DISTRESS',       color: 'error'   },
    { upper: 101, name: 'INTOLERABLE',    color: 'error'   },
  ],
  loneliness: [
    { upper: 55,  name: 'CONNECTED', color: 'success' },
    { upper: 68,  name: 'MILD',      color: 'info'    },
    { upper: 80,  name: 'LONELY',    color: 'warning' },
    { upper: 92,  name: 'ACHING',    color: 'error'   },
    { upper: 101, name: 'ISOLATED',  color: 'error'   },
  ],
  depression: [
    { upper: 35,  name: 'NONE',        color: 'success' },
    { upper: 52,  name: 'LOW MOOD',    color: 'info'    },
    { upper: 68,  name: 'MODERATE',    color: 'warning' },
    { upper: 84,  name: 'SIGNIFICANT', color: 'error'   },
    { upper: 101, name: 'SEVERE',      color: 'error'   },
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

// Color → Tailwind/DaisyUI class mappings
export const COLOR_CLASSES: Record<string, { badge: string; progress: string; text: string }> = {
  success: { badge: 'badge-success',  progress: 'progress-success', text: 'text-success' },
  warning: { badge: 'badge-warning',  progress: 'progress-warning', text: 'text-warning' },
  error:   { badge: 'badge-error',    progress: 'progress-error',   text: 'text-error'   },
  info:    { badge: 'badge-info',     progress: 'progress-info',    text: 'text-info'    },
  neutral: { badge: 'badge-neutral',  progress: 'progress-neutral', text: 'text-base-content' },
};
