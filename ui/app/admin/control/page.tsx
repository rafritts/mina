'use client'

import { useState, useEffect } from 'react'
import { apiFetch } from '../../lib/api'
import type { StateData, CascadeEvent } from '../../lib/api'
import { PRESETS } from '../../lib/presets'

function formatFiresAt(unix: number): string {
  const diff = unix - Date.now() / 1000
  if (diff < 0) return 'fired'
  if (diff < 60) return `${Math.round(diff)}s`
  return `${Math.round(diff / 60)}m`
}

export default function ControlPage() {
  const [heartbeatRunning, setHeartbeatRunning] = useState(false)
  const [heartbeatStatus, setHeartbeatStatus] = useState<string | null>(null)
  const [advanceHours, setAdvanceHours] = useState('1')
  const [advancing, setAdvancing] = useState(false)
  const [cascade, setCascade] = useState<CascadeEvent[]>([])
  const [presetApplying, setPresetApplying] = useState<string | null>(null)
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null)

  const showMsg = (text: string, ok: boolean) => {
    setMessage({ text, ok })
    setTimeout(() => setMessage(null), 3000)
  }

  // Poll cascade queue
  useEffect(() => {
    const poll = async () => {
      try {
        const data = await apiFetch<StateData>('/api/state')
        setCascade(data.cascade_queue ?? [])
      } catch {}
    }
    poll()
    const t = setInterval(poll, 5000)
    return () => clearInterval(t)
  }, [])

  const runHeartbeat = async () => {
    setHeartbeatRunning(true)
    setHeartbeatStatus(null)
    try {
      const result = await apiFetch<{ ok: boolean; message?: string }>('/api/heartbeat', { method: 'POST' })
      setHeartbeatStatus(result.message ?? 'ok')
      showMsg('Heartbeat complete', true)
    } catch (e) {
      showMsg(e instanceof Error ? e.message : 'Failed', false)
    } finally {
      setHeartbeatRunning(false)
    }
  }

  const advance = async () => {
    setAdvancing(true)
    try {
      await apiFetch('/api/state/advance', {
        method: 'POST',
        body: JSON.stringify({ hours: parseFloat(advanceHours) }),
      })
      showMsg(`Advanced ${advanceHours}h`, true)
    } catch (e) {
      showMsg(e instanceof Error ? e.message : 'Failed', false)
    } finally {
      setAdvancing(false)
    }
  }

  const applyPreset = async (name: string, values: Record<string, number>) => {
    setPresetApplying(name)
    try {
      await apiFetch('/api/state', { method: 'PATCH', body: JSON.stringify(values) })
      showMsg(`Applied "${name}"`, true)
    } catch (e) {
      showMsg(e instanceof Error ? e.message : 'Failed', false)
    } finally {
      setPresetApplying(null)
    }
  }

  return (
    
      <div className="p-6 space-y-8 max-w-4xl">
        {/* Toast */}
        {message && (
          <div
            className="fixed top-4 right-4 px-4 py-2 rounded-lg text-sm value-mono z-50"
            style={{ background: message.ok ? 'rgba(52,211,153,0.15)' : 'rgba(248,113,113,0.15)', border: `1px solid ${message.ok ? 'rgba(52,211,153,0.3)' : 'rgba(248,113,113,0.3)'}`, color: message.ok ? '#34d399' : '#f87171' }}
          >
            {message.text}
          </div>
        )}

        {/* Heartbeat */}
        <section>
          <h2 className="text-xs uppercase tracking-widest mb-4" style={{ color: 'rgba(232,228,221,0.3)' }}>Heartbeat</h2>
          <div className="gallery-card rounded-lg p-5 flex items-center gap-4">
            <button
              onClick={runHeartbeat}
              disabled={heartbeatRunning}
              className="px-6 py-2.5 rounded-lg text-sm font-medium transition-all"
              style={{
                background: heartbeatRunning ? 'rgba(232,228,221,0.05)' : 'rgba(232,228,221,0.1)',
                color: heartbeatRunning ? 'rgba(232,228,221,0.35)' : '#e8e4dd',
                border: '1px solid rgba(232,228,221,0.15)',
              }}
            >
              {heartbeatRunning ? '⟳ Running…' : '▶ Run Heartbeat'}
            </button>
            {heartbeatStatus && (
              <span className="text-xs value-mono" style={{ color: 'rgba(232,228,221,0.4)' }}>{heartbeatStatus}</span>
            )}
          </div>
        </section>

        {/* Advance simulation */}
        <section>
          <h2 className="text-xs uppercase tracking-widest mb-4" style={{ color: 'rgba(232,228,221,0.3)' }}>Advance Simulation</h2>
          <div className="gallery-card rounded-lg p-5 flex items-center gap-3">
            <input
              type="number"
              value={advanceHours}
              onChange={e => setAdvanceHours(e.target.value)}
              className="w-24 bg-transparent border rounded px-3 py-2 text-sm value-mono outline-none"
              style={{ borderColor: 'rgba(232,228,221,0.15)', color: '#e8e4dd' }}
              min="0.25"
              max="168"
              step="0.25"
            />
            <span className="text-xs" style={{ color: 'rgba(232,228,221,0.4)' }}>hours</span>
            <button
              onClick={advance}
              disabled={advancing}
              className="px-4 py-2 rounded text-sm transition-colors"
              style={{ background: 'rgba(232,228,221,0.08)', color: '#e8e4dd', border: '1px solid rgba(232,228,221,0.15)' }}
            >
              {advancing ? '…' : 'Advance'}
            </button>
          </div>
        </section>

        {/* Presets */}
        <section>
          <h2 className="text-xs uppercase tracking-widest mb-4" style={{ color: 'rgba(232,228,221,0.3)' }}>Presets</h2>
          <div className="grid grid-cols-3 gap-2.5">
            {PRESETS.map(preset => (
              <div key={preset.name} className="gallery-card rounded-lg p-4 space-y-2">
                <div className="text-sm font-medium" style={{ color: '#e8e4dd' }}>{preset.name}</div>
                <p className="text-xs" style={{ color: 'rgba(232,228,221,0.35)' }}>{preset.description}</p>
                <button
                  onClick={() => applyPreset(preset.name, preset.values)}
                  disabled={presetApplying === preset.name}
                  className="text-xs px-3 py-1.5 rounded border transition-colors w-full"
                  style={{ borderColor: 'rgba(232,228,221,0.15)', color: 'rgba(232,228,221,0.6)', background: 'rgba(232,228,221,0.04)' }}
                >
                  {presetApplying === preset.name ? 'Applying…' : 'Apply'}
                </button>
              </div>
            ))}
          </div>
        </section>

        {/* Cascade queue */}
        <section>
          <h2 className="text-xs uppercase tracking-widest mb-4" style={{ color: 'rgba(232,228,221,0.3)' }}>
            Cascade Queue {cascade.length > 0 && <span className="ml-2 text-amber-400">({cascade.length})</span>}
          </h2>
          <div className="gallery-card rounded-lg overflow-hidden">
            {cascade.length === 0 ? (
              <p className="px-4 py-3 text-xs value-mono" style={{ color: 'rgba(232,228,221,0.2)' }}>Empty</p>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b" style={{ borderColor: 'rgba(232,228,221,0.06)' }}>
                    <th className="text-left px-4 py-2.5" style={{ color: 'rgba(232,228,221,0.35)' }}>Type</th>
                    <th className="text-right px-4 py-2.5 value-mono" style={{ color: 'rgba(232,228,221,0.35)' }}>Fires</th>
                    <th className="text-right px-4 py-2.5 value-mono" style={{ color: 'rgba(232,228,221,0.35)' }}>Magnitude</th>
                  </tr>
                </thead>
                <tbody>
                  {cascade.map((ev, i) => (
                    <tr key={i} className="border-t" style={{ borderColor: 'rgba(232,228,221,0.04)' }}>
                      <td className="px-4 py-2" style={{ color: 'rgba(232,228,221,0.6)' }}>{ev.type}</td>
                      <td className="px-4 py-2 text-right value-mono" style={{ color: 'rgba(232,228,221,0.4)' }}>{formatFiresAt(ev.fires_at_unix)}</td>
                      <td className="px-4 py-2 text-right value-mono" style={{ color: 'rgba(232,228,221,0.6)' }}>{ev.magnitude.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      </div>
    
  )
}
