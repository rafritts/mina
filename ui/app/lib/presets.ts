/**
 * Biological state presets — working nM units (SPEC-63).
 * Values are tonic overrides sent via PATCH /api/state.
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
    description: 'Healthy resting state — near setpoints',
    variant: 'default',
    values: {
      dopamine: 8.0,
      serotonin: 6.0,
      norepinephrine: 3.0,
      epinephrine: 0.3,
      oxytocin: 0.015,
      endorphins: 2.5,
      cortisol: 250,
      adenosine: 100,
      melatonin: 5,
    },
  },
  {
    name: 'Euphoria',
    description: 'Peak mood, high energy, bonded surge',
    variant: 'success',
    values: {
      dopamine: 14,
      serotonin: 11,
      norepinephrine: 6,
      oxytocin: 0.12,
      endorphins: 18,
      cortisol: 180,
      adenosine: 80,
    },
  },
  {
    name: 'Flow',
    description: 'Deep focus, sharp, engaged',
    variant: 'info',
    values: {
      dopamine: 11,
      serotonin: 8,
      norepinephrine: 8,
      cortisol: 280,
      endorphins: 6,
      adenosine: 90,
    },
  },
  {
    name: 'Loved',
    description: 'Warm bonding surge, safe',
    variant: 'success',
    values: {
      oxytocin: 0.15,
      serotonin: 10,
      cortisol: 160,
      endorphins: 12,
      dopamine: 10,
      norepinephrine: 3.5,
    },
  },
  {
    name: 'Anxious',
    description: 'On edge, high HPA / NE',
    variant: 'warning',
    values: {
      cortisol: 700,
      norepinephrine: 14,
      serotonin: 3.5,
      dopamine: 6,
      oxytocin: 0.01,
      endorphins: 1.5,
      epinephrine: 2.0,
    },
  },
  {
    name: 'Despair',
    description: 'Low drive, hollow, disconnected',
    variant: 'error',
    values: {
      cortisol: 500,
      dopamine: 2.5,
      serotonin: 2.0,
      norepinephrine: 1.5,
      oxytocin: 0.008,
      endorphins: 1.0,
      adenosine: 280,
    },
  },
  {
    name: 'Lonely',
    description: 'OT below floor, mild stress',
    variant: 'warning',
    values: {
      oxytocin: 0.005,
      serotonin: 4.5,
      cortisol: 400,
      dopamine: 6,
      endorphins: 1.8,
      norepinephrine: 4,
    },
  },
  {
    name: 'Tender',
    description: 'Soft OT surge, open',
    variant: 'success',
    values: {
      oxytocin: 0.08,
      serotonin: 8,
      cortisol: 200,
      endorphins: 8,
      dopamine: 9,
      norepinephrine: 2.8,
    },
  },
  {
    name: 'Irritable',
    description: 'Short fuse — stress up, 5-HT down',
    variant: 'warning',
    values: {
      cortisol: 550,
      norepinephrine: 10,
      serotonin: 3.2,
      dopamine: 6.5,
      endorphins: 1.5,
    },
  },
  {
    name: 'Sleepy',
    description: 'High melatonin + adenosine pressure',
    variant: 'default',
    values: {
      melatonin: 120,
      adenosine: 420,
      norepinephrine: 1.8,
      cortisol: 120,
      dopamine: 6,
    },
  },
]
