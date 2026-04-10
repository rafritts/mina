<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { apiFetch } from '$lib/api';

  interface MonologueData {
    content: string;
    mtime: number | null;
  }

  let data = $state<MonologueData | null>(null);
  let error = $state('');
  let lastUpdated = $state('');
  let refreshInterval: ReturnType<typeof setInterval>;

  async function load() {
    try {
      data = await apiFetch<MonologueData>('/api/monologue');
      lastUpdated = new Date().toLocaleTimeString();
      error = '';
    } catch (e) {
      error = String(e);
    }
  }

  onMount(() => {
    load();
    refreshInterval = setInterval(load, 10000);
  });

  onDestroy(() => clearInterval(refreshInterval));

  function formatTime(mtime: number | null): string {
    if (!mtime) return 'unknown';
    return new Date(mtime * 1000).toLocaleString();
  }
</script>

<div class="max-w-3xl mx-auto">
  <div class="flex items-center justify-between mb-6">
    <h1 class="text-2xl font-bold">Inner Monologue</h1>
    <span class="text-xs opacity-50">Refreshes every 10s · Last: {lastUpdated}</span>
  </div>

  {#if error}
    <div class="alert alert-error">{error}</div>
  {:else if !data}
    <div class="flex justify-center py-20">
      <span class="loading loading-spinner loading-lg"></span>
    </div>
  {:else}
    <div class="card bg-base-200 p-6">
      {#if data.mtime}
        <p class="text-xs opacity-40 mb-4">Last written: {formatTime(data.mtime)}</p>
      {/if}
      {#if data.content}
        <p class="text-base leading-relaxed whitespace-pre-wrap italic opacity-90">{data.content}</p>
      {:else}
        <p class="opacity-40 italic">No monologue yet.</p>
      {/if}
    </div>
  {/if}
</div>
