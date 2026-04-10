<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { apiFetch } from '$lib/api';
  import { getLabel, COLOR_CLASSES, RANGES, DERIVED_RANGES, DISPLAY_RANGES } from '$lib/labels';

  // ---------------------------------------------------------------------------
  // Types
  // ---------------------------------------------------------------------------

  interface ChemicalEntry {
    value: number;
    unit: string;
    label: string;
    normalized: number;  // 0.0–1.0
  }

  interface VitalEntry {
    value?: number;
    systolic?: number;
    diastolic?: number;
    unit: string;
    label: string;
  }

  interface StateData {
    chemicals: Record<string, ChemicalEntry>;
    sleeping: boolean;
    second_order: Record<string, number>;
    third_order: Record<string, number>;
    vital_signs: Record<string, VitalEntry>;
  }

  interface TokenStats {
    session_start: number | null;
    total_input: number;
    total_output: number;
    total_reasoning: number;
    turns: number;
    by_label: Record<string, { input: number; output: number; reasoning: number }>;
  }

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  let data = $state<StateData | null>(null);
  let tokens = $state<TokenStats | null>(null);
  let error = $state('');
  let lastUpdated = $state('');

  // Local slider values in REAL units — separate from API to avoid fighting mid-drag
  let localValues = $state<Record<string, number>>({});
  let editing = $state(new Set<string>());
  let patchTimers: Record<string, ReturnType<typeof setTimeout>> = {};
  let saving = $state(new Set<string>());

  let refreshInterval: ReturnType<typeof setInterval>;

  // ---------------------------------------------------------------------------
  // Field definitions
  // ---------------------------------------------------------------------------

  const HOMEOSTATIC = ['sleep_pressure', 'glucose', 'hydration'];
  const NEURO       = ['cortisol', 'dopamine', 'serotonin', 'norepinephrine', 'oxytocin', 'endorphins', 'acetylcholine'];
  const NEURO_READONLY = ['melatonin'];

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
  // Presets (values in real physiological units)
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
      values: { sleep_pressure: 30, glucose: 85, hydration: 62, cortisol: 250, dopamine: 80, serotonin: 22, norepinephrine: 200, oxytocin: 4, endorphins: 12, acetylcholine: 38 },
    },
    {
      name: 'Euphoria',
      description: 'Peak mood, high energy, deeply bonded',
      btnClass: 'btn-success',
      values: { cortisol: 144, dopamine: 160, serotonin: 40, norepinephrine: 260, oxytocin: 48, endorphins: 70, acetylcholine: 68, sleep_pressure: 22, glucose: 85, hydration: 64 },
    },
    {
      name: 'Flow',
      description: 'Deep focus, sharp, effortlessly engaged',
      btnClass: 'btn-info',
      values: { acetylcholine: 76, dopamine: 110, norepinephrine: 310, cortisol: 192, serotonin: 34, endorphins: 30, glucose: 80, sleep_pressure: 22 },
    },
    {
      name: 'Loved',
      description: 'Warm, safe, fully trusted',
      btnClass: 'btn-success',
      values: { oxytocin: 58, serotonin: 38, cortisol: 136, endorphins: 56, dopamine: 96, norepinephrine: 220 },
    },
    {
      name: 'Anxious',
      description: 'On edge, socially guarded, narrowed thinking',
      btnClass: 'btn-warning',
      values: { cortisol: 590, norepinephrine: 990, serotonin: 14, dopamine: 72, acetylcholine: 30, endorphins: 7, oxytocin: 6 },
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
      values: { cortisol: 704, norepinephrine: 1300, serotonin: 8, dopamine: 84, acetylcholine: 20, endorphins: 5, oxytocin: 6 },
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
      values: { dopamine: 246, norepinephrine: 1080, cortisol: 440, endorphins: 30, serotonin: 28, acetylcholine: 62, sleep_pressure: 55 },
    },
    {
      name: 'Drunk',
      description: 'Cortisol off, social warmth, cognition softening',
      btnClass: 'btn-info',
      values: { cortisol: 112, serotonin: 38, oxytocin: 26, acetylcholine: 18, norepinephrine: 120, dopamine: 100, endorphins: 42 },
    },
    {
      name: 'Sleepy',
      description: 'Melatonin peak, heavy, drifting',
      btnClass: 'btn-neutral',
      values: { melatonin: 196, sleep_pressure: 78, acetylcholine: 18, norepinephrine: 100, cortisol: 112, dopamine: 56 },
    },
  ];

  let applyingPreset = $state('');
  let presetSnapshot = $state<Record<string, number> | null>(null);

  async function applyPreset(preset: Preset) {
    applyingPreset = preset.name;
    presetSnapshot = { ...localValues };
    try {
      await apiFetch('/api/state', {
        method: 'PATCH',
        body: JSON.stringify(preset.values),
      });
      for (const [k, v] of Object.entries(preset.values)) {
        localValues[k] = v;
      }
      await load();
    } catch (e) {
      error = String(e);
      presetSnapshot = null;
    } finally {
      applyingPreset = '';
    }
  }

  async function undoPreset() {
    if (!presetSnapshot) return;
    const snap = presetSnapshot;
    presetSnapshot = null;
    try {
      await apiFetch('/api/state', {
        method: 'PATCH',
        body: JSON.stringify(snap),
      });
      for (const [k, v] of Object.entries(snap)) {
        localValues[k] = v;
      }
      await load();
    } catch (e) {
      error = String(e);
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

      // Sync local slider values (real units) for fields not being edited
      for (const [k, chem] of Object.entries(d.chemicals)) {
        if (!editing.has(k)) {
          localValues[k] = chem.value;
        }
      }
      error = '';
    } catch (e) {
      error = String(e);
    }

    try {
      tokens = await apiFetch<TokenStats>('/api/tokens');
    } catch (_) {}
  }

  const TOKEN_LABEL_NAMES: Record<string, string> = {
    stimulus:    'Stimulus encode',
    mode1:       'Mode 1 (subconscious)',
    main:        'Main response',
    main_follow: 'Follow-up',
    response:    'Response encode',
    activity:    'Activity encode',
    mode2:       'Heartbeat (Mode 2)',
    compact:     'History compaction',
  };

  function fmtNum(n: number): string {
    return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
  }

  function sessionAge(ts: number | null): string {
    if (!ts) return 'unknown';
    const secs = Math.floor(Date.now() / 1000 - ts);
    if (secs < 60) return `${secs}s ago`;
    if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
    return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m ago`;
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
  // Slider handlers — real units
  // ---------------------------------------------------------------------------

  function onSliderInput(field: string, event: Event) {
    const value = parseFloat((event.target as HTMLInputElement).value);
    localValues[field] = value;
    editing = new Set([...editing, field]);

    if (patchTimers[field]) clearTimeout(patchTimers[field]);
    patchTimers[field] = setTimeout(() => patchField(field, value), 400);
  }

  function onSliderRelease(field: string) {
    editing = new Set([...editing].filter(f => f !== field));
    if (patchTimers[field]) {
      clearTimeout(patchTimers[field]);
      delete patchTimers[field];
    }
    if (localValues[field] !== undefined) {
      patchField(field, localValues[field]);
    }
  }

  async function patchField(field: string, value: number) {
    editing = new Set([...editing, field]);
    saving = new Set([...saving, field]);
    try {
      await apiFetch('/api/state', {
        method: 'PATCH',
        body: JSON.stringify({ [field]: value }),
      });
    } catch (e) {
      error = String(e);
    } finally {
      saving  = new Set([...saving].filter(f => f !== field));
      editing = new Set([...editing].filter(f => f !== field));
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
    const entry = getLabel(field, value);
    if (!entry) return 'progress-primary';
    return COLOR_CLASSES[entry.color]?.progress ?? 'progress-primary';
  }

  function derivedBadgeColor(field: string, value: number): string {
    const entry = getLabel(field, value) ?? { color: 'neutral' as const };
    return COLOR_CLASSES[entry.color]?.badge ?? 'badge-neutral';
  }

  function vitalLabelColor(label: string): string {
    const dangerous = new Set(['BRADYCARDIA', 'DANGEROUS', 'CRITICALLY DEPRESSED', 'CRITICAL', 'HYPERTENSIVE', 'HYPOTENSIVE']);
    const elevated  = new Set(['ELEVATED', 'HIGH', 'VERY HIGH', 'DEPRESSED', 'LOW', 'HYPERVENTILATING']);
    if (dangerous.has(label)) return 'text-error';
    if (elevated.has(label))  return 'text-warning';
    return 'text-success';
  }

  function fmtVal(field: string, value: number): string {
    const range = DISPLAY_RANGES[field];
    if (!range) return value.toFixed(1);
    // Use appropriate precision by unit
    if (range.unit === 'ng/mL' || range.unit === '% TBW') return value.toFixed(1);
    if (range.unit === 'AU') return value.toFixed(1);
    return value.toFixed(0);
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

      {#if presetSnapshot}
        <button class="btn btn-sm btn-ghost gap-1" onclick={undoPreset}>
          ↩ Undo
        </button>
      {/if}
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
          {#if data.sleeping}
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
              {@const range = DISPLAY_RANGES[field]}
              {@const val = localValues[field] ?? (range ? (range.min + range.max) / 2 : 50)}
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
                    <span class="text-xs font-mono opacity-60">{range?.unit ?? ''}</span>
                    <span class="text-sm font-mono w-14 text-right">{fmtVal(field, val)}</span>
                  </div>
                </div>
                <input
                  type="range"
                  min={range?.min ?? 0}
                  max={range?.max ?? 100}
                  step={range ? (range.max - range.min) / 200 : 0.5}
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
              {@const range = DISPLAY_RANGES[field]}
              {@const val = localValues[field] ?? (range ? (range.min + range.max) / 2 : 50)}
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
                    <span class="text-xs font-mono opacity-60">{range?.unit ?? ''}</span>
                    <span class="text-sm font-mono w-14 text-right">{fmtVal(field, val)}</span>
                  </div>
                </div>
                <input
                  type="range"
                  min={range?.min ?? 0}
                  max={range?.max ?? 100}
                  step={range ? (range.max - range.min) / 200 : 0.5}
                  value={val}
                  class="range range-sm w-full {sliderColor(field, val)}"
                  oninput={(e) => onSliderInput(field, e)}
                  onmouseup={() => onSliderRelease(field)}
                  ontouchend={() => onSliderRelease(field)}
                />
              </div>
            {/each}
          </div>

          <!-- Read-only circadian fields -->
          {#each NEURO_READONLY as field}
            {@const range = DISPLAY_RANGES[field]}
            {@const chem = data.chemicals[field]}
            {@const val = chem?.value ?? 0}
            {@const label = getLabel(field, val)}
            <div class="mt-4 pt-4 border-t border-base-300">
              <div class="flex justify-between items-center mb-1">
                <span class="text-sm font-medium opacity-60">{FIELD_LABELS[field] ?? field}</span>
                <div class="flex items-center gap-2">
                  {#if label}
                    <span class="badge badge-xs {COLOR_CLASSES[label.color]?.badge}">{label.name}</span>
                  {/if}
                  <span class="text-xs font-mono opacity-60">{range?.unit ?? ''}</span>
                  <span class="text-sm font-mono w-14 text-right opacity-60">{fmtVal(field, val)}</span>
                </div>
              </div>
              <progress
                class="progress progress-neutral w-full"
                value={chem?.normalized ?? 0}
                max="1"
              ></progress>
              <p class="text-xs opacity-30 mt-1">Circadian formula — read-only</p>
            </div>
          {/each}
        </div>

        <!-- Vital Signs card -->
        {#if data.vital_signs && Object.keys(data.vital_signs).length > 0}
          {@const vs = data.vital_signs}
          <div class="card bg-base-200 p-4">
            <h2 class="text-sm font-semibold opacity-60 uppercase tracking-wider mb-3">Vital Signs</h2>
            <div class="grid grid-cols-2 gap-3">

              {#if vs.heart_rate}
                <div class="flex flex-col">
                  <span class="text-xs opacity-50 mb-0.5">Heart Rate</span>
                  <span class="text-2xl font-mono font-bold {vitalLabelColor(vs.heart_rate.label)}">
                    {vs.heart_rate.value?.toFixed(0)}
                    <span class="text-sm font-normal opacity-60">BPM</span>
                  </span>
                  <span class="text-xs {vitalLabelColor(vs.heart_rate.label)}">{vs.heart_rate.label}</span>
                </div>
              {/if}

              {#if vs.blood_pressure}
                <div class="flex flex-col">
                  <span class="text-xs opacity-50 mb-0.5">Blood Pressure</span>
                  <span class="text-2xl font-mono font-bold {vitalLabelColor(vs.blood_pressure.label)}">
                    {vs.blood_pressure.systolic?.toFixed(0)}/{vs.blood_pressure.diastolic?.toFixed(0)}
                    <span class="text-sm font-normal opacity-60">mmHg</span>
                  </span>
                  <span class="text-xs {vitalLabelColor(vs.blood_pressure.label)}">{vs.blood_pressure.label}</span>
                </div>
              {/if}

              {#if vs.respiration_rate}
                <div class="flex flex-col">
                  <span class="text-xs opacity-50 mb-0.5">Respiration</span>
                  <span class="text-2xl font-mono font-bold {vitalLabelColor(vs.respiration_rate.label)}">
                    {vs.respiration_rate.value?.toFixed(1)}
                    <span class="text-sm font-normal opacity-60">br/min</span>
                  </span>
                  <span class="text-xs {vitalLabelColor(vs.respiration_rate.label)}">{vs.respiration_rate.label}</span>
                </div>
              {/if}

              {#if vs.spo2}
                {@const o2color = vs.spo2.label === 'NORMAL' ? 'text-success' : vs.spo2.label === 'LOW' ? 'text-warning' : 'text-error'}
                <div class="flex flex-col">
                  <span class="text-xs opacity-50 mb-0.5">SpO₂</span>
                  <span class="text-2xl font-mono font-bold {o2color}">
                    {vs.spo2.value?.toFixed(1)}
                    <span class="text-sm font-normal opacity-60">%</span>
                  </span>
                  <span class="text-xs {o2color}">{vs.spo2.label}</span>
                </div>
              {/if}

            </div>
            <p class="text-xs opacity-30 mt-3">Derived from chemistry — read-only. Substance-gated danger only.</p>
          </div>
        {/if}

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

    <!-- Session Token Stats -->
    {#if tokens}
      <div class="card bg-base-200 p-4 mt-2">
        <h2 class="text-sm font-semibold opacity-60 uppercase tracking-wider mb-3">Session Tokens</h2>
        <div class="flex flex-wrap gap-x-6 gap-y-1 text-sm mb-3">
          <span>Started <span class="font-mono opacity-70">{sessionAge(tokens.session_start)}</span></span>
          <span>Turns <span class="font-mono font-bold">{tokens.turns}</span></span>
          <span>In <span class="font-mono font-bold text-info">{fmtNum(tokens.total_input)}</span></span>
          <span>Out <span class="font-mono font-bold text-success">{fmtNum(tokens.total_output)}</span></span>
          {#if tokens.total_reasoning > 0}
            <span>Reasoning <span class="font-mono font-bold text-warning">{fmtNum(tokens.total_reasoning)}</span></span>
          {/if}
          <span class="opacity-50">Total <span class="font-mono">{fmtNum(tokens.total_input + tokens.total_output)}</span></span>
        </div>
        {#if Object.keys(tokens.by_label).length > 0}
          <div class="overflow-x-auto">
            <table class="table table-xs w-full">
              <thead>
                <tr class="opacity-50">
                  <th>Call</th>
                  <th class="text-right">In</th>
                  <th class="text-right">Out</th>
                  {#if tokens.total_reasoning > 0}
                    <th class="text-right">Reasoning</th>
                  {/if}
                </tr>
              </thead>
              <tbody>
                {#each Object.entries(tokens.by_label) as [label, counts]}
                  <tr>
                    <td class="opacity-70">{TOKEN_LABEL_NAMES[label] ?? label}</td>
                    <td class="text-right font-mono text-info">{fmtNum(counts.input)}</td>
                    <td class="text-right font-mono text-success">{fmtNum(counts.output)}</td>
                    {#if tokens.total_reasoning > 0}
                      <td class="text-right font-mono text-warning">{fmtNum(counts.reasoning ?? 0)}</td>
                    {/if}
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      </div>
    {/if}
  {/if}
</div>
