'use client'

import { useEffect, useRef } from 'react'

export function BackgroundAmbience() {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current) return
    let effect: { destroy: () => void } | null = null

    async function init() {
      const THREE = await import('three')
      ;(window as unknown as Record<string, unknown>).THREE = THREE

      const VANTA = await import('vanta/dist/vanta.dots.min')
      effect = VANTA.default({
        el: ref.current!,
        THREE,
        mouseControls: false,
        touchControls: false,
        gyroControls: false,
        minHeight: 200,
        minWidth: 200,
        scale: 1.0,
        scaleMobile: 1.0,
        color: 0xf59e0b,
        color2: 0xea580c,
        backgroundColor: 0x050505,
        size: 3.5,
        spacing: 28,
        showLines: false,
      })
    }

    init().catch(console.error)
    return () => { effect?.destroy() }
  }, [])

  return <div ref={ref} className="ambience-root" aria-hidden />
}
