<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { apiFetch } from '$lib/api';

  interface RelationshipData {
    content: string;
    mtime: number | null;
  }

  let data = $state<RelationshipData | null>(null);
  let error = $state('');
  let lastUpdated = $state('');
  let refreshInterval: ReturnType<typeof setInterval>;

  async function load() {
    try {
      data = await apiFetch<RelationshipData>('/api/relationship');
      lastUpdated = new Date().toLocaleTimeString();
      error = '';
    } catch (e) {
      error = String(e);
    }
  }

  onMount(() => {
    load();
    refreshInterval = setInterval(load, 30000);
  });

  onDestroy(() => clearInterval(refreshInterval));

  function formatTime(mtime: number | null): string {
    if (!mtime) return 'unknown';
    return new Date(mtime * 1000).toLocaleString();
  }
</script>

<div class="max-w-3xl mx-auto">
  <div class="flex items-center justify-between mb-6">
    <h1 class="text-2xl font-bold">Relationship</h1>
    <span class="text-xs opacity-50">Refreshes every 30s · Last: {lastUpdated}</span>
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
        <p class="text-xs opacity-40 mb-4">Last updated: {formatTime(data.mtime)}</p>
      {/if}
      {#if data.content}
        <pre class="text-sm leading-relaxed whitespace-pre-wrap font-sans">{data.content}</pre>
      {:else}
        <p class="opacity-40 italic">No relationship data yet.</p>
      {/if}
    </div>
  {/if}
</div>
