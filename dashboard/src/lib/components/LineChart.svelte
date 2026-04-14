<script lang="ts">
  /**
   * Multi-series SVG line chart.
   * All series are normalized to 0-1 for the Y axis so different-unit metrics
   * can be displayed together. Raw values shown in the hover tooltip.
   */

  interface Point { ts: number; value: number }

  interface Series {
    key:      string;
    label:    string;
    color:    string;
    points:   Point[];
    minVal?:  number;   // default 0
    maxVal?:  number;   // default 100
  }

  interface Props {
    series:      Series[];
    title?:      string;
    height?:     number;
    showSleep?:  boolean;
    sleepBands?: Array<{ start: number; end: number }>;
  }

  let { series, title = '', height = 180, showSleep = false, sleepBands = [] }: Props = $props();

  let containerWidth = $state(800);
  let hoveredX       = $state<number | null>(null);
  let tooltipData    = $state<Array<{ label: string; color: string; rawValue: number; normValue: number }>>([]);
  let tooltipTs      = $state<number | null>(null);

  const PAD_L = 8;
  const PAD_R = 8;
  const PAD_T = 8;
  const PAD_B = 28;

  // Derived min/max timestamps across all series
  let minTs = $derived((() => {
    let min = Infinity;
    for (const s of series) for (const p of s.points) if (p.ts < min) min = p.ts;
    return isFinite(min) ? min : 0;
  })());

  let maxTs = $derived((() => {
    let max = -Infinity;
    for (const s of series) for (const p of s.points) if (p.ts > max) max = p.ts;
    return isFinite(max) ? max : 1;
  })());

  let xTicks = $derived(buildXTicks(minTs, maxTs, 6));

  function normalize(val: number, min: number, max: number): number {
    if (max === min) return 0.5;
    return Math.min(1, Math.max(0, (val - min) / (max - min)));
  }

  function toX(ts: number): number {
    const range = maxTs - minTs;
    if (range === 0) return PAD_L + (containerWidth - PAD_L - PAD_R) / 2;
    return PAD_L + ((ts - minTs) / range) * (containerWidth - PAD_L - PAD_R);
  }

  function toY(norm: number): number {
    return PAD_T + (1 - norm) * (height - PAD_T - PAD_B);
  }

  function buildPath(s: Series): string {
    if (s.points.length === 0) return '';
    const min = s.minVal ?? 0;
    const max = s.maxVal ?? 100;
    return s.points.map((p, i) => {
      const x = toX(p.ts);
      const y = toY(normalize(p.value, min, max));
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
  }

  function buildXTicks(mn: number, mx: number, count: number): Array<{ x: number; label: string }> {
    if (mn === mx) return [];
    return Array.from({ length: count + 1 }, (_, i) => {
      const ts = mn + (i / count) * (mx - mn);
      const d = new Date(ts * 1000);
      return {
        x: PAD_L + (i / count) * (containerWidth - PAD_L - PAD_R),
        label: d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
    });
  }

  function handleMouseMove(e: MouseEvent) {
    const svg = e.currentTarget as SVGElement;
    const rect = svg.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    hoveredX = mx;

    const range = maxTs - minTs;
    const fraction = (mx - PAD_L) / (containerWidth - PAD_L - PAD_R);
    const hoverTs = minTs + fraction * range;
    tooltipTs = hoverTs;

    tooltipData = series.map(s => {
      const min = s.minVal ?? 0;
      const max = s.maxVal ?? 100;
      let best: Point | null = null;
      let bestDist = Infinity;
      for (const p of s.points) {
        const d = Math.abs(p.ts - hoverTs);
        if (d < bestDist) { bestDist = d; best = p; }
      }
      const rawValue = best?.value ?? 0;
      return { label: s.label, color: s.color, rawValue, normValue: normalize(rawValue, min, max) };
    });
  }

  function handleMouseLeave() {
    hoveredX = null;
    tooltipData = [];
    tooltipTs = null;
  }

  function fmtTs(ts: number | null): string {
    if (ts === null) return '';
    return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  const Y_GUIDES = [0.25, 0.5, 0.75];
</script>

<div class="w-full" bind:clientWidth={containerWidth}>
  {#if title}
    <div class="text-xs font-semibold opacity-60 mb-1 uppercase tracking-wide">{title}</div>
  {/if}

  <div class="relative">
    <svg
      width={containerWidth}
      {height}
      viewBox="0 0 {containerWidth} {height}"
      class="block"
      onmousemove={handleMouseMove}
      onmouseleave={handleMouseLeave}
    >
      <!-- Guide lines at 25 / 50 / 75% -->
      {#each Y_GUIDES as g}
        <line
          x1={PAD_L} y1={toY(g)}
          x2={containerWidth - PAD_R} y2={toY(g)}
          stroke="currentColor" stroke-opacity="0.07" stroke-dasharray="3 3"
        />
      {/each}

      <!-- Sleep bands -->
      {#if showSleep}
        {#each sleepBands as band}
          <rect
            x={toX(band.start)} y={PAD_T}
            width={toX(band.end) - toX(band.start)}
            height={height - PAD_T - PAD_B}
            fill="rgba(99,102,241,0.10)"
          />
        {/each}
      {/if}

      <!-- Series lines -->
      {#each series as s}
        {#if s.points.length > 0}
          <path
            d={buildPath(s)}
            fill="none"
            stroke={s.color}
            stroke-width="1.5"
            stroke-linejoin="round"
            stroke-linecap="round"
          />
        {/if}
      {/each}

      <!-- Hover crosshair + dots -->
      {#if hoveredX !== null}
        <line
          x1={hoveredX} y1={PAD_T}
          x2={hoveredX} y2={height - PAD_B}
          stroke="currentColor" stroke-opacity="0.25" stroke-width="1" stroke-dasharray="2 2"
        />
        {#each tooltipData as td}
          <circle
            cx={hoveredX} cy={toY(td.normValue)}
            r="3" fill={td.color}
            stroke="var(--color-base-100,#1d1d2a)" stroke-width="1.5"
          />
        {/each}
      {/if}

      <!-- X-axis labels -->
      {#each xTicks as tick, i}
        {#if i % 2 === 0 || xTicks.length <= 4}
          <text
            x={tick.x} y={height - 4}
            text-anchor="middle" font-size="9"
            fill="currentColor" opacity="0.35"
          >{tick.label}</text>
        {/if}
      {/each}
    </svg>

    <!-- Tooltip -->
    {#if hoveredX !== null && tooltipData.length > 0}
      {@const leftPos = hoveredX > containerWidth * 0.62 ? hoveredX - 168 : hoveredX + 10}
      <div
        class="absolute top-2 bg-base-200 border border-base-300 rounded px-2 py-1.5 text-xs shadow-lg pointer-events-none z-10"
        style="left: {leftPos}px; min-width: 10rem;"
      >
        <div class="opacity-40 mb-1 text-[10px]">{fmtTs(tooltipTs)}</div>
        {#each tooltipData as d}
          <div class="flex items-center gap-1.5 leading-5">
            <span class="inline-block w-2 h-2 rounded-full flex-shrink-0" style="background:{d.color}"></span>
            <span class="opacity-60 truncate" style="max-width:7rem">{d.label}</span>
            <span class="font-mono font-semibold ml-auto pl-2">{d.rawValue.toFixed(1)}</span>
          </div>
        {/each}
      </div>
    {/if}
  </div>

  <!-- Legend -->
  <div class="flex flex-wrap gap-x-4 gap-y-1 mt-1.5">
    {#each series as s}
      <div class="flex items-center gap-1.5 text-[10px] opacity-55">
        <span class="inline-block rounded" style="width:16px; height:2px; background:{s.color}"></span>
        {s.label}
      </div>
    {/each}
  </div>
</div>
