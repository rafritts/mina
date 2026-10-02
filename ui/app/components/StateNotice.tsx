import { cn } from '@/lib/utils'

type Tone = 'loading' | 'empty' | 'error' | 'info'

/** Hide a status-only fetch failure ("500:") behind a sentence a person can read. */
export function offlineDetail(error: string | null | undefined, fallback: string): string {
  if (!error) return fallback
  const bare = error.trim()
  if (/^\d{3}:?\s*$/.test(bare)) return fallback
  return bare
}

/**
 * Shared empty, loading, and error block.
 * `bare` sits inside an existing surface; the default draws its own frame.
 */
export function StateNotice({
  tone = 'empty',
  title,
  detail,
  compact = false,
  bare = false,
  className,
}: {
  tone?: Tone
  title: string
  detail?: string
  compact?: boolean
  bare?: boolean
  className?: string
}) {
  return (
    <div
      className={cn('state', compact && 'state-compact', bare && 'state-bare', className)}
      data-tone={tone}
      role={tone === 'error' ? 'alert' : 'status'}
    >
      {tone === 'loading' ? <span className="photo-spinner state-spinner" aria-hidden /> : null}
      <div className="state-copy">
        <p className="state-title">{title}</p>
        {detail ? <p className="state-detail">{detail}</p> : null}
      </div>
    </div>
  )
}
