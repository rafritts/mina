'use client'

import { useCallback, useEffect, useId, useState } from 'react'
import { createPortal } from 'react-dom'
import { Chip } from './Chip'
import { Segmented } from './Segmented'
import { StateNotice, offlineDetail } from './StateNotice'
import { apiFetch } from '../lib/api'
import { cn } from '@/lib/utils'

type SceneEntry = { name: string; clothing?: string; position?: string }
type WhenWhat = { when: string; what: string }

export type SceneSnapshot = {
  clothing: SceneEntry[]
  positions: SceneEntry[]
  scene_time: string
  timeline: WhenWhat[]
  plans: WhenWhat[]
  updated_at: number
}

type SceneResponse = {
  scene: SceneSnapshot
  has_content: boolean
  inject: string
  system_prompt: string
  updated_at: number
}

type SectionId = 'scene' | 'timeline' | 'plans' | 'inject'

const SECTIONS: { id: SectionId; label: string }[] = [
  { id: 'scene', label: 'Live Scene' },
  { id: 'timeline', label: 'Timeline' },
  { id: 'plans', label: 'Plans' },
  { id: 'inject', label: 'What she gets' },
]

type Props = {
  open: boolean
  onClose: () => void
}

function PersonCard({ name, body }: { name: string; body: string }) {
  return (
    <div className="surface p-3.5">
      <div className="mb-1.5 text-sm font-medium tracking-tight text-[var(--text)]">{name}</div>
      <p className="text-[13px] leading-relaxed text-[var(--text-secondary)] m-0">{body}</p>
    </div>
  )
}

function EmptyHint({ title, detail }: { title: string; detail: string }) {
  return <StateNotice title={title} detail={detail} />
}

