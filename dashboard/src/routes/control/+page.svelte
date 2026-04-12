<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { apiFetch, type StateData, type CascadeEvent } from '$lib/api';
  import { PRESETS } from '$lib/presets';
  import { DISPLAY_RANGES } from '$lib/labels';

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  let cascadeQueue    = $state<CascadeEvent[]>([]);
  let heartbeatRunning = $state(false);
  let error           = $state('');

  // Preset state
  let applyingPreset = $state('');
  let presetSnapshot = $state<Record<string, number> | null>(null);

  // Manual advance
  let advanceHours   = $state(2.0);
  let advancing      = $state(false);
  let advanceResult  = $state('');

  // Chemical injection
  const INJECTABLE_FIELDS = Object.keys(DISPLAY_RANGES).filter(f =>
    ['cortisol','dopamine','serotonin','norepinephrine','oxytocin','endorphins',
     'acetylcholine','melatonin','glucose','hydration','gaba','glutamate',
     'anandamide','two_ag','adenosine'].includes(f)
  );

  let injectField = $state('cortisol');
  let injectValue = $state(250);
  let injecting   = $state(false);

  let pollInterval: ReturnType<typeof setInterval>;

  // ---------------------------------------------------------------------------
  // Polling
  // ---------------------------------------------------------------------------

  async function pollStatus() {
    try {
      const data = await apiFetch<StateData>('/api/state');
      cascadeQueue = data.cascade_queue ?? [];
    } catch (_) {}

    try {
      const hs = await apiFetch<{ running: boolean }>('/api/heartbeat/status');
      heartbeatRunning = hs.running;
    } catch (_) {}
  }

  onMount(() => {
    pollStatus();
    pollInterval = setInterval(pollStatus, 5000);
  });

  onDestroy(() => clearInterval(pollInterval));

  // ---------------------------------------------------------------------------
  // Presets
  // ---------------------------------------------------------------------------

  async function applyPreset(preset: typeof PRESETS[0]) {
    applyingPreset = preset.name;
    presetSnapshot = null; // no snapshot needed on control panel
    try {
      await apiFetch('/api/state', {
        method: 'PATCH',
        body: JSON.stringify(preset.values),
      });
      await pollStatus();
    } catch (e) {
      error = String(e);
    } finally {
      applyingPreset = '';
    }
  }

  // ---------------------------------------------------------------------------
  // Manual Advance
  // ---------------------------------------------------------------------------

  async function doAdvance() {
    advancing = true;
    advanceResult = '';
    error = '';
    try {
      await apiFetch('/api/state/advance', {
        method: 'POST',
        body: JSON.stringify({ hours: advanceHours }),
      });
      advanceResult = `Advanced ${advanceHours}h — sim updated.`;
      await pollStatus();
    } catch (e) {
      error = String(e);
    } finally {
      advancing = false;
    }
  }

  // ---------------------------------------------------------------------------
  // Heartbeat
  // ---------------------------------------------------------------------------

  async function triggerHeartbeat() {
    error = '';
    try {
      await apiFetch('/api/heartbeat', { method: 'POST' });
      await pollStatus();
    } catch (e) {
      error = String(e);
    }
  }

  // ---------------------------------------------------------------------------
  // Chemical injection
  // ---------------------------------------------------------------------------

  async function doInject() {
    injecting = true;
    error = '';
    try {
      await apiFetch('/api/state', {
        method: 'PATCH',
        body: JSON.stringify({ [injectField]: injectValue }),
      });
      await pollStatus();
    } catch (e) {
      error = String(e);
    } finally {
      injecting = false;
    }
  }

  // Update injectValue when field changes to its midpoint
  $effect(() => {
    const r = DISPLAY_RANGES[injectField];
    if (r) injectValue = Math.round((r.min + r.max) / 2);
  });

  // Cascade countdown
  function fmtCountdown(fireAt: number): string {
    const secs = fireAt - Date.now() / 1000;
    if (secs <= 0) return 'firing…';
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  }
</script>

