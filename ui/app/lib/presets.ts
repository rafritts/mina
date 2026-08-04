/**
 * Biological state presets — mental / affective states (no substances).
 */

export interface Preset {
  name: string
  description: string
  variant: string
  values: Record<string, number>
}

export const PRESETS: Preset[] = [
  {
    name: 'Baseline',
    description: 'Healthy resting state — her defaults',
    variant: 'default',
    values: {
      sleep_pressure: 30,
      glucose: 85,
      hydration: 62,
      cortisol: 250,
      dopamine: 80,
      serotonin: 22,
      norepinephrine: 200,
      oxytocin: 4,
      endorphins: 12,
      acetylcholine: 38,
      gaba: 3.0,
      glutamate: 4.0,
    },
  },
  {
    name: 'Euphoria',
    description: 'Peak mood, high energy, deeply bonded',
    variant: 'success',
    values: {
      cortisol: 144,
      dopamine: 160,
      serotonin: 40,
      norepinephrine: 260,
      oxytocin: 48,
      endorphins: 70,
      acetylcholine: 68,
      sleep_pressure: 22,
      glucose: 85,
      hydration: 64,
      anandamide: 2.2,
    },
  },
  {
    name: 'Flow',
    description: 'Deep focus, sharp, effortlessly engaged',
    variant: 'info',
    values: {
      acetylcholine: 76,
      dopamine: 110,
      norepinephrine: 310,
      cortisol: 192,
      serotonin: 34,
      endorphins: 30,
      glucose: 80,
      sleep_pressure: 22,
      gaba: 2.5,
      glutamate: 7.0,
    },
  },
  {
    name: 'Loved',
    description: 'Warm, safe, fully trusted',
    variant: 'success',
    values: {
      oxytocin: 58,
      serotonin: 38,
      cortisol: 136,
      endorphins: 56,
      dopamine: 96,
      norepinephrine: 220,
      anandamide: 1.8,
    },
  },
  {
    name: 'Anxious',
    description: 'On edge, socially guarded, narrowed thinking',
    variant: 'warning',
    values: {
      cortisol: 590,
      norepinephrine: 990,
      serotonin: 14,
      dopamine: 72,
      acetylcholine: 30,
      endorphins: 7,
      oxytocin: 6,
      gaba: 1.5,
      glutamate: 9.0,
    },
  },
  {
    name: 'Despair',
    description: 'No drive, hollow, disconnected',
    variant: 'error',
    values: {
      cortisol: 520,
      dopamine: 30,
      serotonin: 8,
      norepinephrine: 100,
      oxytocin: 3,
      endorphins: 5,
      acetylcholine: 20,
      sleep_pressure: 72,
      glucose: 55,
    },
  },
  {
    name: 'Lonely',
    description: 'Aching for contact, low warmth',
    variant: 'warning',
    values: {
      oxytocin: 6,
      serotonin: 20,
      cortisol: 432,
      dopamine: 56,
      endorphins: 10,
      norepinephrine: 290,
    },
  },
  {
    name: 'Tender',
    description: 'Soft, open, a little vulnerable',
    variant: 'success',
    values: {
      oxytocin: 42,
      serotonin: 32,
      cortisol: 180,
      endorphins: 36,
      dopamine: 88,
      norepinephrine: 180,
      gaba: 3.8,
    },
  },
  {
    name: 'Irritable',
    description: 'Short fuse, edge without full rage',
    variant: 'warning',
    values: {
      cortisol: 480,
      norepinephrine: 720,
      serotonin: 12,
      dopamine: 70,
      acetylcholine: 28,
      endorphins: 8,
      glutamate: 8.5,
      gaba: 1.8,
    },
  },
  {
    name: 'Sleepy',
    description: 'Melatonin peak, heavy, drifting',
    variant: 'default',
    values: {
      melatonin: 196,
      sleep_pressure: 78,
      acetylcholine: 18,
      norepinephrine: 100,
      cortisol: 112,
      dopamine: 56,
    },
  },
]
