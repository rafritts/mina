'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { fetchFreetime, type FreetimeSession, type StateData } from '../../lib/api'
import { getLabel } from '../../lib/labels'
import {
  FIELD_LABELS,
  SECOND_ORDER,
  THIRD_ORDER,
  formatClockTs,
  formatRelativeTs,
  freetimeBody,
  freetimeChipLabels,
  sleepStatusLines,
} from '../../lib/presence'
import { Sheet } from './Sheet'

function chipClass(color?: string): string {
  if (color === 'success') return 'chip chip-success'
  if (color === 'warning') return 'chip chip-warning'
  if (color === 'error') return 'chip chip-error'
  if (color === 'info') return 'chip chip-info'
  return 'chip'
}

function UpdatedAgo({ at }: { at: number | null }) {
  const [now, setNow] = useState<number | null>(null)
  useEffect(() => {
    const tick = () => setNow(Date.now())
    const start = window.setTimeout(tick, 0)
    const id = window.setInterval(tick, 1000)
    return () => {
      window.clearTimeout(start)
      window.clearInterval(id)
    }
  }, [])
  if (at == null || now == null) return <span>—</span>
  const age = Math.max(0, Math.round((now - at) / 1000))
  return <span>updated {age}s ago</span>
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

export function PresenceSheet({
  open,
  onClose,
  state,
  error,
  lastUpdate,
}: {
  open: boolean
  onClose: () => void
  state: StateData | null
  error: string | null
  lastUpdate: number | null
}) {
  const [freetime, setFreetime] = useState<FreetimeSession[]>([])

  const loadFreetime = useCallback(async () => {
    try {
      const data = await fetchFreetime(12)
      setFreetime(data.recent ?? [])
    } catch {
      /* offline / not ready */
    }
  }, [])

  useEffect(() => {
    if (!open) return
    const start = window.setTimeout(() => void loadFreetime(), 0)
    const id = window.setInterval(() => void loadFreetime(), 15_000)
    return () => {
      window.clearTimeout(start)
      window.clearInterval(id)
    }
  }, [open, loadFreetime])
  const latest = freetime[0]
  const sleep = state ? sleepStatusLines(state) : null

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="Presence"
      footer={
        <>
          <UpdatedAgo at={lastUpdate} />
          <span>{state?.sleeping ? 'sleeping' : state ? 'awake' : '—'}</span>
        </>
      }
    >
      {!state ? (
        <div className="p-5 space-y-4">
          <div className="space-y-2">
            <p className="text-xs mono text-muted m-0">{error ?? 'Waiting for sim…'}</p>
            <p className="text-[11.5px] text-faint leading-relaxed m-0">
              Start the backend with <code className="mono">uv run python main.py</code>
            </p>
          </div>
          <nav className="flex flex-wrap gap-x-4 gap-y-1" aria-label="Presence links">
            <Link
              href="/admin"
              className="text-[12px] text-muted no-underline hover:text-secondary"
              onClick={onClose}
            >
              Overview
            </Link>
            <Link
              href="/admin/freetime"
              className="text-[12px] text-muted no-underline hover:text-secondary"
              onClick={onClose}
            >
              Free time
            </Link>
          </nav>
        </div>
      ) : (
        <div className="p-4 space-y-5">
          <section>
            <div className="label section-head">Consciousness</div>
            <div className="surface flex items-center justify-between gap-3 p-3" aria-live="polite">
              <div className="min-w-0">
                <div className="text-[13px] font-medium">{sleep?.title}</div>
                <div className="text-[11px] text-muted mt-0.5 leading-snug">{sleep?.detail}</div>
                {sleep?.sinceLabel && (
                  <div className="text-[11px] mono text-secondary mt-1.5 leading-snug">
                    {sleep.sinceLabel}
                  </div>
                )}
              </div>
              <span className="status-pill shrink-0" data-tone={state.sleeping ? 'sleep' : 'live'}>
                <span className="dot" />
                {state.sleeping ? 'Sleeping' : 'Awake'}
              </span>
            </div>
          </section>

          <section>
            <div className="label section-head">Free time</div>
            <div className="surface p-3 space-y-2">
              {latest ? (
                <>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex flex-wrap gap-1 min-w-0">
                      {freetimeChipLabels(latest)
                        .slice(0, 3)
                        .map((label) => (
                          <span key={label} className="chip chip-info max-w-[7rem] truncate">
                            {label}
                          </span>
                        ))}
                    </div>
                    <span
                      className="mono text-[10px] text-faint shrink-0"
                      title={formatClockTs(latest.ts)}
                    >
                      {formatRelativeTs(latest.ts)}
                    </span>
                  </div>
                  <p className="text-[11.5px] text-secondary m-0 leading-snug line-clamp-2 break-words">
                    {freetimeBody(latest)}
                  </p>
                </>
              ) : (
                <p className="text-[11px] mono text-faint m-0">No free-time sessions yet.</p>
              )}
            </div>
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

          <nav className="flex flex-wrap gap-x-4 gap-y-1" aria-label="Presence links">
            <Link
              href="/admin"
              className="text-[12px] text-muted no-underline hover:text-secondary"
              onClick={onClose}
            >
              Overview
            </Link>
            <Link
              href="/admin/freetime"
              className="text-[12px] text-muted no-underline hover:text-secondary"
              onClick={onClose}
            >
              Free time
            </Link>
          </nav>
        </div>
      )}
    </Sheet>
  )
}
