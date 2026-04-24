'use client'

import { useEffect, useRef, useReducer, useCallback } from 'react'
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
  stimulus:  [0,     -0.55  ],
  context:   [0.55,  -0.35  ],
  rag:       [-0.6,   0.1   ],
  kag:       [0.6,    0.1   ],
  emotion:   [-0.45,  0.45  ],
  reasoning: [0.45,   0.45  ],
}

const NODE_COLORS: Record<NodeType, string> = {
  response:  'rgba(255,255,255,0.10)',
  stimulus:  'rgba(96,165,250,0.12)',
  context:   'rgba(167,139,250,0.12)',
  rag:       'rgba(74,222,128,0.12)',
  kag:       'rgba(45,212,191,0.12)',
  emotion:   'rgba(251,113,133,0.12)',
  reasoning: 'rgba(248,200,79,0.12)',
}

const NODE_BORDER: Record<NodeType, string> = {
  response:  'rgba(255,255,255,0.18)',
  stimulus:  'rgba(96,165,250,0.3)',
  context:   'rgba(167,139,250,0.3)',
  rag:       'rgba(74,222,128,0.3)',
  kag:       'rgba(45,212,191,0.3)',
  emotion:   'rgba(251,113,133,0.3)',
  reasoning: 'rgba(248,200,79,0.3)',
}

interface Props {
  nodes: GraphNode[]
  typewriterText: string
  isTyping: boolean
}

export function ThoughtGraph({ nodes, typewriterText, isTyping }: Props) {
  const [, forceRender] = useReducer(x => x + 1, 0)
  const d3NodesRef = useRef<D3Node[]>([])
  const simRef = useRef<Simulation<D3Node, undefined> | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const cx = useCallback(() => (containerRef.current?.clientWidth ?? window.innerWidth) / 2, [])
  const cy = useCallback(() => (containerRef.current?.clientHeight ?? window.innerHeight) / 2, [])

  // Initialize or update simulation when node list changes
  useEffect(() => {
    const w = containerRef.current?.clientWidth ?? window.innerWidth
    const h = containerRef.current?.clientHeight ?? window.innerHeight
    const halfW = w / 2
    const halfH = h / 2

    // Sync d3NodesRef with incoming nodes list
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
        // Start near cluster target with small random offset
        x: halfW + ox * halfW + (Math.random() - 0.5) * 60,
        y: halfH + oy * halfH + (Math.random() - 0.5) * 60,
        vx: 0,
        vy: 0,
        fx: n.type === 'response' ? halfW : null,
        fy: n.type === 'response' ? halfH : null,
      }
    })

    // Remove nodes that are no longer in the list
    d3NodesRef.current = nextD3.filter(n => incomingIds.has(n.id))

    if (simRef.current) simRef.current.stop()

    if (d3NodesRef.current.length === 0) return

    const sim = forceSimulation<D3Node>(d3NodesRef.current)
      .force('charge', forceManyBody<D3Node>().strength(-220))
      .force('center', forceCenter(halfW, halfH).strength(0.03))
      .force('collide', forceCollide<D3Node>(90))
      .force('cx', forceX<D3Node>(n => halfW + CLUSTER_OFFSET[n.type][0] * halfW).strength(0.08))
      .force('cy', forceY<D3Node>(n => halfH + CLUSTER_OFFSET[n.type][1] * halfH).strength(0.08))
      .on('tick', forceRender)
      .alphaDecay(0.015)

    simRef.current = sim

    return () => { sim.stop() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes])

  // Fix response node at center on resize
  useEffect(() => {
    const onResize = () => {
      const node = d3NodesRef.current.find(n => n.type === 'response')
      if (node) {
        node.fx = cx()
        node.fy = cy()
      }
      simRef.current?.alpha(0.3).restart()
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [cx, cy])

  const responseNode = d3NodesRef.current.find(n => n.type === 'response')
  const inputNodes = d3NodesRef.current.filter(n => n.type !== 'response')

  return (
    <div
      ref={containerRef}
      style={{ position: 'fixed', inset: 0, zIndex: 10, pointerEvents: 'none' }}
    >
      {/* Edges */}
      <svg
        ref={svgRef}
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', overflow: 'visible' }}
      >
        {responseNode && inputNodes.map(n => (
          <line
            key={`edge-${n.id}`}
            x1={responseNode.x}
            y1={responseNode.y}
            x2={n.x}
            y2={n.y}
            stroke="rgba(255,255,255,0.12)"
            strokeWidth={1}
            style={{ opacity: n.opacity * 0.8 }}
          />
        ))}
      </svg>

      {/* Node cards */}
      {d3NodesRef.current.map(node => {
        const isResponse = node.type === 'response'
        const w = isResponse ? 420 : 240
        const text = isResponse ? typewriterText : node.text

        return (
          <div
            key={node.id}
            style={{
              position: 'absolute',
              left: node.x - w / 2,
              top: node.y - (isResponse ? 60 : 40),
              width: w,
              opacity: node.opacity,
              transition: 'opacity 0.2s',
              pointerEvents: 'none',
              background: NODE_COLORS[node.type],
              border: `1px solid ${NODE_BORDER[node.type]}`,
              backdropFilter: 'blur(12px)',
              WebkitBackdropFilter: 'blur(12px)',
              borderRadius: 8,
              padding: isResponse ? '14px 16px' : '8px 12px',
            }}
          >
            {/* Type label */}
            <div style={{
              fontSize: 9,
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
              color: 'rgba(232,228,221,0.3)',
              marginBottom: isResponse ? 8 : 4,
            }}>
              {node.type}
            </div>

            {/* Content */}
            <div style={{
              fontSize: isResponse ? 13 : 11,
              lineHeight: isResponse ? 1.6 : 1.5,
              color: isResponse ? 'rgba(232,228,221,0.85)' : 'rgba(232,228,221,0.55)',
              fontFamily: isResponse ? 'var(--font-geist-sans)' : 'var(--font-geist-mono)',
              wordBreak: 'break-word',
            }}>
              {text}
              {isResponse && isTyping && (
                <span style={{ animation: 'blink 1s step-end infinite', borderRight: '2px solid rgba(232,228,221,0.6)', marginLeft: 1 }} />
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
