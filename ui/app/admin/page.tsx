'use client'

import { useStatePoller } from '../lib/hooks/useStatePoller'
import { apiFetch } from '../lib/api'
import { DerivedCard } from '../components/metrics/DerivedCard'
import { useEffect, useState } from 'react'
import type { EventEntry } from '../lib/api'

const SECOND_ORDER = ['energy', 'cognitive_clarity', 'hedonic_tone', 'social_warmth', 'arousal', 'mood_valence']
const THIRD_ORDER = ['anxiety', 'depression', 'boredom', 'loneliness', 'flow', 'physical_distress', 'craving']

function formatTs(ts: number): string {
  const d = new Date(ts * 1000)
  const diff = Date.now() - d.getTime()
  if (diff < 60000) return 'just now'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
  return d.toLocaleDateString()
}

const EVENT_TYPE_COLORS: Record<string, string> = {
  stimulus: 'text-blue-400 border-blue-500/30 bg-blue-500/10',
  response: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10',
  activity: 'text-amber-400 border-amber-500/30 bg-amber-500/10',
  tool: 'text-purple-400 border-purple-500/30 bg-purple-500/10',
}

export default function OverviewPage() {
  const { state } = useStatePoller()
  const [events, setEvents] = useState<EventEntry[]>([])

  useEffect(() => {
    apiFetch<EventEntry[]>('/api/events?limit=5').then(setEvents).catch(() => {})
  }, [])

  if (!state) {
    return (
      
        <div className="p-8 text-center" style={{ color: 'rgba(232,228,221,0.3)' }}>
          <div className="value-mono text-sm">connecting...</div>
        </div>
      
    )
  }

  return (
    
      <div className="p-8 mx-auto space-y-8 max-w-6xl">
        {/* Second-order metrics */}
        <section>
          <h2 className="text-xs uppercase tracking-widest mb-4" style={{ color: 'rgba(232,228,221,0.3)' }}>State</h2>
          <div className="grid grid-cols-3 gap-3">
            {SECOND_ORDER.map(field => (
              <DerivedCard key={field} field={field} value={state.second_order[field] ?? 50} size="large" />
            ))}
          </div>
        </section>

        {/* Third-order metrics */}
        <section>
          <h2 className="text-xs uppercase tracking-widest mb-4" style={{ color: 'rgba(232,228,221,0.3)' }}>Derived Signals</h2>
          <div className="grid grid-cols-4 gap-2.5">
            {THIRD_ORDER.map(field => (
              <DerivedCard key={field} field={field} value={state.third_order[field] ?? 0} size="small" />
            ))}
          </div>
        </section>

        {/* Recent events */}
        <section>
          <h2 className="text-xs uppercase tracking-widest mb-4" style={{ color: 'rgba(232,228,221,0.3)' }}>Recent Events</h2>
          <div className="gallery-card rounded-lg divide-y" style={{ borderColor: 'rgba(232,228,221,0.06)' }}>
            {events.length === 0 && (
              <p className="p-4 text-xs value-mono" style={{ color: 'rgba(232,228,221,0.2)' }}>No recent events</p>
            )}
            {events.map((ev, i) => (
              <div key={i} className="px-4 py-3 flex items-start gap-3">
                <span className={`text-[10px] px-1.5 py-0.5 rounded border mt-0.5 flex-shrink-0 ${EVENT_TYPE_COLORS[ev.type] ?? EVENT_TYPE_COLORS.activity}`}>
                  {ev.type}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-xs truncate" style={{ color: 'rgba(232,228,221,0.6)' }}>{ev.content}</p>
                </div>
                <span className="text-xs value-mono flex-shrink-0" style={{ color: 'rgba(232,228,221,0.25)' }}>{formatTs(ev.ts)}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    
  )
}
