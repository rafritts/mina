'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { apiFetch, type StateData } from '../lib/api'
import { useStatePoller } from '../lib/hooks/useStatePoller'
import { PRESETS } from '../lib/presets'
import { getLabel, COLOR_CLASSES, DISPLAY_RANGES } from '../lib/labels'
import { BUILD_INFO } from '../lib/build-info'

type Tab = 'presence' | 'chemistry' | 'instruments'

const SECOND_ORDER = [
  'energy',
  'mood_valence',
  'social_warmth',
  'cognitive_clarity',
  'arousal',
  'hedonic_tone',
] as const

const THIRD_ORDER = [
  'anxiety',
  'depression',
  'boredom',
  'loneliness',
  'flow',
  'physical_distress',
] as const

const CHEM_GROUPS: { label: string; chemicals: string[] }[] = [
  { label: 'Monoamines', chemicals: ['dopamine', 'serotonin', 'norepinephrine'] },
  { label: 'Bonding', chemicals: ['oxytocin', 'endorphins'] },
  { label: 'Stress', chemicals: ['cortisol', 'epinephrine'] },
  { label: 'Cognition', chemicals: ['acetylcholine', 'glutamate', 'gaba'] },
  { label: 'Body', chemicals: ['adenosine', 'melatonin', 'glucose', 'hydration', 'sleep_pressure'] },
]

const FIELD_LABELS: Record<string, string> = {
  energy: 'Energy',
  cognitive_clarity: 'Clarity',
  hedonic_tone: 'Hedonic',
  social_warmth: 'Warmth',
  arousal: 'Arousal',
  mood_valence: 'Mood',
  anxiety: 'Anxiety',
  depression: 'Low mood',
  boredom: 'Boredom',
  loneliness: 'Loneliness',
  flow: 'Flow',
  physical_distress: 'Distress',
}

function dominantLabel(state: StateData): string {
  if (state.sleeping) return 'Sleeping'
  const so = state.second_order ?? {}
  const to = state.third_order ?? {}
  if ((to.anxiety ?? 0) > 65) return 'Anxious'
  if ((so.energy ?? 50) > 70 && (so.mood_valence ?? 50) > 65) return 'Elevated'
  if ((so.cognitive_clarity ?? 50) > 65 && (so.energy ?? 50) > 55) return 'Focused'
  if ((so.social_warmth ?? 50) > 65) return 'Warm'
  if ((so.mood_valence ?? 50) < 35) return 'Low'
  if ((so.energy ?? 50) < 30) return 'Depleted'
  return 'Present'
}

function MetricBar({
  label,
  value,
  field,
}: {
  label: string
  value: number
  field: string
}) {
  const entry = getLabel(field, value)
  const colorCls = entry ? COLOR_CLASSES[entry.color] : COLOR_CLASSES.neutral
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px]" style={{ color: 'rgba(232,228,221,0.5)' }}>
          {label}
        </span>
        <div className="flex items-center gap-1.5">
          {entry && (
            <span className={`text-[9px] px-1 py-0.5 rounded border ${colorCls.badge}`}>
              {entry.name}
            </span>
          )}
          <span className="text-[11px] value-mono w-7 text-right" style={{ color: 'rgba(232,228,221,0.7)' }}>
            {Math.round(value)}
          </span>
        </div>
      </div>
      <div className="h-1 rounded-full overflow-hidden" style={{ background: 'rgba(232,228,221,0.07)' }}>
        <div
          className={`h-full rounded-full transition-all duration-700 ${colorCls.bar}`}
          style={{ width: `${Math.min(100, Math.max(0, value))}%`, opacity: 0.75 }}
        />
      </div>
    </div>
  )
}

