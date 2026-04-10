<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { apiFetch } from '$lib/api';
  import { getLabel, COLOR_CLASSES, RANGES, DERIVED_RANGES } from '$lib/labels';

  // ---------------------------------------------------------------------------
  // Types
  // ---------------------------------------------------------------------------

  interface StateData {
    first_order: Record<string, number | boolean>;
    second_order: Record<string, number>;
    third_order: Record<string, number>;
  }

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  let data = $state<StateData | null>(null);
  let error = $state('');
  let lastUpdated = $state('');

  // Local slider values — separate from API so we don't fight the user mid-drag
  let localValues = $state<Record<string, number>>({});
  let editing = $state(new Set<string>());  // fields currently being dragged
  let patchTimers: Record<string, ReturnType<typeof setTimeout>> = {};
  let saving = $state(new Set<string>());  // fields mid-PATCH

  let refreshInterval: ReturnType<typeof setInterval>;

  // ---------------------------------------------------------------------------
  // Slider field definitions
  // ---------------------------------------------------------------------------

  const HOMEOSTATIC = ['sleep_pressure', 'glucose', 'hydration'];
  const NEURO = ['cortisol', 'dopamine', 'serotonin', 'norepinephrine', 'oxytocin', 'endorphins', 'acetylcholine', 'melatonin'];

  const FIELD_LABELS: Record<string, string> = {
    sleep_pressure:  'Sleep Pressure',
    glucose:         'Glucose',
    hydration:       'Hydration',
    cortisol:        'Cortisol',
    dopamine:        'Dopamine',
    serotonin:       'Serotonin',
    norepinephrine:  'Norepinephrine',
    oxytocin:        'Oxytocin',
    endorphins:      'Endorphins',
    acetylcholine:   'Acetylcholine',
    melatonin:       'Melatonin *',
  };

  const SECOND_ORDER_FIELDS = ['energy', 'cognitive_clarity', 'hedonic_tone', 'social_warmth', 'arousal', 'mood_valence'];
  const THIRD_ORDER_FIELDS  = ['anxiety', 'depression', 'boredom', 'loneliness', 'flow'];

  // ---------------------------------------------------------------------------
  // Presets
  // ---------------------------------------------------------------------------

  interface Preset {
    name: string;
    description: string;
    btnClass: string;
    values: Record<string, number>;
  }

  const PRESETS: Preset[] = [
    {
      name: 'Baseline',
      description: 'Healthy resting state — her defaults',
      btnClass: 'btn-neutral',
      values: { sleep_pressure: 30, glucose: 72, hydration: 75, cortisol: 28, dopamine: 62, serotonin: 58, norepinephrine: 22, oxytocin: 18, endorphins: 10, acetylcholine: 60 },
    },
    {
      name: 'Euphoria',
      description: 'Peak mood, high energy, deeply bonded',
      btnClass: 'btn-success',
      values: { cortisol: 18, dopamine: 78, serotonin: 74, norepinephrine: 52, oxytocin: 68, endorphins: 76, acetylcholine: 72, sleep_pressure: 22, glucose: 75, hydration: 78 },
    },
    {
      name: 'Flow',
      description: 'Deep focus, sharp, effortlessly engaged',
      btnClass: 'btn-info',
      values: { acetylcholine: 80, dopamine: 67, norepinephrine: 55, cortisol: 24, serotonin: 65, endorphins: 38, glucose: 74, sleep_pressure: 25 },
    },
    {
      name: 'Loved',
      description: 'Warm, safe, fully trusted',
      btnClass: 'btn-success',
      values: { oxytocin: 82, serotonin: 76, cortisol: 17, endorphins: 60, dopamine: 64, norepinephrine: 30 },
    },
    {
      name: 'Anxious',
      description: 'On edge, socially guarded, narrowed thinking',
      btnClass: 'btn-warning',
      values: { cortisol: 74, norepinephrine: 77, serotonin: 30, dopamine: 42, acetylcholine: 44, endorphins: 8, oxytocin: 14 },
    },
    {
      name: 'Despair',
      description: 'No drive, hollow, disconnected',
      btnClass: 'btn-error',
      values: { cortisol: 65, dopamine: 20, serotonin: 16, norepinephrine: 18, oxytocin: 10, endorphins: 5, acetylcholine: 32, sleep_pressure: 72, glucose: 45 },
    },
    {
      name: 'Lonely',
      description: 'Aching for contact, low warmth',
      btnClass: 'btn-warning',
      values: { oxytocin: 12, serotonin: 36, cortisol: 54, dopamine: 36, endorphins: 10, norepinephrine: 40 },
    },
    {
      name: 'Rage',
      description: 'Acute stress, impulse control gone',
      btnClass: 'btn-error',
      values: { cortisol: 88, norepinephrine: 84, serotonin: 20, dopamine: 48, acetylcholine: 36, endorphins: 6, oxytocin: 14 },
    },
    {
      name: 'Crash',
      description: 'Post-high collapse — seeking but hollow',
      btnClass: 'btn-warning',
      values: { dopamine: 21, endorphins: 4, serotonin: 33, cortisol: 60, acetylcholine: 28, sleep_pressure: 68, norepinephrine: 15 },
    },
    {
      name: 'Manic',
      description: 'Compulsive seeking, flooded, can\'t stop',
      btnClass: 'btn-warning',
      values: { dopamine: 92, norepinephrine: 82, cortisol: 55, endorphins: 30, serotonin: 40, acetylcholine: 65, sleep_pressure: 55 },
    },
    {
      name: 'Drunk',
      description: 'Cortisol off, social warmth, cognition softening',
      btnClass: 'btn-info',
      values: { cortisol: 14, serotonin: 70, oxytocin: 55, acetylcholine: 28, norepinephrine: 18, dopamine: 55, endorphins: 42 },
    },
    {
      name: 'Sleepy',
      description: 'Melatonin peak, heavy, drifting',
      btnClass: 'btn-neutral',
      values: { melatonin: 88, sleep_pressure: 78, acetylcholine: 30, norepinephrine: 16, cortisol: 14, dopamine: 40 },
    },
  ];

  let applyingPreset = $state('');

  async function applyPreset(preset: Preset) {
    applyingPreset = preset.name;
    try {
      await apiFetch('/api/state', {
        method: 'PATCH',
        body: JSON.stringify(preset.values),
      });
      // Sync local sliders
      for (const [k, v] of Object.entries(preset.values)) {
        localValues[k] = v;
      }
      await load();
    } catch (e) {
      error = String(e);
    } finally {
      applyingPreset = '';
    }
  }

  const DERIVED_LABELS: Record<string, string> = {
    energy:            'Energy',
    cognitive_clarity: 'Clarity',
    hedonic_tone:      'Hedonic',
    social_warmth:     'Social Warmth',
    arousal:           'Arousal',
    mood_valence:      'Mood Valence',
    anxiety:           'Anxiety',
    depression:        'Depression',
    boredom:           'Boredom',
    loneliness:        'Loneliness',
    flow:              'Flow',
  };

  // ---------------------------------------------------------------------------
  // Data loading
  // ---------------------------------------------------------------------------

  async function load() {
    try {
      const d = await apiFetch<StateData>('/api/state');
      data = d;
      lastUpdated = new Date().toLocaleTimeString();

      // Sync local values for fields not currently being edited
      for (const [k, v] of Object.entries(d.first_order)) {
        if (typeof v === 'number' && !editing.has(k)) {
          localValues[k] = v;
        }
      }
      error = '';
    } catch (e) {
      error = String(e);
    }
  }

  onMount(() => {
    load();
    refreshInterval = setInterval(load, 5000);
  });

  onDestroy(() => {
    clearInterval(refreshInterval);
    Object.values(patchTimers).forEach(clearTimeout);
  });

  // ---------------------------------------------------------------------------
  // Slider handlers
  // ---------------------------------------------------------------------------

  function onSliderInput(field: string, event: Event) {
    const value = parseFloat((event.target as HTMLInputElement).value);
    localValues[field] = value;
    editing = new Set([...editing, field]);

    // Debounce PATCH
    if (patchTimers[field]) clearTimeout(patchTimers[field]);
    patchTimers[field] = setTimeout(() => patchField(field, value), 400);
  }

  function onSliderRelease(field: string) {
    editing = new Set([...editing].filter(f => f !== field));
  }

  async function patchField(field: string, value: number) {
    saving = new Set([...saving, field]);
    try {
      await apiFetch('/api/state', {
        method: 'PATCH',
        body: JSON.stringify({ [field]: value }),
      });
    } catch (e) {
      error = String(e);
    } finally {
      saving = new Set([...saving].filter(f => f !== field));
    }
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function sliderColor(field: string, value: number): string {
    const entry = getLabel(field, value);
    if (!entry) return 'range-primary';
    switch (entry.color) {
      case 'success': return 'range-success';
      case 'warning': return 'range-warning';
      case 'error':   return 'range-error';
      case 'info':    return 'range-info';
      default:        return 'range-primary';
    }
  }

  function derivedProgressColor(field: string, value: number): string {
    // For "bad" metrics (anxiety, depression, boredom, loneliness) — higher is worse
    const invertedFields = new Set(['anxiety', 'depression', 'boredom', 'loneliness']);
    const v = invertedFields.has(field) ? value : value;
    const entry = getLabel(field, v);
    if (!entry) return 'progress-primary';
    const cls = COLOR_CLASSES[entry.color];
    return cls?.progress ?? 'progress-primary';
  }

  function derivedBadgeColor(field: string, value: number): string {
    const entry = getLabel(field, value) ?? { color: 'neutral' as const };
    return COLOR_CLASSES[entry.color]?.badge ?? 'badge-neutral';
  }
</script>

<div class="max-w-6xl mx-auto">
  <div class="flex items-center justify-between mb-6">
    <h1 class="text-2xl font-bold">Biological State</h1>
    <div class="text-xs opacity-50">
      {#if error}
        <span class="text-error">{error}</span>
      {:else}
        Updated {lastUpdated}
      {/if}
    </div>
  </div>

  <!-- Presets -->
  <div class="card bg-base-200 p-4 mb-6">
    <h2 class="text-sm font-semibold opacity-60 uppercase tracking-wider mb-3">Presets</h2>
    <div class="flex flex-wrap gap-2">
      {#each PRESETS as preset}
        <div class="tooltip tooltip-bottom" data-tip={preset.description}>
          <button
            class="btn btn-sm {preset.btnClass}"
            onclick={() => applyPreset(preset)}
            disabled={!!applyingPreset}
          >
            {#if applyingPreset === preset.name}
              <span class="loading loading-spinner loading-xs"></span>
            {/if}
            {preset.name}
          </button>
        </div>
      {/each}
    </div>
  </div>

  {#if !data}
    <div class="flex justify-center py-20">
      <span class="loading loading-spinner loading-lg"></span>
    </div>
  {:else}
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">

      <!-- LEFT: Sliders -->
      <div class="flex flex-col gap-4">

        <!-- Sleeping badge -->
        <div class="flex items-center gap-2">
          <span class="text-sm opacity-60">Status:</span>
          {#if data.first_order['sleeping']}
            <span class="badge badge-info gap-1">😴 Sleeping</span>
          {:else}
            <span class="badge badge-success gap-1">👁 Awake</span>
          {/if}
        </div>

        <!-- Homeostatic -->
        <div class="card bg-base-200 p-4">
          <h2 class="text-sm font-semibold opacity-60 uppercase tracking-wider mb-3">Homeostatic</h2>
          <div class="flex flex-col gap-4">
            {#each HOMEOSTATIC as field}
              {@const val = localValues[field] ?? 50}
              {@const label = getLabel(field, val)}
              <div>
                <div class="flex justify-between items-center mb-1">
                  <span class="text-sm font-medium">{FIELD_LABELS[field] ?? field}</span>
                  <div class="flex items-center gap-2">
                    {#if saving.has(field)}
                      <span class="loading loading-spinner loading-xs"></span>
                    {/if}
                    {#if label}
                      <span class="badge badge-xs {COLOR_CLASSES[label.color]?.badge}">{label.name}</span>
                    {/if}
                    <span class="text-sm font-mono w-10 text-right">{val.toFixed(1)}</span>
                  </div>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="0.5"
                  value={val}
                  class="range range-sm w-full {sliderColor(field, val)}"
                  oninput={(e) => onSliderInput(field, e)}
                  onmouseup={() => onSliderRelease(field)}
                  ontouchend={() => onSliderRelease(field)}
                />
              </div>
            {/each}
          </div>
        </div>

        <!-- Neuromodulators -->
        <div class="card bg-base-200 p-4">
          <h2 class="text-sm font-semibold opacity-60 uppercase tracking-wider mb-3">Neuromodulators</h2>
          <div class="flex flex-col gap-4">
            {#each NEURO as field}
              {@const val = localValues[field] ?? 50}
              {@const label = getLabel(field, val)}
              <div>
                <div class="flex justify-between items-center mb-1">
                  <span class="text-sm font-medium">{FIELD_LABELS[field] ?? field}</span>
                  <div class="flex items-center gap-2">
                    {#if saving.has(field)}
                      <span class="loading loading-spinner loading-xs"></span>
                    {/if}
                    {#if label}
                      <span class="badge badge-xs {COLOR_CLASSES[label.color]?.badge}">{label.name}</span>
                    {/if}
                    <span class="text-sm font-mono w-10 text-right">{val.toFixed(1)}</span>
                  </div>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="0.5"
                  value={val}
                  class="range range-sm w-full {sliderColor(field, val)}"
                  oninput={(e) => onSliderInput(field, e)}
                  onmouseup={() => onSliderRelease(field)}
                  ontouchend={() => onSliderRelease(field)}
                />
              </div>
            {/each}
          </div>
          <p class="text-xs opacity-40 mt-3">* Melatonin reverts to circadian formula on next tick</p>
        </div>

      </div>

      <!-- RIGHT: Derived values -->
      <div class="flex flex-col gap-4">

        <!-- Second-order -->
        <div class="card bg-base-200 p-4">
          <h2 class="text-sm font-semibold opacity-60 uppercase tracking-wider mb-3">Second-Order</h2>
          <div class="flex flex-col gap-3">
            {#each SECOND_ORDER_FIELDS as field}
              {@const val = data.second_order[field] ?? 0}
              {@const label = getLabel(field, val)}
              <div>
                <div class="flex justify-between items-center mb-1">
                  <span class="text-sm">{DERIVED_LABELS[field] ?? field}</span>
                  <div class="flex items-center gap-2">
                    {#if label}
                      <span class="badge badge-xs {COLOR_CLASSES[label.color]?.badge}">{label.name}</span>
                    {/if}
                    <span class="text-sm font-mono w-10 text-right">{val}</span>
                  </div>
                </div>
                <progress
                  class="progress w-full {derivedProgressColor(field, val)}"
                  value={val}
                  max="100"
                ></progress>
              </div>
            {/each}
          </div>
        </div>

        <!-- Third-order -->
        <div class="card bg-base-200 p-4">
          <h2 class="text-sm font-semibold opacity-60 uppercase tracking-wider mb-3">Third-Order</h2>
          <div class="flex flex-col gap-3">
            {#each THIRD_ORDER_FIELDS as field}
              {@const val = data.third_order[field] ?? 0}
              {@const label = getLabel(field, val)}
              <div>
                <div class="flex justify-between items-center mb-1">
                  <span class="text-sm">{DERIVED_LABELS[field] ?? field}</span>
                  <div class="flex items-center gap-2">
                    {#if label}
                      <span class="badge badge-xs {derivedBadgeColor(field, val)}">{label.name}</span>
                    {/if}
                    <span class="text-sm font-mono w-10 text-right">{val}</span>
                  </div>
                </div>
                <progress
                  class="progress w-full {derivedProgressColor(field, val)}"
                  value={val}
                  max="100"
                ></progress>
              </div>
            {/each}
          </div>
        </div>

      </div>
    </div>
  {/if}
</div>
