import { getLabel, COLOR_CLASSES, DISPLAY_RANGES } from '../../lib/labels'
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

export function StatBar({ field, entry }: Props) {
  const labelEntry = getLabel(field, entry.value)
  const range = DISPLAY_RANGES[field]
  const pct = range
    ? Math.min(100, Math.max(0, ((entry.value - range.min) / (range.max - range.min)) * 100))
    : entry.normalized * 100
  const barColor = labelEntry ? COLOR_CLASSES[labelEntry.color]?.bar : undefined

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
            {entry.value.toFixed(entry.value < 10 ? 2 : 0)}{' '}
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
      {labelEntry && (
        <p className="text-[11px] text-faint m-0 leading-snug">{labelEntry.implication}</p>
      )}
    </div>
  )
}
