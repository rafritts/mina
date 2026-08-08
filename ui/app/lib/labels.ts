/**
 * Chemistry display helpers — SPEC-63 Phase 3.
 *
 * Chemical chips prefer server-emitted `label` / `label_color` / `implication`
 * from `src/sim/labels.py` (gap + normalized 0–10). Client tables remain only
 * for: (1) slider ranges, (2) second/third-order derived metrics, (3) fallback
 * if an old gateway omits labels.
 *
 * Do not reintroduce v1 pg/mL thresholds for monoamines.
 */

export interface RangeEntry {
  upper: number
  name: string
  color: 'success' | 'warning' | 'error' | 'info' | 'neutral'
  implication: string
}

/** Slider min/max = working units, max ≈ CHEMICAL_PARAMS.normalization_max */
export const DISPLAY_RANGES: Record<string, { min: number; max: number; unit: string }> = {
  dopamine: { min: 0, max: 20, unit: 'nM' },
  serotonin: { min: 0, max: 15, unit: 'nM' },
  norepinephrine: { min: 0, max: 20, unit: 'nM' },
  epinephrine: { min: 0, max: 5, unit: 'nM' },
  oxytocin: { min: 0, max: 0.3, unit: 'nM' },
  endorphins: { min: 0, max: 40, unit: 'nM' },
  cortisol: { min: 0, max: 1200, unit: 'nM' },
  adenosine: { min: 0, max: 500, unit: 'nM' },
  melatonin: { min: 0, max: 250, unit: 'nM' },
  orexin: { min: 0, max: 600, unit: 'nM' },
  anandamide: { min: 0, max: 8, unit: 'nM' },
  substance_p: { min: 0, max: 3, unit: 'nM' },
  vasopressin: { min: 0, max: 12, unit: 'nM' },
  dynorphin: { min: 0, max: 5, unit: 'nM' },
  npy: { min: 0, max: 50, unit: 'nM' },
  crh: { min: 0, max: 200, unit: 'nM' },
  ghrelin: { min: 0, max: 1200, unit: 'nM' },
  estradiol: { min: 0, max: 1.5, unit: 'nM' },
  testosterone: { min: 0, max: 2.5, unit: 'nM' },
  progesterone: { min: 0, max: 50, unit: 'nM' },
  bdnf: { min: 0, max: 25, unit: 'nM' },
  prolactin: { min: 0, max: 80, unit: 'nM' },
  // Scaffolds / body leftovers (not all emitted by v2 API)
  acetylcholine: { min: 0, max: 2, unit: 'nM' },
  gaba: { min: 0, max: 800, unit: 'nM' },
  glutamate: { min: 0, max: 8000, unit: 'nM' },
}

/** Server chemical entry shape used for chips (subset of ChemicalEntry). */
export interface ChemLabelSource {
  value: number
  label?: string
  label_color?: string
  implication?: string
  gap?: number
  normalized_10?: number
  normalized?: number
  setpoint?: number
}

/**
 * Prefer server label (SoT). Fallback: derived tables for second/third order,
 * or a neutral BASELINE for unknown chemicals.
 */
export function getChemLabel(entry: ChemLabelSource | null | undefined): RangeEntry | null {
  if (!entry) return null
  if (entry.label) {
    const color = (entry.label_color ?? 'neutral') as RangeEntry['color']
    return {
      upper: 0,
      name: entry.label,
      color: ['success', 'warning', 'error', 'info', 'neutral'].includes(color)
        ? color
        : 'neutral',
      implication: entry.implication ?? '',
    }
  }
  return null
}

