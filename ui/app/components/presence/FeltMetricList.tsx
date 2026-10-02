import { Chip, chipTone } from '../Chip'
import { getLabel } from '../../lib/labels'
import { FIELD_LABELS } from '../../lib/presence'

function labelFor(field: string): string {
  return FIELD_LABELS[field] ?? field.replace(/_/g, ' ')
}

function fillWidth(value: number): string {
  return `${Math.min(100, Math.max(0, value))}%`
}

function FeltBar({ field, value }: { field: string; value: number }) {
  const entry = getLabel(field, value)
  return (
    <div className="metric">
      <div className="metric-top">
        <span className="text-[11.5px] text-muted">{labelFor(field)}</span>
        <div className="flex items-center gap-1.5">
          {entry && <Chip tone={chipTone(entry.color)}>{entry.name}</Chip>}
          <span className="mono text-[11px] text-secondary w-7 text-right">
            {Math.round(value)}
          </span>
        </div>
      </div>
      <div className="metric-track">
        <div className="metric-fill" style={{ width: fillWidth(value) }} />
      </div>
    </div>
  )
}

function FeltCard({ field, value }: { field: string; value: number }) {
  const entry = getLabel(field, value)
  return (
    <div className="metric-cell">
      <div className="flex items-center justify-between gap-2">
        <span className="label">{labelFor(field)}</span>
        {entry && <Chip tone={chipTone(entry.color)}>{entry.name}</Chip>}
      </div>
      <div className="text-2xl font-light mono tracking-tight">{Math.round(value)}</div>
      <div className="metric-track">
        <div className="metric-fill" style={{ width: fillWidth(value) }} />
      </div>
    </div>
  )
}

/**
 * Felt state and signals, one readout.
 * `bar` is the compact Presence sheet; `card` is the Overview dashboard.
 */
export function FeltMetricList({
  fields,
  values,
  variant,
  emptyValue,
}: {
  fields: readonly string[]
  values: Record<string, number> | undefined
  variant: 'bar' | 'card'
  emptyValue: number
}) {
  const items = fields.map((field) => {
    const value = values?.[field] ?? emptyValue
    return variant === 'card' ? (
      <FeltCard key={field} field={field} value={value} />
    ) : (
      <FeltBar key={field} field={field} value={value} />
    )
  })

  if (variant === 'card') {
    return <div className="metric-board">{items}</div>
  }
  return <div className="space-y-3">{items}</div>
}
