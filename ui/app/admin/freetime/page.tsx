'use client'

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import {
  fetchFreetime,
  fetchFreetimeMarkdown,
  type FreetimeSession,
  type FreetimeContext,
} from '../../lib/api'
import {
  formatClockTs,
  formatDuration,
  formatRelativeTs,
  freetimeBody,
  freetimeChipLabels,
} from '../../lib/presence'
import { Chip } from '../../components/Chip'
import { StateNotice, offlineDetail } from '../../components/StateNotice'
import { cn } from '@/lib/utils'

type SectionKey =
  | 'message'
  | 'tools'
  | 'reply'
  | 'encoder'
  | 'decoder'
  | 'assembly'
  | 'insula'
  | 'hippocampus'
  | 'pfc'
  | 'system'

const SECTION_META: { key: SectionKey; label: string; tone: string }[] = [
  { key: 'message', label: 'Synthetic input', tone: 'sense' },
  { key: 'tools', label: 'Tools & diary', tone: 'tools' },
  { key: 'reply', label: 'Reply / note', tone: 'reply' },
  { key: 'encoder', label: 'Encoder (amygdala)', tone: 'tools' },
  { key: 'decoder', label: 'Decoder (chemistry)', tone: 'chem' },
  { key: 'assembly', label: 'Context assembly', tone: 'assembly' },
  { key: 'insula', label: 'Insula (emotion)', tone: 'feel' },
  { key: 'hippocampus', label: 'Hippocampus (situation)', tone: 'situate' },
  { key: 'pfc', label: 'PFC (strategy)', tone: 'decide' },
  { key: 'system', label: 'System prompt (Mina sees)', tone: 'system' },
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
  tone,
  open,
  onToggle,
  children,
  badge,
}: {
  label: string
  tone: string
  open: boolean
  onToggle: () => void
  children: ReactNode
  badge?: string
}) {
  return (
    <section className="surface overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 text-left border-0 bg-transparent cursor-pointer hover:bg-[var(--surface-hover)] transition-colors"
      >
        <span className="flex items-center gap-2 min-w-0">
          <span className="section-accent" data-tone={tone}>
            {label}
          </span>
          {badge && <Chip>{badge}</Chip>}
        </span>
        <span className="text-xs mono text-faint shrink-0">{open ? '−' : '+'}</span>
      </button>
      {open && (
        <div className="px-4 pb-4 border-t border-[var(--border-subtle)]">
          <div className="pt-3">{children}</div>
        </div>
      )}
    </section>
  )
}

