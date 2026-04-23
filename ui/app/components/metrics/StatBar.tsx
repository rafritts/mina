import { getLabel, COLOR_CLASSES, DISPLAY_RANGES } from '../../lib/labels'
import type { ChemicalEntry } from '../../lib/api'

interface Props {
  field: string
  entry: ChemicalEntry
  showSlider?: boolean
  onValueChange?: (v: number) => void
}

export function StatBar({ field, entry }: Props) {
  const labelEntry = getLabel(field, entry.value)
  const colorCls = labelEntry ? COLOR_CLASSES[labelEntry.color] : COLOR_CLASSES.neutral
  const range = DISPLAY_RANGES[field]
  const pct = range
    ? Math.min(100, Math.max(0, ((entry.value - range.min) / (range.max - range.min)) * 100))
    : entry.normalized * 100

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs uppercase tracking-wider" style={{ color: 'rgba(232,228,221,0.45)', fontFamily: 'var(--font-geist-sans)' }}>
          {field.replace(/_/g, ' ')}
        </span>
        <div className="flex items-center gap-2">
          {labelEntry && (
            <span className={`text-xs px-1.5 py-0.5 rounded border ${colorCls.badge}`}>
              {labelEntry.name}
            </span>
          )}
          <span className="text-xs value-mono" style={{ color: '#e8e4dd' }}>
            {entry.value.toFixed(entry.value < 10 ? 2 : 0)} {entry.unit}
          </span>
        </div>
      </div>
      <div className="h-1 rounded-full overflow-hidden" style={{ background: 'rgba(232,228,221,0.06)' }}>
        <div
          className={`h-full rounded-full transition-all duration-500 ${colorCls.bar}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {labelEntry && (
        <p className="text-xs" style={{ color: 'rgba(232,228,221,0.3)' }}>{labelEntry.implication}</p>
      )}
    </div>
  )
}
