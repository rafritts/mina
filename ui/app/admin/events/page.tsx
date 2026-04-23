'use client'

import { useEffect, useRef, useState } from 'react'
import { apiFetch } from '../../lib/api'
import type { EventEntry } from '../../lib/api'
import AuthGate from '../../components/AuthGate'

const TYPE_COLORS: Record<string, string> = {
  stimulus: 'text-blue-400 border-blue-500/30 bg-blue-500/10',
  response: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10',
  activity: 'text-amber-400 border-amber-500/30 bg-amber-500/10',
  tool: 'text-purple-400 border-purple-500/30 bg-purple-500/10',
}

const TYPE_FILTERS = ['all', 'stimulus', 'response', 'activity', 'tool']

function formatTs(ts: number): { relative: string; absolute: string } {
  const d = new Date(ts * 1000)
  const diff = Date.now() - d.getTime()
  let relative: string
  if (diff < 60000) relative = 'just now'
  else if (diff < 3600000) relative = `${Math.floor(diff / 60000)}m ago`
  else if (diff < 86400000) relative = `${Math.floor(diff / 3600000)}h ago`
  else relative = `${Math.floor(diff / 86400000)}d ago`
  return { relative, absolute: d.toLocaleString() }
}

export default function EventsPage() {
  const [events, setEvents] = useState<EventEntry[]>([])
  const [filter, setFilter] = useState('all')
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = async (limit = 100) => {
    try {
      const data = await apiFetch<EventEntry[]>(`/api/events?limit=${limit}`)
      setEvents(data)
    } catch {}
  }

  useEffect(() => {
    load()
    if (autoRefresh) {
      timerRef.current = setInterval(() => load(), 5000)
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [autoRefresh])

  const visible = filter === 'all' ? events : events.filter(e => e.type === filter)

  const toggleExpand = (i: number) => {
    setExpanded(s => {
      const n = new Set(s)
      n.has(i) ? n.delete(i) : n.add(i)
      return n
    })
  }

  return (
    <AuthGate>
      <div className="p-6 max-w-4xl space-y-4">
        {/* Controls */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex gap-1">
            {TYPE_FILTERS.map(t => (
              <button
                key={t}
                onClick={() => setFilter(t)}
                className="px-3 py-1.5 text-xs rounded border capitalize transition-colors"
                style={{
                  borderColor: filter === t ? 'rgba(232,228,221,0.3)' : 'rgba(232,228,221,0.1)',
                  color: filter === t ? '#e8e4dd' : 'rgba(232,228,221,0.35)',
                  background: filter === t ? 'rgba(232,228,221,0.08)' : 'transparent',
                }}
              >
                {t}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 text-xs cursor-pointer" style={{ color: 'rgba(232,228,221,0.4)' }}>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={e => setAutoRefresh(e.target.checked)}
              className="accent-zinc-400"
            />
            Auto-refresh
          </label>
        </div>

        {/* Event list */}
        <div className="gallery-card rounded-lg divide-y" style={{ borderColor: 'rgba(232,228,221,0.04)' }}>
          {visible.length === 0 && (
            <p className="p-4 text-xs value-mono" style={{ color: 'rgba(232,228,221,0.2)' }}>No events</p>
          )}
          {visible.map((ev, i) => {
            const isOpen = expanded.has(i)
            const { relative, absolute } = formatTs(ev.ts)
            return (
              <div
                key={i}
                className="px-4 py-3 cursor-pointer transition-colors"
                style={{ background: isOpen ? 'rgba(232,228,221,0.02)' : 'transparent' }}
                onClick={() => toggleExpand(i)}
              >
                <div className="flex items-start gap-3">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded border mt-0.5 flex-shrink-0 ${TYPE_COLORS[ev.type] ?? TYPE_COLORS.activity}`}>
                    {ev.type}
                  </span>
                  <div className="flex-1 min-w-0 space-y-1">
                    <p className="text-xs truncate" style={{ color: 'rgba(232,228,221,0.7)' }}>{ev.content}</p>
                    {ev.deltas && Object.keys(ev.deltas).length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {Object.entries(ev.deltas).slice(0, 5).map(([k, v]) => (
                          <span
                            key={k}
                            className="text-[10px] px-1.5 py-0.5 rounded value-mono"
                            style={{
                              background: v > 0 ? 'rgba(52,211,153,0.1)' : 'rgba(248,113,113,0.1)',
                              color: v > 0 ? '#34d399' : '#f87171',
                            }}
                          >
                            {v > 0 ? '+' : ''}{v.toFixed(1)} {k}
                          </span>
                        ))}
                      </div>
                    )}
                    {isOpen && (
                      <p className="text-xs whitespace-pre-wrap mt-2 pt-2 border-t" style={{ color: 'rgba(232,228,221,0.5)', borderColor: 'rgba(232,228,221,0.06)' }}>
                        {ev.content}
                      </p>
                    )}
                  </div>
                  <div className="text-right flex-shrink-0">
                    <span className="text-xs value-mono block" style={{ color: 'rgba(232,228,221,0.25)' }} title={absolute}>{relative}</span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        <button
          onClick={() => load(500)}
          className="text-xs px-4 py-2 rounded border transition-colors"
          style={{ borderColor: 'rgba(232,228,221,0.1)', color: 'rgba(232,228,221,0.4)' }}
        >
          Load more
        </button>
      </div>
    </AuthGate>
  )
}
