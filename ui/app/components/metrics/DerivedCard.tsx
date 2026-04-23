import { getLabel, COLOR_CLASSES } from '../../lib/labels'

interface Props {
  field: string
  value: number
  size?: 'large' | 'small'
}

const FIELD_LABELS: Record<string, string> = {
  energy: 'Energy',
  cognitive_clarity: 'Clarity',
  hedonic_tone: 'Hedonic Tone',
  social_warmth: 'Social Warmth',
  arousal: 'Arousal',
  mood_valence: 'Mood',
  anxiety: 'Anxiety',
  depression: 'Depression',
  boredom: 'Boredom',
  loneliness: 'Loneliness',
  flow: 'Flow',
  physical_distress: 'Physical Distress',
  craving: 'Craving',
}

export function DerivedCard({ field, value, size = 'small' }: Props) {
  const labelEntry = getLabel(field, value)
  const colorCls = labelEntry ? COLOR_CLASSES[labelEntry.color] : COLOR_CLASSES.neutral

  return (
    <div className={`gallery-card rounded-lg ${size === 'large' ? 'p-4' : 'p-3'} space-y-1.5`}>
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-widest" style={{ color: 'rgba(232,228,221,0.5)' }}>
          {FIELD_LABELS[field] ?? field.replace(/_/g, ' ')}
        </span>
        {labelEntry && (
          <span className={`text-[9px] px-1 py-0.5 rounded border ${colorCls.badge}`}>
            {labelEntry.name}
          </span>
        )}
      </div>
      <div className={`value-mono ${size === 'large' ? 'text-2xl font-light' : 'text-lg font-light'}`} style={{ color: '#f0ebe2' }}>
        {value.toFixed(0)}
      </div>
      <div className="h-[2px] rounded-full overflow-hidden" style={{ background: 'rgba(232,228,221,0.08)' }}>
        <div
          className={`h-full rounded-full transition-all duration-700 ${colorCls.bar}`}
          style={{ width: `${value}%` }}
        />
      </div>
      {size === 'large' && labelEntry && (
        <p className="text-[11px] leading-tight" style={{ color: 'rgba(232,228,221,0.4)' }}>{labelEntry.implication}</p>
      )}
    </div>
  )
}
