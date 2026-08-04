'use client'

import { useState } from 'react'
import { useStatePoller } from '../../lib/hooks/useStatePoller'
import { apiFetch } from '../../lib/api'
import { StatBar } from '../../components/metrics/StatBar'
import { DISPLAY_RANGES } from '../../lib/labels'
import type { SecretionQueueEntry } from '../../lib/api'

const GROUPS: { label: string; chemicals: string[] }[] = [
  { label: 'Monoamines', chemicals: ['dopamine', 'serotonin', 'norepinephrine'] },
  { label: 'Bonding & social', chemicals: ['oxytocin', 'endorphins'] },
  { label: 'Modulators', chemicals: ['acetylcholine', 'anandamide', 'two_ag'] },
  { label: 'Excitatory / inhibitory', chemicals: ['glutamate', 'gaba'] },
  { label: 'Stress', chemicals: ['cortisol', 'epinephrine'] },
  { label: 'Circadian', chemicals: ['melatonin', 'sleep_pressure'] },
  { label: 'Physiological', chemicals: ['glucose', 'hydration'] },
]

export default function NeuroPage() {
  const { state, error } = useStatePoller()
  const [pending, setPending] = useState<Record<string, number>>({})
  const [saving, setSaving] = useState<Record<string, boolean>>({})

  if (!state) {
    return (
      <div className="page">
        <p className="mono text-sm text-muted m-0">{error ?? 'Connecting…'}</p>
      </div>
    )
  }

  const save = async (field: string) => {
    setSaving((s) => ({ ...s, [field]: true }))
    try {
      await apiFetch('/api/state', {
        method: 'PATCH',
        body: JSON.stringify({ [field]: pending[field] }),
      })
      setPending((p) => {
        const n = { ...p }
        delete n[field]
        return n
      })
    } finally {
      setSaving((s) => ({ ...s, [field]: false }))
    }
  }

  return (
    <div className="page">
      <h1 className="page-title">Chemistry</h1>
      <p className="page-desc">
        Direct tonic overrides. Same values as Chat → Control → Chemistry, with full groups and
        receptor readouts.
      </p>

      {GROUPS.map(({ label, chemicals }) => (
        <section key={label} className="section">
          <div className="label section-head">{label}</div>
          <div className="surface divide-y divide-[var(--border-subtle)]">
            {chemicals.map((field) => {
              const entry = state.chemicals[field]
              if (!entry) return null
              const isDirty = field in pending
              const range = DISPLAY_RANGES[field]
              const min = range?.min ?? 0
              const max = range?.max ?? Math.max(entry.value * 3, 1)
              return (
                <div key={field} className="px-4 py-3.5 space-y-2">
                  <StatBar
                    field={field}
                    entry={isDirty ? { ...entry, value: pending[field] } : entry}
                  />
                  <div className="flex items-center gap-3">
                    <input
                      type="range"
                      min={min}
                      max={max}
                      step={entry.value < 10 ? 0.01 : 1}
                      value={pending[field] ?? entry.value}
                      onChange={(e) =>
                        setPending((p) => ({ ...p, [field]: parseFloat(e.target.value) }))
                      }
                      className="flex-1"
                    />
                    {isDirty && (
                      <button
                        type="button"
                        className="btn btn-soft btn-sm"
                        onClick={() => void save(field)}
                        disabled={saving[field]}
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

      <section className="section">
        <div className="label section-head">Secretion queue</div>
        {!state.secretion_queue?.length ? (
          <div className="surface px-4 py-3 text-xs mono text-faint">Empty</div>
        ) : (
          <div className="surface overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[var(--border-subtle)]">
                  <th className="text-left px-4 py-2.5 text-muted font-medium">Chemical</th>
                  <th className="text-right px-4 py-2.5 text-muted font-medium mono">Remaining</th>
                  <th className="text-right px-4 py-2.5 text-muted font-medium mono">Rate/hr</th>
                </tr>
              </thead>
              <tbody>
                {state.secretion_queue.map((entry: SecretionQueueEntry, i: number) => (
                  <tr key={i} className="border-t border-[var(--border-subtle)]">
                    <td className="px-4 py-2 text-secondary">
                      {entry.chemical.replace(/_/g, ' ')}
                    </td>
                    <td className="px-4 py-2 text-right mono">
                      {entry.remaining > 0 ? '+' : ''}
                      {entry.remaining.toFixed(2)}
                    </td>
                    <td className="px-4 py-2 text-right mono text-muted">
                      {entry.rate_per_sim_hour.toFixed(0)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="section">
        <div className="label section-head">Receptor sensitivities</div>
        <div className="surface overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-[var(--border-subtle)]">
                <th className="text-left px-4 py-2.5 text-muted font-medium">Receptor</th>
                <th className="text-right px-4 py-2.5 text-muted font-medium mono">Sensitivity</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(state.receptor_sensitivity).map(([k, v]) => (
                <tr key={k} className="border-t border-[var(--border-subtle)]">
                  <td className="px-4 py-2 text-secondary">{k.replace(/_/g, ' ')}</td>
                  <td className="px-4 py-2 text-right mono">{v.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
