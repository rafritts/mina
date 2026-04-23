'use client'

import { useEffect, useRef, useState } from 'react'
import { apiFetch, type StateData } from '../api'

function applyThemeHint(state: StateData) {
  const dopNorm = state.chemicals.dopamine?.normalized ?? 0
  const cortNorm = state.chemicals.cortisol?.normalized ?? 0
  const oxy = state.chemicals.oxytocin?.normalized ?? 0

  let hue = 0
  if (cortNorm > 0.6 && cortNorm >= dopNorm && cortNorm >= oxy) hue = 0
  else if (dopNorm > 0.6 && dopNorm >= cortNorm && dopNorm >= oxy) hue = 38
  else if (oxy > 0.6 && oxy >= dopNorm && oxy >= cortNorm) hue = 340

  document.documentElement.style.setProperty('--accent-hue', String(hue))
}

export function useStatePoller(interval = 2000) {
  const [state, setState] = useState<StateData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<number | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const poll = async () => {
    try {
      const data = await apiFetch<StateData>('/api/state')
      setState(data)
      setLastUpdate(Date.now())
      setError(null)
      applyThemeHint(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Poll failed')
    }
  }

  useEffect(() => {
    poll()
    timerRef.current = setInterval(poll, interval)
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [interval])

  return { state, error, lastUpdate }
}
