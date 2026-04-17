<script lang="ts">
  import { getLabel, COLOR_CLASSES, DISPLAY_RANGES } from '$lib/labels';

  interface Props {
    field:      string;
    label:      string;
    value:      number;
    unit:       string;
    normalized: number;   // 0.0–1.0 for progress bar
    tooltip:    string;
    dimmed?:    boolean;  // opacity-60 for formula-driven fields
  }

  let { field, label, value, unit, normalized, tooltip, dimmed = false }: Props = $props();

  let entry      = $derived(getLabel(field, value));
  let barColor   = $derived(entry ? (COLOR_CLASSES[entry.color]?.progress ?? 'progress-neutral') : 'progress-neutral');
  let badgeColor = $derived(entry ? (COLOR_CLASSES[entry.color]?.badge ?? 'badge-neutral') : 'badge-neutral');

  function fmtVal(v: number, u: string): string {
    if (u === 'ng/mL' || u === '% TBW' || u === '°C') return v.toFixed(2);
    if (u === 'nM' || u === 'µmol/L' || u === 'mIU/L' || u === '') return v.toFixed(3);
    if (v < 1) return v.toFixed(3);
    if (v < 10) return v.toFixed(2);
    if (v < 100) return v.toFixed(1);
    return v.toFixed(0);
  }
</script>

<div class="{dimmed ? 'opacity-60' : ''}">
  <div class="flex justify-between items-center mb-1">
    <div class="tooltip tooltip-bottom text-left">
      <span class="text-sm cursor-help {dimmed ? 'opacity-70' : ''}">{label}</span>
      <div class="tooltip-content text-left text-xs leading-relaxed" style="max-width: 20rem; white-space: normal;">{@html tooltip.replace(/^([^\n]+)/, '<strong>$1</strong>').replace(/\n/g, '<br>')}</div>
    </div>
    <div class="flex items-center gap-2">
      {#if entry}
        <span class="badge badge-xs {badgeColor}">{entry.name}</span>
      {/if}
      <span class="text-xs font-mono opacity-50">{unit}</span>
      <span class="text-sm font-mono w-14 text-right">{fmtVal(value, unit)}</span>
    </div>
  </div>
  <progress class="progress {barColor} w-full" value={normalized} max="1"></progress>
</div>
