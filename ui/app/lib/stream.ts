'use client'

import { useEffect, useRef, useState } from 'react'
import type { ChemicalEntry } from './api'

// --- Event payload types (matching stream_bus.emit calls in the backend) ---

export interface StateSnapshotEvent {
  type: 'state_snapshot'
  payload: {
    chemicals: Record<string, ChemicalEntry>
    second_order: Record<string, number>
    third_order: Record<string, number>
    sleeping: boolean
  }
}

export interface DeltaEvent {
  type: 'delta'
  payload: {
    source: string
    preview: string
    deltas: Record<string, number>
    event_override: string | null
  }
}

export interface StimulusLandEvent {
  type: 'stimulus_land'
  payload: { preview: string }
}

export interface ContextPillarEvent {
  type: 'context_pillar'
  payload: {
    social_context: string
    urgency: string
    notable: string | null
  }
}

export interface RagHitEvent {
  type: 'rag_hit'
  payload: { index: number; excerpt: string; bucket: string }
}

export interface KagSelectionEvent {
  type: 'kag_selection'
  payload: { filename: string; excerpt: string }
}

export interface EmotionPillarEvent {
  type: 'emotion_pillar'
  payload: {
    dominant_affect: string
    trend: string
    arousal: string
    valence: string
    availability: string
    dominant_drive: string
  }
}

export interface ReasoningEvent {
  type: 'reasoning'
  payload: {
    approach: string
    tone: string
    internal_reaction: string
  }
}

export interface ResponseCompleteEvent {
  type: 'response_complete'
  payload: { text: string; token_count: number }
}

export type StreamEvent =
  | StateSnapshotEvent
  | DeltaEvent
  | StimulusLandEvent
  | ContextPillarEvent
  | RagHitEvent
  | KagSelectionEvent
  | EmotionPillarEvent
  | ReasoningEvent
  | ResponseCompleteEvent

// --- Hook ---

export function useStream(onEvent: (e: StreamEvent) => void): { connected: boolean } {
  const [connected, setConnected] = useState(false)
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  useEffect(() => {
    let es: EventSource | null = null
    let backoff = 1000
    let timer: ReturnType<typeof setTimeout> | null = null
    let alive = true

    function connect() {
      if (!alive) return
      es = new EventSource('/api/stream')

      es.onopen = () => {
        setConnected(true)
        backoff = 1000
      }

      es.onmessage = (e: MessageEvent) => {
        try {
          const raw = JSON.parse(e.data as string) as StreamEvent
          onEventRef.current(raw)
        } catch {
          // malformed event — skip
        }
      }

      es.onerror = () => {
        setConnected(false)
        es?.close()
        es = null
        // exponential backoff with ±20% jitter, cap 30s
        const jitter = backoff * (0.8 + Math.random() * 0.4)
        timer = setTimeout(() => {
          backoff = Math.min(backoff * 2, 30_000)
          connect()
        }, jitter)
      }
    }

    connect()

    return () => {
      alive = false
      if (timer) clearTimeout(timer)
      es?.close()
    }
  }, [])

  return { connected }
}
