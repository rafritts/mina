'use client'

import { useEffect, useRef, useState } from 'react'

// --- Event payload types (matching stream_bus.emit in the backend) ---

export interface StateSnapshotEvent {
  type: 'state_snapshot'
  payload: {
    chemicals: Record<string, number>
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

export interface StageEvent {
  type: 'stage'
  payload: { stage: string; label: string }
}

export interface EncoderEvent {
  type: 'encoder'
  payload: {
    preview: string
    axes?: Record<string, unknown>
  }
}

export interface ContextPillarEvent {
  type: 'context_pillar'
  payload: {
    social_context: string
    urgency: string
    notable: string | null
    situational_summary: string
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
    arousal: number
    valence: number
    availability: string
    dominant_drive: string
    emotional_response_texturing: string
    emotional_summary?: string
    somatic?: string
  }
}

export interface ReasoningEvent {
  type: 'reasoning'
  payload: {
    approach: string
    tone: string
    internal_reaction: string
    lead_with?: string
    strategy_rationale?: string
  }
}

export interface ResponseCompleteEvent {
  type: 'response_complete'
  payload: {
    text: string
    token_count: number
    skipped?: boolean
    images?: string[]
  }
}

export interface TickObsEvent {
  type: 'tick_obs'
  payload: Record<string, unknown>
}

export type StreamEvent =
  | StateSnapshotEvent
  | DeltaEvent
  | StimulusLandEvent
  | StageEvent
  | EncoderEvent
  | ContextPillarEvent
  | RagHitEvent
  | KagSelectionEvent
  | EmotionPillarEvent
  | ReasoningEvent
  | ResponseCompleteEvent
  | TickObsEvent

// --- Turn mind state (accumulated while a turn is in flight) ---

export type PillarStageId =
  | 'sense'
  | 'chemistry'
  | 'feel'
  | 'remember'
  | 'situate'
  | 'decide'
  | 'speak'

export interface TurnMind {
  active: boolean
  stage: PillarStageId | null
  stageLabel: string | null
  stimulus: string | null
  /** Amygdala encoder axes/flags — drives chemistry, not raw nM levels */
  encoder: EncoderEvent['payload'] | null
  emotion: EmotionPillarEvent['payload'] | null
  memory: { type: 'rag' | 'kag'; text: string; bucket?: string }[]
  context: ContextPillarEvent['payload'] | null
  reasoning: ReasoningEvent['payload'] | null
  completed: boolean
  skipped: boolean
}

export const EMPTY_TURN_MIND: TurnMind = {
  active: false,
  stage: null,
  stageLabel: null,
  stimulus: null,
  encoder: null,
  emotion: null,
  memory: [],
  context: null,
  reasoning: null,
  completed: false,
  skipped: false,
}

export function reduceTurnMind(prev: TurnMind, event: StreamEvent): TurnMind {
  switch (event.type) {
    case 'stimulus_land':
      return {
        ...EMPTY_TURN_MIND,
        active: true,
        stage: 'sense',
        stageLabel: 'Sensing',
        stimulus: event.payload.preview,
      }
    case 'stage': {
      const stage = event.payload.stage as PillarStageId
      return {
        ...prev,
        active: true,
        stage,
        stageLabel: event.payload.label,
      }
    }
    case 'encoder':
      return {
        ...prev,
        active: true,
        encoder: event.payload,
        // Encoder lands just before chemistry stage; keep stage if already set
        stage: prev.stage === 'sense' || prev.stage === null ? 'chemistry' : prev.stage,
        stageLabel:
          prev.stage === 'sense' || prev.stage === null
            ? 'Chemistry settling'
            : prev.stageLabel,
      }
    case 'emotion_pillar':
      return {
        ...prev,
        active: true,
        emotion: event.payload,
        stage: prev.stage ?? 'feel',
        stageLabel: prev.stageLabel ?? 'Feeling',
      }
    case 'rag_hit':
      return {
        ...prev,
        active: true,
        memory: [
          ...prev.memory,
          {
            type: 'rag',
            text: event.payload.excerpt,
            bucket: event.payload.bucket,
          },
        ],
      }
    case 'kag_selection':
      return {
        ...prev,
        active: true,
        memory: [
          ...prev.memory,
          { type: 'kag', text: event.payload.filename || event.payload.excerpt },
        ],
      }
    case 'context_pillar':
      return {
        ...prev,
        active: true,
        context: event.payload,
        stage: prev.stage ?? 'situate',
        stageLabel: prev.stageLabel ?? 'Situating',
      }
    case 'reasoning':
      return {
        ...prev,
        active: true,
        reasoning: event.payload,
        stage: prev.stage ?? 'decide',
        stageLabel: prev.stageLabel ?? 'Deciding',
      }
    case 'response_complete':
      return {
        ...prev,
        active: true,
        completed: true,
        skipped: Boolean(event.payload.skipped),
        stage: 'speak',
        stageLabel: event.payload.skipped ? 'Silence' : 'Speaking',
      }
    default:
      return prev
  }
}

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