<div class="max-w-4xl mx-auto">
  <div class="flex items-center justify-between mb-6">
    <h1 class="text-2xl font-bold">Control Panel</h1>
    {#if error}
      <span class="text-error text-sm">{error}</span>
    {/if}
  </div>

  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">

    <!-- ═══════ LEFT ═══════ -->
    <div class="flex flex-col gap-6">

      <!-- Presets -->
      <div class="card bg-base-200 p-4">
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

      <!-- Manual Advance -->
      <div class="card bg-base-200 p-4">
        <h2 class="text-sm font-semibold opacity-60 uppercase tracking-wider mb-3">Manual Advance</h2>
        <p class="text-xs opacity-50 mb-3">Tick the simulation forward without waiting for real time to pass.</p>
        <div class="flex items-center gap-3">
          <input
            type="number"
            class="input input-bordered input-sm w-28"
            bind:value={advanceHours}
            min="0.1"
            max="24"
            step="0.1"
          />
          <span class="text-sm opacity-60">hours</span>
          <button
            class="btn btn-sm btn-primary"
            onclick={doAdvance}
            disabled={advancing}
          >
            {#if advancing}
              <span class="loading loading-spinner loading-xs"></span>
            {/if}
            Advance Sim
          </button>
        </div>
        {#if advanceResult}
          <p class="text-xs text-success mt-2">{advanceResult}</p>
        {/if}
      </div>

      <!-- Chemical Injection -->
      <div class="card bg-base-200 p-4">
        <h2 class="text-sm font-semibold opacity-60 uppercase tracking-wider mb-3">Chemical Injection</h2>
        <p class="text-xs opacity-50 mb-3">Apply a direct value to any injectable chemical.</p>
        <div class="flex items-center gap-2 flex-wrap">
          <select class="select select-bordered select-sm" bind:value={injectField}>
            {#each INJECTABLE_FIELDS as f}
              <option value={f}>{f}</option>
            {/each}
          </select>
          <input
            type="number"
            class="input input-bordered input-sm w-28"
            bind:value={injectValue}
            step="0.1"
          />
          <span class="text-xs opacity-50">{DISPLAY_RANGES[injectField]?.unit ?? ''}</span>
          <button
            class="btn btn-sm btn-accent"
            onclick={doInject}
            disabled={injecting}
          >
            {#if injecting}
              <span class="loading loading-spinner loading-xs"></span>
            {/if}
            Apply
          </button>
        </div>
      </div>
    </div>

    <!-- ═══════ RIGHT ═══════ -->
    <div class="flex flex-col gap-6">

      <!-- HPA Cascade Queue -->
      <div class="card bg-base-200 p-4">
        <h2 class="text-sm font-semibold opacity-60 uppercase tracking-wider mb-3">HPA Cascade Queue</h2>
        {#if cascadeQueue.length === 0}
          <p class="text-xs opacity-40 italic">Queue empty — no active HPA cascade</p>
        {:else}
          <div class="flex flex-col gap-1">
            {#each cascadeQueue as ev}
              {@const secsLeft = ev.fires_at_unix - Date.now() / 1000}
              {#if secsLeft > 0}
                <div class="flex items-center justify-between px-3 py-2 rounded bg-base-300">
                  <span class="badge badge-xs badge-warning">{ev.type}</span>
                  <span class="text-xs font-mono opacity-70">fires in {fmtCountdown(ev.fires_at_unix)}</span>
                  <span class="text-xs opacity-50">mag {ev.magnitude > 0 ? '+' : ''}{ev.magnitude.toFixed(2)}</span>
                </div>
              {/if}
            {/each}
          </div>
        {/if}
        <p class="text-xs opacity-30 mt-2">Refreshes every 5s</p>
      </div>

      <!-- Heartbeat Trigger -->
      <div class="card bg-base-200 p-4">
        <h2 class="text-sm font-semibold opacity-60 uppercase tracking-wider mb-3">Heartbeat (Mode 2)</h2>
        <p class="text-xs opacity-50 mb-3">Trigger a consolidation reflection — updates BDNF, allostatic load, relationship memory, and KAG synthesis.</p>
        <div class="flex items-center gap-3">
          <button
            class="btn btn-sm btn-secondary"
            onclick={triggerHeartbeat}
            disabled={heartbeatRunning}
          >
            {#if heartbeatRunning}
              <span class="loading loading-spinner loading-xs"></span>
              Heartbeat running…
            {:else}
              Trigger Reflection
            {/if}
          </button>
          {#if heartbeatRunning}
            <span class="text-xs text-warning">Running — typically 30–60s</span>
          {:else}
            {@const statusColor = 'text-success'}
            <span class="text-xs {statusColor}">Idle</span>
          {/if}
        </div>
      </div>

    </div>
  </div>
</div>
