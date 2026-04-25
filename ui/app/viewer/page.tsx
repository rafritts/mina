'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { ViewerTopology } from './components/ViewerTopology'
import { PipelineView, type MemoryItem, type LabeledField } from './components/PipelineView'
import { useStream, type StreamEvent } from '../lib/stream'


export default function ViewerPage() {
  const [chemicals, setChemicals] = useState<Record<string, number> | null>(null)
  const [pulseChemicals, setPulseChemicals] = useState<string[] | null>(null)

  const [stimulus, setStimulus] = useState<string | null>(null)
  const [memory, setMemory] = useState<MemoryItem[]>([])
  const [emotion, setEmotion] = useState<LabeledField[] | null>(null)
  const [context, setContext] = useState<LabeledField[] | null>(null)
  const [reasoning, setReasoning] = useState<LabeledField[] | null>(null)
  const [response, setResponse] = useState<string | null>(null)
  // rag/kag events arrive before stimulus_land — buffer them and flush on landing
  const memoryBufferRef = useRef<MemoryItem[]>([])

  // Performance mode — defaults to minimal; only goes full if user explicitly saved 'full'
  const [lowPower, setLowPower] = useState<boolean>(() => {
    if (typeof window === 'undefined') return true
    return localStorage.getItem('viewerMode') !== 'full'
  })

  const handleLowPower = useCallback(() => {
    setLowPower(true)
    localStorage.setItem('viewerMode', 'low')
  }, [])

  const toggleLowPower = useCallback(() => {
    setLowPower(prev => {
      const next = !prev
      localStorage.setItem('viewerMode', next ? 'low' : 'full')
      return next
    })
  }, [])

  // Hamburger visibility
  const [hamburgerVisible, setHamburgerVisible] = useState(false)
  const [navOpen, setNavOpen] = useState(false)
  const inactivityRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const onMouseMove = useCallback(() => {
    setHamburgerVisible(true)
    if (inactivityRef.current) clearTimeout(inactivityRef.current)
    inactivityRef.current = setTimeout(() => setHamburgerVisible(false), 2000)
  }, [])

  useEffect(() => {
    window.addEventListener('mousemove', onMouseMove)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      if (inactivityRef.current) clearTimeout(inactivityRef.current)
    }
  }, [onMouseMove])

  const handleEvent = useCallback((event: StreamEvent) => {
    switch (event.type) {
      case 'state_snapshot':
        setChemicals(event.payload.chemicals)
        break

      case 'delta':
        setPulseChemicals(Object.keys(event.payload.deltas))
        break

      case 'stimulus_land':
        // Flush buffered rag/kag that arrived before this stimulus, then reset other columns
        setStimulus(event.payload.preview)
        setMemory(memoryBufferRef.current)
        memoryBufferRef.current = []
        setEmotion(null)
        setContext(null)
        setReasoning(null)
        setResponse(null)
        break

      case 'context_pillar': {
        const p = event.payload
        const fields: LabeledField[] = [{ label: 'context', value: p.social_context }]
        if (p.urgency && p.urgency !== 'none') fields.push({ label: 'urgency', value: p.urgency })
        if (p.situational_summary) fields.push({ label: 'situation', value: p.situational_summary })
        if (p.notable) fields.push({ label: 'notable', value: p.notable })
        setContext(fields)
        break
      }

      case 'rag_hit':
        memoryBufferRef.current.push({ type: 'rag', text: event.payload.excerpt })
        break

      case 'kag_selection':
        memoryBufferRef.current.push({ type: 'kag', text: event.payload.filename })
        break

      case 'emotion_pillar': {
        const p = event.payload
        const fields: LabeledField[] = [
          { label: 'affect', value: `${p.dominant_affect} · ${p.trend}` },

          { label: 'avail', value: p.availability },
        ]
        if (p.dominant_drive) fields.push({ label: 'drive', value: p.dominant_drive })
        if (p.emotional_response_texturing) fields.push({ label: 'texture', value: p.emotional_response_texturing })
        setEmotion(fields)
        break
      }

      case 'reasoning': {
        const p = event.payload
        const fields: LabeledField[] = [{ label: 'approach', value: p.approach }]
        if (p.tone) fields.push({ label: 'tone', value: p.tone })
        if (p.internal_reaction) fields.push({ label: 'reaction', value: p.internal_reaction })
        setReasoning(fields)
        break
      }

      case 'response_complete':
        setResponse(event.payload.text)
        break
    }
  }, [])

  useStream(handleEvent)

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: '#050505',
        overflow: 'hidden',
      }}
      onMouseMove={onMouseMove}
    >
      {/* Layer 0: Vanta topology */}
      <ViewerTopology
        chemicals={chemicals}
        pulseChemicals={pulseChemicals}
        lowPower={lowPower}
        onLowPower={handleLowPower}
      />

      {/* Layer 1: Pipeline columns */}
      <PipelineView
        stimulus={stimulus}
        memory={memory}
        emotion={emotion}
        context={context}
        reasoning={reasoning}
        response={response}
      />

      {/* Layer 2: Hamburger + nav */}
      <div
        style={{
          position: 'fixed',
          bottom: 24,
          left: 24,
          zIndex: 20,
          opacity: hamburgerVisible ? 1 : 0,
          transition: 'opacity 0.4s',
          pointerEvents: hamburgerVisible ? 'auto' : 'none',
        }}
      >
        <button
          onClick={() => setNavOpen(o => !o)}
          style={{
            width: 36,
            height: 36,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'rgba(4,4,4,0.75)',
            border: '1px solid rgba(232,228,221,0.1)',
            borderRadius: 6,
            color: 'rgba(232,228,221,0.5)',
            fontSize: 16,
            cursor: 'pointer',
            backdropFilter: 'blur(12px)',
            WebkitBackdropFilter: 'blur(12px)',
          }}
          aria-label="Toggle navigation"
        >
          ≡
        </button>
      </div>

      {/* Slide-in nav */}
      <div
        style={{
          position: 'fixed',
          bottom: 0,
          left: 0,
          top: 0,
          width: 200,
          zIndex: 30,
          transform: navOpen ? 'translateX(0)' : 'translateX(-100%)',
          transition: 'transform 0.25s ease',
          background: 'rgba(4,4,4,0.85)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          borderRight: '1px solid rgba(232,228,221,0.06)',
          display: 'flex',
          flexDirection: 'column',
          padding: '24px 16px',
          gap: 8,
        }}
      >
        <div
          style={{
            fontSize: 10,
            letterSpacing: '0.15em',
            textTransform: 'uppercase',
            color: 'rgba(232,228,221,0.25)',
            marginBottom: 12,
          }}
        >
          Mina
        </div>
        <Link
          href="/admin"
          style={{
            fontSize: 13,
            color: 'rgba(232,228,221,0.55)',
            padding: '6px 10px',
            borderRadius: 6,
            textDecoration: 'none',
          }}
        >
          Admin
        </Link>

        <div style={{
          marginTop: 8,
          paddingTop: 8,
          borderTop: '1px solid rgba(232,228,221,0.06)',
        }}>
          <div style={{
            fontSize: 9,
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            color: 'rgba(232,228,221,0.2)',
            marginBottom: 10,
          }}>
            Graphics
          </div>
          {/* Toggle row */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '2px 2px' }}>
            <span style={{ fontSize: 12, color: 'rgba(232,228,221,0.45)' }}>
              Full effects
            </span>
            <button
              onClick={toggleLowPower}
              aria-label="Toggle graphics mode"
              style={{
                position: 'relative',
                width: 36,
                height: 20,
                borderRadius: 10,
                border: 'none',
                cursor: 'pointer',
                padding: 0,
                background: lowPower ? 'rgba(232,228,221,0.12)' : 'rgba(96,165,250,0.55)',
                transition: 'background 0.25s ease',
                flexShrink: 0,
              }}
            >
              <span style={{
                position: 'absolute',
                top: 3,
                left: lowPower ? 3 : 17,
                width: 14,
                height: 14,
                borderRadius: '50%',
                background: lowPower ? 'rgba(232,228,221,0.35)' : 'rgba(232,228,221,0.9)',
                transition: 'left 0.2s ease, background 0.25s ease',
              }} />
            </button>
          </div>
        </div>

        <button
          onClick={() => setNavOpen(false)}
          style={{
            position: 'absolute',
            bottom: 24,
            left: 16,
            background: 'none',
            border: 'none',
            color: 'rgba(232,228,221,0.25)',
            fontSize: 11,
            cursor: 'pointer',
            padding: 0,
          }}
        >
          close
        </button>
      </div>

      {/* Backdrop for nav */}
      {navOpen && (
        <div
          style={{ position: 'fixed', inset: 0, zIndex: 25 }}
          onClick={() => setNavOpen(false)}
        />
      )}

      {/* Blink keyframe */}
      <style>{`
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
      `}</style>
    </div>
  )
}
