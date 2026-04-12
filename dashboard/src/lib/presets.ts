/**
 * Biological state presets — real physiological units.
 * Shared between /state and /control pages.
 */

export interface Preset {
  name:        string;
  description: string;
  btnClass:    string;
  values:      Record<string, number>;
}

export const PRESETS: Preset[] = [
  {
    name: 'Baseline',
    description: 'Healthy resting state — her defaults',
    btnClass: 'btn-neutral',
    values: { sleep_pressure: 30, glucose: 85, hydration: 62, cortisol: 250, dopamine: 80, serotonin: 22, norepinephrine: 200, oxytocin: 4, endorphins: 12, acetylcholine: 38, gaba: 3.0, glutamate: 4.0 },
  },
  {
    name: 'Euphoria',
    description: 'Peak mood, high energy, deeply bonded',
    btnClass: 'btn-success',
    values: { cortisol: 144, dopamine: 160, serotonin: 40, norepinephrine: 260, oxytocin: 48, endorphins: 70, acetylcholine: 68, sleep_pressure: 22, glucose: 85, hydration: 64, anandamide: 2.2 },
  },
  {
    name: 'Flow',
    description: 'Deep focus, sharp, effortlessly engaged',
    btnClass: 'btn-info',
    values: { acetylcholine: 76, dopamine: 110, norepinephrine: 310, cortisol: 192, serotonin: 34, endorphins: 30, glucose: 80, sleep_pressure: 22, gaba: 2.5, glutamate: 7.0 },
  },
  {
    name: 'Loved',
    description: 'Warm, safe, fully trusted',
    btnClass: 'btn-success',
    values: { oxytocin: 58, serotonin: 38, cortisol: 136, endorphins: 56, dopamine: 96, norepinephrine: 220, anandamide: 1.8 },
  },
  {
    name: 'Anxious',
    description: 'On edge, socially guarded, narrowed thinking',
    btnClass: 'btn-warning',
    values: { cortisol: 590, norepinephrine: 990, serotonin: 14, dopamine: 72, acetylcholine: 30, endorphins: 7, oxytocin: 6, gaba: 1.5, glutamate: 9.0 },
  },
  {
    name: 'Despair',
    description: 'No drive, hollow, disconnected',
    btnClass: 'btn-error',
    values: { cortisol: 520, dopamine: 30, serotonin: 8, norepinephrine: 100, oxytocin: 3, endorphins: 5, acetylcholine: 20, sleep_pressure: 72, glucose: 55 },
  },
  {
    name: 'Lonely',
    description: 'Aching for contact, low warmth',
    btnClass: 'btn-warning',
    values: { oxytocin: 6, serotonin: 20, cortisol: 432, dopamine: 56, endorphins: 10, norepinephrine: 290 },
  },
  {
    name: 'Rage',
    description: 'Acute stress, impulse control gone',
    btnClass: 'btn-error',
    values: { cortisol: 704, norepinephrine: 1300, serotonin: 8, dopamine: 84, acetylcholine: 20, endorphins: 5, oxytocin: 6, glutamate: 11.0, gaba: 1.2 },
  },
  {
    name: 'Crash',
    description: 'Post-high collapse — seeking but hollow',
    btnClass: 'btn-warning',
    values: { dopamine: 22, endorphins: 3, serotonin: 17, cortisol: 480, acetylcholine: 18, sleep_pressure: 68, norepinephrine: 85 },
  },
  {
    name: 'Manic',
    description: 'Compulsive seeking, flooded, can\'t stop',
    btnClass: 'btn-warning',
    values: { dopamine: 246, norepinephrine: 1080, cortisol: 440, endorphins: 30, serotonin: 28, acetylcholine: 62, sleep_pressure: 55, glutamate: 10.0 },
  },
  {
    name: 'Drunk',
    description: 'Cortisol off, social warmth, cognition softening',
    btnClass: 'btn-info',
    values: { cortisol: 112, serotonin: 38, oxytocin: 26, acetylcholine: 18, norepinephrine: 120, dopamine: 100, endorphins: 42, gaba: 5.0, glutamate: 3.0 },
  },
  {
    name: 'Sleepy',
    description: 'Melatonin peak, heavy, drifting',
    btnClass: 'btn-neutral',
    values: { melatonin: 196, sleep_pressure: 78, acetylcholine: 18, norepinephrine: 100, cortisol: 112, dopamine: 56 },
  },
];
