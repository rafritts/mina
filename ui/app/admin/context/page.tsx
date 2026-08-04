'use client'

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { apiFetch } from '../../lib/api'

interface ContextAssembly {
  window_context?: string
  rag_context?: string
  kag_context?: string
  sliding_raw?: string
  experiences_raw?: string
}

interface ContextRecord {
  ts?: number
  ts_human?: string
  username?: string
  source?: string
  message?: string
  encoder?: Record<string, unknown>
  relationship_modifier?: number
  sim_snapshot?: Record<string, { normalized?: number; setpoint?: number; gap?: number; rate?: number }>
  big5?: Record<string, number>
  assembly?: ContextAssembly
  insula?: Record<string, unknown>
  hippocampus?: Record<string, unknown>
  pfc?: Record<string, unknown>
  system_prompt?: string
  reply?: string
  skipped?: boolean
}

type SectionKey =
  | 'message'
  | 'encoder'
  | 'decoder'
  | 'assembly'
  | 'insula'
  | 'hippocampus'
  | 'pfc'
  | 'system'
  | 'reply'

const SECTION_META: { key: SectionKey; label: string; accent: string }[] = [
  { key: 'message', label: 'User message', accent: 'rgba(96,165,250,0.75)' },
  { key: 'encoder', label: 'Encoder (amygdala)', accent: 'rgba(251,146,60,0.75)' },
  { key: 'decoder', label: 'Decoder (chemistry)', accent: 'rgba(52,211,153,0.75)' },
  { key: 'assembly', label: 'Context assembly', accent: 'rgba(167,139,250,0.75)' },
  { key: 'insula', label: 'Insula (emotion)', accent: 'rgba(251,113,133,0.75)' },
  { key: 'hippocampus', label: 'Hippocampus (situation)', accent: 'rgba(196,181,253,0.75)' },
  { key: 'pfc', label: 'PFC (strategy)', accent: 'rgba(248,200,79,0.75)' },
  { key: 'system', label: 'System prompt (Mina sees)', accent: 'rgba(232,228,221,0.55)' },
  { key: 'reply', label: 'Reply', accent: 'rgba(52,211,153,0.65)' },
]

function fmtVal(v: unknown): string {
  if (v == null || v === '') return '—'
  if (typeof v === 'object') return JSON.stringify(v, null, 2)
  return String(v)
}

function KvList({ data }: { data: Record<string, unknown> | undefined }) {
  if (!data || Object.keys(data).length === 0) {
    return <p className="text-xs mono text-faint m-0">(none)</p>
  }
  return (
    <dl className="space-y-3 m-0">
      {Object.entries(data).map(([k, v]) => (
        <div key={k}>
          <dt className="label mb-1">{k.replace(/_/g, ' ')}</dt>
          <dd className="text-sm leading-relaxed whitespace-pre-wrap break-words mono text-secondary m-0">
            {fmtVal(v)}
          </dd>
        </div>
      ))}
    </dl>
  )
}

function Prose({ text }: { text: string | undefined }) {
  const t = (text ?? '').trim()
  if (!t) {
    return <p className="text-xs mono text-faint m-0">(empty)</p>
  }
  return (
    <p className="text-sm leading-relaxed whitespace-pre-wrap break-words text-secondary m-0">
      {t}
    </p>
  )
}

function Section({
  label,
  accent,
  open,
  onToggle,
  children,
}: {
  label: string
  accent: string
  open: boolean
  onToggle: () => void
  children: ReactNode
}) {
  return (
    <section className="surface overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 text-left border-0 bg-transparent cursor-pointer hover:bg-[var(--surface-hover)] transition-colors"
      >
        <span className="text-[11px] uppercase tracking-[0.14em] font-medium" style={{ color: accent }}>
          {label}
        </span>
        <span className="text-xs mono text-faint">{open ? '−' : '+'}</span>
      </button>
      {open && (
        <div className="px-4 pb-4 border-t border-[var(--border-subtle)]">
          <div className="pt-3">{children}</div>
        </div>
      )}
    </section>
  )
}

