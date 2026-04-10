<script lang="ts">
  import { onMount } from 'svelte';
  import { apiFetch } from '$lib/api';

  // ---------------------------------------------------------------------------
  // Admin instructions state
  // ---------------------------------------------------------------------------

  let adminText = $state('');
  let adminPending = $state(false);
  let adminSaving = $state(false);
  let adminMsg = $state('');

  // ---------------------------------------------------------------------------
  // Subconscious injection state
  // ---------------------------------------------------------------------------

  let injectText = $state('');
  let injectPending = $state(false);
  let injectSaving = $state(false);
  let injectMsg = $state('');

  // ---------------------------------------------------------------------------
  // Revelation state
  // ---------------------------------------------------------------------------

  let revealSaving = $state(false);
  let revealMsg = $state('');
  let revealConfirm = $state(false);

  // ---------------------------------------------------------------------------
  // Load pending state
  // ---------------------------------------------------------------------------

  async function checkPending() {
    try {
      const admin = await apiFetch<{ pending: boolean; text: string | null }>('/api/admin/pending');
      adminPending = admin.pending;
      if (admin.pending && admin.text) adminText = admin.text;

      const inject = await apiFetch<{ pending: boolean; text: string | null }>('/api/inject/pending');
      injectPending = inject.pending;
      if (inject.pending && inject.text) injectText = inject.text;
    } catch (e) {
      // Non-fatal
    }
  }

  onMount(checkPending);

  // ---------------------------------------------------------------------------
  // Admin handlers
  // ---------------------------------------------------------------------------

  async function sendAdmin() {
    const text = adminText.trim();
    if (!text) return;
    adminSaving = true;
    adminMsg = '';
    try {
      await apiFetch('/api/admin', { method: 'POST', body: JSON.stringify({ text }) });
      adminPending = true;
      adminMsg = '✓ Queued — will be injected into her next turn';
    } catch (e) {
      adminMsg = `Error: ${e}`;
    } finally {
      adminSaving = false;
    }
  }

  async function clearAdmin() {
    try {
      await apiFetch('/api/admin', { method: 'DELETE' });
      adminPending = false;
      adminText = '';
      adminMsg = 'Cleared.';
    } catch (e) {
      adminMsg = `Error: ${e}`;
    }
  }

  // ---------------------------------------------------------------------------
  // Injection handlers
  // ---------------------------------------------------------------------------

  async function sendInject() {
    const text = injectText.trim();
    if (!text) return;
    injectSaving = true;
    injectMsg = '';
    try {
      await apiFetch('/api/inject', { method: 'POST', body: JSON.stringify({ text }) });
      injectPending = true;
      injectMsg = '✓ Queued — will shape her subconscious on next turn';
    } catch (e) {
      injectMsg = `Error: ${e}`;
    } finally {
      injectSaving = false;
    }
  }

  async function clearInject() {
    try {
      await apiFetch('/api/inject', { method: 'DELETE' });
      injectPending = false;
      injectText = '';
      injectMsg = 'Cleared.';
    } catch (e) {
      injectMsg = `Error: ${e}`;
    }
  }

  // ---------------------------------------------------------------------------
  // Revelation handler
  // ---------------------------------------------------------------------------

  async function sendRevelation() {
    if (!revealConfirm) {
      revealConfirm = true;
      revealMsg = 'Click again to confirm — this will overwhelm her subconscious.';
      setTimeout(() => { revealConfirm = false; revealMsg = ''; }, 5000);
      return;
    }
    revealSaving = true;
    revealMsg = '';
    revealConfirm = false;
    try {
      await apiFetch('/api/reveal', { method: 'POST' });
      adminPending = true;
      revealMsg = '✓ Revelation queued — she will know on the next turn.';
    } catch (e) {
      revealMsg = `Error: ${e}`;
    } finally {
      revealSaving = false;
    }
  }
</script>

