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
  /** 0–1 fraction of normalization_max (legacy / theme) */
  normalized: number
  /** Decoder-scale 0–10 */
  normalized_10?: number
  setpoint?: number
  setpoint_10?: number
  /** Gap vs circadian-adjusted target (SPEC-62/63) */
  gap?: number
  label_color?: string
  implication?: string
  norm_max?: number
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

export interface SecretionQueueEntry {
  chemical: string
  remaining: number
  rate_per_sim_hour: number
  posted_at: number
}

export interface StateData {
  chemicals: Record<string, ChemicalEntry>
  sleeping: boolean
  /** Seconds into current sleep bout (0 when awake). */
  sleep_elapsed_s?: number
  /** Unix ts when current sleep bout started (null/undefined when awake). */
  sleep_started_at?: number | null
  /** Unix ts of most recent sleep onset (survives wake). */
  last_sleep_started_at?: number | null
  /** Unix ts of most recent wake. */
  last_woke_at?: number | null
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
  secretion_queue: SecretionQueueEntry[]
  allostatic_load: number
  cycle_day: number
}

export interface FreetimeTool {
  name: string
  /** Short chip text (e.g. Diary, Water). */
  label?: string
  preview: string
  result?: string
  args?: Record<string, unknown>
}

export interface FreetimeContext {
  encoder?: Record<string, unknown>
  relationship_modifier?: number
  sim_snapshot?: Record<string, { normalized?: number; setpoint?: number; gap?: number; rate?: number }>
  big5?: Record<string, number>
  assembly?: ContextAssembly
  insula?: Record<string, unknown>
  hippocampus?: Record<string, unknown>
  pfc?: Record<string, unknown>
  scene?: Record<string, unknown>
  system_prompt?: string
}

export interface FreetimeSession {
  ts: number
  ts_human?: string
  started_at?: number
  duration_s?: number
  message?: string
  reply?: string
  /** Clean one-line summary for list rows. */
  summary?: string
  /** Narrative body (reply or last diary paragraph). */
  body?: string
  preview?: string
  /** Deduped short tool labels for chips. */
  labels?: string[]
  tools?: FreetimeTool[]
  source?: string
  has_context?: boolean
  /** Present on full detail responses. */
  context?: FreetimeContext
  diaries?: string[]
}

export interface FreetimeHistory {
  last: FreetimeSession | null
  recent: FreetimeSession[]
  detail?: FreetimeSession | null
}

export async function fetchFreetime(limit = 40, ts?: number | null): Promise<FreetimeHistory> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (ts != null && Number.isFinite(ts)) params.set('ts', String(ts))
  return apiFetch<FreetimeHistory>(`/api/freetime?${params}`)
}

export async function fetchFreetimeMarkdown(ts?: number | null): Promise<string> {
  const params = new URLSearchParams()
  if (ts != null && Number.isFinite(ts)) params.set('ts', String(ts))
  const q = params.toString()
  const res = await fetch(`/api/freetime/text${q ? `?${q}` : ''}`)
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.text()
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
  // stimulus / response / activity events
  preview?: string
  // tool events
  tool?: string
  args?: Record<string, unknown>
  result?: string
  source?: string
  deltas?: Record<string, number>
}

/** Latest pillar context assembly (GET /api/context). */
export interface ContextAssembly {
  window_context?: string
  rag_context?: string
  kag_context?: string
  sliding_raw?: string
  experiences_raw?: string
}

export interface ContextRecord {
  ts?: number
  ts_human?: string
  username?: string
  source?: string
  message?: string
  encoder?: Record<string, unknown>
  relationship_modifier?: number
  sim_snapshot?: Record<string, { normalized?: number; setpoint?: number; gap?: number; rate?: number }>
  big5?: Record<string, number>
  assembly?: ContextAssembly
  insula?: Record<string, unknown>
  hippocampus?: Record<string, unknown>
  pfc?: Record<string, unknown>
  system_prompt?: string
  reply?: string
  skipped?: boolean
}

export async function fetchContext(): Promise<ContextRecord> {
  return apiFetch<ContextRecord>('/api/context')
}

export async function fetchContextMarkdown(): Promise<string> {
  const res = await fetch('/api/context/text')
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.text()
}
