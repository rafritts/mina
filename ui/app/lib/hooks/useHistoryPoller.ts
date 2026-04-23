'use client'

import { useEffect, useRef, useState } from 'react'
import { fetchHistory, type HistorySnapshot } from '../api'

export function useHistoryPoller(hours = 6, interval = 30000) {
  const [history, setHistory] = useState<HistorySnapshot[]>([])
  const [loading, setLoading] = useState(true)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const poll = async () => {
    try {
      const data = await fetchHistory(hours)
      setHistory(data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setLoading(true)
    poll()
    timerRef.current = setInterval(poll, interval)
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hours, interval])

  return { history, loading }
}
