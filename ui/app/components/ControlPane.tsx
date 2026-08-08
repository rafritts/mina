'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { apiFetch, fetchFreetime } from '../lib/api'
import { useStatePoller } from '../lib/hooks/useStatePoller'
import { PRESETS } from '../lib/presets'
import { getLabel, getChemLabel, DISPLAY_RANGES } from '../lib/labels'
import type { ChemicalEntry, FreetimeSession } from '../lib/api'
import {
  FIELD_LABELS,
  SECOND_ORDER,
  THIRD_ORDER,
  presenceLabel,
  sleepStatusLines,
  formatRelativeTs,
  formatClockTs,
} from '../lib/presence'
import { cn } from '@/lib/utils'

type Tab = 'presence' | 'chemistry' | 'tools'

const CHEM_GROUPS: { label: string; chemicals: string[] }[] = [
  { label: 'Monoamines', chemicals: ['dopamine', 'serotonin', 'norepinephrine'] },
  { label: 'Bonding', chemicals: ['oxytocin', 'endorphins'] },
  { label: 'Stress', chemicals: ['cortisol', 'epinephrine'] },
  { label: 'Sleep & clock', chemicals: ['adenosine', 'melatonin', 'orexin'] },
  { label: 'Other', chemicals: ['anandamide', 'crh', 'ghrelin'] },
]

function formatChemValue(value: number): string {
  if (value < 0.1) return value.toFixed(3)
  if (value < 10) return value.toFixed(2)
  if (value < 100) return value.toFixed(1)
  return String(Math.round(value))
}

function chipClass(color?: string): string {
  if (color === 'success') return 'chip chip-success'
  if (color === 'warning') return 'chip chip-warning'
  if (color === 'error') return 'chip chip-error'
  if (color === 'info') return 'chip chip-info'
  return 'chip'
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
  return (
    <div className="metric">
      <div className="metric-top">
        <span className="text-[11.5px] text-muted">{label}</span>
        <div className="flex items-center gap-1.5">
          {entry && <span className={chipClass(entry.color)}>{entry.name}</span>}
          <span className="mono text-[11px] text-secondary w-7 text-right">
            {Math.round(value)}
          </span>
        </div>
      </div>
      <div className="metric-track">
        <div
          className="metric-fill"
          style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
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
  entry: ChemicalEntry
  pending: number | undefined
  onPending: (v: number) => void
  onSave: () => void
  saving: boolean
}) {
  const value = pending ?? entry.value
  const range = DISPLAY_RANGES[field]
  const min = range?.min ?? 0
  const max = entry.norm_max ?? range?.max ?? Math.max(entry.value * 3, 1)
  // Prefer live server label; when slider is dirty, chip still shows last server label
  // (re-label on set/poll). Gap is a sim debug instrument (SPEC-63).
  const labelEntry = getChemLabel(entry)
  const dirty = pending !== undefined
  const step = max <= 1 ? 0.001 : max <= 20 ? 0.01 : 1
  const gap = entry.gap
  const gapStr =
    gap === undefined
      ? null
      : Math.abs(gap) < 0.05
        ? '0'
        : `${gap > 0 ? '+' : ''}${gap.toFixed(1)}`

  return (
    <div className="py-2.5 space-y-1.5 border-b border-[var(--border-subtle)] last:border-0">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11.5px] capitalize text-muted">
          {field.replace(/_/g, ' ')}
        </span>
        <div className="flex items-center gap-1.5">
          {labelEntry && (
            <span className={chipClass(labelEntry.color)} title={labelEntry.implication}>
              {labelEntry.name}
            </span>
          )}
          <span className="mono text-[11px]">
            {formatChemValue(value)}
            <span className="text-faint"> {entry.unit}</span>
          </span>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={Math.min(max, Math.max(min, value))}
          onChange={(e) => onPending(parseFloat(e.target.value))}
          className="flex-1"
        />
        {dirty && (
          <button type="button" className="btn btn-soft btn-sm" onClick={onSave} disabled={saving}>
            {saving ? '…' : 'Set'}
          </button>
        )}
      </div>
      {gapStr !== null && (
        <div className="flex justify-end">
          <span className="mono text-[10px] text-faint" title="Gap vs circadian-adjusted target">
            gap {gapStr}
            {entry.normalized_10 !== undefined && <> · {entry.normalized_10.toFixed(1)}/10</>}
          </span>
        </div>
      )}
    </div>
  )
}

