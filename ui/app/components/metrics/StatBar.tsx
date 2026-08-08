import { getChemLabel, COLOR_CLASSES, DISPLAY_RANGES } from '../../lib/labels'
import type { ChemicalEntry } from '../../lib/api'
import { cn } from '@/lib/utils'

interface Props {
  field: string
  entry: ChemicalEntry
}

function chipClass(color?: string): string {
  if (color === 'success') return 'chip chip-success'
  if (color === 'warning') return 'chip chip-warning'
  if (color === 'error') return 'chip chip-error'
  if (color === 'info') return 'chip chip-info'
  return 'chip'
}

function formatValue(value: number): string {
  if (value < 0.1) return value.toFixed(3)
  if (value < 10) return value.toFixed(2)
  if (value < 100) return value.toFixed(1)
  return String(Math.round(value))
}

export function StatBar({ field, entry }: Props) {
  const labelEntry = getChemLabel(entry)
  const range = DISPLAY_RANGES[field]
  const max = entry.norm_max ?? range?.max ?? Math.max(entry.value * 3, 1)
  const min = range?.min ?? 0
  const pct = Math.min(100, Math.max(0, ((entry.value - min) / (max - min || 1)) * 100))
  const barColor = labelEntry ? COLOR_CLASSES[labelEntry.color]?.bar : undefined
  const gap = entry.gap
  const gapStr =
    gap === undefined
      ? null
      : Math.abs(gap) < 0.05
        ? 'gap 0'
        : `gap ${gap > 0 ? '+' : ''}${gap.toFixed(1)}`

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11.5px] capitalize text-muted">
          {field.replace(/_/g, ' ')}
        </span>
        <div className="flex items-center gap-2">
          {labelEntry && (
            <span className={chipClass(labelEntry.color)}>{labelEntry.name}</span>
          )}
          <span className="text-xs mono">
            {formatValue(entry.value)}{' '}
            <span className="text-faint">{entry.unit}</span>
          </span>
        </div>
      </div>
      <div className="metric-track">
        <div
          className={cn('metric-fill', barColor)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="flex items-center justify-between gap-2">
        {labelEntry?.implication ? (
          <p className="text-[11px] text-faint m-0 leading-snug flex-1">{labelEntry.implication}</p>
        ) : (
          <span />
        )}
        {gapStr && (
          <span className="mono text-[10px] text-faint shrink-0" title="Gap vs circadian target (sim debug)">
            {gapStr}
            {entry.normalized_10 !== undefined && (
              <> · {entry.normalized_10.toFixed(1)}/10</>
            )}
          </span>
        )}
      </div>
    </div>
  )
}
