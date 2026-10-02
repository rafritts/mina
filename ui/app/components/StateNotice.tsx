import { cn } from '@/lib/utils'

type Tone = 'loading' | 'empty' | 'error' | 'info'

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
