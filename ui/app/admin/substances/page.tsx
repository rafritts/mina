'use client'

import { useEffect, useState } from 'react'
import { apiFetch } from '../../lib/api'
import AuthGate from '../../components/AuthGate'

interface SubstanceEntry {
  name: string
  dose_level?: number
  half_life_hours?: number
  active?: boolean
  [key: string]: unknown
}

export default function SubstancesPage() {
  const [substances, setSubstances] = useState<SubstanceEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [dosing, setDosing] = useState<string | null>(null)
  const [clearing, setClearing] = useState<string | null>(null)
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null)

  const showMsg = (text: string, ok: boolean) => {
    setMessage({ text, ok })
    setTimeout(() => setMessage(null), 3000)
  }

  const load = async () => {
    try {
      const data = await apiFetch<Record<string, SubstanceEntry>>('/api/substance')
      // API returns object keyed by name, convert to array
      const arr = Object.entries(data).map(([name, sub]) => ({ ...sub, name }))
      setSubstances(arr)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const dose = async (name: string) => {
    setDosing(name)
    try {
      await apiFetch(`/api/substance/${name}/dose`, { method: 'POST' })
      showMsg(`Dosed ${name}`, true)
      load()
    } catch (e) {
      showMsg(e instanceof Error ? e.message : 'Failed', false)
    } finally {
      setDosing(null)
    }
  }

  const clear = async (name: string) => {
    setClearing(name)
    try {
      await apiFetch(`/api/substance/${name}`, { method: 'DELETE' })
      showMsg(`Cleared ${name}`, true)
      load()
    } catch (e) {
      showMsg(e instanceof Error ? e.message : 'Failed', false)
    } finally {
      setClearing(null)
    }
  }

  return (
    <AuthGate>
      <div className="p-6 max-w-3xl">
        {message && (
          <div
            className="fixed top-4 right-4 px-4 py-2 rounded-lg text-sm value-mono z-50"
            style={{ background: message.ok ? 'rgba(52,211,153,0.15)' : 'rgba(248,113,113,0.15)', border: `1px solid ${message.ok ? 'rgba(52,211,153,0.3)' : 'rgba(248,113,113,0.3)'}`, color: message.ok ? '#34d399' : '#f87171' }}
          >
            {message.text}
          </div>
        )}
        <h2 className="text-xs uppercase tracking-widest mb-4" style={{ color: 'rgba(232,228,221,0.3)' }}>Substances</h2>
        <div className="gallery-card rounded-lg overflow-hidden">
          {loading ? (
            <p className="p-4 text-xs value-mono" style={{ color: 'rgba(232,228,221,0.2)' }}>loading...</p>
          ) : substances.length === 0 ? (
            <p className="p-4 text-xs value-mono" style={{ color: 'rgba(232,228,221,0.2)' }}>No active substances</p>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b" style={{ borderColor: 'rgba(232,228,221,0.06)' }}>
                  <th className="text-left px-4 py-3" style={{ color: 'rgba(232,228,221,0.35)' }}>Substance</th>
                  <th className="text-right px-4 py-3 value-mono" style={{ color: 'rgba(232,228,221,0.35)' }}>Level</th>
                  <th className="text-right px-4 py-3 value-mono" style={{ color: 'rgba(232,228,221,0.35)' }}>Half-life</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {substances.map(sub => (
                  <tr key={sub.name} className="border-t" style={{ borderColor: 'rgba(232,228,221,0.04)' }}>
                    <td className="px-4 py-3 font-medium" style={{ color: '#e8e4dd' }}>{sub.name}</td>
                    <td className="px-4 py-3 text-right value-mono" style={{ color: 'rgba(232,228,221,0.6)' }}>
                      {typeof sub.level === 'number' ? (sub.level as number).toFixed(1) : (sub.dose_level?.toFixed(2) ?? '—')}
                    </td>
                    <td className="px-4 py-3 text-right value-mono" style={{ color: 'rgba(232,228,221,0.4)' }}>
                      {sub.half_life_hours ? `${sub.half_life_hours}h` : '—'}
                    </td>
                    <td className="px-4 py-3 text-right space-x-2">
                      <button
                        onClick={() => dose(sub.name)}
                        disabled={dosing === sub.name}
                        className="px-3 py-1 rounded border text-xs transition-colors"
                        style={{ borderColor: 'rgba(52,211,153,0.3)', color: '#34d399', background: 'rgba(52,211,153,0.06)' }}
                      >
                        {dosing === sub.name ? '…' : 'Dose'}
                      </button>
                      <button
                        onClick={() => clear(sub.name)}
                        disabled={clearing === sub.name}
                        className="px-3 py-1 rounded border text-xs transition-colors"
                        style={{ borderColor: 'rgba(248,113,113,0.3)', color: '#f87171', background: 'rgba(248,113,113,0.06)' }}
                      >
                        {clearing === sub.name ? '…' : 'Clear'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </AuthGate>
  )
}
