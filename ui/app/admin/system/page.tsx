'use client'

import { useEffect, useState } from 'react'
import { apiFetch } from '../../lib/api'
import type { TokenStats } from '../../lib/api'

interface BillingData {
  cap: number
  used: number
  remaining: number
  period?: string
}

interface HeartbeatStatus {
  last_run?: number
  is_running?: boolean
  running?: boolean
}

export default function SystemPage() {
  const [billing, setBilling] = useState<BillingData | null>(null)
  const [tokens, setTokens] = useState<TokenStats | null>(null)
  const [heartbeatStatus, setHeartbeatStatus] = useState<HeartbeatStatus | null>(null)

  useEffect(() => {
    apiFetch<BillingData>('/api/billing').then(setBilling).catch(() => {})
    apiFetch<TokenStats>('/api/tokens').then(setTokens).catch(() => {})
    apiFetch<HeartbeatStatus>('/api/heartbeat/status').then(setHeartbeatStatus).catch(() => {})
  }, [])

  const billingPct = billing ? Math.min(100, (billing.used / billing.cap) * 100) : 0

  return (
    
      <div className="p-6 space-y-8 max-w-3xl">
        {/* Billing */}
        <section>
          <h2 className="text-xs uppercase tracking-widest mb-4" style={{ color: 'rgba(232,228,221,0.3)' }}>Billing</h2>
          <div className="gallery-card rounded-lg p-5 space-y-3">
            {billing ? (
              <>
                <div className="flex justify-between text-xs">
                  <span style={{ color: 'rgba(232,228,221,0.45)' }}>Used</span>
                  <span className="value-mono" style={{ color: '#e8e4dd' }}>${billing.used.toFixed(2)} / ${billing.cap.toFixed(2)}</span>
                </div>
                <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(232,228,221,0.06)' }}>
                  <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{
                      width: `${billingPct}%`,
                      background: billingPct > 80 ? '#f87171' : billingPct > 60 ? '#f59e0b' : '#34d399',
                    }}
                  />
                </div>
                <div className="flex justify-between text-xs">
                  <span style={{ color: 'rgba(232,228,221,0.3)' }}>{billingPct.toFixed(1)}% used</span>
                  <span className="value-mono" style={{ color: 'rgba(232,228,221,0.45)' }}>${billing.remaining.toFixed(2)} remaining</span>
                </div>
              </>
            ) : (
              <p className="text-xs value-mono" style={{ color: 'rgba(232,228,221,0.2)' }}>loading...</p>
            )}
          </div>
        </section>

        {/* Heartbeat status */}
        {heartbeatStatus && (
          <section>
            <h2 className="text-xs uppercase tracking-widest mb-4" style={{ color: 'rgba(232,228,221,0.3)' }}>Health</h2>
            <div className="gallery-card rounded-lg p-5 space-y-2">
              <div className="flex justify-between text-xs">
                <span style={{ color: 'rgba(232,228,221,0.45)' }}>Last heartbeat</span>
                <span className="value-mono" style={{ color: 'rgba(232,228,221,0.6)' }}>
                  {heartbeatStatus.last_run
                    ? new Date(heartbeatStatus.last_run * 1000).toLocaleString()
                    : 'never'}
                </span>
              </div>
              <div className="flex justify-between text-xs">
                <span style={{ color: 'rgba(232,228,221,0.45)' }}>Running</span>
                <span className="value-mono" style={{ color: (heartbeatStatus.is_running || heartbeatStatus.running) ? '#34d399' : 'rgba(232,228,221,0.35)' }}>
                  {(heartbeatStatus.is_running || heartbeatStatus.running) ? 'yes' : 'no'}
                </span>
              </div>
            </div>
          </section>
        )}

        {/* Token usage */}
        {tokens && (
          <section>
            <h2 className="text-xs uppercase tracking-widest mb-4" style={{ color: 'rgba(232,228,221,0.3)' }}>Token Usage</h2>
            <div className="gallery-card rounded-lg overflow-hidden">
              <div className="px-4 py-3 grid grid-cols-4 gap-4 border-b" style={{ borderColor: 'rgba(232,228,221,0.06)' }}>
                {[
                  ['Input', tokens.total_input.toLocaleString()],
                  ['Output', tokens.total_output.toLocaleString()],
                  ['Cached', tokens.total_cached.toLocaleString()],
                  ['Turns', tokens.turns.toLocaleString()],
                ].map(([label, val]) => (
                  <div key={label} className="space-y-1">
                    <div className="text-[10px] uppercase tracking-widest" style={{ color: 'rgba(232,228,221,0.3)' }}>{label}</div>
                    <div className="text-sm value-mono" style={{ color: '#e8e4dd' }}>{val}</div>
                  </div>
                ))}
              </div>
              {Object.keys(tokens.by_label).length > 0 && (
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b" style={{ borderColor: 'rgba(232,228,221,0.06)' }}>
                      <th className="text-left px-4 py-2.5" style={{ color: 'rgba(232,228,221,0.35)' }}>Call type</th>
                      <th className="text-right px-4 py-2.5 value-mono" style={{ color: 'rgba(232,228,221,0.35)' }}>Input</th>
                      <th className="text-right px-4 py-2.5 value-mono" style={{ color: 'rgba(232,228,221,0.35)' }}>Output</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(tokens.by_label).map(([label, call]) => (
                      <tr key={label} className="border-t" style={{ borderColor: 'rgba(232,228,221,0.04)' }}>
                        <td className="px-4 py-2" style={{ color: 'rgba(232,228,221,0.6)' }}>{label}</td>
                        <td className="px-4 py-2 text-right value-mono" style={{ color: 'rgba(232,228,221,0.5)' }}>{call.input.toLocaleString()}</td>
                        <td className="px-4 py-2 text-right value-mono" style={{ color: 'rgba(232,228,221,0.5)' }}>{call.output.toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </section>
        )}
      </div>
    
  )
}
