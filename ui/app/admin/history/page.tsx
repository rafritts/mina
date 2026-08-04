'use client'

import { useState } from 'react'
import { useHistoryPoller } from '../../lib/hooks/useHistoryPoller'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'

const CHART_GROUPS: { label: string; fields: string[]; colors: string[] }[] = [
  {
    label: 'Monoamines',
    fields: ['dopamine', 'serotonin', 'norepinephrine'],
    colors: ['#d4a574', '#5dcf9b', '#7aafef'],
  },
  {
    label: 'Stress',
    fields: ['cortisol', 'norepinephrine'],
    colors: ['#e87880', '#7aafef'],
  },
  {
    label: 'Derived',
    fields: ['energy', 'hedonic_tone', 'mood_valence', 'anxiety'],
    colors: ['#d4a574', '#b39df0', '#5dcf9b', '#e87880'],
  },
  {
    label: 'Social',
    fields: ['oxytocin', 'social_warmth'],
    colors: ['#e878a0', '#fb7185'],
  },
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

  const chartData = history.map((snap) => {
    const point: Record<string, number> = { ts: snap.ts * 1000 }
    group.fields.forEach((f) => {
      const val = snap.chemicals[f] ?? snap.second_order?.[f] ?? snap.third_order?.[f]
      if (val !== undefined) point[f] = val
    })
    return point
  })

  return (
    <div className="page" style={{ maxWidth: '56rem' }}>
      <h1 className="page-title">History</h1>
      <p className="page-desc">Chemical and derived-state trajectories over the recent window.</p>

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <div className="flex gap-1">
          {TIME_RANGES.map(({ label, hours: h }) => (
            <button
              key={h}
              type="button"
              className="btn btn-sm"
              style={
                hours === h
                  ? {
                      background: 'var(--accent-dim)',
                      border: '1px solid var(--accent-border)',
                      color: 'var(--accent-bright)',
                    }
                  : { border: '1px solid var(--border)' }
              }
              onClick={() => setHours(h)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="flex gap-1 flex-wrap">
          {CHART_GROUPS.map(({ label }, i) => (
            <button
              key={label}
              type="button"
              className="btn btn-sm"
              style={
                activeGroup === i
                  ? {
                      background: 'var(--surface-2)',
                      border: '1px solid var(--border-strong)',
                      color: 'var(--text)',
                    }
                  : { border: '1px solid var(--border)' }
              }
              onClick={() => setActiveGroup(i)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="surface-raised p-4 sm:p-6">
        {loading ? (
          <div className="h-64 flex items-center justify-center text-xs mono text-faint">
            Loading…
          </div>
        ) : chartData.length === 0 ? (
          <div className="h-64 flex items-center justify-center text-xs mono text-faint">
            No history samples yet
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
                  if (hours <= 24) {
                    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                  }
                  return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
                }}
                stroke="var(--border)"
                tick={{ fill: 'var(--text-muted)', fontSize: 11, fontFamily: 'var(--font-geist-mono)' }}
                scale="time"
              />
              <YAxis
                stroke="var(--border)"
                tick={{ fill: 'var(--text-muted)', fontSize: 11, fontFamily: 'var(--font-geist-mono)' }}
              />
              <Tooltip
                contentStyle={{
                  background: 'var(--bg-elevated)',
                  border: '1px solid var(--border)',
                  borderRadius: 8,
                  fontSize: 12,
                  fontFamily: 'var(--font-geist-mono)',
                }}
                labelStyle={{ color: 'var(--text-muted)' }}
                labelFormatter={(v) => new Date(Number(v)).toLocaleString()}
              />
              <Legend
                wrapperStyle={{
                  fontSize: 12,
                  color: 'var(--text-muted)',
                }}
              />
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
  )
}
