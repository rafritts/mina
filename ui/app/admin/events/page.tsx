'use client'

import { useEffect, useRef, useState } from 'react'
import { Chip } from '../../components/Chip'
import { Segmented } from '../../components/Segmented'
import { StateNotice } from '../../components/StateNotice'
import { apiFetch, type EventEntry } from '../../lib/api'

const TYPE_FILTERS = ['all', 'activity', 'tool', 'stimulus', 'response'] as const

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
        <Segmented
          ariaLabel="Event type"
          value={filter}
          options={TYPE_FILTERS.map((t) => ({
            value: t,
            label: t.charAt(0).toUpperCase() + t.slice(1),
          }))}
          onChange={setFilter}
        />
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
          <StateNotice
            bare
            title={filter === 'all' ? 'No events yet' : `No ${filter} events`}
            detail="The log fills as the sim handles stimuli, tools, and replies."
          />
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
                <Chip className="shrink-0 mt-0.5">{ev.type}</Chip>
                <div className="flex-1 min-w-0 space-y-1">
                  <p className="text-xs text-secondary truncate m-0">{eventText(ev)}</p>
                  {ev.deltas && Object.keys(ev.deltas).length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {Object.entries(ev.deltas)
                        .slice(0, 5)
                        .map(([k, v]) => (
                          <Chip key={k} tone={v > 0 ? 'success' : 'error'} className="mono">
                            {v > 0 ? '+' : ''}
                            {v.toFixed(1)} {k}
                          </Chip>
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
