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

const STAGE_ORDER = STAGES.map((s) => s.id)

function stageIndex(id: PillarStageId | null): number {
  if (!id) return -1
  return STAGE_ORDER.indexOf(id)
}

function Typewriter({ text, speed = 58 }: { text: string; speed?: number }) {
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
        <span
          className="inline-block w-px h-3 ml-0.5 align-middle opacity-50"
          style={{ background: 'currentColor' }}
        />
      )}
    </>
  )
}

function Chip({ children }: { children: React.ReactNode }) {
  return <span className="chip">{children}</span>
}

function Section({
  title,
  tone,
  children,
}: {
  title: string
  tone: 'feel' | 'memory' | 'situate' | 'decide'
  children: React.ReactNode
}) {
  return (
    <div className="mind-section" data-tone={tone}>
      <div className="label mb-1.5" style={{ color: 'inherit', opacity: 0.75 }}>
        {title}
      </div>
      <div className="text-[13px] leading-relaxed text-secondary">{children}</div>
    </div>
  )
}

export function ThoughtStream({ mind }: { mind: TurnMind }) {
  if (!mind.active) return null

  const currentIdx = stageIndex(mind.stage)
  const done = mind.completed
  const head =
    done
      ? mind.skipped
        ? 'Chose silence'
        : 'Ready'
      : mind.stageLabel ?? 'Thinking'

  return (
    <div className="w-full max-w-2xl mx-auto">
      <div className="mind-stage-rail">
        {STAGES.map((s, i) => {
          const reached = i <= currentIdx || (done && i <= STAGE_ORDER.indexOf('speak'))
          const active = s.id === mind.stage && !done
          return (
            <div key={s.id} className="flex items-center gap-1 shrink-0">
              {i > 0 && (
                <div
                  className="w-2.5 h-px"
                  style={{
                    background: reached ? 'var(--accent-border)' : 'var(--border-subtle)',
                  }}
                />
              )}
              <div
                className="mind-stage"
                data-reached={reached ? 'true' : 'false'}
                data-active={active ? 'true' : 'false'}
              >
                <span className="dot" style={{ width: 5, height: 5 }} />
                {s.label}
              </div>
            </div>
          )
        })}
      </div>

      <div className="mind">
        <div className="mind-head">
          <div className="flex items-center gap-2">
            <span
              className="status-pill"
              data-tone={done ? 'live' : 'busy'}
            >
              <span className={`dot ${done ? '' : 'dot-pulse'}`} />
              {head}
            </span>
          </div>
          <span className="label">Mind</span>
        </div>

        <div className="mind-body">
          {mind.emotion && (
            <Section title="Insula · felt state" tone="feel">
              <div className="flex flex-wrap gap-1.5 mb-2">
                {mind.emotion.dominant_affect && (
                  <Chip>{mind.emotion.dominant_affect}</Chip>
                )}
                {mind.emotion.trend && <Chip>{mind.emotion.trend}</Chip>}
                {mind.emotion.availability && (
                  <Chip>{mind.emotion.availability.replace(/_/g, ' ')}</Chip>
                )}
              </div>
              {(mind.emotion.emotional_summary ||
                mind.emotion.emotional_response_texturing) && (
                <p className="m-0 mb-1.5">
                  <Typewriter
                    text={
                      mind.emotion.emotional_summary ||
                      mind.emotion.emotional_response_texturing
                    }
                  />
                </p>
              )}
              {mind.emotion.somatic && (
                <p className="m-0 text-muted italic text-[12.5px]">
                  <Typewriter text={mind.emotion.somatic} speed={48} />
                </p>
              )}
              {mind.emotion.dominant_drive && (
                <p className="m-0 mt-1.5 text-[11.5px] text-muted">
                  drive · {mind.emotion.dominant_drive}
                </p>
              )}
            </Section>
          )}

          {mind.memory.length > 0 && (
            <Section title="Memory · what surfaces" tone="memory">
              <ul className="m-0 p-0 list-none space-y-1.5">
                {mind.memory.slice(0, 5).map((m, i) => (
                  <li
                    key={i}
                    className="text-[12.5px] leading-snug pl-2 border-l"
                    style={{
                      borderColor:
                        m.type === 'kag' ? 'rgba(179,157,240,0.45)' : 'var(--success-border)',
                      color: 'var(--text-secondary)',
                    }}
                  >
                    <span className="label mr-1.5 inline">
                      {m.type === 'kag' ? 'know' : m.bucket || 'recall'}
                    </span>
                    {m.text}
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {mind.context && (
            <Section title="Hippocampus · situation" tone="situate">
              <div className="flex flex-wrap gap-1.5 mb-2">
                {mind.context.social_context && (
                  <Chip>{mind.context.social_context}</Chip>
                )}
                {mind.context.urgency && mind.context.urgency !== 'none' && (
                  <Chip>urgency {mind.context.urgency}</Chip>
                )}
              </div>
              {mind.context.situational_summary && (
                <p className="m-0">
                  <Typewriter
                    text={mind.context.situational_summary.slice(0, 480)}
                    speed={72}
                  />
                  {mind.context.situational_summary.length > 480 ? '…' : ''}
                </p>
              )}
              {mind.context.notable && (
                <p className="m-0 mt-2 text-[12px]" style={{ color: 'var(--accent-bright)' }}>
                  notable · {mind.context.notable}
                </p>
              )}
            </Section>
          )}

          {mind.reasoning && (
            <Section title="PFC · internal monologue" tone="decide">
              {mind.reasoning.internal_reaction && (
                <p
                  className="m-0 mb-2 font-medium italic"
                  style={{ color: 'var(--accent-bright)' }}
                >
                  “
                  <Typewriter text={mind.reasoning.internal_reaction} speed={50} />
                  ”
                </p>
              )}
              <div className="flex flex-wrap gap-1.5 mb-1">
                {mind.reasoning.approach && <Chip>{mind.reasoning.approach}</Chip>}
                {mind.reasoning.tone && <Chip>{mind.reasoning.tone}</Chip>}
              </div>
              {mind.reasoning.lead_with && (
                <p className="m-0 text-[11.5px] text-muted">
                  lead with · {mind.reasoning.lead_with}
                </p>
              )}
            </Section>
          )}

          {!mind.emotion &&
            !mind.context &&
            !mind.reasoning &&
            mind.memory.length === 0 && (
              <p className="m-0 text-center text-[12px] mono text-faint py-2">
                {mind.stageLabel ?? 'Pipeline starting'}…
              </p>
            )}
        </div>
      </div>
    </div>
  )
}
