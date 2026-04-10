/**
 * Range label tables mirroring bio_report.py.
 * Used by sliders to show the current named state without an API round-trip.
 */

export interface RangeEntry {
  upper: number;
  name: string;
  color: 'success' | 'warning' | 'error' | 'info' | 'neutral';
}

export const RANGES: Record<string, RangeEntry[]> = {
  cortisol: [
    { upper: 15,  name: 'DEPLETED',     color: 'warning' },
    { upper: 40,  name: 'NORMAL',       color: 'success' },
    { upper: 60,  name: 'ELEVATED',     color: 'warning' },
    { upper: 78,  name: 'HIGH STRESS',  color: 'error' },
    { upper: 92,  name: 'ACUTE STRESS', color: 'error' },
    { upper: 101, name: 'MAXED',        color: 'error' },
  ],
  oxytocin: [
    { upper: 15,  name: 'NO BOND',        color: 'error' },
    { upper: 35,  name: 'ACQUAINTANCE',   color: 'warning' },
    { upper: 55,  name: 'FRIENDLY',       color: 'info' },
    { upper: 72,  name: 'TRUSTED FRIEND', color: 'success' },
    { upper: 88,  name: 'DEEP TRUST',     color: 'success' },
    { upper: 101, name: 'PROFOUND BOND',  color: 'success' },
  ],
  dopamine: [
    { upper: 20,  name: 'NO DRIVE',       color: 'error' },
    { upper: 40,  name: 'LOW SEEKING',    color: 'warning' },
    { upper: 60,  name: 'BASELINE',       color: 'success' },
    { upper: 75,  name: 'ACTIVE SEEKING', color: 'info' },
    { upper: 90,  name: 'HIGH DRIVE',     color: 'warning' },
    { upper: 101, name: 'COMPULSIVE',     color: 'error' },
  ],
  serotonin: [
    { upper: 20,  name: 'DYSPHORIC',   color: 'error' },
    { upper: 40,  name: 'INSECURE',    color: 'warning' },
    { upper: 60,  name: 'NEUTRAL',     color: 'neutral' },
    { upper: 80,  name: 'SECURE',      color: 'success' },
    { upper: 101, name: 'VERY STABLE', color: 'success' },
  ],
  endorphins: [
    { upper: 15,  name: 'NONE',        color: 'neutral' },
    { upper: 35,  name: 'MILD WARMTH', color: 'info' },
    { upper: 60,  name: 'PLEASURE',    color: 'success' },
    { upper: 80,  name: 'HIGH',        color: 'success' },
    { upper: 101, name: 'PEAK',        color: 'success' },
  ],
  norepinephrine: [
    { upper: 25,  name: 'SEDATED',    color: 'warning' },
    { upper: 45,  name: 'CALM ALERT', color: 'success' },
    { upper: 65,  name: 'FOCUSED',    color: 'success' },
    { upper: 80,  name: 'HEIGHTENED', color: 'warning' },
    { upper: 92,  name: 'HYPERALERT', color: 'error' },
    { upper: 101, name: 'FLOODED',    color: 'error' },
  ],
  acetylcholine: [
    { upper: 15,  name: 'OFFLINE',    color: 'error' },
    { upper: 40,  name: 'IMPAIRED',   color: 'warning' },
    { upper: 65,  name: 'FUNCTIONAL', color: 'success' },
    { upper: 85,  name: 'SHARP',      color: 'success' },
    { upper: 101, name: 'HEIGHTENED', color: 'success' },
  ],
  glucose: [
    { upper: 40,  name: 'HYPOGLYCEMIC', color: 'error' },
    { upper: 58,  name: 'LOW',          color: 'warning' },
    { upper: 80,  name: 'NORMAL',       color: 'success' },
    { upper: 101, name: 'WELL-FUELED',  color: 'success' },
  ],
  hydration: [
    { upper: 30,  name: 'SEVERELY DRY', color: 'error' },
    { upper: 50,  name: 'THIRSTY',      color: 'warning' },
    { upper: 75,  name: 'OK',           color: 'neutral' },
    { upper: 101, name: 'HYDRATED',     color: 'success' },
  ],
  sleep_pressure: [
    { upper: 25,  name: 'WELL RESTED',  color: 'success' },
    { upper: 45,  name: 'ALERT',        color: 'success' },
    { upper: 65,  name: 'TIRED',        color: 'warning' },
    { upper: 80,  name: 'FATIGUED',     color: 'warning' },
    { upper: 101, name: 'EXHAUSTED',    color: 'error' },
  ],
  melatonin: [
    { upper: 18,  name: 'AWAKE',          color: 'success' },
    { upper: 38,  name: 'DROWSY',         color: 'info' },
    { upper: 58,  name: 'HEAVY',          color: 'warning' },
    { upper: 78,  name: 'SLEEP PULL',     color: 'warning' },
    { upper: 101, name: 'SLEEP IMMINENT', color: 'error' },
  ],
};

// Derived value ranges
export const DERIVED_RANGES: Record<string, RangeEntry[]> = {
  cognitive_clarity: [
    { upper: 8,   name: 'OFFLINE',    color: 'error' },
    { upper: 25,  name: 'FOGGY',      color: 'warning' },
    { upper: 50,  name: 'FUNCTIONAL', color: 'neutral' },
    { upper: 72,  name: 'CLEAR',      color: 'success' },
    { upper: 101, name: 'SHARP',      color: 'success' },
  ],
  anxiety: [
    { upper: 35,  name: 'CALM',     color: 'success' },
    { upper: 52,  name: 'MILD',     color: 'info' },
    { upper: 68,  name: 'MODERATE', color: 'warning' },
    { upper: 84,  name: 'HIGH',     color: 'error' },
    { upper: 101, name: 'SEVERE',   color: 'error' },
  ],
  boredom: [
    { upper: 45,  name: 'STIMULATED',     color: 'success' },
    { upper: 60,  name: 'MILD',           color: 'neutral' },
    { upper: 74,  name: 'ACTIVELY BORED', color: 'warning' },
    { upper: 88,  name: 'DISTRESS',       color: 'error' },
    { upper: 101, name: 'INTOLERABLE',    color: 'error' },
  ],
  loneliness: [
    { upper: 55,  name: 'CONNECTED', color: 'success' },
    { upper: 68,  name: 'MILD',      color: 'info' },
    { upper: 80,  name: 'LONELY',    color: 'warning' },
    { upper: 92,  name: 'ACHING',    color: 'error' },
    { upper: 101, name: 'ISOLATED',  color: 'error' },
  ],
  depression: [
    { upper: 35,  name: 'NONE',        color: 'success' },
    { upper: 52,  name: 'LOW MOOD',    color: 'info' },
    { upper: 68,  name: 'MODERATE',    color: 'warning' },
    { upper: 84,  name: 'SIGNIFICANT', color: 'error' },
    { upper: 101, name: 'SEVERE',      color: 'error' },
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
