'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useStatePoller } from '../lib/hooks/useStatePoller'
import { apiFetch, type EventEntry } from '../lib/api'
import { SECOND_ORDER, THIRD_ORDER, presenceLabel } from '../lib/presence'
import { Chip } from '../components/Chip'
import { FeltMetricList } from '../components/presence/FeltMetricList'
import { SleepStatusCard } from '../components/presence/SleepStatusCard'
import { StateNotice } from '../components/StateNotice'

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
        <StateNotice
          tone={error ? 'error' : 'loading'}
          title={error ? 'Can’t reach the sim' : 'Connecting'}
          detail={error ?? 'Waiting for chemistry state. Overview fills in as soon as the sim answers.'}
        />
      </div>
    )
  }

  return (
    <div className="page">
      <h1 className="page-title">{presenceLabel(state)}</h1>
      <p className="page-desc">
        Felt state, signals, and recent events. The latest free-time session is on the status
        pill. Chemistry editors are on the Chemistry page.
      </p>

      <section className="section">
        <div className="label section-head">Sleep</div>
        <SleepStatusCard state={state} density="page" />
      </section>

      <section className="section">
        <div className="label section-head">Felt state</div>
        <FeltMetricList
          fields={SECOND_ORDER}
          values={state.second_order}
          variant="card"
          emptyValue={50}
        />
      </section>

      <section className="section">
        <div className="label section-head">Signals</div>
        <FeltMetricList
          fields={THIRD_ORDER}
          values={state.third_order}
          variant="card"
          emptyValue={0}
        />
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
            <StateNotice
              bare
              compact
              title="No recent events"
              detail="Stimulus, replies, and tool calls land here after a turn."
            />
          )}
          {events.map((ev, i) => (
            <div key={i} className="px-3.5 py-2.5 flex items-center gap-2.5">
              <Chip tone={ev.type === 'response' ? 'success' : 'neutral'} className="shrink-0">
                {ev.type}
              </Chip>
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
