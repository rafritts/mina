'use client'

import { useEffect, useRef, useState } from 'react'
import { apiFetch, type EventEntry } from '../../lib/api'

const TYPE_FILTERS = ['all', 'stimulus', 'response', 'activity', 'tool'] as const

function eventText(ev: EventEntry): string {
  if (ev.preview) return ev.preview
  if (ev.result) return ev.result
  if (ev.tool) return ev.tool
  return '—'
}

function formatTs(ts: number): { relative: string; absolute: string } {
  const d = new Date(ts * 1000)
  const diff = Date.now() - d.getTime()
  let relative: string
  if (diff < 60_000) relative = 'just now'
  else if (diff < 3_600_000) relative = `${Math.floor(diff / 60_000)}m ago`
  else if (diff < 86_400_000) relative = `${Math.floor(diff / 3_600_000)}h ago`
  else relative = `${Math.floor(diff / 86_400_000)}d ago`
  return { relative, absolute: d.toLocaleString() }
}

export default function EventsPage() {
  const [events, setEvents] = useState<EventEntry[]>([])
  const [filter, setFilter] = useState<string>('all')
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = async (limit = 100) => {
    try {
      setEvents(await apiFetch<EventEntry[]>(`/api/events?limit=${limit}`))
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    void load()
    if (autoRefresh) {
      timerRef.current = setInterval(() => void load(), 5000)
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [autoRefresh])

  const visible = filter === 'all' ? events : events.filter((e) => e.type === filter)

  return (
    <div className="page">
      <h1 className="page-title">Events</h1>
      <p className="page-desc">Stimulus, response, activity, and tool log from the sim process.</p>

      <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
        <div className="flex gap-1 flex-wrap">
          {TYPE_FILTERS.map((t) => (
            <button
              key={t}
              type="button"
              className="btn btn-sm capitalize"
              style={
                filter === t
                  ? {
                      background: 'var(--accent-dim)',
                      border: '1px solid var(--accent-border)',
                      color: 'var(--accent-bright)',
                    }
                  : { border: '1px solid var(--border)' }
              }
              onClick={() => setFilter(t)}
            >
              {t}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-xs text-muted cursor-pointer">
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
          />
          Auto-refresh
        </label>
      </div>

      <div className="surface divide-y divide-[var(--border-subtle)]">
        {visible.length === 0 && (
          <p className="p-4 text-xs mono text-faint m-0">No events</p>
        )}
        {visible.map((ev, i) => {
          const isOpen = expanded.has(i)
          const { relative, absolute } = formatTs(ev.ts)
          return (
            <button
              key={i}
              type="button"
              className="w-full text-left px-4 py-3 border-0 bg-transparent cursor-pointer transition-colors hover:bg-[var(--surface)]"
              onClick={() =>
                setExpanded((s) => {
                  const n = new Set(s)
                  if (n.has(i)) n.delete(i)
                  else n.add(i)
                  return n
                })
              }
            >
              <div className="flex items-start gap-3">
                <span className="chip shrink-0 mt-0.5">{ev.type}</span>
                <div className="flex-1 min-w-0 space-y-1">
                  <p className="text-xs text-secondary truncate m-0">{eventText(ev)}</p>
                  {ev.deltas && Object.keys(ev.deltas).length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {Object.entries(ev.deltas)
                        .slice(0, 5)
                        .map(([k, v]) => (
                          <span
                            key={k}
                            className="chip mono"
                            style={{
                              color: v > 0 ? 'var(--success)' : 'var(--danger)',
                              borderColor:
                                v > 0 ? 'var(--success-border)' : 'var(--danger-border)',
                            }}
                          >
                            {v > 0 ? '+' : ''}
                            {v.toFixed(1)} {k}
                          </span>
                        ))}
                    </div>
                  )}
                  {isOpen && (
                    <p className="text-xs whitespace-pre-wrap mt-2 pt-2 border-t border-[var(--border-subtle)] text-muted m-0">
                      {eventText(ev)}
                    </p>
                  )}
                </div>
                <span className="mono text-[11px] text-faint shrink-0" title={absolute}>
                  {relative}
                </span>
              </div>
            </button>
          )
        })}
      </div>

      <button type="button" className="btn btn-soft btn-sm mt-4" onClick={() => void load(500)}>
        Load more
      </button>
    </div>
  )
}
