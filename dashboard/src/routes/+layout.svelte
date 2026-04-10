<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';
  import { setToken, apiFetch } from '$lib/api';
  import { page } from '$app/stores';

  let { children } = $props();

  // Accept token from URL query param — strips it after saving
  if (typeof window !== 'undefined') {
    const params = new URLSearchParams(window.location.search);
    const urlToken = params.get('token');
    if (urlToken) {
      localStorage.setItem('dashboard_token', urlToken);
      params.delete('token');
      const newUrl = window.location.pathname + (params.size ? '?' + params : '');
      window.history.replaceState({}, '', newUrl);
    }
  }

  let token = $state(typeof localStorage !== 'undefined' ? (localStorage.getItem('dashboard_token') ?? '') : '');
  let authRequired = $state<boolean | null>(null);  // null = still checking
  let showModal = $derived(authRequired === true && !token);
  let modalInput = $state('');

  onMount(async () => {
    try {
      const res = await fetch('/healthz');
      const data = await res.json();
      authRequired = data.auth_required ?? false;
    } catch {
      authRequired = false;  // can't reach server — let them try anyway
    }
  });

  $effect(() => { setToken(token); });

  function saveToken() {
    const t = modalInput.trim();
    if (!t) return;
    token = t;
    localStorage.setItem('dashboard_token', t);
    setToken(t);
  }

  // Billing
  let billingRemaining = $state<number | null>(null);

  async function fetchBilling() {
    try {
      const data = await apiFetch<{ remaining?: number; error?: string }>('/api/billing');
      if (typeof data.remaining === 'number') billingRemaining = data.remaining;
    } catch { /* silent */ }
  }

  $effect(() => {
    fetchBilling();
    const id = setInterval(fetchBilling, 30_000);
    return () => clearInterval(id);
  });

  const navLinks = [
    { href: '/state',        label: 'State' },
    { href: '/monologue',    label: 'Monologue' },
    { href: '/admin',        label: 'Admin' },
    { href: '/substances',   label: 'Substances' },
    { href: '/relationship', label: 'Relationship' },
  ];

  let pageTitle = $derived(
    (navLinks.find(l => l.href === $page.url.pathname)?.label ?? 'Mina') + ' — Mina'
  );
</script>

<svelte:head>
  <title>{pageTitle}</title>
</svelte:head>

{#if authRequired === null}
  <!-- waiting for healthz — render nothing to avoid modal flash -->
{:else if showModal}
  <div class="modal modal-open">
    <div class="modal-box">
      <h3 class="font-bold text-lg mb-4">Dashboard Token Required</h3>
      <p class="mb-4 text-sm opacity-70">Enter your <code>DASHBOARD_TOKEN</code> to continue.</p>
      <input
        class="input input-bordered w-full mb-4"
        type="password"
        placeholder="Token"
        bind:value={modalInput}
        onkeydown={(e) => e.key === 'Enter' && saveToken()}
      />
      <div class="modal-action">
        <button class="btn btn-primary" onclick={saveToken}>Unlock</button>
      </div>
    </div>
  </div>
{:else}
  <div class="min-h-screen flex flex-col">
    <nav class="navbar bg-base-200 px-4 border-b border-base-300">
      <div class="navbar-start">
        <span class="text-lg font-bold text-primary">Mina</span>
      </div>

      <div class="navbar-center hidden md:flex">
        <ul class="flex gap-1">
          {#each navLinks as link}
            {@const isActive = $page.url.pathname === link.href}
            <li>
              <a
                href={link.href}
                class="px-3 py-2 rounded text-sm transition-colors
                  {isActive
                    ? 'text-primary font-semibold border-b-2 border-primary'
                    : 'opacity-70 hover:opacity-100 hover:bg-base-300'}"
              >{link.label}</a>
            </li>
          {/each}
        </ul>
      </div>

      <div class="navbar-end gap-3">
        {#if billingRemaining !== null}
          <span class="text-xs tabular-nums opacity-50">${billingRemaining.toFixed(2)} left</span>
        {/if}
        <button
          class="btn btn-ghost btn-xs"
          onclick={() => { localStorage.removeItem('dashboard_token'); window.location.reload(); }}
        >
          Logout
        </button>
        <div class="dropdown dropdown-bottom dropdown-end md:hidden">
          <div tabindex="0" role="button" class="btn btn-ghost btn-sm">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </div>
          <ul tabindex="0" class="dropdown-content menu bg-base-100 rounded-box z-50 w-48 p-2 shadow-lg">
            {#each navLinks as link}
              {@const isActive = $page.url.pathname === link.href}
              <li>
                <a
                  href={link.href}
                  class="{isActive ? 'bg-base-300 text-primary font-semibold' : ''}"
                >{link.label}</a>
              </li>
            {/each}
          </ul>
        </div>
      </div>
    </nav>

    <main class="flex-1 p-3 md:p-6">
      {@render children()}
    </main>
  </div>
{/if}
