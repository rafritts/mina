<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { getLabel, COLOR_CLASSES, DISPLAY_RANGES } from '$lib/labels';

  interface Props {
    field:    string;
    label:    string;
    value:    number;    // current real-unit value
    unit:     string;
    min:      number;
    max:      number;
    tooltip:  string;
    saving?:  boolean;
  }

  let { field, label, value, unit, min, max, tooltip, saving = false }: Props = $props();

  const dispatch = createEventDispatcher<{ change: { field: string; value: number } }>();

  let localVal = $state(value);
  let patchTimer: ReturnType<typeof setTimeout> | null = null;
  let isEditing = $state(false);

  // Keep in sync when parent value changes (and not currently editing)
  $effect(() => {
    if (!isEditing) localVal = value;
  });

  let entry      = $derived(getLabel(field, localVal));
  let badgeColor = $derived(entry ? (COLOR_CLASSES[entry.color]?.badge ?? 'badge-neutral') : 'badge-neutral');

  function rangeColor(): string {
    if (!entry) return 'range-primary';
    switch (entry.color) {
      case 'success': return 'range-success';
      case 'warning': return 'range-warning';
      case 'error':   return 'range-error';
      case 'info':    return 'range-info';
      default:        return 'range-primary';
    }
  }

  function fmtVal(v: number): string {
    if (unit === 'ng/mL' || unit === '% TBW') return v.toFixed(1);
    if (unit === 'nM' || unit === 'µmol/L' || unit === '') return v.toFixed(2);
    return v.toFixed(0);
  }

  function onInput(e: Event) {
    const v = parseFloat((e.target as HTMLInputElement).value);
    localVal = v;
    isEditing = true;
    if (patchTimer) clearTimeout(patchTimer);
    patchTimer = setTimeout(() => {
      dispatch('change', { field, value: v });
    }, 400);
  }

  function onRelease() {
    if (patchTimer) {
      clearTimeout(patchTimer);
      patchTimer = null;
    }
    dispatch('change', { field, value: localVal });
    isEditing = false;
  }
</script>

<div>
  <div class="flex justify-between items-center mb-1">
    <div class="tooltip tooltip-bottom text-left">
      <span class="text-sm font-medium cursor-help">{label}</span>
      <div class="tooltip-content text-left text-xs leading-relaxed whitespace-pre-line" style="max-width: 20rem;">{tooltip}</div>
    </div>
    <div class="flex items-center gap-2">
      {#if saving}
        <span class="loading loading-spinner loading-xs"></span>
      {/if}
      {#if entry}
        <span class="badge badge-xs {badgeColor}">{entry.name}</span>
      {/if}
      <span class="text-xs font-mono opacity-50">{unit}</span>
      <span class="text-sm font-mono w-14 text-right">{fmtVal(localVal)}</span>
    </div>
  </div>
  <input
    type="range"
    {min}
    {max}
    step={(max - min) / 200}
    value={localVal}
    class="range range-sm w-full {rangeColor()}"
    oninput={onInput}
    onmouseup={onRelease}
    ontouchend={onRelease}
  />
</div>
