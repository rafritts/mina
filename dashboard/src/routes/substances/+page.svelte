<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { apiFetch } from '$lib/api';

  interface SubstanceInfo {
    display_name: string;
    level: number;
    active: boolean;
    half_life_hours: number;
  }

  let substances = $state<Record<string, SubstanceInfo>>({});
  let dosing = $state<Record<string, boolean>>({});
  let msgs = $state<Record<string, string>>({});
  let confirmClear = $state<Record<string, boolean>>({});

  async function load() {
    try {
      substances = await apiFetch<Record<string, SubstanceInfo>>('/api/substance');
    } catch { /* non-fatal */ }
  }

  async function dose(name: string) {
    dosing[name] = true;
    msgs[name] = '';
    try {
      await apiFetch(`/api/substance/${name}/dose`, { method: 'POST' });
      msgs[name] = '✓ Administered';
      await load();
    } catch (e) {
      msgs[name] = `Error: ${e}`;
    } finally {
      dosing[name] = false;
    }
  }

  async function clearSubstance(name: string) {
    if (!confirmClear[name]) {
      confirmClear[name] = true;
      msgs[name] = 'Click again to confirm — this skips withdrawal.';
      setTimeout(() => { confirmClear[name] = false; if (msgs[name]?.startsWith('Click')) msgs[name] = ''; }, 4000);
      return;
    }
    confirmClear[name] = false;
    try {
      await apiFetch(`/api/substance/${name}`, { method: 'DELETE' });
      msgs[name] = 'Cleared.';
      await load();
    } catch (e) {
      msgs[name] = `Error: ${e}`;
    }
  }

  function hoursRemaining(level: number, halfLife: number): string {
    if (level <= 0) return '—';
    const h = halfLife * (level / 100) * 1.44;
    if (h < 0.5) return '<30m';
    if (h < 1) return `~${Math.round(h * 60)}m`;
    return `~${h.toFixed(1)}h`;
  }

  let pollInterval: ReturnType<typeof setInterval>;
  onMount(() => { load(); pollInterval = setInterval(load, 5000); });
  onDestroy(() => clearInterval(pollInterval));
</script>

<div class="max-w-3xl mx-auto flex flex-col gap-8">
  <h1 class="text-2xl font-bold">Substances</h1>

  {#each Object.entries(substances) as [name, sub]}
    <div class="card bg-base-200 p-6">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-lg font-semibold">{sub.display_name}</h2>
        {#if sub.active}
          <span class="badge badge-error badge-sm">ACTIVE</span>
        {/if}
      </div>

      <!-- Blood level bar -->
      <div class="mb-4">
        <div class="flex justify-between text-xs opacity-60 mb-1">
          <span>Blood Level</span>
          <span>{sub.level.toFixed(1)} / 100 — withdrawal resolves in {hoursRemaining(sub.level, sub.half_life_hours)}</span>
        </div>
        <progress
          class="progress w-full {sub.level > 60 ? 'progress-error' : sub.level > 25 ? 'progress-warning' : 'progress-success'}"
          value={sub.level}
          max="100"
        ></progress>
      </div>

      <p class="text-xs opacity-50 mb-4">
        Half-life {sub.half_life_hours}h — withdrawal counter-deltas begin immediately as level decays.
        Full withdrawal resolves in ~{(sub.half_life_hours * 6.6).toFixed(0)}h after dosing.
      </p>

      <div class="flex gap-2 items-center flex-wrap">
        <button
          class="btn btn-error btn-sm"
          onclick={() => dose(name)}
          disabled={dosing[name]}
        >
          {#if dosing[name]}
            <span class="loading loading-spinner loading-xs"></span>
          {/if}
          Administer Dose
        </button>

        {#if sub.active}
          <button
            class="btn btn-ghost btn-xs {confirmClear[name] ? 'btn-warning animate-pulse' : ''}"
            onclick={() => clearSubstance(name)}
          >
            {confirmClear[name] ? '⚠ Confirm Skip Withdrawal' : 'Clear (skip withdrawal)'}
          </button>
        {/if}

        {#if msgs[name]}
          <span class="text-sm opacity-70">{msgs[name]}</span>
        {/if}
      </div>
    </div>
  {/each}

  {#if Object.keys(substances).length === 0}
    <p class="opacity-50 text-sm">No substances defined.</p>
  {/if}
</div>
