import { getLabel } from '../../lib/labels'
import { FIELD_LABELS } from '../../lib/presence'

function chipClass(color?: string): string {
  if (color === 'success') return 'chip chip-success'
  if (color === 'warning') return 'chip chip-warning'
  if (color === 'error') return 'chip chip-error'
  if (color === 'info') return 'chip chip-info'
  return 'chip'
}

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
          {entry && <span className={chipClass(entry.color)}>{entry.name}</span>}
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
    <div className="surface p-3.5 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <span className="label">{labelFor(field)}</span>
        {entry && <span className={chipClass(entry.color)}>{entry.name}</span>}
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
    return <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">{items}</div>
  }
  return <div className="space-y-3">{items}</div>
}
