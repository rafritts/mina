'use client'

import { useEffect, useState } from 'react'
import { StateNotice } from '../../components/StateNotice'
import { apiFetch, type TokenStats } from '../../lib/api'
import { BUILD_INFO } from '../../lib/build-info'

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
    <div className="page">
      <h1 className="page-title">System</h1>
      <p className="page-desc">
        Runtime health, token usage, and build identity. Heartbeat status is on this page. Run a
        heartbeat, reset chemistry, or erase history from the header Tools sheet.
      </p>

      <section className="section">
        <div className="label section-head">Build</div>
        <div className="surface p-4 space-y-2 text-xs">
          <div className="flex justify-between gap-3">
            <span className="text-muted">Build id</span>
            <span className="mono text-secondary">{BUILD_INFO.id}</span>
          </div>
          <div className="flex justify-between gap-3">
            <span className="text-muted">Git</span>
            <span className="mono text-secondary">{BUILD_INFO.git}</span>
          </div>
          <div className="flex justify-between gap-3">
            <span className="text-muted">Built at</span>
            <span className="mono text-secondary">{BUILD_INFO.builtAt}</span>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="label section-head">Billing</div>
        <div className="surface p-4 space-y-3">
          {billing ? (
            <>
              <div className="flex justify-between text-xs">
                <span className="text-muted">Used</span>
                <span className="mono">
                  ${billing.used.toFixed(2)} / ${billing.cap.toFixed(2)}
                </span>
              </div>
              <div className="metric-track" style={{ height: 6 }}>
                <div
                  className="metric-fill"
                  style={{
                    width: `${billingPct}%`,
                    background:
                      billingPct > 80
                        ? 'var(--danger)'
                        : billingPct > 60
                          ? 'var(--warning)'
                          : 'var(--success)',
                  }}
                />
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-faint">{billingPct.toFixed(1)}% used</span>
                <span className="mono text-muted">
                  ${billing.remaining.toFixed(2)} remaining
                </span>
              </div>
            </>
          ) : (
            <StateNotice
              bare
              compact
              title="No billing data"
              detail="The cap and spend appear when the sim exposes /api/billing."
            />
          )}
        </div>
      </section>

      {heartbeatStatus && (
        <section className="section">
          <div className="label section-head">Heartbeat</div>
          <div className="surface p-4 space-y-2 text-xs">
            <div className="flex justify-between">
              <span className="text-muted">Last run</span>
              <span className="mono text-secondary">
                {heartbeatStatus.last_run
                  ? new Date(heartbeatStatus.last_run * 1000).toLocaleString()
                  : 'never'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted">Running</span>
              <span className="mono text-secondary">
                {heartbeatStatus.is_running || heartbeatStatus.running ? 'yes' : 'no'}
              </span>
            </div>
          </div>
        </section>
      )}

      {tokens && (
        <section className="section">
          <div className="label section-head">Token usage</div>
          <div className="surface overflow-hidden">
            <div className="px-4 py-3 grid grid-cols-2 sm:grid-cols-4 gap-4 border-b border-[var(--border-subtle)]">
              {[
                ['Input', tokens.total_input.toLocaleString()],
                ['Output', tokens.total_output.toLocaleString()],
                ['Cached', tokens.total_cached.toLocaleString()],
                ['Turns', tokens.turns.toLocaleString()],
              ].map(([label, val]) => (
                <div key={label} className="space-y-1">
                  <div className="label">{label}</div>
                  <div className="text-sm mono">{val}</div>
                </div>
              ))}
            </div>
            {Object.keys(tokens.by_label).length > 0 && (
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-[var(--border-subtle)]">
                    <th className="text-left px-4 py-2.5 text-muted font-medium">Call type</th>
                    <th className="text-right px-4 py-2.5 text-muted font-medium mono">Input</th>
                    <th className="text-right px-4 py-2.5 text-muted font-medium mono">Output</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(tokens.by_label).map(([label, call]) => (
                    <tr key={label} className="border-t border-[var(--border-subtle)]">
                      <td className="px-4 py-2 text-secondary">{label}</td>
                      <td className="px-4 py-2 text-right mono text-muted">
                        {call.input.toLocaleString()}
                      </td>
                      <td className="px-4 py-2 text-right mono text-muted">
                        {call.output.toLocaleString()}
                      </td>
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
