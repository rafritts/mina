'use client'

import { useEffect, useState } from 'react'
import type { TurnMind, PillarStageId } from '../lib/stream'

const STAGES: { id: PillarStageId; label: string }[] = [
  { id: 'sense', label: 'Sense' },
  { id: 'chemistry', label: 'Chem' },
  { id: 'feel', label: 'Feel' },
  { id: 'remember', label: 'Memory' },
  { id: 'situate', label: 'Situate' },
  { id: 'decide', label: 'Decide' },
  { id: 'speak', label: 'Speak' },
]

const STAGE_ORDER: PillarStageId[] = STAGES.map((s) => s.id)

function stageIndex(id: PillarStageId | null): number {
  if (!id) return -1
  return STAGE_ORDER.indexOf(id)
}

function Typewriter({ text, speed = 55 }: { text: string; speed?: number }) {
  const [count, setCount] = useState(0)
  useEffect(() => {
    if (!text) {
      setCount(0)
      return
    }
    setCount(0)
    let i = 0
    const iv = setInterval(() => {
      i += 1
      setCount(i)
      if (i >= text.length) clearInterval(iv)
    }, 1000 / speed)
    return () => clearInterval(iv)
  }, [text, speed])

  return (
    <>
      {text.slice(0, count)}
      {count < text.length && (
        <span className="inline-block w-px h-3 ml-0.5 align-middle animate-pulse bg-current opacity-50" />
      )}
    </>
  )
}

function Pill({ children, accent }: { children: React.ReactNode; accent?: string }) {
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] tracking-wide uppercase value-mono"
      style={{
        background: accent ? `${accent}18` : 'rgba(232,228,221,0.06)',
        color: accent ?? 'rgba(232,228,221,0.55)',
        border: `1px solid ${accent ? `${accent}40` : 'rgba(232,228,221,0.1)'}`,
      }}
    >
      {children}
    </span>
  )
}

function Section({
  title,
  accent,
  children,
  delay = 0,
}: {
  title: string
  accent: string
  children: React.ReactNode
  delay?: number
}) {
  return (
    <div
      className="thought-section"
      style={{
        animationDelay: `${delay}ms`,
        borderLeftColor: accent,
      }}
    >
      <div
        className="text-[9px] uppercase tracking-[0.18em] mb-1.5"
        style={{ color: accent }}
      >
        {title}
      </div>
      <div className="text-[12.5px] leading-relaxed" style={{ color: 'rgba(232,228,221,0.78)' }}>
        {children}
      </div>
    </div>
  )
}

