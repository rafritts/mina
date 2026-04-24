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

export interface GraphNode {
  id: string
  type: NodeType
  text: string
  opacity: number
}

// D3 internal node — mutated in place by the simulation
interface D3Node {
  id: string
  type: NodeType
  text: string
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
  typewriterText: string
  isTyping: boolean
}

export function ThoughtGraph({ nodes, typewriterText, isTyping }: Props) {
  // Render tick — incremented from the RAF loop to force re-renders while sim is hot
  const [, setRenderTick] = useState(0)
  const d3NodesRef = useRef<D3Node[]>([])
  const simRef = useRef<Simulation<D3Node, undefined> | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const rafRef = useRef<number>(0)

  // RAF loop: manually tick the simulation and trigger re-renders while hot
  useEffect(() => {
    function frame() {
      rafRef.current = requestAnimationFrame(frame)
      const sim = simRef.current
      if (!sim) return
      if (sim.alpha() > sim.alphaMin()) {
        sim.tick()
        setRenderTick(t => t + 1)
      }
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
        return existing
      }
      return {
        id: n.id,
        type: n.type,
        text: n.text,
        opacity: n.opacity,
        x: halfW + ox * halfW + (Math.random() - 0.5) * 60,
        y: halfH + oy * halfH + (Math.random() - 0.5) * 60,
        vx: 0, vy: 0,
        fx: n.type === 'response' ? halfW : null,
        fy: n.type === 'response' ? halfH : null,
      }
    })

    d3NodesRef.current = nextD3.filter(n => incomingIds.has(n.id))

    // Stop previous sim before creating a new one
    simRef.current?.stop()

    if (d3NodesRef.current.length === 0) {
      simRef.current = null
      return
    }

    // Create simulation in stopped state — the RAF loop ticks it manually
    simRef.current = forceSimulation<D3Node>(d3NodesRef.current)
      .force('charge', forceManyBody<D3Node>().strength(-200))
      .force('center', forceCenter(halfW, halfH).strength(0.02))
      .force('collide', forceCollide<D3Node>(80))
      .force('cx', forceX<D3Node>(n => halfW + CLUSTER_OFFSET[n.type][0] * halfW).strength(0.1))
      .force('cy', forceY<D3Node>(n => halfH + CLUSTER_OFFSET[n.type][1] * halfH).strength(0.1))
      .alphaDecay(0.02)
      .stop()  // do NOT auto-start — RAF loop drives it

    // Kick off the RAF loop render immediately
    setRenderTick(t => t + 1)
  }, [nodes])

  // Fix response node at center on resize
  useEffect(() => {
    function onResize() {
      const el = containerRef.current
      const halfW = (el?.clientWidth ?? window.innerWidth) / 2
      const halfH = (el?.clientHeight ?? window.innerHeight) / 2
      const node = d3NodesRef.current.find(n => n.type === 'response')
      if (node) { node.fx = halfW; node.fy = halfH }
      simRef.current?.alpha(0.3).restart()
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const responseNode = d3NodesRef.current.find(n => n.type === 'response')
  const inputNodes = d3NodesRef.current.filter(n => n.type !== 'response')

  return (
    <div
      ref={containerRef}
      style={{ position: 'fixed', inset: 0, zIndex: 10, pointerEvents: 'none' }}
    >
      {/* Edges */}
      <svg
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', overflow: 'visible' }}
      >
        {responseNode && inputNodes.map(n => (
          <line
            key={`edge-${n.id}`}
            x1={responseNode.x}
            y1={responseNode.y}
            x2={n.x}
            y2={n.y}
            stroke="rgba(255,255,255,0.15)"
            strokeWidth={1}
            style={{ opacity: Math.min(responseNode.opacity, n.opacity) }}
          />
        ))}
      </svg>

      {/* Node cards */}
      {d3NodesRef.current.map(node => {
        const isResponse = node.type === 'response'
        const w = isResponse ? 420 : 260
        const text = isResponse ? typewriterText : node.text

        return (
          <div
            key={node.id}
            style={{
              position: 'absolute',
              left: node.x - w / 2,
              top: node.y - (isResponse ? 60 : 44),
              width: w,
              opacity: node.opacity,
              transition: 'opacity 0.3s',
              pointerEvents: 'none',
              background: NODE_COLORS[node.type],
              border: `1px solid ${NODE_BORDER[node.type]}`,
              backdropFilter: 'blur(10px)',
              WebkitBackdropFilter: 'blur(10px)',
              borderRadius: 8,
              padding: isResponse ? '14px 16px' : '8px 12px',
            }}
          >
            <div style={{
              fontSize: 9,
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
              color: 'rgba(232,228,221,0.4)',
              marginBottom: isResponse ? 8 : 4,
            }}>
              {node.type}
            </div>
            <div style={{
              fontSize: isResponse ? 13 : 11,
              lineHeight: isResponse ? 1.6 : 1.5,
              color: isResponse ? 'rgba(232,228,221,0.9)' : 'rgba(232,228,221,0.7)',
              fontFamily: isResponse ? 'var(--font-geist-sans)' : 'var(--font-geist-mono)',
              wordBreak: 'break-word',
            }}>
              {text || ' '}
              {isResponse && isTyping && (
                <span style={{
                  borderRight: '2px solid rgba(232,228,221,0.7)',
                  marginLeft: 1,
                  animation: 'blink 1s step-end infinite',
                }} />
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
