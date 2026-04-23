'use client'

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {}),
    },
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status}: ${text}`)
  }
  const ct = res.headers.get('content-type') ?? ''
  if (ct.includes('application/json')) return res.json() as Promise<T>
  return res.text() as unknown as Promise<T>
}

export interface ChemicalEntry {
  value: number
  unit: string
  label: string
  normalized: number
}

export interface VitalEntry {
  value?: number
  systolic?: number
  diastolic?: number
  unit: string
  label: string
}

export interface CascadeEvent {
  type: string
  fires_at_unix: number
  magnitude: number
}

export interface StateData {
  chemicals: Record<string, ChemicalEntry>
  sleeping: boolean
  second_order: Record<string, number>
  third_order: Record<string, number>
  vital_signs: Record<string, VitalEntry>
  neuroendocrine: Record<string, number>
  immune: Record<string, number>
  pain: Record<string, number>
  neuroplasticity: Record<string, number>
  personality_drift: Record<string, number>
  body: Record<string, number>
  receptor_sensitivity: Record<string, number>
  cascade_queue: CascadeEvent[]
  allostatic_load: number
  cycle_day: number
}

export interface HistorySnapshot {
  ts: number
  chemicals: Record<string, number>
  second_order: Record<string, number>
  third_order: Record<string, number>
  sleeping: boolean
}

export async function fetchHistory(hours = 6, limit = 2000): Promise<HistorySnapshot[]> {
  const params = new URLSearchParams({ limit: String(limit), hours: String(hours) })
  return apiFetch<HistorySnapshot[]>(`/api/history?${params}`)
}

export interface TokenCall {
  input: number
  output: number
  reasoning: number
  cached: number
}

export interface TurnEntry {
  turn: number
  ts: number
  calls: Record<string, TokenCall>
  totals: TokenCall
}

export interface TokenStats {
  session_start: number | null
  total_input: number
  total_output: number
  total_reasoning: number
  total_cached: number
  turns: number
  by_label: Record<string, TokenCall>
  turn_log: TurnEntry[]
  current_turn: Record<string, TokenCall>
}

export interface EventEntry {
  id?: string
  ts: number
  type: string
  content: string
  deltas?: Record<string, number>
}
