'use client'

import { useEffect, useRef, useState } from 'react'
import {
  forceSimulation,
  forceManyBody,
  forceCenter,
  forceX,
  forceY,
  forceCollide,
  type Simulation,
} from 'd3-force'

export type NodeType = 'response' | 'stimulus' | 'context' | 'rag' | 'kag' | 'emotion' | 'reasoning'

export interface GraphField {
  label: string
  value: string
}

export interface GraphNode {
  id: string
  type: NodeType
  text?: string       // plain text (response/stimulus/rag/kag)
  fields?: GraphField[] // structured rows (context/emotion/reasoning)
  opacity: number
}

export interface GraphEdge {
  source: string
  target: string
}

// D3 internal node — mutated in place by the simulation
interface D3Node {
  id: string
  type: NodeType
  text?: string
  fields?: GraphField[]
  x: number
  y: number
  vx: number
  vy: number
  fx: number | null
  fy: number | null
  opacity: number
}

// Cluster target offsets (fraction of viewport half-size)
const CLUSTER_OFFSET: Record<NodeType, [number, number]> = {
  response:  [0,      0     ],
  stimulus:  [0,     -0.5   ],
  context:   [0.5,   -0.3   ],
  rag:       [-0.55,  0.1   ],
  kag:       [0.55,   0.1   ],
  emotion:   [-0.4,   0.45  ],
  reasoning: [0.4,    0.45  ],
}

const NODE_COLORS: Record<NodeType, string> = {
  response:  'rgba(255,255,255,0.08)',
  stimulus:  'rgba(96,165,250,0.18)',
  context:   'rgba(167,139,250,0.18)',
  rag:       'rgba(74,222,128,0.18)',
  kag:       'rgba(45,212,191,0.18)',
  emotion:   'rgba(251,113,133,0.18)',
  reasoning: 'rgba(248,200,79,0.18)',
}

const NODE_BORDER: Record<NodeType, string> = {
  response:  'rgba(255,255,255,0.22)',
  stimulus:  'rgba(96,165,250,0.45)',
  context:   'rgba(167,139,250,0.45)',
  rag:       'rgba(74,222,128,0.45)',
  kag:       'rgba(45,212,191,0.45)',
  emotion:   'rgba(251,113,133,0.45)',
  reasoning: 'rgba(248,200,79,0.45)',
}

interface Props {
  nodes: GraphNode[]
  edges: GraphEdge[]
  typewriterText: string
  isTyping: boolean
}

