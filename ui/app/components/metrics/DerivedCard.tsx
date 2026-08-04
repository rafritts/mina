import { getLabel } from '../../lib/labels'
import { FIELD_LABELS } from '../../lib/presence'

interface Props {
  field: string
  value: number
  size?: 'large' | 'small'
}

function chipClass(color?: string): string {
  if (color === 'success') return 'chip chip-success'
  if (color === 'warning') return 'chip chip-warning'
  if (color === 'error') return 'chip chip-error'
  if (color === 'info') return 'chip chip-info'
  return 'chip'
}

export function DerivedCard({ field, value, size = 'small' }: Props) {
  const labelEntry = getLabel(field, value)

  return (
    <div className={`surface ${size === 'large' ? 'p-4' : 'p-3'} space-y-1.5`}>
      <div className="flex items-center justify-between gap-2">
        <span className="label">
          {FIELD_LABELS[field] ?? field.replace(/_/g, ' ')}
        </span>
        {labelEntry && <span className={chipClass(labelEntry.color)}>{labelEntry.name}</span>}
      </div>
      <div className={`mono font-light ${size === 'large' ? 'text-2xl' : 'text-lg'}`}>
        {value.toFixed(0)}
      </div>
      <div className="metric-track">
        <div className="metric-fill" style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
      </div>
      {size === 'large' && labelEntry && (
        <p className="text-[11px] text-muted leading-tight m-0">{labelEntry.implication}</p>
      )}
    </div>
  )
}
