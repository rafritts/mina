<script lang="ts">
  import { getLabel, COLOR_CLASSES } from '$lib/labels';

  interface Props {
    field:   string;
    label:   string;
    value:   number;    // 0–100
    tooltip: string;
  }

  let { field, label, value, tooltip }: Props = $props();

  let entry    = $derived(getLabel(field, value));
  let barColor = $derived(entry ? (COLOR_CLASSES[entry.color]?.progress ?? 'progress-primary') : 'progress-primary');
  let badgeColor = $derived(entry ? (COLOR_CLASSES[entry.color]?.badge ?? 'badge-neutral') : 'badge-neutral');
</script>

<div>
  <div class="flex justify-between items-center mb-1">
    <div class="tooltip tooltip-bottom text-left" data-tip={tooltip}>
      <span class="text-sm cursor-help">{label}</span>
    </div>
    <div class="flex items-center gap-2">
      {#if entry}
        <span class="badge badge-xs {badgeColor}">{entry.name}</span>
      {/if}
      <span class="text-sm font-mono w-10 text-right">{value}</span>
    </div>
  </div>
  <progress class="progress w-full {barColor}" {value} max="100"></progress>
</div>