function ChemRow({
  field,
  entry,
  pending,
  onPending,
  onSave,
  saving,
}: {
  field: string
  entry: { value: number; unit: string; normalized: number; label: string }
  pending: number | undefined
  onPending: (v: number) => void
  onSave: () => void
  saving: boolean
}) {
  const value = pending ?? entry.value
  const range = DISPLAY_RANGES[field]
  const min = range?.min ?? 0
  const max = range?.max ?? Math.max(entry.value * 3, 1)
  const labelEntry = getLabel(field, value)
  const colorCls = labelEntry ? COLOR_CLASSES[labelEntry.color] : COLOR_CLASSES.neutral
  const dirty = pending !== undefined

  return (
    <div className="py-2.5 space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] capitalize" style={{ color: 'rgba(232,228,221,0.55)' }}>
          {field.replace(/_/g, ' ')}
        </span>
        <div className="flex items-center gap-1.5">
          {labelEntry && (
            <span className={`text-[9px] px-1 py-0.5 rounded border ${colorCls.badge}`}>
              {labelEntry.name}
            </span>
          )}
          <span className="text-[11px] value-mono" style={{ color: '#e8e4dd' }}>
            {value < 10 ? value.toFixed(2) : Math.round(value)}
            <span style={{ color: 'rgba(232,228,221,0.3)' }}> {entry.unit}</span>
          </span>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <input
          type="range"
          min={min}
          max={max}
          step={value < 10 ? 0.01 : 1}
          value={value}
          onChange={(e) => onPending(parseFloat(e.target.value))}
          className="flex-1 h-1 accent-amber-400/80"
        />
        {dirty && (
          <button
            type="button"
            onClick={onSave}
            disabled={saving}
            className="text-[10px] px-2 py-1 rounded border transition-colors"
            style={{
              borderColor: 'rgba(251,191,36,0.35)',
              color: 'rgba(251,191,36,0.9)',
              background: 'rgba(251,191,36,0.08)',
            }}
          >
            {saving ? '…' : 'Set'}
          </button>
        )}
      </div>
    </div>
  )
}

