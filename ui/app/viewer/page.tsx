'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { ViewerTopology } from './components/ViewerTopology'
import { ThoughtGraph, type GraphNode, type NodeType } from './components/ThoughtGraph'
import { useStream, type StreamEvent } from '../lib/stream'

// Typewriter at ~35 chars/sec
const TYPEWRITER_INTERVAL = Math.round(1000 / 35)

let nodeCounter = 0
function nextId(type: NodeType) { return `${type}-${++nodeCounter}` }

export default function ViewerPage() {
  const [chemicals, setChemicals] = useState<Record<string, number> | null>(null)
  const [pulseChemicals, setPulseChemicals] = useState<string[] | null>(null)

  const [nodes, setNodes] = useState<GraphNode[]>([])
  const [typewriterText, setTypewriterText] = useState('')
  const [isTyping, setIsTyping] = useState(false)
  const typewriterRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const fullResponseRef = useRef('')

  // Hamburger visibility
  const [hamburgerVisible, setHamburgerVisible] = useState(false)
  const [navOpen, setNavOpen] = useState(false)
  const inactivityRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Nav slide in/out
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

  // Cancel typewriter and start a new one
  const startTypewriter = useCallback((text: string) => {
    if (typewriterRef.current) clearInterval(typewriterRef.current)
    fullResponseRef.current = text
    let i = 0
    setTypewriterText('')
    setIsTyping(true)

    typewriterRef.current = setInterval(() => {
      i++
      setTypewriterText(text.slice(0, i))
      if (i >= text.length) {
        clearInterval(typewriterRef.current!)
        typewriterRef.current = null
        setIsTyping(false)
      }
    }, TYPEWRITER_INTERVAL)
  }, [])

  // Fade out all non-response nodes and clear them after transition
  const startNewCycle = useCallback((firstNode: GraphNode) => {
    if (typewriterRef.current) {
      clearInterval(typewriterRef.current)
      typewriterRef.current = null
      setIsTyping(false)
    }
    setTypewriterText('')

    setNodes(prev => prev.map(n => ({ ...n, opacity: 0 })))
    setTimeout(() => {
      setNodes([firstNode])
    }, 500)
  }, [])

  const handleEvent = useCallback((event: StreamEvent) => {
    switch (event.type) {
      case 'state_snapshot':
        setChemicals(event.payload.chemicals)
        break

      case 'delta':
        setPulseChemicals(Object.keys(event.payload.deltas))
        break

      case 'stimulus_land': {
        const node: GraphNode = {
          id: nextId('stimulus'),
          type: 'stimulus',
          text: event.payload.preview,
          opacity: 1,
        }
        startNewCycle(node)
        break
      }

      case 'context_pillar': {
        const parts = [event.payload.social_context]
        if (event.payload.urgency !== 'none') parts.push(`urgency: ${event.payload.urgency}`)
        if (event.payload.situational_summary) parts.push(event.payload.situational_summary)
        if (event.payload.notable) parts.push(`↳ ${event.payload.notable}`)
        const node: GraphNode = {
          id: nextId('context'),
          type: 'context',
          text: parts.join('\n'),
          opacity: 1,
        }
        setNodes(prev => [...prev.filter(n => n.type !== 'context'), node])
        break
      }

      case 'rag_hit': {
        const node: GraphNode = {
          id: nextId('rag'),
          type: 'rag',
          text: event.payload.excerpt,
          opacity: 1,
        }
        setNodes(prev => [...prev, node])
        break
      }

      case 'kag_selection': {
        const node: GraphNode = {
          id: nextId('kag'),
          type: 'kag',
          text: event.payload.filename,
          opacity: 1,
        }
        setNodes(prev => [...prev, node])
        break
      }

      case 'emotion_pillar': {
        const parts = [`${event.payload.dominant_affect} · ${event.payload.trend}`]
        if (event.payload.dominant_drive) parts.push(event.payload.dominant_drive)
        if (event.payload.emotional_response_texturing) parts.push(event.payload.emotional_response_texturing)
        const node: GraphNode = {
          id: nextId('emotion'),
          type: 'emotion',
          text: parts.join('\n'),
          opacity: 1,
        }
        setNodes(prev => [...prev.filter(n => n.type !== 'emotion'), node])
        break
      }

      case 'reasoning': {
        const parts = [event.payload.tone
          ? `${event.payload.approach} · ${event.payload.tone}`
          : event.payload.approach]
        if (event.payload.internal_reaction) parts.push(event.payload.internal_reaction)
        const node: GraphNode = {
          id: nextId('reasoning'),
          type: 'reasoning',
          text: parts.join('\n'),
          opacity: 1,
        }
        setNodes(prev => [...prev.filter(n => n.type !== 'reasoning'), node])
        break
      }

      case 'response_complete': {
        const responseNode: GraphNode = {
          id: nextId('response'),
          type: 'response',
          text: event.payload.text,
          opacity: 1,
        }
        setNodes(prev => [...prev.filter(n => n.type !== 'response'), responseNode])
        startTypewriter(event.payload.text)
        break
      }
    }
  }, [startNewCycle, startTypewriter])

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
      <ViewerTopology chemicals={chemicals} pulseChemicals={pulseChemicals} />

      {/* Layer 1: Thought graph */}
      <ThoughtGraph
        nodes={nodes}
        typewriterText={typewriterText}
        isTyping={isTyping}
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