export function ChatContextModal({ open, onClose }: Props) {
  const titleId = useId()
  const [mounted, setMounted] = useState(false)
  const [active, setActive] = useState<SectionId>('scene')
  const [data, setData] = useState<SceneResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await apiFetch<SceneResponse>('/api/scene')
      setData(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!open) return
    setActive('scene')
    void load()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
    }
  }, [open, onClose, load])

  const copyInject = useCallback(async () => {
    const text = data?.system_prompt || data?.inject || ''
    if (!text) return
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1600)
    } catch {
      /* ignore */
    }
  }, [data])

  if (!open || !mounted) return null

  const scene = data?.scene
  const hasScene = Boolean(data?.has_content)
  const clothing = scene?.clothing ?? []
  const positions = scene?.positions ?? []
  const timeline = scene?.timeline ?? []
  const plans = scene?.plans ?? []

  const panel = (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center p-3 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
    >
      <button
        type="button"
        className="absolute inset-0 border-0 bg-black/60 backdrop-blur-sm cursor-default"
        aria-label="Close"
        onClick={onClose}
      />
      <div className="modal-panel relative flex max-h-[min(90vh,52rem)] w-full max-w-2xl flex-col overflow-hidden">
        <header className="shrink-0 border-b border-[var(--border)] px-4 sm:px-5 py-3.5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span
                  className="flex h-7 w-7 items-center justify-center rounded-lg text-[11px] font-semibold"
                  style={{
                    background: 'var(--accent-dim)',
                    border: '1px solid var(--accent-border)',
                    color: 'var(--accent-bright)',
                  }}
                >
                  ∿
                </span>
                <div>
                  <h2
                    id={titleId}
                    className="text-[15px] font-semibold tracking-tight text-[var(--text)] m-0"
                  >
                    Scene
                  </h2>
                  <p className="text-[11px] text-[var(--text-muted)] m-0 mt-0.5">
                    Live scene · timeline · plans — short-term coherence
                  </p>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => void load()}
                disabled={loading}
              >
                {loading ? '…' : 'Refresh'}
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={onClose}
                aria-label="Close"
              >
                ✕
              </button>
            </div>
          </div>

          <div className="mt-3">
            <Segmented
              ariaLabel="Scene sections"
              value={active}
              options={SECTIONS.map((s) => ({ value: s.id, label: s.label }))}
              onChange={(id) => {
                setActive(id)
                document
                  .getElementById(`mina-ctx-${id}`)
                  ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
              }}
            />
          </div>
        </header>

        <div className="flex-1 overflow-y-auto px-4 sm:px-5 py-4 space-y-6">
          {error && (
            <StateNotice
              tone="error"
              title="Can’t load the scene"
              detail={offlineDetail(error, 'The sim did not answer. Refresh once it is running.')}
            />
          )}

          <section id="mina-ctx-scene" className="scroll-mt-3">
            <h3 className="label m-0 mb-1">
              Live Scene
            </h3>
            <p className="text-[12px] text-[var(--text-muted)] m-0 mb-3 leading-relaxed">
              Agent-authored clothing + positions + soft fiction now. Narrative
              coherence — update when the story moves.
            </p>
            {!hasScene ? (
              <EmptyHint
                title="No live scene yet"
                detail="Mina authors it in her reply JSON after the first turn with a body in the room."
              />
            ) : (
              <div className="space-y-3">
                <div className="surface px-3.5 py-3">
                  <div className="label-accent mb-1">
                    Fiction now
                  </div>
                  <p className="text-[14px] text-[var(--text)] m-0 leading-relaxed">
                    {scene?.scene_time || '(none recorded)'}
                  </p>
                </div>
                {clothing.length > 0 && (
                  <div>
                    <div className="label mb-2">
                      Clothing
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {clothing.map((e, i) => (
                        <PersonCard
                          key={`c-${e.name}-${i}`}
                          name={e.name}
                          body={e.clothing || ''}
                        />
                      ))}
                    </div>
                  </div>
                )}
                {positions.length > 0 && (
                  <div>
                    <div className="label mb-2">
                      Positions
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {positions.map((e, i) => (
                        <PersonCard
                          key={`p-${e.name}-${i}`}
                          name={e.name}
                          body={e.position || ''}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </section>

          <section id="mina-ctx-timeline" className="scroll-mt-3">
            <h3 className="label m-0 mb-1">
              Timeline
            </h3>
            <p className="text-[12px] text-[var(--text-muted)] m-0 mb-3 leading-relaxed">
              Past beats that still matter for continuity — not a minute ledger.
            </p>
            {timeline.length === 0 ? (
              <EmptyHint
                title="No timeline rows yet"
                detail="Mina writes timeline[] when story beats need to stick."
              />
            ) : (
              <ol className="m-0 p-0 list-none space-y-2 relative">
                {timeline.map((e, i) => {
                  const isLast = i === timeline.length - 1
                  return (
                    <li
                      key={`${e.when}-${i}`}
                      className={cn('surface px-3.5 py-2.5', isLast && 'border-[var(--accent-border)]')}
                      style={isLast ? { background: 'var(--accent-dim)' } : undefined}
                    >
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className="text-[12px] font-medium text-[var(--text)]">
                          {e.when}
                        </span>
                        {isLast && (
                          <Chip tone="info">Latest</Chip>
                        )}
                      </div>
                      <p className="text-[13px] text-[var(--text-secondary)] m-0 leading-relaxed">
                        {e.what}
                      </p>
                    </li>
                  )
                })}
              </ol>
            )}
          </section>

          <section id="mina-ctx-plans" className="scroll-mt-3">
            <h3 className="label m-0 mb-1">
              Plans
            </h3>
            <p className="text-[12px] text-[var(--text-muted)] m-0 mb-3 leading-relaxed">
              Fuzzy open commitments. Memory hooks, not a calendar — max 6.
            </p>
            {plans.length === 0 ? (
              <EmptyHint
                title="No open plans"
                detail="Mina writes plans[] when something is scheduled ahead of scene time."
              />
            ) : (
              <ol className="m-0 p-0 list-none space-y-2">
                {plans.map((e, i) => (
                  <li
                    key={`${e.when}-${i}`}
                    className="surface px-3.5 py-2.5 flex gap-3"
                  >
                    <span
                      className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-medium"
                      style={{
                        background: 'var(--accent-dim)',
                        color: 'var(--accent-bright)',
                      }}
                    >
                      {i + 1}
                    </span>
                    <div className="min-w-0">
                      <div className="text-[12px] font-medium text-[var(--text)]">
                        {e.when}
                      </div>
                      <p className="text-[13px] text-[var(--text-secondary)] m-0 mt-0.5">
                        {e.what}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <section id="mina-ctx-inject" className="scroll-mt-3">
            <div className="flex items-center justify-between gap-2 mb-1">
              <h3 className="label m-0">
                What the model gets
              </h3>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => void copyInject()}
                disabled={!data?.system_prompt && !data?.inject}
              >
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
            <p className="text-[12px] text-[var(--text-muted)] m-0 mb-3 leading-relaxed">
              Prior live scene re-injected into pillars + mouth. Full system
              prompt when available (last turn).
            </p>
            {data?.system_prompt || data?.inject ? (
              <pre className="inset text-[11px] leading-relaxed mono text-[var(--text-secondary)] overflow-x-auto whitespace-pre-wrap break-words max-h-80 m-0">
                {data.system_prompt || data.inject}
              </pre>
            ) : (
              <EmptyHint
                title="No inject payload yet"
                detail="After a turn, the scene and system prompt land here."
              />
            )}
          </section>
        </div>
      </div>
    </div>
  )

  return createPortal(panel, document.body)
}