function ToolBlock({ tools }: { tools: FreetimeSession['tools'] }) {
  if (!tools?.length) {
    return <p className="text-xs mono text-faint m-0">(no tools called)</p>
  }
  return (
    <div className="space-y-4">
      {tools.map((t, i) => {
        const args = t.args ?? {}
        const isDiary = t.name === 'record_diary'
        const entry = typeof args.entry === 'string' ? args.entry : ''
        return (
          <div key={`${t.name}-${i}`} className="inset space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
              <Chip tone="info">{t.label || t.name}</Chip>
              <span className="mono text-[10px] text-faint">{t.name}</span>
            </div>
            {isDiary && entry ? (
              <Prose text={entry} />
            ) : Object.keys(args).length > 0 ? (
              <KvList data={args as Record<string, unknown>} />
            ) : (
              <p className="text-xs text-muted m-0">{t.preview || '—'}</p>
            )}
            {t.result && (
              <p className="text-[11px] mono text-faint m-0 pt-1 border-t border-[var(--border-subtle)]">
                result: {t.result}
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}

function DecoderTable({
  snap,
}: {
  snap: FreetimeContext['sim_snapshot'] | undefined
}) {
  if (!snap || Object.keys(snap).length === 0) {
    return <p className="text-xs mono text-faint m-0">(none)</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs value-mono">
        <thead>
          <tr className="text-faint">
            <th className="text-left font-normal py-1 pr-3">chemical</th>
            <th className="text-right font-normal py-1 px-2">norm</th>
            <th className="text-right font-normal py-1 px-2">set</th>
            <th className="text-right font-normal py-1 px-2">gap</th>
            <th className="text-right font-normal py-1 pl-2">rate</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(snap)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([name, vals]) => (
              <tr key={name} className="text-secondary">
                <td className="py-0.5 pr-3">{name}</td>
                <td className="text-right px-2">{vals?.normalized ?? '—'}</td>
                <td className="text-right px-2">{vals?.setpoint ?? '—'}</td>
                <td className="text-right px-2">
                  {vals?.gap != null && vals.gap > 0 ? `+${vals.gap}` : (vals?.gap ?? '—')}
                </td>
                <td className="text-right pl-2">
                  {vals?.rate != null && vals.rate > 0 ? `+${vals.rate}` : (vals?.rate ?? '—')}
                </td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  )
}

export default function FreetimePage() {
  const [recent, setRecent] = useState<FreetimeSession[]>([])
  const [selectedTs, setSelectedTs] = useState<number | null>(null)
  const [detail, setDetail] = useState<FreetimeSession | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [showRaw, setShowRaw] = useState(false)
  const [markdown, setMarkdown] = useState('')
  const [copied, setCopied] = useState<'json' | 'md' | null>(null)
  const [open, setOpen] = useState<Record<SectionKey, boolean>>({
    message: true,
    tools: true,
    reply: true,
    encoder: false,
    decoder: true,
    assembly: true,
    insula: true,
    hippocampus: true,
    pfc: true,
    system: false,
  })
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const selectedTsRef = useRef<number | null>(null)
  selectedTsRef.current = selectedTs

  const loadList = useCallback(async () => {
    try {
      const data = await fetchFreetime(50)
      setRecent(data.recent ?? [])
      setError(null)
      // Auto-select newest on first load
      setSelectedTs((prev) => {
        if (prev != null) return prev
        const first = data.recent?.[0]?.ts ?? data.last?.ts
        return first ?? null
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  const loadDetail = useCallback(async (ts: number | null) => {
    if (ts == null) {
      setDetail(null)
      setLoading(false)
      return
    }
    try {
      const data = await fetchFreetime(50, ts)
      setDetail(data.detail ?? null)
      if (data.recent?.length) setRecent(data.recent)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  const loadMarkdown = useCallback(async (ts: number | null) => {
    try {
      setMarkdown(await fetchFreetimeMarkdown(ts))
    } catch {
      setMarkdown('')
    }
  }, [])

  useEffect(() => {
    void loadList().then(() => {
      const ts = selectedTsRef.current
      void loadDetail(ts)
      void loadMarkdown(ts)
    })
  }, [loadList, loadDetail, loadMarkdown])

  useEffect(() => {
    if (selectedTs == null) return
    setLoading(true)
    void loadDetail(selectedTs)
    void loadMarkdown(selectedTs)
  }, [selectedTs, loadDetail, loadMarkdown])

  useEffect(() => {
    if (!autoRefresh) return
    timerRef.current = setInterval(() => {
      void loadList()
      const ts = selectedTsRef.current
      void loadDetail(ts)
      void loadMarkdown(ts)
    }, 8000)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [autoRefresh, loadList, loadDetail, loadMarkdown])

  const toggle = (key: SectionKey) => setOpen((s) => ({ ...s, [key]: !s[key] }))

  const copy = async (kind: 'json' | 'md') => {
    try {
      const text =
        kind === 'json'
          ? JSON.stringify(detail, null, 2)
          : markdown || (await fetchFreetimeMarkdown(selectedTs))
      await navigator.clipboard.writeText(text)
      setCopied(kind)
      setTimeout(() => setCopied(null), 1500)
    } catch {
      /* ignore */
    }
  }

  const ctx = detail?.context
  const a = ctx?.assembly

  return (
    <div className="page space-y-4">
      <div className="page-head">
        <div>
          <h1 className="page-title">Free time</h1>
          <p className="page-desc mb-0">
            What she does alone — tools, diary, pillar chain. Also{' '}
            <code className="mono">run/last_freetime.md</code>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={() => setAutoRefresh((v) => !v)}
            className="btn btn-soft btn-sm mono"
            data-tone={autoRefresh ? 'live' : undefined}
          >
            {autoRefresh ? 'live' : 'paused'}
          </button>
          <button
            type="button"
            onClick={() => {
              void loadList()
              void loadDetail(selectedTs)
              void loadMarkdown(selectedTs)
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

      <div className="grid gap-4 lg:grid-cols-[minmax(0,15rem)_minmax(0,1fr)]">
        {/* Session list */}
        <aside className="surface overflow-hidden max-h-[70vh] flex flex-col">
          <div className="px-3 py-2 border-b border-[var(--border-subtle)] label shrink-0">
            Sessions
          </div>
          <div className="overflow-y-auto flex-1 divide-y divide-[var(--border-subtle)]">
            {recent.length === 0 && (
              <StateNotice
                bare
                compact
                title="No free-time sessions yet"
                detail="Run a heartbeat from Tools to write the first one."
              />
            )}
            {recent.map((s) => {
              const active = selectedTs != null && Math.abs(s.ts - selectedTs) < 1.5
              const chips = freetimeChipLabels(s)
              return (
                <button
                  key={s.ts}
                  type="button"
                  onClick={() => setSelectedTs(s.ts)}
                  className={cn(
                    'w-full text-left px-3 py-2.5 border-0 cursor-pointer transition-colors',
                    active
                      ? 'bg-[var(--accent-dim)]'
                      : 'bg-transparent hover:bg-[var(--surface-hover)]',
                  )}
                >
                  <div className="flex items-center justify-between gap-2 mb-0.5">
                    <span className="mono text-[10px] text-faint">
                      {formatRelativeTs(s.ts)}
                    </span>
                    {s.duration_s != null && (
                      <span className="mono text-[10px] text-faint">
                        {formatDuration(s.duration_s)}
                      </span>
                    )}
                  </div>
                  {chips.length > 0 && (
                    <div className="flex flex-wrap gap-0.5 mb-1">
                      {chips.slice(0, 3).map((l) => (
                        <Chip key={l} className="max-w-[5.5rem]">
                          {l}
                        </Chip>
                      ))}
                    </div>
                  )}
                  <p className="text-[11px] text-secondary m-0 line-clamp-2 leading-snug">
                    {freetimeBody(s)}
                  </p>
                </button>
              )
            })}
          </div>
        </aside>

        {/* Detail */}
        <div className="min-w-0 space-y-3">
          {loading && !detail && (
            <StateNotice tone="loading" title="Loading session" detail="Fetching the latest free-time record." />
          )}
          {error && !detail && (
            <StateNotice
              tone="info"
              title="Free time unavailable"
              detail={offlineDetail(
                error,
                'Sessions appear after a heartbeat. Run one from the Tools sheet.',
              )}
            />
          )}

          {detail && (
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs mono text-muted px-0.5">
              <span>{detail.ts_human || formatClockTs(detail.ts)}</span>
              <span>{formatRelativeTs(detail.ts)}</span>
              {detail.duration_s != null && (
                <span>ran {formatDuration(detail.duration_s)}</span>
              )}
              <span>
                {(detail.labels ?? []).join(', ') || 'no tools'}
              </span>
              {detail.has_context ? (
                <span className="text-success">pillars</span>
              ) : (
                <span className="text-faint">no pillar dump</span>
              )}
            </div>
          )}

          {showRaw && markdown && (
            <pre
              className="surface p-4 text-xs leading-relaxed overflow-x-auto whitespace-pre-wrap mono text-secondary m-0"
              style={{ maxHeight: '70vh' }}
            >
              {markdown}
            </pre>
          )}

          {!showRaw && detail && (
            <div className="space-y-2">
              <Section
                label={SECTION_META[0].label}
                tone={SECTION_META[0].tone}
                open={open.message}
                onToggle={() => toggle('message')}
              >
                <Prose text={detail.message} />
              </Section>

              <Section
                label={SECTION_META[1].label}
                tone={SECTION_META[1].tone}
                open={open.tools}
                onToggle={() => toggle('tools')}
                badge={
                  detail.tools?.length
                    ? String(detail.tools.length)
                    : undefined
                }
              >
                <ToolBlock tools={detail.tools} />
              </Section>

              <Section
                label={SECTION_META[2].label}
                tone={SECTION_META[2].tone}
                open={open.reply}
                onToggle={() => toggle('reply')}
              >
                <Prose text={detail.reply || detail.body} />
              </Section>

              <Section
                label={SECTION_META[3].label}
                tone={SECTION_META[3].tone}
                open={open.encoder}
                onToggle={() => toggle('encoder')}
              >
                {ctx ? (
                  <>
                    <KvList data={ctx.encoder as Record<string, unknown>} />
                    {ctx.relationship_modifier != null && (
                      <p className="mt-3 text-xs value-mono text-faint m-0">
                        relationship_modifier: {ctx.relationship_modifier}
                      </p>
                    )}
                  </>
                ) : (
                  <p className="text-xs mono text-faint m-0">
                    No pillar dump on this session (older free time or conversation-only).
                    New runs store the full chain.
                  </p>
                )}
              </Section>

              <Section
                label={SECTION_META[4].label}
                tone={SECTION_META[4].tone}
                open={open.decoder}
                onToggle={() => toggle('decoder')}
              >
                <DecoderTable snap={ctx?.sim_snapshot} />
                {ctx?.big5 && Object.keys(ctx.big5).length > 0 && (
                  <div className="mt-4">
                    <div className="label mb-2">
                      Big 5
                    </div>
                    <KvList data={ctx.big5 as Record<string, unknown>} />
                  </div>
                )}
              </Section>

              <Section
                label={SECTION_META[5].label}
                tone={SECTION_META[5].tone}
                open={open.assembly}
                onToggle={() => toggle('assembly')}
              >
                {a ? (
                  <div className="space-y-4">
                    <div>
                      <div className="label mb-1.5">
                        Window synthesis
                      </div>
                      <Prose text={a.window_context} />
                    </div>
                    <div>
                      <div className="label mb-1.5">
                        RAG synthesis
                      </div>
                      <Prose text={a.rag_context} />
                    </div>
                    <div>
                      <div className="label mb-1.5">
                        KAG
                      </div>
                      <Prose text={a.kag_context} />
                    </div>
                    {(a.sliding_raw || a.experiences_raw) && (
                      <details className="text-xs">
                        <summary className="label cursor-pointer">
                          Raw retrieval
                        </summary>
                        <div className="mt-3 space-y-3">
                          {a.sliding_raw && (
                            <div>
                              <div className="mb-1 text-faint">Sliding</div>
                              <Prose text={a.sliding_raw} />
                            </div>
                          )}
                          {a.experiences_raw && (
                            <div>
                              <div className="mb-1 text-faint">Episodic</div>
                              <Prose text={a.experiences_raw} />
                            </div>
                          )}
                        </div>
                      </details>
                    )}
                  </div>
                ) : (
                  <p className="text-xs mono text-faint m-0">(no assembly on this session)</p>
                )}
              </Section>

              <Section
                label={SECTION_META[6].label}
                tone={SECTION_META[6].tone}
                open={open.insula}
                onToggle={() => toggle('insula')}
              >
                <KvList data={ctx?.insula as Record<string, unknown> | undefined} />
              </Section>

              <Section
                label={SECTION_META[7].label}
                tone={SECTION_META[7].tone}
                open={open.hippocampus}
                onToggle={() => toggle('hippocampus')}
              >
                <KvList data={ctx?.hippocampus as Record<string, unknown> | undefined} />
              </Section>

              <Section
                label={SECTION_META[8].label}
                tone={SECTION_META[8].tone}
                open={open.pfc}
                onToggle={() => toggle('pfc')}
              >
                <KvList data={ctx?.pfc as Record<string, unknown> | undefined} />
              </Section>

              <Section
                label={SECTION_META[9].label}
                tone={SECTION_META[9].tone}
                open={open.system}
                onToggle={() => toggle('system')}
              >
                <pre
                  className="text-xs leading-relaxed whitespace-pre-wrap break-words value-mono text-secondary max-h-[28rem] overflow-y-auto m-0"
                >
                  {(ctx?.system_prompt || '').trim() || '(none)'}
                </pre>
              </Section>
            </div>
          )}

          {!loading && !detail && recent.length === 0 && (
            <p className="text-xs mono text-muted m-0">
              Free time runs ~every 30 min while she is awake. Trigger one from the header Tools
              sheet → Run freetime heartbeat. Reset chemistry and erase history are on that same
              sheet. System only shows heartbeat status.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