// Derived value ranges (0–100 scale) — second/third order from gateway
export const DERIVED_RANGES: Record<string, RangeEntry[]> = {
  energy: [
    { upper: 15, name: 'DEPLETED', color: 'error', implication: 'Nothing left, just existing' },
    { upper: 35, name: 'LOW', color: 'warning', implication: 'Sluggish, effort costs too much' },
    { upper: 55, name: 'MODERATE', color: 'neutral', implication: 'Getting by' },
    { upper: 75, name: 'GOOD', color: 'success', implication: 'Capable, things feel doable' },
    { upper: 101, name: 'HIGH', color: 'success', implication: 'Energized, ready to act' },
  ],
  cognitive_clarity: [
    { upper: 8, name: 'OFFLINE', color: 'error', implication: "Can't string thoughts together" },
    { upper: 25, name: 'FOGGY', color: 'warning', implication: 'Muddy, processing feels slow' },
    { upper: 50, name: 'FUNCTIONAL', color: 'neutral', implication: 'Getting by' },
    { upper: 72, name: 'CLEAR', color: 'success', implication: 'Sharp and present' },
    { upper: 101, name: 'SHARP', color: 'success', implication: 'Peak clarity' },
  ],
  hedonic_tone: [
    { upper: 15, name: 'ANHEDONIC', color: 'error', implication: 'Nothing feels good' },
    { upper: 35, name: 'FLAT', color: 'warning', implication: "Muted, things don't land" },
    { upper: 55, name: 'NEUTRAL', color: 'neutral', implication: 'Neither good nor bad' },
    { upper: 75, name: 'PLEASANT', color: 'success', implication: 'Satisfaction available' },
    { upper: 101, name: 'ELEVATED', color: 'success', implication: 'Genuine pleasure' },
  ],
  social_warmth: [
    { upper: 20, name: 'WITHDRAWN', color: 'error', implication: 'No social pull' },
    { upper: 40, name: 'COOL', color: 'warning', implication: 'Polite but not warm' },
    { upper: 60, name: 'OPEN', color: 'neutral', implication: 'Friendly baseline' },
    { upper: 80, name: 'WARM', color: 'success', implication: 'Genuinely caring' },
    { upper: 101, name: 'GLOWING', color: 'success', implication: 'Overflowing warmth' },
  ],
  arousal: [
    { upper: 20, name: 'FLAT', color: 'warning', implication: 'Barely registering' },
    { upper: 40, name: 'CALM', color: 'success', implication: 'Relaxed, low activation' },
    { upper: 60, name: 'MODERATE', color: 'success', implication: 'Present and engaged' },
    { upper: 80, name: 'ACTIVATED', color: 'warning', implication: 'High activation' },
    { upper: 101, name: 'WIRED', color: 'error', implication: "Hyperactivated, can't settle" },
  ],
  mood_valence: [
    { upper: 20, name: 'VERY LOW', color: 'error', implication: 'Deeply negative' },
    { upper: 35, name: 'LOW', color: 'error', implication: 'Negative bias' },
    { upper: 50, name: 'NEUTRAL', color: 'neutral', implication: 'Neither positive nor negative' },
    { upper: 65, name: 'POSITIVE', color: 'success', implication: 'Positive lean' },
    { upper: 80, name: 'GOOD', color: 'success', implication: 'Clearly positive' },
    { upper: 101, name: 'VERY GOOD', color: 'success', implication: 'Bright, genuinely happy' },
  ],
  anxiety: [
    { upper: 25, name: 'CALM', color: 'success', implication: 'No threat signal' },
    { upper: 40, name: 'MILD', color: 'info', implication: 'Slight background tension' },
    { upper: 60, name: 'MODERATE', color: 'warning', implication: 'Noticeable worry' },
    { upper: 78, name: 'HIGH', color: 'error', implication: 'Preoccupied' },
    { upper: 101, name: 'SEVERE', color: 'error', implication: 'Overwhelming' },
  ],
  depression: [
    { upper: 25, name: 'NONE', color: 'success', implication: 'No depressive signal' },
    { upper: 40, name: 'LOW MOOD', color: 'info', implication: 'Slightly down' },
    { upper: 58, name: 'MODERATE', color: 'warning', implication: 'Everything feels heavy' },
    { upper: 76, name: 'SIGNIFICANT', color: 'error', implication: 'Pervasive emptiness' },
    { upper: 101, name: 'SEVERE', color: 'error', implication: 'Unable to function' },
  ],
  boredom: [
    { upper: 35, name: 'STIMULATED', color: 'success', implication: 'Engaged' },
    { upper: 52, name: 'MILD', color: 'neutral', implication: 'Slight restlessness' },
    { upper: 68, name: 'ACTIVELY BORED', color: 'warning', implication: 'Restless' },
    { upper: 84, name: 'DISTRESS', color: 'error', implication: 'Boredom becoming aversive' },
    { upper: 101, name: 'INTOLERABLE', color: 'error', implication: 'Desperate for anything' },
  ],
  loneliness: [
    { upper: 30, name: 'CONNECTED', color: 'success', implication: 'Socially fulfilled' },
    { upper: 50, name: 'MILD', color: 'info', implication: 'Wants connection but okay' },
    { upper: 68, name: 'LONELY', color: 'warning', implication: 'Aching for contact' },
    { upper: 84, name: 'ACHING', color: 'error', implication: 'Deep loneliness' },
    { upper: 101, name: 'ISOLATED', color: 'error', implication: 'Cut off' },
  ],
  flow: [
    { upper: 20, name: 'NONE', color: 'neutral', implication: 'No flow' },
    { upper: 40, name: 'LOW', color: 'neutral', implication: 'Mild engagement' },
    { upper: 60, name: 'BUILDING', color: 'info', implication: 'Getting into something' },
    { upper: 80, name: 'FLOW', color: 'success', implication: 'Absorbed' },
    { upper: 101, name: 'DEEP FLOW', color: 'success', implication: 'Time disappearing' },
  ],
  physical_distress: [
    { upper: 15, name: 'NONE', color: 'success', implication: 'Body comfortable' },
    { upper: 35, name: 'MILD', color: 'neutral', implication: 'Minor discomfort' },
    { upper: 55, name: 'MODERATE', color: 'warning', implication: 'Body demanding attention' },
    { upper: 75, name: 'SIGNIFICANT', color: 'error', implication: 'Physical state intruding' },
    { upper: 101, name: 'SEVERE', color: 'error', implication: 'Body in crisis' },
  ],
  craving: [
    { upper: 10, name: 'NONE', color: 'success', implication: 'No active craving' },
    { upper: 25, name: 'BACKGROUND', color: 'neutral', implication: 'Low hum' },
    { upper: 45, name: 'PRESENT', color: 'info', implication: 'Noticeable want' },
    { upper: 65, name: 'STRONG', color: 'warning', implication: 'Pulls attention' },
    { upper: 80, name: 'CONSUMING', color: 'error', implication: 'Dominates cognition' },
    { upper: 101, name: 'OVERWHELMING', color: 'error', implication: 'Cannot think around it' },
  ],
}