export function ControlPane({
  streamConnected,
  onClose,
  className,
}: {
  streamConnected: boolean
  onClose?: () => void
  className?: string
}) {
  const { state, error, lastUpdate } = useStatePoller(2500)
  const [tab, setTab] = useState<Tab>('presence')
  const [pending, setPending] = useState<Record<string, number>>({})
  const [saving, setSaving] = useState<Record<string, boolean>>({})
  const [toast, setToast] = useState<{ text: string; ok: boolean } | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [advanceHours, setAdvanceHours] = useState('1')
  const [freetime, setFreetime] = useState<FreetimeSession[]>([])
  const [expandedFt, setExpandedFt] = useState<number | null>(null)

  const showToast = useCallback((text: string, ok: boolean) => {
    setToast({ text, ok })
    setTimeout(() => setToast(null), 2800)
  }, [])

  const loadFreetime = useCallback(async () => {
    try {
      const data = await fetchFreetime(12)
      setFreetime(data.recent ?? [])
    } catch {
      /* offline / not ready */
    }
  }, [])

  useEffect(() => {
    void loadFreetime()
    const id = setInterval(() => void loadFreetime(), 15_000)
    return () => clearInterval(id)
  }, [loadFreetime])

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
      void loadFreetime()
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Failed', false)
    } finally {
      setBusy(null)
    }
  }

  const eraseHistory = async () => {
    if (
      !confirm(
        'Erase conversation history?\n\nWipes chat logs, rolling window, and short-term memory.\nKeeps chemistry and long-term memory.',
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

  const tabs: { id: Tab; label: string }[] = [
    { id: 'presence', label: 'Presence' },
    { id: 'chemistry', label: 'Chemistry' },
    { id: 'tools', label: 'Tools' },
  ]

  return (
    <aside className={cn('control-panel', className)}>
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-[var(--border)] px-4 py-3">
        <div className="min-w-0">
          <div className="label">Control</div>
          <div className="text-sm font-medium mt-0.5 truncate">
            {state ? presenceLabel(state) : error ? 'Offline' : '…'}
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="status-pill" data-tone={streamConnected ? 'live' : 'off'}>
            <span className="dot" />
            {streamConnected ? 'Stream' : '…'}
          </span>
          {onClose && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close control">
              ✕
            </button>
          )}
        </div>
      </div>

      <div className="tabs shrink-0">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            className="tab"
            data-active={tab === t.id ? 'true' : 'false'}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto">
        {!state ? (
          <div className="p-5 space-y-2">
            <p className="text-xs mono text-muted m-0">{error ?? 'Waiting for sim…'}</p>
            <p className="text-[11.5px] text-faint leading-relaxed m-0">
              Start the backend with <code className="mono">uv run python main.py</code>
            </p>
          </div>
        ) : tab === 'presence' ? (
          <div className="p-4 space-y-5">
            <section>
              <div className="label section-head">Consciousness</div>
              <div
                className="surface flex items-center justify-between gap-3 p-3"
                aria-live="polite"
              >
                {(() => {
                  const sleep = sleepStatusLines(state)
                  return (
                    <>
                      <div className="min-w-0">
                        <div className="text-[13px] font-medium">{sleep.title}</div>
                        <div className="text-[11px] text-muted mt-0.5 leading-snug">
                          {sleep.detail}
                        </div>
                        {sleep.sinceLabel && (
                          <div className="text-[11px] mono text-secondary mt-1.5 leading-snug">
                            {sleep.sinceLabel}
                          </div>
                        )}
                      </div>
                      <span
                        className="status-pill shrink-0"
                        data-tone={state.sleeping ? 'sleep' : 'live'}
                      >
                        <span className="dot" />
                        {state.sleeping ? 'Sleeping' : 'Awake'}
                      </span>
                    </>
                  )
                })()}
              </div>
            </section>

            <section>
              <div className="flex items-center justify-between section-head">
                <div className="label m-0">Free time</div>
                <button
                  type="button"
                  className="text-[11px] text-muted hover:text-secondary bg-transparent border-0 cursor-pointer p-0"
                  onClick={() => void loadFreetime()}
                >
                  Refresh
                </button>
              </div>
              <div className="surface divide-y divide-[var(--border-subtle)] overflow-hidden">
                {freetime.length === 0 ? (
                  <p className="px-3 py-3 text-[11px] mono text-faint m-0">
                    No free-time sessions yet. She acts alone roughly every 30 min while awake.
                  </p>
                ) : (
                  freetime.slice(0, 8).map((session, i) => {
                    const open = expandedFt === i
                    const tools = session.tools ?? []
                    const body = (session.reply || session.preview || '').trim()
                    return (
                      <button
                        key={`${session.ts}-${i}`}
                        type="button"
                        className="w-full text-left px-3 py-2.5 border-0 bg-transparent cursor-pointer hover:bg-[var(--surface)] transition-colors"
                        onClick={() => setExpandedFt(open ? null : i)}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0 flex-1">
                            {tools.length > 0 && (
                              <div className="flex flex-wrap gap-1 mb-1">
                                {tools.map((t, ti) => (
                                  <span key={ti} className="chip chip-info text-[10px]">
                                    {t.preview || t.name}
                                  </span>
                                ))}
                              </div>
                            )}
                            <p
                              className={cn(
                                'text-[11.5px] text-secondary m-0 leading-snug',
                                !open && 'line-clamp-2',
                                open && 'whitespace-pre-wrap',
                              )}
                            >
                              {body || '(no written free-time note)'}
                            </p>
                          </div>
                          <span
                            className="mono text-[10px] text-faint shrink-0"
                            title={formatClockTs(session.ts)}
                          >
                            {formatRelativeTs(session.ts)}
                          </span>
                        </div>
                      </button>
                    )
                  })
                )}
              </div>
              <p className="text-[10.5px] text-faint mt-1.5 m-0 leading-snug">
                What she does when nobody is chatting — tools, diary, solitary notes.
              </p>
            </section>

            <section>
              <div className="label section-head">Felt state</div>
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
              <div className="label section-head">Signals</div>
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
          <div className="p-4 space-y-4">
            {CHEM_GROUPS.map(({ label, chemicals }) => {
              const rows = chemicals
                .map((c) => ({ c, entry: state.chemicals[c] }))
                .filter((x) => x.entry)
              if (!rows.length) return null
              return (
                <section key={label}>
                  <div className="label mb-1">{label}</div>
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
                </section>
              )
            })}
          </div>
        ) : (
          <div className="p-4 space-y-5">
            <section>
              <div className="label section-head">Mood presets</div>
              <div className="grid grid-cols-2 gap-2">
                {PRESETS.map((preset) => (
                  <button
                    key={preset.name}
                    type="button"
                    disabled={busy === `preset:${preset.name}`}
                    onClick={() => void applyPreset(preset.name, preset.values)}
                    className="surface-interactive p-2.5 text-left"
                  >
                    <div className="text-[12.5px] font-medium">{preset.name}</div>
                    <div className="text-[10.5px] text-muted leading-snug mt-0.5">
                      {preset.description}
                    </div>
                  </button>
                ))}
              </div>
            </section>

            <section>
              <div className="label section-head">Time</div>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  className="field w-20 mono text-sm"
                  value={advanceHours}
                  onChange={(e) => setAdvanceHours(e.target.value)}
                  min={0.25}
                  max={168}
                  step={0.25}
                />
                <span className="text-[11.5px] text-muted">hours</span>
                <button
                  type="button"
                  className="btn btn-soft btn-sm ml-auto"
                  onClick={() => void advance()}
                  disabled={busy === 'advance'}
                >
                  {busy === 'advance' ? '…' : 'Advance'}
                </button>
              </div>
            </section>

            <section className="space-y-2">
              <div className="label section-head">Actions</div>
              <button
                type="button"
                className="btn btn-soft btn-block"
                onClick={() => void runHeartbeat()}
                disabled={busy === 'heartbeat'}
              >
                {busy === 'heartbeat' ? 'Running freetime…' : 'Run freetime heartbeat'}
              </button>
              <button
                type="button"
                className="btn btn-danger btn-block"
                onClick={() => void resetBaseline()}
                disabled={busy === 'reset'}
              >
                {busy === 'reset' ? 'Resetting…' : 'Reset chemistry to baseline'}
              </button>
              <button
                type="button"
                className="btn btn-danger btn-block"
                onClick={() => void eraseHistory()}
                disabled={busy === 'erase'}
              >
                {busy === 'erase' ? 'Erasing…' : 'Erase conversation history'}
              </button>
            </section>

            <Link href="/admin" className="text-[12px] text-muted no-underline hover:text-secondary">
              Open Lab for history, context & system →
            </Link>
          </div>
        )}
      </div>

      <div className="shrink-0 border-t border-[var(--border)] px-4 py-2 flex justify-between text-[10px] mono text-faint">
        <span>
          {lastUpdate
            ? `updated ${Math.max(0, Math.round((Date.now() - lastUpdate) / 1000))}s ago`
            : '—'}
        </span>
        <span>{state?.sleeping ? 'sleeping' : state ? 'awake' : '—'}</span>
      </div>

      {toast && (
        <div className={cn('toast', toast.ok ? 'toast-ok' : 'toast-err')}>{toast.text}</div>
      )}
    </aside>
  )
}
