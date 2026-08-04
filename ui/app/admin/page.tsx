'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useStatePoller } from '../lib/hooks/useStatePoller'
import { apiFetch, type EventEntry } from '../lib/api'
import { getLabel } from '../lib/labels'
import {
  FIELD_LABELS,
  SECOND_ORDER,
  THIRD_ORDER,
  presenceLabel,
} from '../lib/presence'
import { cn } from '@/lib/utils'

function chipClass(color?: string): string {
  if (color === 'success') return 'chip chip-success'
  if (color === 'warning') return 'chip chip-warning'
  if (color === 'error') return 'chip chip-error'
  if (color === 'info') return 'chip chip-info'
  return 'chip'
}

function MetricCard({ field, value }: { field: string; value: number }) {
  const entry = getLabel(field, value)
  return (
    <div className="surface p-3.5 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <span className="label">{FIELD_LABELS[field] ?? field.replace(/_/g, ' ')}</span>
        {entry && <span className={chipClass(entry.color)}>{entry.name}</span>}
      </div>
      <div className="text-2xl font-light mono tracking-tight">{Math.round(value)}</div>
      <div className="metric-track">
        <div className="metric-fill" style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
      </div>
    </div>
  )
}

function formatTs(ts: number): string {
  const diff = Date.now() - ts * 1000
  if (diff < 60_000) return 'just now'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`
  return new Date(ts * 1000).toLocaleDateString()
}

export default function OverviewPage() {
  const { state, error } = useStatePoller()
  const [events, setEvents] = useState<EventEntry[]>([])

  useEffect(() => {
    apiFetch<EventEntry[]>('/api/events?limit=8')
      .then(setEvents)
      .catch(() => {})
  }, [])

  if (!state) {
    return (
      <div className="page">
        <p className="mono text-sm text-muted m-0">
          {error ?? 'Connecting to sim…'}
        </p>
      </div>
    )
  }

  return (
    <div className="page">
      <h1 className="page-title">{presenceLabel(state)}</h1>
      <p className="page-desc">
        Live overview of felt state and recent activity. Adjust chemistry from Chat → Control,
        or open the Chemistry lab page for full editors.
      </p>

      <section className="section">
        <div className="label section-head">Felt state</div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
          {SECOND_ORDER.map((field) => (
            <MetricCard
              key={field}
              field={field}
              value={state.second_order[field] ?? 50}
            />
          ))}
        </div>
      </section>

      <section className="section">
        <div className="label section-head">Signals</div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
          {THIRD_ORDER.map((field) => (
            <MetricCard
              key={field}
              field={field}
              value={state.third_order[field] ?? 0}
            />
          ))}
        </div>
      </section>

      <section className="section">
        <div className="flex items-center justify-between section-head">
          <div className="label m-0">Recent events</div>
          <Link href="/admin/events" className="text-[12px] text-muted no-underline hover:text-secondary">
            View all
          </Link>
        </div>
        <div className="surface divide-y divide-[var(--border-subtle)] overflow-hidden">
          {events.length === 0 && (
            <p className="px-3.5 py-3 text-xs mono text-faint m-0">No recent events</p>
          )}
          {events.map((ev, i) => (
            <div key={i} className="px-3.5 py-2.5 flex items-center gap-2.5">
              <span className={cn('chip shrink-0', ev.type === 'response' && 'chip-success')}>
                {ev.type}
              </span>
              <p className="flex-1 min-w-0 text-xs text-secondary truncate m-0">
                {ev.preview ?? ev.result ?? ev.tool ?? '—'}
              </p>
              <span className="mono text-[11px] text-faint shrink-0">
                {formatTs(ev.ts)}
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