export function ControlPane({ streamConnected }: { streamConnected: boolean }) {
  const { state, error, lastUpdate } = useStatePoller(2500)
  const [tab, setTab] = useState<Tab>('presence')
  const [pending, setPending] = useState<Record<string, number>>({})
  const [saving, setSaving] = useState<Record<string, boolean>>({})
  const [toast, setToast] = useState<{ text: string; ok: boolean } | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [advanceHours, setAdvanceHours] = useState('1')

  const showToast = useCallback((text: string, ok: boolean) => {
    setToast({ text, ok })
    setTimeout(() => setToast(null), 2800)
  }, [])

  const saveChem = async (field: string) => {
    if (pending[field] === undefined) return
    setSaving((s) => ({ ...s, [field]: true }))
    try {
      await apiFetch('/api/state', {
        method: 'PATCH',
        body: JSON.stringify({ [field]: pending[field] }),
      })
      setPending((p) => {
        const n = { ...p }
        delete n[field]
        return n
      })
      showToast(`Set ${field}`, true)
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Failed', false)
    } finally {
      setSaving((s) => ({ ...s, [field]: false }))
    }
  }

  const applyPreset = async (name: string, values: Record<string, number>) => {
    setBusy(`preset:${name}`)
    try {
      await apiFetch('/api/state', { method: 'PATCH', body: JSON.stringify(values) })
      showToast(`Applied “${name}”`, true)
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Failed', false)
    } finally {
      setBusy(null)
    }
  }

  const advance = async () => {
    setBusy('advance')
    try {
      await apiFetch('/api/state/advance', {
        method: 'POST',
        body: JSON.stringify({ hours: parseFloat(advanceHours) || 1 }),
      })
      showToast(`Advanced ${advanceHours}h`, true)
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Failed', false)
    } finally {
      setBusy(null)
    }
  }

  const resetBaseline = async () => {
    if (!confirm('Reset chemistry to baseline? Keeps chat & memory.')) return
    setBusy('reset')
    try {
      await apiFetch('/api/state/reset', { method: 'POST' })
      showToast('Reset to baseline', true)
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Failed', false)
    } finally {
      setBusy(null)
    }
  }

  const runHeartbeat = async () => {
    setBusy('heartbeat')
    try {
      const r = await apiFetch<{ ok: boolean; message?: string }>('/api/heartbeat', {
        method: 'POST',
      })
      showToast(r.message ?? 'Heartbeat done', r.ok)
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Failed', false)
    } finally {
      setBusy(null)
    }
  }

  const eraseHistory = async () => {
    if (
      !confirm(
        'Erase chat history?\n\nWipes conversation logs, rolling window, and short-term memory.\nKeeps chemistry, RAG, KAG, relationships.',
      )
    ) {
      return
    }
    setBusy('erase')
    try {
      await apiFetch('/api/conversation/erase', { method: 'POST' })
      showToast('History erased', true)
      window.dispatchEvent(new CustomEvent('mina:erase-chat'))
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Failed', false)
    } finally {
      setBusy(null)
    }
  }

  // Refresh pending when state updates for fields not dirty
  useEffect(() => {
    if (!state) return
  }, [state])

  const tabs: { id: Tab; label: string }[] = [
    { id: 'presence', label: 'Presence' },
    { id: 'chemistry', label: 'Chemistry' },
    { id: 'instruments', label: 'Tools' },
  ]

  return (
    <aside className="flex h-full flex-col min-h-0 border-l" style={{ borderColor: 'rgba(232,228,221,0.07)' }}>
      {/* Header */}
      <div
        className="flex-shrink-0 px-4 py-3 border-b flex items-center justify-between gap-2"
        style={{
          borderColor: 'rgba(232,228,221,0.07)',
          background: 'rgba(6,6,8,0.85)',
        }}
      >
        <div>
          <div className="text-[10px] tracking-[0.2em] uppercase" style={{ color: 'rgba(232,228,221,0.35)' }}>
            Control
          </div>
          <div className="text-sm font-medium mt-0.5" style={{ color: '#f0ebe2' }}>
            {state ? dominantLabel(state) : error ? 'Offline' : '…'}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div
            className="flex items-center gap-1.5 text-[10px] value-mono px-2 py-1 rounded-full border"
            style={{
              borderColor: streamConnected
                ? 'rgba(52,211,153,0.25)'
                : 'rgba(232,228,221,0.1)',
              color: streamConnected
                ? 'rgba(52,211,153,0.85)'
                : 'rgba(232,228,221,0.3)',
            }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{
                background: streamConnected ? 'rgba(52,211,153,0.9)' : 'rgba(232,228,221,0.25)',
                boxShadow: streamConnected ? '0 0 6px rgba(52,211,153,0.7)' : undefined,
              }}
            />
            {streamConnected ? 'live' : '…'}
          </div>
          {state && (
            <div
              className="w-1.5 h-1.5 rounded-full"
              title={state.sleeping ? 'sleeping' : 'awake'}
              style={{
                background: state.sleeping ? 'rgba(96,165,250,0.9)' : 'rgba(52,211,153,0.9)',
                boxShadow: state.sleeping
                  ? '0 0 6px rgba(96,165,250,0.7)'
                  : '0 0 6px rgba(52,211,153,0.7)',
              }}
            />
          )}
        </div>
      </div>

      {/* Tabs */}
      <div
        className="flex-shrink-0 flex border-b px-2"
        style={{ borderColor: 'rgba(232,228,221,0.06)', background: 'rgba(4,4,6,0.5)' }}
      >
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className="flex-1 py-2.5 text-[11px] tracking-wide transition-colors"
            style={{
              color: tab === t.id ? 'rgba(251,191,36,0.95)' : 'rgba(232,228,221,0.35)',
              borderBottom: tab === t.id ? '2px solid rgba(251,191,36,0.5)' : '2px solid transparent',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {!state ? (
          <div className="p-5 text-xs value-mono space-y-2" style={{ color: 'rgba(232,228,221,0.3)' }}>
            <p>{error ?? 'Waiting for sim…'}</p>
            <p className="text-[11px] leading-relaxed" style={{ color: 'rgba(232,228,221,0.22)' }}>
              Start the backend: <code className="value-mono">uv run python main.py</code>
            </p>
          </div>
        ) : tab === 'presence' ? (
          <div className="p-4 space-y-5">
            <section>
              <h3 className="text-[10px] uppercase tracking-[0.16em] mb-3" style={{ color: 'rgba(232,228,221,0.3)' }}>
                Felt state
              </h3>
              <div className="space-y-3">
                {SECOND_ORDER.map((key) => (
                  <MetricBar
                    key={key}
                    field={key}
                    label={FIELD_LABELS[key] ?? key}
                    value={state.second_order[key] ?? 50}
                  />
                ))}
              </div>
            </section>
            <section>
              <h3 className="text-[10px] uppercase tracking-[0.16em] mb-3" style={{ color: 'rgba(232,228,221,0.3)' }}>
                Signals
              </h3>
              <div className="space-y-3">
                {THIRD_ORDER.map((key) => (
                  <MetricBar
                    key={key}
                    field={key}
                    label={FIELD_LABELS[key] ?? key}
                    value={state.third_order[key] ?? 0}
                  />
                ))}
              </div>
            </section>
          </div>
        ) : tab === 'chemistry' ? (
          <div className="p-4 space-y-5">
            {CHEM_GROUPS.map(({ label, chemicals }) => {
              const rows = chemicals
                .map((c) => ({ c, entry: state.chemicals[c] }))
                .filter((x) => x.entry)
              if (!rows.length) return null
              return (
                <section key={label}>
                  <h3 className="text-[10px] uppercase tracking-[0.16em] mb-1" style={{ color: 'rgba(232,228,221,0.3)' }}>
                    {label}
                  </h3>
                  <div className="divide-y" style={{ borderColor: 'rgba(232,228,221,0.05)' }}>
                    {rows.map(({ c, entry }) => (
                      <ChemRow
                        key={c}
                        field={c}
                        entry={entry!}
                        pending={pending[c]}
                        onPending={(v) => setPending((p) => ({ ...p, [c]: v }))}
                        onSave={() => void saveChem(c)}
                        saving={Boolean(saving[c])}
                      />
                    ))}
                  </div>
                </section>
              )
            })}
          </div>
        ) : (
          <div className="p-4 space-y-6">
            {/* Presets */}
            <section>
              <h3 className="text-[10px] uppercase tracking-[0.16em] mb-3" style={{ color: 'rgba(232,228,221,0.3)' }}>
                Mood presets
              </h3>
              <div className="grid grid-cols-2 gap-2">
                {PRESETS.map((preset) => (
                  <button
                    key={preset.name}
                    type="button"
                    disabled={busy === `preset:${preset.name}`}
                    onClick={() => void applyPreset(preset.name, preset.values)}
                    className="text-left rounded-lg px-3 py-2.5 border transition-all hover:border-amber-400/25"
                    style={{
                      background: 'rgba(232,228,221,0.03)',
                      borderColor: 'rgba(232,228,221,0.08)',
                    }}
                  >
                    <div className="text-[12px] font-medium" style={{ color: '#e8e4dd' }}>
                      {preset.name}
                    </div>
                    <div className="text-[10px] mt-0.5 leading-snug" style={{ color: 'rgba(232,228,221,0.35)' }}>
                      {preset.description}
                    </div>
                  </button>
                ))}
              </div>
            </section>

            {/* Time */}
            <section>
              <h3 className="text-[10px] uppercase tracking-[0.16em] mb-3" style={{ color: 'rgba(232,228,221,0.3)' }}>
                Time
              </h3>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  value={advanceHours}
                  onChange={(e) => setAdvanceHours(e.target.value)}
                  min={0.25}
                  max={168}
                  step={0.25}
                  className="w-20 rounded-md border px-2 py-1.5 text-sm value-mono outline-none"
                  style={{
                    background: 'rgba(232,228,221,0.04)',
                    borderColor: 'rgba(232,228,221,0.12)',
                    color: '#e8e4dd',
                  }}
                />
                <span className="text-[11px]" style={{ color: 'rgba(232,228,221,0.4)' }}>
                  hours
                </span>
                <button
                  type="button"
                  onClick={() => void advance()}
                  disabled={busy === 'advance'}
                  className="ml-auto text-[11px] px-3 py-1.5 rounded-md border"
                  style={{
                    borderColor: 'rgba(232,228,221,0.15)',
                    color: 'rgba(232,228,221,0.7)',
                    background: 'rgba(232,228,221,0.05)',
                  }}
                >
                  {busy === 'advance' ? '…' : 'Advance'}
                </button>
              </div>
            </section>

            {/* Actions */}
            <section className="space-y-2">
              <h3 className="text-[10px] uppercase tracking-[0.16em] mb-3" style={{ color: 'rgba(232,228,221,0.3)' }}>
                Actions
              </h3>
              <button
                type="button"
                onClick={() => void runHeartbeat()}
                disabled={busy === 'heartbeat'}
                className="w-full text-left text-[12px] px-3 py-2.5 rounded-lg border transition-colors"
                style={{
                  borderColor: 'rgba(232,228,221,0.1)',
                  color: 'rgba(232,228,221,0.75)',
                  background: 'rgba(232,228,221,0.03)',
                }}
              >
                {busy === 'heartbeat' ? 'Running freetime…' : '▶ Run freetime heartbeat'}
              </button>
              <button
                type="button"
                onClick={() => void resetBaseline()}
                disabled={busy === 'reset'}
                className="w-full text-left text-[12px] px-3 py-2.5 rounded-lg border transition-colors"
                style={{
                  borderColor: 'rgba(248,113,113,0.2)',
                  color: 'rgba(248,113,113,0.8)',
                  background: 'rgba(248,113,113,0.05)',
                }}
              >
                {busy === 'reset' ? 'Resetting…' : 'Reset chemistry to baseline'}
              </button>
              <button
                type="button"
                onClick={() => void eraseHistory()}
                disabled={busy === 'erase'}
                className="w-full text-left text-[12px] px-3 py-2.5 rounded-lg border transition-colors"
                style={{
                  borderColor: 'rgba(248,113,113,0.25)',
                  color: 'rgba(248,113,113,0.75)',
                  background: 'rgba(248,113,113,0.04)',
                }}
              >
                {busy === 'erase' ? 'Erasing…' : 'Erase conversation history'}
              </button>
            </section>

            <section>
              <Link
                href="/admin"
                className="text-[11px] value-mono block"
                style={{ color: 'rgba(232,228,221,0.3)' }}
              >
                Advanced admin →
              </Link>
            </section>
          </div>
        )}
      </div>

      {/* Footer */}
      <div
        className="flex-shrink-0 px-4 py-2 border-t flex items-center justify-between text-[10px] value-mono"
        style={{ borderColor: 'rgba(232,228,221,0.06)', color: 'rgba(232,228,221,0.22)' }}
      >
        <span>
          {lastUpdate
            ? `updated ${Math.max(0, Math.round((Date.now() - lastUpdate) / 1000))}s ago`
            : '—'}
        </span>
        <span title={BUILD_INFO.builtAt}>build {BUILD_INFO.id}</span>
      </div>

      {toast && (
        <div
          className="fixed bottom-6 right-6 z-50 px-3 py-2 rounded-lg text-xs value-mono shadow-xl"
          style={{
            background: toast.ok ? 'rgba(16,40,32,0.95)' : 'rgba(40,16,16,0.95)',
            border: `1px solid ${toast.ok ? 'rgba(52,211,153,0.35)' : 'rgba(248,113,113,0.35)'}`,
            color: toast.ok ? '#34d399' : '#f87171',
          }}
        >
          {toast.text}
        </div>
      )}
    </aside>
  )
}
