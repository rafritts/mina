'use client'

import { useEffect, useRef } from 'react'
import { DISPLAY_RANGES } from '../../lib/labels'

type RGB = [number, number, number]

const MONOAMINE_COLORS: Record<string, RGB> = {
  dopamine:       [245, 158,  11],
  serotonin:      [ 96, 165, 250],
  norepinephrine: [249, 115,  22],
  cortisol:       [ 74, 222, 128],
  oxytocin:       [251, 113, 133],
  acetylcholine:  [167, 139, 250],
  gaba:           [ 45, 212, 191],
  endorphins:     [248, 200,  79],
  anandamide:     [134, 239, 172],
}

function normalize(name: string, value: number): number {
  const range = DISPLAY_RANGES[name]
  if (!range) return 0
  return Math.max(0, Math.min(1, (value - range.min) / (range.max - range.min)))
}

function blendByNormalized(chemicals: Record<string, number>): RGB {
  let r = 0, g = 0, b = 0, total = 0
  for (const [name, rgb] of Object.entries(MONOAMINE_COLORS)) {
    const raw = chemicals[name]
    if (raw === undefined) continue
    const norm = normalize(name, raw)
    r += rgb[0] * norm
    g += rgb[1] * norm
    b += rgb[2] * norm
    total += norm
  }
  if (total === 0) return [137, 150, 78]
  return [r / total, g / total, b / total]
}

function blendByNames(names: string[]): RGB {
  const colors = names.flatMap(n => (MONOAMINE_COLORS[n] ? [MONOAMINE_COLORS[n]] : []))
  if (colors.length === 0) return [200, 200, 255]
  let r = 0, g = 0, b = 0
  for (const c of colors) { r += c[0]; g += c[1]; b += c[2] }
  return [r / colors.length, g / colors.length, b / colors.length]
}

function lerp(a: RGB, b: RGB, t: number): RGB {
  return [
    a[0] + (b[0] - a[0]) * t,
    a[1] + (b[1] - a[1]) * t,
    a[2] + (b[2] - a[2]) * t,
  ]
}

interface Props {
  chemicals: Record<string, number> | null
  pulseChemicals: string[] | null
}

type PulsePhase = 'idle' | 'in' | 'hold' | 'out'

/** Chemistry-tinted CSS gradient backdrop (no Vanta / WebGL). */
export function ViewerTopology({ chemicals, pulseChemicals }: Props) {
  const gradientRef = useRef<HTMLDivElement>(null)
  const currentColorRef = useRef<RGB>([137, 150, 78])
  const baselineRef = useRef<RGB>([137, 150, 78])
  const targetColorRef = useRef<RGB>([137, 150, 78])
  const phaseRef = useRef<PulsePhase>('idle')
  const phaseStartRef = useRef<number>(0)
  const rafRef = useRef<number>(0)

  useEffect(() => {
    if (!chemicals) return
    baselineRef.current = blendByNormalized(chemicals)
    if (phaseRef.current === 'idle') {
      targetColorRef.current = baselineRef.current
    }
  }, [chemicals])

  const prevPulseRef = useRef<string[] | null>(null)
  useEffect(() => {
    if (pulseChemicals === null) return
    if (pulseChemicals === prevPulseRef.current) return
    prevPulseRef.current = pulseChemicals
    targetColorRef.current = blendByNames(pulseChemicals)
    phaseRef.current = 'in'
    phaseStartRef.current = performance.now()
  }, [pulseChemicals])

  useEffect(() => {
    const PHASE_DURATION: Record<PulsePhase, number> = {
      idle: 0, in: 400, hold: 300, out: 2500,
    }

    function tick(now: number) {
      rafRef.current = requestAnimationFrame(tick)

      const phase = phaseRef.current
      const elapsed = now - phaseStartRef.current

      if (phase === 'idle') {
        currentColorRef.current = lerp(currentColorRef.current, baselineRef.current, 0.02)
      } else {
        const t = Math.min(elapsed / PHASE_DURATION[phase], 1)
        if (phase === 'in') {
          currentColorRef.current = lerp(currentColorRef.current, targetColorRef.current, t)
          if (t >= 1) { phaseRef.current = 'hold'; phaseStartRef.current = now }
        } else if (phase === 'hold') {
          if (t >= 1) { phaseRef.current = 'out'; phaseStartRef.current = now }
        } else if (phase === 'out') {
          currentColorRef.current = lerp(targetColorRef.current, baselineRef.current, t)
          if (t >= 1) {
            currentColorRef.current = baselineRef.current
            phaseRef.current = 'idle'
          }
        }
      }

      const el = gradientRef.current
      if (el) {
        const [r, g, b] = currentColorRef.current.map(Math.round)
        el.style.background =
          `radial-gradient(ellipse 80% 80% at 50% 50%, rgba(${r},${g},${b},0.13) 0%, #050505 68%)`
      }
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [])

  return (
    <div
      ref={gradientRef}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 0,
        background: '#050505',
      }}
      aria-hidden
    />
  )
}
