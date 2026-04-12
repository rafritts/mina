<script lang="ts">
  interface Props {
    title:       string;
    defaultOpen?: boolean;
    badge?:      string;
    children:    import('svelte').Snippet;
  }

  let { title, defaultOpen = true, badge = '', children }: Props = $props();

  let open = $state(defaultOpen);
</script>

<div class="card bg-base-200">
  <button
    class="w-full flex items-center justify-between px-4 py-3 text-left"
    onclick={() => open = !open}
  >
    <div class="flex items-center gap-2">
      <span class="text-sm font-semibold opacity-60 uppercase tracking-wider">{title}</span>
      {#if badge}
        <span class="badge badge-xs badge-ghost opacity-50">{badge}</span>
      {/if}
    </div>
    <svg
      class="w-4 h-4 opacity-40 transition-transform duration-200 {open ? 'rotate-180' : ''}"
      fill="none" viewBox="0 0 24 24" stroke="currentColor"
    >
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
    </svg>
  </button>

  {#if open}
    <div class="px-4 pb-4">
      {@render children()}
    </div>
  {/if}
</div>
