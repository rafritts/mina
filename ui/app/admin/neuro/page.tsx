'use client'

import { useStatePoller } from '../../lib/hooks/useStatePoller'
import { apiFetch } from '../../lib/api'
import { StatBar } from '../../components/metrics/StatBar'
import { useState } from 'react'

const GROUPS: { label: string; chemicals: string[] }[] = [
  { label: 'Monoamines', chemicals: ['dopamine', 'serotonin', 'norepinephrine'] },
  { label: 'Bonding & Social', chemicals: ['oxytocin', 'endorphins'] },
  { label: 'Modulators', chemicals: ['acetylcholine', 'anandamide', 'two_ag'] },
  { label: 'Excitatory / Inhibitory', chemicals: ['glutamate', 'gaba'] },
  { label: 'Stress', chemicals: ['cortisol'] },
  { label: 'Circadian', chemicals: ['melatonin', 'sleep_pressure', 'glucose', 'hydration'] },
]

export default function NeuroPage() {
  const { state } = useStatePoller()
  const [pending, setPending] = useState<Record<string, number>>({})
  const [saving, setSaving] = useState<Record<string, boolean>>({})

  if (!state) return (
    
      <div className="p-8 text-xs value-mono" style={{ color: 'rgba(232,228,221,0.3)' }}>connecting...</div>
    
  )

  const save = async (field: string) => {
    setSaving(s => ({ ...s, [field]: true }))
    try {
      await apiFetch('/api/state', {
        method: 'PATCH',
        body: JSON.stringify({ [field]: pending[field] }),
      })
      setPending(p => { const n = { ...p }; delete n[field]; return n })
    } finally {
      setSaving(s => ({ ...s, [field]: false }))
    }
  }

  return (
    
      <div className="p-8 mx-auto space-y-8 max-w-3xl">
        {GROUPS.map(({ label, chemicals }) => (
          <section key={label}>
            <h2 className="text-xs uppercase tracking-widest mb-4" style={{ color: 'rgba(232,228,221,0.3)' }}>{label}</h2>
            <div className="gallery-card rounded-lg divide-y" style={{ borderColor: 'rgba(232,228,221,0.06)' }}>
              {chemicals.map(field => {
                const entry = state.chemicals[field]
                if (!entry) return null
                const isDirty = field in pending
                return (
                  <div key={field} className="px-5 py-4 space-y-2">
                    <StatBar
                      field={field}
                      entry={isDirty ? { ...entry, value: pending[field] } : entry}
                    />
                    <div className="flex items-center gap-3">
                      <input
                        type="range"
                        min={0}
                        max={entry.value * 3}
                        step={entry.value < 10 ? 0.01 : 1}
                        value={pending[field] ?? entry.value}
                        onChange={e => setPending(p => ({ ...p, [field]: parseFloat(e.target.value) }))}
                        className="flex-1 h-1 accent-zinc-400"
                      />
                      {isDirty && (
                        <button
                          onClick={() => save(field)}
                          disabled={saving[field]}
                          className="text-xs px-3 py-1 rounded border transition-colors"
                          style={{ borderColor: 'rgba(232,228,221,0.2)', color: '#e8e4dd', background: 'rgba(232,228,221,0.06)' }}
                        >
                          {saving[field] ? '…' : 'Save'}
                        </button>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </section>
        ))}

        {/* Receptor sensitivities */}
        <section>
          <h2 className="text-xs uppercase tracking-widest mb-4" style={{ color: 'rgba(232,228,221,0.3)' }}>
            Receptor Sensitivities
          </h2>
          <div className="gallery-card rounded-lg overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b" style={{ borderColor: 'rgba(232,228,221,0.06)' }}>
                  <th className="text-left px-4 py-2.5" style={{ color: 'rgba(232,228,221,0.35)' }}>Receptor</th>
                  <th className="text-right px-4 py-2.5 value-mono" style={{ color: 'rgba(232,228,221,0.35)' }}>Sensitivity</th>
                </tr>
              </thead>
              <tbody className="divide-y" style={{ borderColor: 'rgba(232,228,221,0.04)' }}>
                {Object.entries(state.receptor_sensitivity).map(([k, v]) => (
                  <tr key={k} className="border-t" style={{ borderColor: 'rgba(232,228,221,0.04)' }}>
                    <td className="px-4 py-2" style={{ color: 'rgba(232,228,221,0.6)' }}>{k.replace(/_/g, ' ')}</td>
                    <td className="px-4 py-2 text-right value-mono" style={{ color: v > 1.2 ? '#34d399' : v < 0.8 ? '#f87171' : '#e8e4dd' }}>
                      {v.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    
  )
}
