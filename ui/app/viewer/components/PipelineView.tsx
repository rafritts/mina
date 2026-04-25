'use client'

import React, { useEffect, useState } from 'react'

function TypewriterText({ text: rawText, speed = 45 }: { text: string; speed?: number }) {
  const text = String(rawText ?? '')
  const [count, setCount] = useState(0)

  useEffect(() => {
    if (!text) { setCount(0); return }
    setCount(0)
    let i = 0
    const iv = setInterval(() => {
      i++
      setCount(i)
      if (i >= text.length) clearInterval(iv)
    }, 1000 / speed)
    return () => clearInterval(iv)
  }, [text, speed])

  return (
    <>
      {text.slice(0, count)}
      {count < text.length && (
        <span style={{ borderRight: '1px solid currentColor', opacity: 0.6, marginLeft: 1 }} />
      )}
    </>
  )
}

export interface MemoryItem { type: 'rag' | 'kag'; text: string }
export interface LabeledField { label: string; value: string }

interface Props {
  stimulus: string | null
  memory: MemoryItem[]
  emotion: LabeledField[] | null
  context: LabeledField[] | null
  reasoning: LabeledField[] | null
  response: string | null
}

const COL_COLOR: Record<string, string> = {
  stimulus:  'rgba(96,165,250,0.7)',
  memory:    'rgba(74,222,128,0.7)',
  emotion:   'rgba(251,113,133,0.7)',
  context:   'rgba(167,139,250,0.7)',
  reasoning: 'rgba(248,200,79,0.7)',
}

function ColHeader({ label, col }: { label: string; col: string }) {
  return (
    <div style={{
      fontSize: 9,
      letterSpacing: '0.18em',
      textTransform: 'uppercase' as const,
      color: COL_COLOR[col],
      marginBottom: 12,
      paddingBottom: 6,
      borderBottom: `1px solid ${COL_COLOR[col].replace('0.7', '0.18')}`,
    }}>
      {label}
    </div>
  )
}

function FieldRow({ label, value }: LabeledField) {
  return (
    <div style={{ marginBottom: 9 }}>
      <div style={{
        fontSize: 8,
        letterSpacing: '0.1em',
        textTransform: 'uppercase' as const,
        color: 'rgba(232,228,221,0.28)',
        marginBottom: 2,
      }}>
        {label}
      </div>
      <div style={{
        fontSize: 11,
        lineHeight: 1.5,
        color: 'rgba(232,228,221,0.75)',
        fontFamily: 'var(--font-geist-mono)',
        wordBreak: 'break-word' as const,
      }}>
        <TypewriterText key={value} text={value} />
      </div>
    </div>
  )
}

const COL_PANEL: React.CSSProperties = {
  flex: 1,
  minWidth: 0,
  background: 'rgba(5,5,5,0.62)',
  backdropFilter: 'blur(14px)',
  WebkitBackdropFilter: 'blur(14px)',
  border: '1px solid rgba(232,228,221,0.05)',
  borderRadius: 8,
  padding: '14px 16px',
}

export function PipelineView({ stimulus, memory, emotion, context, reasoning, response }: Props) {
  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      zIndex: 10,
      pointerEvents: 'none',
      display: 'flex',
      flexDirection: 'column',
      padding: '36px 36px 44px',
      gap: 28,
    }}>
      {/* Five columns */}
      <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start', flex: 1, minHeight: 0 }}>

        {/* Stimulus */}
        <div style={COL_PANEL}>
          <ColHeader label="Stimulus" col="stimulus" />
          {stimulus && (
            <div style={{
              fontSize: 11,
              lineHeight: 1.55,
              color: 'rgba(232,228,221,0.75)',
              fontFamily: 'var(--font-geist-mono)',
              wordBreak: 'break-word',
            }}>
              <TypewriterText key={stimulus} text={stimulus} />
            </div>
          )}
        </div>

        {/* Memory */}
        <div style={COL_PANEL}>
          <ColHeader label="Memory" col="memory" />
          {memory.map((item, i) => (
            <div key={i} style={{ marginBottom: 9 }}>
              <div style={{ fontSize: 8, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'rgba(232,228,221,0.28)', marginBottom: 2 }}>
                {item.type === 'kag' ? 'knowledge' : 'recall'}
              </div>
              <div style={{ fontSize: 11, lineHeight: 1.5, color: 'rgba(232,228,221,0.75)', fontFamily: 'var(--font-geist-mono)', wordBreak: 'break-word' }}>
                <TypewriterText key={`${i}-${item.text.slice(0, 20)}`} text={item.text} />
              </div>
            </div>
          ))}
        </div>

        {/* Emotion */}
        <div style={COL_PANEL}>
          <ColHeader label="Emotional" col="emotion" />
          {emotion?.map(f => <FieldRow key={f.label} {...f} />)}
        </div>

        {/* Context */}
        <div style={COL_PANEL}>
          <ColHeader label="Context" col="context" />
          {context?.map(f => <FieldRow key={f.label} {...f} />)}
        </div>

        {/* Reasoning */}
        <div style={COL_PANEL}>
          <ColHeader label="Conversational" col="reasoning" />
          {reasoning?.map(f => <FieldRow key={f.label} {...f} />)}
        </div>
      </div>

      {/* Response */}
      {response !== null && (
        <div style={{ alignSelf: 'center', width: '100%', maxWidth: 660 }}>
          <div style={{
            background: 'rgba(5,5,5,0.62)',
            border: '1px solid rgba(232,228,221,0.05)',
            backdropFilter: 'blur(12px)',
            WebkitBackdropFilter: 'blur(12px)',
            borderRadius: 10,
            padding: '14px 20px',
          }}>
            <div style={{
              fontSize: 9,
              letterSpacing: '0.15em',
              textTransform: 'uppercase',
              color: 'rgba(232,228,221,0.28)',
              marginBottom: 8,
            }}>
              Response
            </div>
            <div style={{
              fontSize: 14,
              lineHeight: 1.65,
              color: 'rgba(232,228,221,0.9)',
              fontFamily: 'var(--font-geist-sans)',
              wordBreak: 'break-word',
            }}>
              <TypewriterText key={response} text={response} speed={35} />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
