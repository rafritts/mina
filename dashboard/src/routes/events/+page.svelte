<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { apiFetch } from '$lib/api';
  import { DISPLAY_RANGES } from '$lib/labels';

  interface EncoderEvent {
    ts: number;
    type: 'stimulus' | 'response' | 'activity' | 'tool';
    // encoder event fields
    preview?: string;
    deltas?: Record<string, number>;
    event_override?: boolean;
    momentum_dampened?: boolean;
    // tool event fields
    tool?: string;
    args?: Record<string, unknown>;
    result?: string;
    source?: string;
  }

  // Chemical short labels for compact display
  const CHEM_SHORT: Record<string, string> = {
    cortisol:       'cort',
    norepinephrine: 'norepi',
    dopamine:       'dopa',
    serotonin:      'sero',
    oxytocin:       'oxy',
    endorphins:     'endo',
    acetylcholine:  'ach',
    melatonin:      'mela',
    glucose:        'gluc',
    hydration:      'hydr',
    sleep_pressure: 'sleep',
  };

  // Display order — social/reward chemicals first, then homeostatic
  const CHEM_ORDER = [
    'oxytocin', 'dopamine', 'serotonin', 'endorphins', 'acetylcholine',
    'norepinephrine', 'cortisol', 'glucose', 'hydration', 'sleep_pressure', 'melatonin',
  ];

  const TYPE_CONFIG: Record<string, { label: string; border: string; badge: string }> = {
    stimulus: { label: 'stimulus',  border: 'border-l-info',      badge: 'badge-info'      },
    response: { label: 'response',  border: 'border-l-secondary', badge: 'badge-secondary' },
    activity: { label: 'activity',  border: 'border-l-success',   badge: 'badge-success'   },
    tool:     { label: 'tool',      border: 'border-l-warning',   badge: 'badge-warning'   },
  };

  let events = $state<EncoderEvent[]>([]);
  let error = $state('');
  let filter = $state<'all' | 'stimulus' | 'response' | 'activity' | 'tool'>('all');

  let filtered = $derived(
    filter === 'all' ? events : events.filter(e => e.type === filter)
  );

  let counts = $derived({
    all:      events.length,
    stimulus: events.filter(e => e.type === 'stimulus').length,
    response: events.filter(e => e.type === 'response').length,
    activity: events.filter(e => e.type === 'activity').length,
    tool:     events.filter(e => e.type === 'tool').length,
  });

  async function load() {
    try {
      events = await apiFetch<EncoderEvent[]>('/api/events');
      error = '';
    } catch (e) {
      error = String(e);
    }
  }

  function relTime(ts: number): string {
    const delta = Date.now() / 1000 - ts;
    if (delta < 60)    return 'just now';
    if (delta < 3600)  return `${Math.floor(delta / 60)}m ago`;
    if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
    return `${Math.floor(delta / 86400)}d ago`;
  }

  function formatTs(ts: number): string {
    return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  function sortedDeltas(deltas: Record<string, number>): [string, number][] {
    return CHEM_ORDER
      .filter(k => deltas[k] !== undefined && deltas[k] !== 0)
      .map(k => [k, deltas[k]] as [string, number])
      .concat(
        Object.entries(deltas)
          .filter(([k]) => !CHEM_ORDER.includes(k) && deltas[k] !== 0)
      );
  }

  function deltaClass(value: number): string {
    return value > 0 ? 'text-success' : 'text-error';
  }

  function deltaSign(value: number): string {
    return value > 0 ? `+${value.toFixed(1)}` : value.toFixed(1);
  }

  // Scale chip opacity by magnitude relative to a per-chemical reference
  const MAGNITUDE_REF: Record<string, number> = {
    cortisol: 150, norepinephrine: 300, dopamine: 15, serotonin: 2,
    oxytocin: 8, endorphins: 15, acetylcholine: 8, melatonin: 30,
    glucose: 30, hydration: 20, sleep_pressure: 20,
  };

  function chipOpacity(chem: string, value: number): string {
    const ref = MAGNITUDE_REF[chem] ?? 10;
    const ratio = Math.min(Math.abs(value) / ref, 1);
    if (ratio > 0.6) return 'opacity-100';
    if (ratio > 0.25) return 'opacity-75';
    return 'opacity-50';
  }

  function formatArgs(args: Record<string, unknown>): string {
    return Object.entries(args)
      .map(([k, v]) => `${k}: ${String(v)}`)
      .join(' · ');
  }

  let pollInterval: ReturnType<typeof setInterval>;
  onMount(() => { load(); pollInterval = setInterval(load, 5000); });
  onDestroy(() => clearInterval(pollInterval));
</script>

<div class="max-w-4xl mx-auto flex flex-col gap-4">

  <!-- Header + filter tabs -->
  <div class="flex items-center justify-between flex-wrap gap-2">
    <h1 class="text-2xl font-bold">Encoder Events</h1>
    <span class="text-xs opacity-40 tabular-nums">{counts.all} events</span>
  </div>

  <!-- Filter tabs -->
  <div class="tabs tabs-box tabs-sm w-fit">
    {#each ([['all', 'All'], ['tool', 'Tools'], ['stimulus', 'Stimulus'], ['response', 'Response'], ['activity', 'Activity']] as const) as [val, label]}
      <button
        class="tab {filter === val ? 'tab-active' : ''}"
        onclick={() => { filter = val; }}
      >
        {label}
        <span class="ml-1.5 text-xs opacity-50">
          {counts[val]}
        </span>
      </button>
    {/each}
  </div>

  {#if error}
    <div class="alert alert-error text-sm">{error}</div>
  {/if}

  <!-- Event list -->
  {#if filtered.length === 0}
    <div class="text-sm opacity-40 mt-8 text-center">
      {#if events.length === 0}
        No encoder events yet. Events appear here as messages are exchanged.
      {:else}
        No {filter} events.
      {/if}
    </div>
  {:else}
    <div class="flex flex-col gap-2">
      {#each filtered as event (event.ts)}
        {@const cfg = TYPE_CONFIG[event.type] ?? TYPE_CONFIG.stimulus}
        <div class="card bg-base-200 border-l-4 {cfg.border} shadow-sm hover:shadow-md transition-shadow">
          <div class="card-body p-4 gap-2">

            <!-- Top row: type badge + content + timestamp -->
            <div class="flex items-start justify-between gap-3">
              <div class="flex items-start gap-2 min-w-0 flex-1">
                <span class="badge {cfg.badge} badge-sm mt-0.5 shrink-0 uppercase text-xs font-mono">
                  {event.type === 'tool' ? (event.tool ?? 'tool') : cfg.label}
                </span>
                <p class="text-sm opacity-70 leading-snug break-words min-w-0 font-mono">
                  {#if event.type === 'tool'}
                    {event.args ? formatArgs(event.args) : ''}
                  {:else}
                    {event.preview ?? ''}
                  {/if}
                </p>
              </div>
              <div class="flex items-center gap-2 shrink-0">
                {#if event.type === 'tool' && event.source}
                  <span class="text-xs opacity-30 font-mono">{event.source}</span>
                {/if}
                <span
                  class="text-xs opacity-40 tabular-nums"
                  title={formatTs(event.ts)}
                >
                  {relTime(event.ts)}
                </span>
              </div>
            </div>

            <!-- Tool result -->
            {#if event.type === 'tool' && event.result}
              <p class="text-xs opacity-50 leading-snug font-mono break-words">{event.result}</p>
            {/if}

            <!-- Delta chips (encoder events and tool events both may have deltas) -->
            {#each [sortedDeltas(event.deltas ?? {})] as pairs}
              {#if pairs.length > 0}
                <div class="flex flex-wrap gap-1.5 mt-1">
                  {#each pairs as [chem, value]}
                    {@const unit = DISPLAY_RANGES[chem]?.unit ?? ''}
                    <span
                      class="inline-flex items-baseline gap-0.5 bg-base-300 rounded px-2 py-0.5 font-mono text-xs {chipOpacity(chem, value)}"
                      title="{chem}: {value > 0 ? '+' : ''}{value.toFixed(2)} {unit}"
                    >
                      <span class="opacity-60">{CHEM_SHORT[chem] ?? chem}</span>
                      <span class="font-semibold {deltaClass(value)}">{deltaSign(value)}</span>
                    </span>
                  {/each}
                </div>
              {/if}
            {/each}

            <!-- Encoder flags -->
            {#if event.event_override || event.momentum_dampened}
              <div class="flex gap-2 mt-0.5">
                {#if event.event_override}
                  <span class="badge badge-warning badge-xs font-mono">⚡ override</span>
                {/if}
                {#if event.momentum_dampened}
                  <span class="badge badge-neutral badge-xs font-mono opacity-60">〜 dampened</span>
                {/if}
              </div>
            {/if}

          </div>
        </div>
      {/each}
    </div>
  {/if}

</div>