export function ThoughtStream({ mind }: { mind: TurnMind }) {
  if (!mind.active) return null

  const currentIdx = stageIndex(mind.stage)
  const done = mind.completed

  return (
    <div className="thought-stream mx-auto w-full max-w-2xl">
      {/* Stage rail */}
      <div className="flex items-center gap-1 mb-4 px-1 overflow-x-auto">
        {STAGES.map((s, i) => {
          const reached = i <= currentIdx || (done && i <= STAGE_ORDER.indexOf('speak'))
          const active = s.id === mind.stage && !done
          return (
            <div key={s.id} className="flex items-center gap-1 flex-shrink-0">
              {i > 0 && (
                <div
                  className="w-3 h-px"
                  style={{
                    background: reached
                      ? 'rgba(251,191,36,0.35)'
                      : 'rgba(232,228,221,0.08)',
                  }}
                />
              )}
              <div
                className="flex items-center gap-1.5 px-2 py-1 rounded-md text-[10px] value-mono transition-all duration-500"
                style={{
                  color: active
                    ? 'rgba(251,191,36,0.95)'
                    : reached
                      ? 'rgba(232,228,221,0.55)'
                      : 'rgba(232,228,221,0.22)',
                  background: active
                    ? 'rgba(251,191,36,0.1)'
                    : reached
                      ? 'rgba(232,228,221,0.04)'
                      : 'transparent',
                  border: active
                    ? '1px solid rgba(251,191,36,0.28)'
                    : '1px solid transparent',
                }}
              >
                <span
                  className="w-1.5 h-1.5 rounded-full"
                  style={{
                    background: active
                      ? 'rgba(251,191,36,0.9)'
                      : reached
                        ? 'rgba(52,211,153,0.7)'
                        : 'rgba(232,228,221,0.15)',
                    boxShadow: active ? '0 0 8px rgba(251,191,36,0.7)' : undefined,
                  }}
                />
                {s.label}
              </div>
            </div>
          )
        })}
      </div>

      {/* Pillar cards */}
      <div
        className="rounded-2xl border overflow-hidden"
        style={{
          background: 'linear-gradient(165deg, rgba(18,16,14,0.92) 0%, rgba(8,8,10,0.95) 100%)',
          borderColor: 'rgba(251,191,36,0.12)',
          boxShadow: '0 12px 40px rgba(0,0,0,0.45), inset 0 1px 0 rgba(251,191,36,0.06)',
        }}
      >
        <div
          className="px-4 py-2.5 flex items-center justify-between border-b"
          style={{ borderColor: 'rgba(232,228,221,0.06)' }}
        >
          <div className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              {!done && (
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-40" />
              )}
              <span
                className="relative inline-flex rounded-full h-2 w-2"
                style={{
                  background: done ? 'rgba(52,211,153,0.8)' : 'rgba(251,191,36,0.9)',
                }}
              />
            </span>
            <span
              className="text-[11px] tracking-widest uppercase"
              style={{ color: 'rgba(232,228,221,0.45)' }}
            >
              {done ? (mind.skipped ? 'Chose silence' : 'Ready') : mind.stageLabel ?? 'Thinking'}
            </span>
          </div>
          <span className="text-[10px] value-mono" style={{ color: 'rgba(232,228,221,0.25)' }}>
            mind
          </span>
        </div>

        <div className="p-4 space-y-3.5">
          {mind.emotion && (
            <Section title="Insula · felt state" accent="rgba(251,113,133,0.85)" delay={0}>
              <div className="flex flex-wrap gap-1.5 mb-2">
                {mind.emotion.dominant_affect && (
                  <Pill accent="rgba(251,113,133,0.9)">{mind.emotion.dominant_affect}</Pill>
                )}
                {mind.emotion.trend && <Pill>{mind.emotion.trend}</Pill>}
                {mind.emotion.availability && <Pill>{mind.emotion.availability.replace(/_/g, ' ')}</Pill>}
              </div>
              {(mind.emotion.emotional_summary || mind.emotion.emotional_response_texturing) && (
                <p className="mb-1.5">
                  <Typewriter
                    text={
                      mind.emotion.emotional_summary ||
                      mind.emotion.emotional_response_texturing
                    }
                  />
                </p>
              )}
              {mind.emotion.somatic && (
                <p style={{ color: 'rgba(232,228,221,0.45)', fontStyle: 'italic' }}>
                  <Typewriter text={mind.emotion.somatic} speed={48} />
                </p>
              )}
              {mind.emotion.dominant_drive && (
                <p className="mt-1.5 text-[11px]" style={{ color: 'rgba(232,228,221,0.4)' }}>
                  drive · {mind.emotion.dominant_drive}
                </p>
              )}
            </Section>
          )}

          {mind.memory.length > 0 && (
            <Section title="Memory · what surfaces" accent="rgba(74,222,128,0.8)" delay={80}>
              <ul className="space-y-1.5">
                {mind.memory.slice(0, 5).map((m, i) => (
                  <li
                    key={i}
                    className="text-[11.5px] leading-snug pl-2 border-l"
                    style={{
                      borderColor:
                        m.type === 'kag'
                          ? 'rgba(167,139,250,0.4)'
                          : 'rgba(74,222,128,0.35)',
                      color: 'rgba(232,228,221,0.65)',
                    }}
                  >
                    <span
                      className="text-[9px] uppercase tracking-wider mr-1.5 value-mono"
                      style={{
                        color:
                          m.type === 'kag'
                            ? 'rgba(167,139,250,0.7)'
                            : 'rgba(74,222,128,0.7)',
                      }}
                    >
                      {m.type === 'kag' ? 'know' : m.bucket || 'recall'}
                    </span>
                    {m.text}
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {mind.context && (
            <Section title="Hippocampus · situation" accent="rgba(167,139,250,0.85)" delay={120}>
              <div className="flex flex-wrap gap-1.5 mb-2">
                {mind.context.social_context && (
                  <Pill accent="rgba(167,139,250,0.9)">{mind.context.social_context}</Pill>
                )}
                {mind.context.urgency && mind.context.urgency !== 'none' && (
                  <Pill accent="rgba(248,113,113,0.85)">urgency {mind.context.urgency}</Pill>
                )}
              </div>
              {mind.context.situational_summary && (
                <p>
                  <Typewriter text={mind.context.situational_summary.slice(0, 480)} speed={70} />
                  {mind.context.situational_summary.length > 480 ? '…' : ''}
                </p>
              )}
              {mind.context.notable && (
                <p className="mt-2 text-[11px]" style={{ color: 'rgba(251,191,36,0.7)' }}>
                  notable · {mind.context.notable}
                </p>
              )}
            </Section>
          )}

          {mind.reasoning && (
            <Section title="PFC · internal monologue" accent="rgba(251,191,36,0.9)" delay={160}>
              {mind.reasoning.internal_reaction && (
                <p
                  className="mb-2 font-medium"
                  style={{ color: 'rgba(251,191,36,0.88)', fontStyle: 'italic' }}
                >
                  “
                  <Typewriter text={mind.reasoning.internal_reaction} speed={50} />
                  ”
                </p>
              )}
              <div className="flex flex-wrap gap-1.5 mb-1.5">
                {mind.reasoning.approach && (
                  <Pill accent="rgba(251,191,36,0.9)">{mind.reasoning.approach}</Pill>
                )}
                {mind.reasoning.tone && <Pill>{mind.reasoning.tone}</Pill>}
              </div>
              {mind.reasoning.lead_with && (
                <p className="text-[11px]" style={{ color: 'rgba(232,228,221,0.4)' }}>
                  lead with · {mind.reasoning.lead_with}
                </p>
              )}
            </Section>
          )}

          {!mind.emotion && !mind.context && !mind.reasoning && mind.memory.length === 0 && (
            <div
              className="text-[12px] value-mono py-3 text-center"
              style={{ color: 'rgba(232,228,221,0.3)' }}
            >
              {mind.stageLabel ?? 'Pipeline starting'}…
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