export function ThoughtGraph({ nodes, edges, typewriterText, isTyping }: Props) {
  const [, setRenderTick] = useState(0)
  const d3NodesRef = useRef<D3Node[]>([])
  const simRef = useRef<Simulation<D3Node, undefined> | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const rafRef = useRef<number>(0)

  // RAF loop: manually tick simulation; reheat every 8s so nodes never fully settle
  useEffect(() => {
    let lastReheat = performance.now()
    function frame(now: number) {
      rafRef.current = requestAnimationFrame(frame)
      const sim = simRef.current
      if (!sim) return

      if (now - lastReheat > 8000) {
        lastReheat = now
        if (sim.alpha() < 0.05) sim.alpha(0.05)
      }

      const simHot = sim.alpha() > sim.alphaMin()
      if (simHot) sim.tick()

      // Always clamp — even after sim cools, spawned nodes may sit outside bounds
      const el = containerRef.current
      const W = el?.clientWidth ?? window.innerWidth
      const H = el?.clientHeight ?? window.innerHeight
      const PADX = 120   // card half-width (100) + 20px margin
      const PADY = 90    // generous vertical margin for tall cards
      let clamped = false
      for (const node of d3NodesRef.current) {
        const cx = Math.max(PADX, Math.min(W - PADX, node.x))
        const cy = Math.max(PADY, Math.min(H - PADY, node.y))
        if (cx !== node.x || cy !== node.y) { node.x = cx; node.y = cy; clamped = true }
      }

      if (simHot || clamped) setRenderTick(t => t + 1)
    }
    rafRef.current = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(rafRef.current)
  }, [])

  // Rebuild D3 nodes and simulation whenever the node list changes
  useEffect(() => {
    const el = containerRef.current
    const halfW = (el?.clientWidth ?? window.innerWidth) / 2
    const halfH = (el?.clientHeight ?? window.innerHeight) / 2

    const incomingIds = new Set(nodes.map(n => n.id))
    const existingMap = new Map(d3NodesRef.current.map(n => [n.id, n]))

    const nextD3: D3Node[] = nodes.map(n => {
      const existing = existingMap.get(n.id)
      const [ox, oy] = CLUSTER_OFFSET[n.type]
      if (existing) {
        existing.opacity = n.opacity
        existing.text = n.text
        existing.fields = n.fields
        return existing
      }
      return {
        id: n.id,
        type: n.type,
        text: n.text,
        fields: n.fields,
        opacity: n.opacity,
        // Wider jitter so siblings within a cluster spread out on spawn
        x: halfW + ox * halfW + (Math.random() - 0.5) * 120,
        y: halfH + oy * halfH + (Math.random() - 0.5) * 120,
        vx: 0, vy: 0,
        fx: null,
        fy: null,
      }
    })

    d3NodesRef.current = nextD3.filter(n => incomingIds.has(n.id))

    // Clamp initial spawn positions before first render
    const W0 = el?.clientWidth ?? window.innerWidth
    const H0 = el?.clientHeight ?? window.innerHeight
    for (const node of d3NodesRef.current) {
      node.x = Math.max(120, Math.min(W0 - 120, node.x))
      node.y = Math.max(90, Math.min(H0 - 90, node.y))
    }

    simRef.current?.stop()

    if (d3NodesRef.current.length === 0) {
      simRef.current = null
      return
    }

    const PAD = 140
    const clampX = (x: number) => Math.max(PAD, Math.min(halfW * 2 - PAD, x))
    const clampY = (y: number) => Math.max(PAD, Math.min(halfH * 2 - PAD, y))

    simRef.current = forceSimulation<D3Node>(d3NodesRef.current)
      .force('charge', forceManyBody<D3Node>().strength(-400))
      .force('center', forceCenter(halfW, halfH).strength(0.01))
      .force('collide', forceCollide<D3Node>(160))
      .force('cx', forceX<D3Node>(n => clampX(halfW + CLUSTER_OFFSET[n.type][0] * halfW)).strength(n => n.type === 'response' ? 0.2 : 0.05))
      .force('cy', forceY<D3Node>(n => clampY(halfH + CLUSTER_OFFSET[n.type][1] * halfH)).strength(n => n.type === 'response' ? 0.2 : 0.05))
      .alphaDecay(0.02)
      .stop()

    setRenderTick(t => t + 1)
  }, [nodes])

  useEffect(() => {
    function onResize() { simRef.current?.alpha(0.3).restart() }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  // Build a lookup map for edge rendering
  const d3Map = new Map(d3NodesRef.current.map(n => [n.id, n]))

  return (
    <div
      ref={containerRef}
      style={{ position: 'fixed', inset: 0, zIndex: 10, pointerEvents: 'none' }}
    >
      {/* Edges */}
      <svg
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', overflow: 'visible' }}
      >
        {edges.map(edge => {
          const src = d3Map.get(edge.source)
          const tgt = d3Map.get(edge.target)
          if (!src || !tgt) return null
          return (
            <line
              key={`${edge.source}→${edge.target}`}
              x1={src.x} y1={src.y}
              x2={tgt.x} y2={tgt.y}
              stroke="rgba(255,255,255,0.15)"
              strokeWidth={1}
              style={{ opacity: Math.min(src.opacity, tgt.opacity) }}
            />
          )
        })}
      </svg>

      {/* Node cards */}
      {d3NodesRef.current.map(node => {
        const isResponse = node.type === 'response'
        const hasFields = !isResponse && node.fields && node.fields.length > 0
        const w = isResponse ? 460 : 240

        return (
          <div
            key={node.id}
            style={{
              position: 'absolute',
              left: node.x - w / 2,
              top: node.y - (isResponse ? 70 : 50),
              width: w,
              opacity: node.opacity,
              transition: 'opacity 0.3s',
              pointerEvents: 'none',
              background: NODE_COLORS[node.type],
              border: `1px solid ${NODE_BORDER[node.type]}`,
              backdropFilter: 'blur(10px)',
              WebkitBackdropFilter: 'blur(10px)',
              borderRadius: 8,
              padding: isResponse ? '14px 18px' : '10px 14px',
            }}
          >
            {/* Card header */}
            <div style={{
              fontSize: 9,
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
              color: 'rgba(232,228,221,0.35)',
              marginBottom: isResponse ? 8 : 6,
            }}>
              {node.type}
            </div>

            {/* Structured fields */}
            {hasFields && node.fields!.map((f, i) => (
              <div key={i} style={{
                display: 'flex',
                gap: 8,
                marginBottom: i < node.fields!.length - 1 ? 4 : 0,
                alignItems: 'flex-start',
              }}>
                <span style={{
                  fontSize: 9,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  color: 'rgba(232,228,221,0.3)',
                  whiteSpace: 'nowrap',
                  paddingTop: 1,
                  minWidth: 64,
                }}>
                  {f.label}
                </span>
                <span style={{
                  fontSize: 11,
                  lineHeight: 1.45,
                  color: 'rgba(232,228,221,0.75)',
                  fontFamily: 'var(--font-geist-mono)',
                  wordBreak: 'break-word',
                }}>
                  {f.value}
                </span>
              </div>
            ))}

            {/* Plain text (response / stimulus / rag / kag) */}
            {!hasFields && (
              <div style={{
                fontSize: isResponse ? 13 : 11,
                lineHeight: isResponse ? 1.65 : 1.5,
                color: isResponse ? 'rgba(232,228,221,0.9)' : 'rgba(232,228,221,0.7)',
                fontFamily: isResponse ? 'var(--font-geist-sans)' : 'var(--font-geist-mono)',
                wordBreak: 'break-word',
                whiteSpace: 'pre-wrap',
              }}>
                {(isResponse ? typewriterText : node.text) || ' '}
                {isResponse && isTyping && (
                  <span style={{
                    borderRight: '2px solid rgba(232,228,221,0.7)',
                    marginLeft: 1,
                    animation: 'blink 1s step-end infinite',
                  }} />
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
