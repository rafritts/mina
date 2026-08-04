import type { StateData } from './api'

/** Short human label for overall presence from derived state. */
export function presenceLabel(state: StateData | null | undefined): string {
  if (!state) return '—'
  if (state.sleeping) return 'Sleeping'
  const so = state.second_order ?? {}
  const to = state.third_order ?? {}
  if ((to.anxiety ?? 0) > 65) return 'Anxious'
  if ((so.energy ?? 50) > 70 && (so.mood_valence ?? 50) > 65) return 'Elevated'
  if ((so.cognitive_clarity ?? 50) > 65 && (so.energy ?? 50) > 55) return 'Focused'
  if ((so.social_warmth ?? 50) > 65) return 'Warm'
  if ((so.mood_valence ?? 50) < 35) return 'Low'
  if ((so.energy ?? 50) < 30) return 'Depleted'
  return 'Present'
}

export const FIELD_LABELS: Record<string, string> = {
  energy: 'Energy',
  cognitive_clarity: 'Clarity',
  hedonic_tone: 'Hedonic',
  social_warmth: 'Warmth',
  arousal: 'Arousal',
  mood_valence: 'Mood',
  anxiety: 'Anxiety',
  depression: 'Low mood',
  boredom: 'Boredom',
  loneliness: 'Loneliness',
  flow: 'Flow',
  physical_distress: 'Distress',
}

export const SECOND_ORDER = [
  'energy',
  'mood_valence',
  'social_warmth',
  'cognitive_clarity',
  'arousal',
  'hedonic_tone',
] as const

export const THIRD_ORDER = [
  'anxiety',
  'depression',
  'boredom',
  'loneliness',
  'flow',
  'physical_distress',
] as const