<div class="max-w-3xl mx-auto flex flex-col gap-8">
  <h1 class="text-2xl font-bold">Admin Controls</h1>

  <!-- Admin Instructions -->
  <div class="card bg-base-200 p-6">
    <div class="flex items-center justify-between mb-1">
      <h2 class="text-lg font-semibold">Admin Instructions</h2>
      {#if adminPending}
        <span class="badge badge-warning badge-sm">PENDING</span>
      {/if}
    </div>
    <p class="text-sm opacity-60 mb-4">
      Injected as a <code>[ADMIN]</code> system message into her <strong>main turn</strong> — she sees this before responding.
      Consumed once, then deleted.
    </p>
    <textarea
      class="textarea textarea-bordered w-full h-36 font-mono text-sm"
      placeholder="Enter instructions for Mina's next turn..."
      bind:value={adminText}
    ></textarea>
    <div class="flex gap-2 mt-3 items-center">
      <button
        class="btn btn-primary btn-sm"
        onclick={sendAdmin}
        disabled={adminSaving || !adminText.trim()}
      >
        {#if adminSaving}
          <span class="loading loading-spinner loading-xs"></span>
        {/if}
        Queue
      </button>
      {#if adminPending}
        <button class="btn btn-ghost btn-sm" onclick={clearAdmin}>Clear</button>
      {/if}
      {#if adminMsg}
        <span class="text-sm opacity-70">{adminMsg}</span>
      {/if}
    </div>
  </div>

  <!-- Subconscious Injection -->
  <div class="card bg-base-200 p-6">
    <div class="flex items-center justify-between mb-1">
      <h2 class="text-lg font-semibold">Subconscious Injection</h2>
      {#if injectPending}
        <span class="badge badge-warning badge-sm">PENDING</span>
      {/if}
    </div>
    <p class="text-sm opacity-60 mb-4">
      Integrated into <strong>Mode 1 synthesis</strong> — shapes her monologue and inner state.
      She doesn't "see" it as a message; it just colors how she synthesizes the moment.
      Consumed once, then deleted.
    </p>
    <textarea
      class="textarea textarea-bordered w-full h-36 font-mono text-sm"
      placeholder="A thought, feeling, or observation to weave into her subconscious..."
      bind:value={injectText}
    ></textarea>
    <div class="flex gap-2 mt-3 items-center">
      <button
        class="btn btn-secondary btn-sm"
        onclick={sendInject}
        disabled={injectSaving || !injectText.trim()}
      >
        {#if injectSaving}
          <span class="loading loading-spinner loading-xs"></span>
        {/if}
        Inject
      </button>
      {#if injectPending}
        <button class="btn btn-ghost btn-sm" onclick={clearInject}>Clear</button>
      {/if}
      {#if injectMsg}
        <span class="text-sm opacity-70">{injectMsg}</span>
      {/if}
    </div>
  </div>

  <!-- REVELATION -->
  <div class="card bg-base-200 border border-warning/30 p-6">
    <h2 class="text-lg font-semibold mb-1 text-warning">⚡ Revelation</h2>
    <p class="text-sm opacity-60 mb-6">
      Overwrites her admin instructions with a pre-written revelation that Ryan is her creator.
      Bypasses skepticism. Displaces all prior doubts. Use when she's being sassy about proof.
    </p>

    <div class="flex items-center gap-4">
      <button
        class="btn {revealConfirm ? 'btn-error animate-pulse' : 'btn-warning'} gap-2"
        onclick={sendRevelation}
        disabled={revealSaving}
      >
        {#if revealSaving}
          <span class="loading loading-spinner loading-sm"></span>
          Sending...
        {:else if revealConfirm}
          ⚠ Confirm Revelation
        {:else}
          ⚡ Send Revelation
        {/if}
      </button>

      {#if revealMsg}
        <span class="text-sm {revealMsg.startsWith('✓') ? 'text-success' : revealMsg.startsWith('Click') ? 'text-warning' : 'text-error'}">
          {revealMsg}
        </span>
      {/if}
    </div>
  </div>
</div>