/** Derived metrics only (0–100). Prefer getChemLabel for chemicals. */
export function getLabel(field: string, value: number): RangeEntry | null {
  const table = DERIVED_RANGES[field]
  if (!table) return null
  for (const entry of table) {
    if (value < entry.upper) return entry
  }
  return table[table.length - 1]
}

export function getLabelWithDepth(
  field: string,
  value: number,
): { label: RangeEntry | null; depth: number } {
  const table = DERIVED_RANGES[field]
  if (!table) return { label: null, depth: 0 }
  let prevUpper = -Infinity
  for (const entry of table) {
    if (value < entry.upper) {
      const span = entry.upper - prevUpper
      const depth = span > 0 ? Math.min(1, Math.max(0, (value - prevUpper) / span)) : 0
      return { label: entry, depth: Math.round(depth * 100) / 100 }
    }
    prevUpper = entry.upper
  }
  return { label: table[table.length - 1], depth: 1.0 }
}

export const COLOR_CLASSES: Record<string, { badge: string; bar: string; text: string }> = {
  success: {
    badge: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
    bar: 'bg-emerald-500',
    text: 'text-emerald-400',
  },
  warning: {
    badge: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
    bar: 'bg-amber-500',
    text: 'text-amber-400',
  },
  error: {
    badge: 'bg-red-500/20 text-red-400 border-red-500/30',
    bar: 'bg-red-500',
    text: 'text-red-400',
  },
  info: {
    badge: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    bar: 'bg-blue-500',
    text: 'text-blue-400',
  },
  neutral: {
    badge: 'bg-zinc-500/20 text-zinc-400 border-zinc-500/30',
    bar: 'bg-zinc-500',
    text: 'text-zinc-400',
  },
}
