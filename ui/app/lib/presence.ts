import type { FreetimeSession, StateData } from './api'

/** Short human label for overall presence from derived state. */
export function presenceLabel(state: StateData | null | undefined): string {
  if (!state) return '—'
  if (state.sleeping) return 'Sleeping'
  const so = state.second_order ?? {}
  const to = state.third_order ?? {}
  if ((to.anxiety ?? 0) > 65) return 'Anxious'
  if ((so.energy ?? 50) > 70 && (so.mood_valence ?? 50) > 65) return 'Elevated'
  if ((so.cognitive_clarity ?? 50) > 65 && (so.energy ?? 50) > 55) return 'Focused'
  if ((so.social_warmth ?? 50) > 65) return 'Warm'
  if ((so.mood_valence ?? 50) < 35) return 'Low'
  if ((so.energy ?? 50) < 30) return 'Depleted'
  return 'Present'
}

/** Relative age from a unix timestamp (seconds). */
export function formatRelativeTs(ts: number | null | undefined): string {
  if (ts == null || ts <= 0) return '—'
  const diff = Date.now() - ts * 1000
  if (diff < 0) return 'just now'
  if (diff < 60_000) return 'just now'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`
  if (diff < 7 * 86_400_000) return `${Math.floor(diff / 86_400_000)}d ago`
  return new Date(ts * 1000).toLocaleDateString()
}

/** Absolute clock string for a unix ts. */
export function formatClockTs(ts: number | null | undefined): string {
  if (ts == null || ts <= 0) return '—'
  return new Date(ts * 1000).toLocaleString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

/** Human duration from seconds. */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0 || !Number.isFinite(seconds)) return '—'
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return m > 0 ? `${h}h ${m}m` : `${h}h`
}

/** Sleep status copy for presence UI. */
export function sleepStatusLines(state: StateData): {
  title: string
  detail: string
  sinceLabel: string | null
} {
  if (state.sleeping) {
    const started = state.sleep_started_at ?? state.last_sleep_started_at
    const elapsed =
      state.sleep_elapsed_s && state.sleep_elapsed_s > 0
        ? state.sleep_elapsed_s
        : started
          ? (Date.now() / 1000 - started)
          : null
    return {
      title: 'Asleep',
      detail: 'Auto-sleep or voluntary rest — monoamines recover while she rests.',
      sinceLabel: started
        ? `Since ${formatClockTs(started)}${elapsed != null ? ` · ${formatDuration(elapsed)}` : ''}`
        : elapsed != null
          ? `For ${formatDuration(elapsed)}`
          : null,
    }
  }
  const lastStart = state.last_sleep_started_at
  const lastWake = state.last_woke_at
  if (lastStart && lastWake && lastWake >= lastStart) {
    const bout = lastWake - lastStart
    return {
      title: 'Awake',
      detail: 'Sim is running in wake mode.',
      sinceLabel: `Last slept ${formatClockTs(lastStart)} · ${formatDuration(bout)} · woke ${formatRelativeTs(lastWake)}`,
    }
  }
  if (lastStart) {
    return {
      title: 'Awake',
      detail: 'Sim is running in wake mode.',
      sinceLabel: `Last went to sleep ${formatClockTs(lastStart)}`,
    }
  }
  return {
    title: 'Awake',
    detail: 'Sim is running in wake mode.',
    sinceLabel: 'No sleep bout recorded yet this process lifetime.',
  }
}

/** Short unique tool chips for a free-time session. */
export function freetimeChipLabels(session: FreetimeSession): string[] {
  if (session.labels?.length) return session.labels.slice(0, 6)
  const seen = new Set<string>()
  const out: string[] = []
  for (const t of session.tools ?? []) {
    const label = (t.label || t.name || '').replace(/_/g, ' ').trim()
    if (!label || seen.has(label)) continue
    // Skip long previews mistaken for labels
    if (label.length > 28) continue
    seen.add(label)
    out.push(label)
    if (out.length >= 6) break
  }
  return out
}

/**
 * Main free-time line: reply, diary body, or quiet — never the tool-dump preview.
 */
export function freetimeBody(session: FreetimeSession): string {
  const reply = (session.reply || '').trim()
  if (reply) return reply

  const body = (session.body || '').trim()
  if (body) return body

  const summary = (session.summary || '').trim()
  if (summary && !summary.includes(' · ')) return summary

  // Last diary entry from tools (expand/backfill)
  for (let i = (session.tools?.length ?? 0) - 1; i >= 0; i--) {
    const t = session.tools![i]
    if (t.name !== 'record_diary') continue
    const entry = String(t.args?.entry ?? '').trim()
    if (entry) {
      const para = entry.split(/\n\n/)[0].replace(/\n/g, ' ').trim()
      return para
    }
  }

  for (let i = (session.tools?.length ?? 0) - 1; i >= 0; i--) {
    const t = session.tools![i]
    if (t.name === 'do_action') {
      const act = String(t.args?.activity ?? '').trim()
      const desc = String(t.args?.description ?? '').trim()
      const line = [act, desc].filter(Boolean).join(' — ')
      if (line) return line
    }
    if (t.name === 'drink' && t.args?.description) {
      return `Drank ${String(t.args.description)}`
    }
    if (t.name === 'eat' && t.args?.description) {
      return `Ate ${String(t.args.description)}`
    }
  }

  const preview = (session.preview || '').trim()
  if (preview && !preview.includes(' · ')) return preview

  return 'Quiet free time — no note.'
}

export const FIELD_LABELS: Record<string, string> = {
  energy: 'Energy',
  cognitive_clarity: 'Clarity',
  hedonic_tone: 'Hedonic',
  social_warmth: 'Warmth',
  arousal: 'Arousal',
  mood_valence: 'Mood',
  anxiety: 'Anxiety',
  depression: 'Low mood',
  boredom: 'Boredom',
  loneliness: 'Loneliness',
  flow: 'Flow',
  physical_distress: 'Distress',
}

export const SECOND_ORDER = [
  'energy',
  'mood_valence',
  'social_warmth',
  'cognitive_clarity',
  'arousal',
  'hedonic_tone',
] as const

export const THIRD_ORDER = [
  'anxiety',
  'depression',
  'boredom',
  'loneliness',
  'flow',
  'physical_distress',
] as const
