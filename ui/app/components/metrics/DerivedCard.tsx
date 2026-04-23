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
    <div className={`gallery-card rounded-lg ${size === 'large' ? 'p-5' : 'p-3.5'} space-y-2`}>
      <div className="flex items-start justify-between">
        <span className={`uppercase tracking-widest ${size === 'large' ? 'text-xs' : 'text-[10px]'}`} style={{ color: 'rgba(232,228,221,0.4)' }}>
          {FIELD_LABELS[field] ?? field.replace(/_/g, ' ')}
        </span>
        {labelEntry && (
          <span className={`text-[10px] px-1.5 py-0.5 rounded border ${colorCls.badge}`}>
            {labelEntry.name}
          </span>
        )}
      </div>
      <div className={`value-mono font-light ${size === 'large' ? 'text-3xl' : 'text-xl'}`} style={{ color: '#e8e4dd' }}>
        {value.toFixed(0)}
      </div>
      <div className="h-0.5 rounded-full overflow-hidden" style={{ background: 'rgba(232,228,221,0.06)' }}>
        <div
          className={`h-full rounded-full transition-all duration-700 ${colorCls.bar}`}
          style={{ width: `${value}%` }}
        />
      </div>
      {size === 'large' && labelEntry && (
        <p className="text-xs" style={{ color: 'rgba(232,228,221,0.3)' }}>{labelEntry.implication}</p>
      )}
    </div>
  )
}
