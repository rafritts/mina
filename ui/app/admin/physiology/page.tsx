'use client'

import { useStatePoller } from '../../lib/hooks/useStatePoller'
import { getLabel, COLOR_CLASSES } from '../../lib/labels'
import { useState } from 'react'

const IMMUNE_FIELDS = ['il1b', 'il6', 'tnf_alpha', 'crp', 'il10', 'inflammation_index']
const PAIN_FIELDS = ['substance_p', 'pge2', 'pain_intensity', 'central_sensitization', 'vagal_tone']
const BODY_FIELDS = ['core_temp', 'adenosine', 'circadian_phase']
const NEURO_FIELDS = ['crh', 'acth', 'tsh', 't4', 't3', 'estradiol', 'progesterone', 'testosterone', 'ghrelin', 'leptin', 'insulin', 'vasopressin', 'prolactin', 'growth_hormone', 'dhea', 'orexin']
const NEUROPLASTICITY_FIELDS = ['bdnf', 'synaptic_potentiation', 'allostatic_load']

type Tab = 'hormones' | 'immune' | 'body'

function ReadOnlyRow({ field, value, unit }: { field: string; value: number; unit?: string }) {
  const label = getLabel(field, value)
  const colorCls = label ? COLOR_CLASSES[label.color] : COLOR_CLASSES.neutral
  return (
    <tr className="border-t" style={{ borderColor: 'rgba(232,228,221,0.04)' }}>
      <td className="px-4 py-2.5 text-xs" style={{ color: 'rgba(232,228,221,0.5)' }}>{field.replace(/_/g, ' ')}</td>
      <td className="px-4 py-2.5 text-xs text-right value-mono" style={{ color: '#e8e4dd' }}>
        {value.toFixed(value < 10 ? 2 : 0)} {unit ?? ''}
      </td>
      <td className="px-4 py-2.5 text-right">
        {label && (
          <span className={`text-[10px] px-1.5 py-0.5 rounded border ${colorCls.badge}`}>{label.name}</span>
        )}
      </td>
    </tr>
  )
}

export default function PhysiologyPage() {
  const { state } = useStatePoller()
  const [tab, setTab] = useState<Tab>('hormones')

  if (!state) return (
    
      <div className="p-8 text-xs value-mono" style={{ color: 'rgba(232,228,221,0.3)' }}>connecting...</div>
    
  )

  const tabs: { id: Tab; label: string }[] = [
    { id: 'hormones', label: 'Hormones' },
    { id: 'immune', label: 'Immune' },
    { id: 'body', label: 'Body' },
  ]

  return (
    
      <div className="p-8 mx-auto space-y-6 max-w-3xl">
        {/* Tabs */}
        <div className="flex gap-1">
          {tabs.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className="px-4 py-2 text-xs rounded border transition-colors"
              style={{
                borderColor: tab === t.id ? 'rgba(232,228,221,0.3)' : 'rgba(232,228,221,0.1)',
                color: tab === t.id ? '#e8e4dd' : 'rgba(232,228,221,0.35)',
                background: tab === t.id ? 'rgba(232,228,221,0.08)' : 'transparent',
              }}
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === 'hormones' && (
          <div className="space-y-6">
            <div className="gallery-card rounded-lg overflow-hidden">
              <h3 className="px-4 pt-4 pb-2 text-xs uppercase tracking-widest" style={{ color: 'rgba(232,228,221,0.3)' }}>Neuroendocrine</h3>
              <table className="w-full">
                <tbody>
                  {NEURO_FIELDS.map(f => {
                    const v = state.neuroendocrine[f]
                    if (v === undefined) return null
                    return <ReadOnlyRow key={f} field={f} value={v} />
                  })}
                </tbody>
              </table>
            </div>
            <div className="gallery-card rounded-lg overflow-hidden">
              <h3 className="px-4 pt-4 pb-2 text-xs uppercase tracking-widest" style={{ color: 'rgba(232,228,221,0.3)' }}>Neuroplasticity</h3>
              <table className="w-full">
                <tbody>
                  {NEUROPLASTICITY_FIELDS.map(f => {
                    const v = state.neuroplasticity[f]
                    if (v === undefined) return null
                    return <ReadOnlyRow key={f} field={f} value={v} />
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {tab === 'immune' && (
          <div className="gallery-card rounded-lg overflow-hidden">
            <table className="w-full">
              <tbody>
                {IMMUNE_FIELDS.map(f => {
                  const v = state.immune[f]
                  if (v === undefined) return null
                  return <ReadOnlyRow key={f} field={f} value={v} />
                })}
              </tbody>
            </table>
          </div>
        )}

        {tab === 'body' && (
          <div className="space-y-6">
            <div className="gallery-card rounded-lg overflow-hidden">
              <table className="w-full">
                <tbody>
                  {BODY_FIELDS.map(f => {
                    const v = state.body[f]
                    if (v === undefined) return null
                    return <ReadOnlyRow key={f} field={f} value={v} />
                  })}
                  {PAIN_FIELDS.map(f => {
                    const v = state.pain[f]
                    if (v === undefined) return null
                    return <ReadOnlyRow key={f} field={f} value={v} />
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    
  )
}