function relativeAge(ts?: number): string {
  if (!ts) return '—'
  const diff = Date.now() - ts * 1000
  if (diff < 15_000) return 'just now'
  if (diff < 60_000) return `${Math.floor(diff / 1000)}s ago`
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`
  return `${Math.floor(diff / 86_400_000)}d ago`
}

export default function ContextPage() {
  const [record, setRecord] = useState<ContextRecord | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [showRaw, setShowRaw] = useState(false)
  const [markdown, setMarkdown] = useState('')
  const [copied, setCopied] = useState<'json' | 'md' | null>(null)
  const [open, setOpen] = useState<Record<SectionKey, boolean>>({
    message: true,
    encoder: false,
    decoder: true,
    assembly: true,
    insula: true,
    hippocampus: true,
    pfc: true,
    system: false,
    reply: true,
  })
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<ContextRecord>('/api/context')
      setRecord(data)
      setError(null)
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      if (msg.startsWith('404')) {
        setRecord(null)
        setError('No assembly yet — send a chat message first.')
      } else {
        setError(msg)
      }
    } finally {
      setLoading(false)
    }
  }, [])

  const loadMarkdown = useCallback(async () => {
    try {
      const res = await fetch('/api/context/text')
      if (!res.ok) throw new Error(`${res.status}`)
      setMarkdown(await res.text())
    } catch {
      setMarkdown('')
    }
  }, [])

  useEffect(() => {
    load()
    loadMarkdown()
    if (autoRefresh) {
      timerRef.current = setInterval(() => {
        load()
        loadMarkdown()
      }, 4000)
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [autoRefresh, load, loadMarkdown])

  const toggle = (key: SectionKey) =>
    setOpen((s) => ({ ...s, [key]: !s[key] }))

  const copy = async (kind: 'json' | 'md') => {
    try {
      const text =
        kind === 'json'
          ? JSON.stringify(record, null, 2)
          : markdown || (await (await fetch('/api/context/text')).text())
      await navigator.clipboard.writeText(text)
      setCopied(kind)
      setTimeout(() => setCopied(null), 1500)
    } catch {
      /* ignore */
    }
  }

  const a = record?.assembly

  return (
    <div className="page space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="page-title">Context</h1>
          <p className="page-desc mb-0">
            Latest pillar chain — also written to <code className="mono">run/last_context.md</code>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={() => setAutoRefresh((v) => !v)}
            className="btn btn-sm mono"
            style={
              autoRefresh
                ? {
                    border: '1px solid var(--success-border)',
                    color: 'var(--success)',
                    background: 'var(--success-dim)',
                  }
                : { border: '1px solid var(--border)' }
            }
          >
            {autoRefresh ? 'live' : 'paused'}
          </button>
          <button
            type="button"
            onClick={() => {
              void load()
              void loadMarkdown()
            }}
            className="btn btn-soft btn-sm"
          >
            Refresh
          </button>
          <button type="button" onClick={() => void copy('md')} className="btn btn-soft btn-sm">
            {copied === 'md' ? 'Copied md' : 'Copy md'}
          </button>
          <button type="button" onClick={() => void copy('json')} className="btn btn-soft btn-sm">
            {copied === 'json' ? 'Copied json' : 'Copy json'}
          </button>
          <button type="button" onClick={() => setShowRaw((v) => !v)} className="btn btn-soft btn-sm">
            {showRaw ? 'Sections' : 'Raw md'}
          </button>
        </div>
      </div>

      {record && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs mono text-muted px-0.5">
          <span>{record.ts_human || '—'}</span>
          <span>{relativeAge(record.ts)}</span>
          <span>source={record.source || 'chat'}</span>
          <span>user={record.username || '—'}</span>
          {record.skipped && <span style={{ color: 'var(--danger)' }}>skipped reply</span>}
        </div>
      )}

      {loading && !record && <p className="text-xs mono text-muted m-0">Loading…</p>}

      {error && !record && <div className="alert alert-info">{error}</div>}

      {showRaw && markdown && (
        <pre
          className="surface p-4 text-xs leading-relaxed overflow-x-auto whitespace-pre-wrap mono text-secondary m-0"
          style={{ maxHeight: '70vh' }}
        >
          {markdown}
        </pre>
      )}

      {!showRaw && record && (
        <div className="space-y-2">
          <Section
            label={SECTION_META[0].label}
            accent={SECTION_META[0].accent}
            open={open.message}
            onToggle={() => toggle('message')}
          >
            <Prose text={record.message} />
          </Section>

          <Section
            label={SECTION_META[1].label}
            accent={SECTION_META[1].accent}
            open={open.encoder}
            onToggle={() => toggle('encoder')}
          >
            <KvList data={record.encoder as Record<string, unknown>} />
            {record.relationship_modifier != null && (
              <p className="mt-3 text-xs value-mono" style={{ color: 'rgba(232,228,221,0.45)' }}>
                relationship_modifier: {record.relationship_modifier}
              </p>
            )}
          </Section>

          <Section
            label={SECTION_META[2].label}
            accent={SECTION_META[2].accent}
            open={open.decoder}
            onToggle={() => toggle('decoder')}
          >
            {record.sim_snapshot && Object.keys(record.sim_snapshot).length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-xs value-mono">
                  <thead>
                    <tr style={{ color: 'rgba(232,228,221,0.35)' }}>
                      <th className="text-left font-normal py-1 pr-3">chemical</th>
                      <th className="text-right font-normal py-1 px-2">norm</th>
                      <th className="text-right font-normal py-1 px-2">set</th>
                      <th className="text-right font-normal py-1 px-2">gap</th>
                      <th className="text-right font-normal py-1 pl-2">rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(record.sim_snapshot)
                      .sort(([a], [b]) => a.localeCompare(b))
                      .map(([name, vals]) => (
                        <tr key={name} style={{ color: 'rgba(232,228,221,0.75)' }}>
                          <td className="py-0.5 pr-3">{name}</td>
                          <td className="text-right px-2">{vals.normalized ?? '—'}</td>
                          <td className="text-right px-2">{vals.setpoint ?? '—'}</td>
                          <td className="text-right px-2">
                            {vals.gap != null && vals.gap > 0 ? `+${vals.gap}` : (vals.gap ?? '—')}
                          </td>
                          <td className="text-right pl-2">
                            {vals.rate != null && vals.rate > 0 ? `+${vals.rate}` : (vals.rate ?? '—')}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-xs value-mono" style={{ color: 'rgba(232,228,221,0.3)' }}>(none)</p>
            )}
            {record.big5 && Object.keys(record.big5).length > 0 && (
              <div className="mt-4">
                <div
                  className="text-[10px] uppercase tracking-widest mb-2"
                  style={{ color: 'rgba(232,228,221,0.32)' }}
                >
                  Big 5
                </div>
                <KvList data={record.big5 as Record<string, unknown>} />
              </div>
            )}
          </Section>

          <Section
            label={SECTION_META[3].label}
            accent={SECTION_META[3].accent}
            open={open.assembly}
            onToggle={() => toggle('assembly')}
          >
            <div className="space-y-4">
              <div>
                <div
                  className="text-[10px] uppercase tracking-widest mb-1.5"
                  style={{ color: 'rgba(232,228,221,0.32)' }}
                >
                  Window synthesis
                </div>
                <Prose text={a?.window_context} />
              </div>
              <div>
                <div
                  className="text-[10px] uppercase tracking-widest mb-1.5"
                  style={{ color: 'rgba(232,228,221,0.32)' }}
                >
                  RAG synthesis
                </div>
                <Prose text={a?.rag_context} />
              </div>
              <div>
                <div
                  className="text-[10px] uppercase tracking-widest mb-1.5"
                  style={{ color: 'rgba(232,228,221,0.32)' }}
                >
                  KAG
                </div>
                <Prose text={a?.kag_context} />
              </div>
              {(a?.sliding_raw || a?.experiences_raw) && (
                <details className="text-xs">
                  <summary
                    className="cursor-pointer uppercase tracking-widest text-[10px]"
                    style={{ color: 'rgba(232,228,221,0.35)' }}
                  >
                    Raw retrieval
                  </summary>
                  <div className="mt-3 space-y-3">
                    {a.sliding_raw && (
                      <div>
                        <div className="mb-1" style={{ color: 'rgba(232,228,221,0.32)' }}>
                          Sliding
                        </div>
                        <Prose text={a.sliding_raw} />
                      </div>
                    )}
                    {a.experiences_raw && (
                      <div>
                        <div className="mb-1" style={{ color: 'rgba(232,228,221,0.32)' }}>
                          Episodic
                        </div>
                        <Prose text={a.experiences_raw} />
                      </div>
                    )}
                  </div>
                </details>
              )}
            </div>
          </Section>

          <Section
            label={SECTION_META[4].label}
            accent={SECTION_META[4].accent}
            open={open.insula}
            onToggle={() => toggle('insula')}
          >
            <KvList data={record.insula as Record<string, unknown>} />
          </Section>

          <Section
            label={SECTION_META[5].label}
            accent={SECTION_META[5].accent}
            open={open.hippocampus}
            onToggle={() => toggle('hippocampus')}
          >
            <KvList data={record.hippocampus as Record<string, unknown>} />
          </Section>

          <Section
            label={SECTION_META[6].label}
            accent={SECTION_META[6].accent}
            open={open.pfc}
            onToggle={() => toggle('pfc')}
          >
            <KvList data={record.pfc as Record<string, unknown>} />
          </Section>

          <Section
            label={SECTION_META[7].label}
            accent={SECTION_META[7].accent}
            open={open.system}
            onToggle={() => toggle('system')}
          >
            <pre
              className="text-xs leading-relaxed whitespace-pre-wrap break-words value-mono max-h-[28rem] overflow-y-auto"
              style={{ color: 'rgba(232,228,221,0.72)' }}
            >
              {(record.system_prompt || '').trim() || '(none)'}
            </pre>
          </Section>

          <Section
            label={SECTION_META[8].label}
            accent={SECTION_META[8].accent}
            open={open.reply}
            onToggle={() => toggle('reply')}
          >
            <Prose text={record.reply || (record.skipped ? '(silence)' : '')} />
          </Section>
        </div>
      )}
    </div>
  )
}
