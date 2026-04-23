'use client'

import { useState } from 'react'
import { useHistoryPoller } from '../../lib/hooks/useHistoryPoller'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import AuthGate from '../../components/AuthGate'

const CHART_GROUPS: { label: string; fields: string[]; colors: string[] }[] = [
  { label: 'Monoamines', fields: ['dopamine', 'serotonin', 'norepinephrine'], colors: ['#f59e0b', '#34d399', '#60a5fa'] },
  { label: 'Stress', fields: ['cortisol', 'norepinephrine'], colors: ['#f87171', '#60a5fa'] },
  { label: 'Derived', fields: ['energy', 'hedonic_tone', 'mood_valence', 'anxiety'], colors: ['#f59e0b', '#a78bfa', '#34d399', '#f87171'] },
  { label: 'Social', fields: ['oxytocin', 'social_warmth'], colors: ['#f472b6', '#fb7185'] },
]

const TIME_RANGES = [
  { label: '1h', hours: 1 },
  { label: '6h', hours: 6 },
  { label: '24h', hours: 24 },
  { label: '7d', hours: 168 },
]

export default function HistoryPage() {
  const [hours, setHours] = useState(6)
  const [activeGroup, setActiveGroup] = useState(0)
  const { history, loading } = useHistoryPoller(hours)

  const group = CHART_GROUPS[activeGroup]

  const chartData = history.map(snap => {
    const point: Record<string, number> = { ts: snap.ts * 1000 }
    group.fields.forEach(f => {
      const val = snap.chemicals[f] ?? snap.second_order?.[f] ?? snap.third_order?.[f]
      if (val !== undefined) point[f] = val
    })
    return point
  })

  return (
    <AuthGate>
      <div className="p-6 space-y-6 max-w-5xl">
        {/* Controls */}
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex gap-1">
            {TIME_RANGES.map(({ label, hours: h }) => (
              <button
                key={h}
                onClick={() => setHours(h)}
                className="px-3 py-1.5 text-xs rounded border transition-colors"
                style={{
                  borderColor: hours === h ? 'rgba(232,228,221,0.3)' : 'rgba(232,228,221,0.1)',
                  color: hours === h ? '#e8e4dd' : 'rgba(232,228,221,0.35)',
                  background: hours === h ? 'rgba(232,228,221,0.08)' : 'transparent',
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="flex gap-1 ml-4">
            {CHART_GROUPS.map(({ label }, i) => (
              <button
                key={label}
                onClick={() => setActiveGroup(i)}
                className="px-3 py-1.5 text-xs rounded border transition-colors"
                style={{
                  borderColor: activeGroup === i ? 'rgba(232,228,221,0.3)' : 'rgba(232,228,221,0.1)',
                  color: activeGroup === i ? '#e8e4dd' : 'rgba(232,228,221,0.35)',
                  background: activeGroup === i ? 'rgba(232,228,221,0.08)' : 'transparent',
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Chart */}
        <div className="gallery-card rounded-xl p-6">
          {loading ? (
            <div className="h-64 flex items-center justify-center text-xs value-mono" style={{ color: 'rgba(232,228,221,0.2)' }}>
              loading...
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={chartData}>
                <XAxis
                  dataKey="ts"
                  type="number"
                  domain={['auto', 'auto']}
                  tickFormatter={(v: number) => {
                    const d = new Date(v)
                    if (hours <= 1) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                    if (hours <= 24) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                    return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
                  }}
                  stroke="rgba(232,228,221,0.15)"
                  tick={{ fill: 'rgba(232,228,221,0.35)', fontSize: 11, fontFamily: 'var(--font-geist-mono)' }}
                  scale="time"
                />
                <YAxis
                  stroke="rgba(232,228,221,0.15)"
                  tick={{ fill: 'rgba(232,228,221,0.35)', fontSize: 11, fontFamily: 'var(--font-geist-mono)' }}
                />
                <Tooltip
                  contentStyle={{
                    background: '#0d0d12',
                    border: '1px solid rgba(232,228,221,0.1)',
                    borderRadius: 8,
                    fontSize: 12,
                    fontFamily: 'var(--font-geist-mono)',
                  }}
                  labelStyle={{ color: 'rgba(232,228,221,0.5)' }}
                  labelFormatter={(v) => new Date(Number(v)).toLocaleString()}
                />
                <Legend wrapperStyle={{ fontSize: 12, fontFamily: 'var(--font-geist-sans)', color: 'rgba(232,228,221,0.5)' }} />
                {group.fields.map((f, i) => (
                  <Line
                    key={f}
                    type="monotone"
                    dataKey={f}
                    stroke={group.colors[i]}
                    strokeWidth={1.5}
                    dot={false}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </AuthGate>
  )
}
