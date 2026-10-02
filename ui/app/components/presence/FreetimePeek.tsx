'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { fetchFreetime, type FreetimeSession } from '../../lib/api'
import {
  formatClockTs,
  formatRelativeTs,
  freetimeBody,
  freetimeChipLabels,
} from '../../lib/presence'

const CHIP_LIMIT = 4

/**
 * The only free-time peek. The Free time page stays the session log.
 * Overview does not render a second copy.
 */
export function FreetimePeek({ onNavigate }: { onNavigate?: () => void }) {
  const [sessions, setSessions] = useState<FreetimeSession[]>([])

  const load = useCallback(async () => {
    try {
      const data = await fetchFreetime(12)
      setSessions(data.recent ?? [])
    } catch {
      /* offline / not ready */
    }
  }, [])

  useEffect(() => {
    const start = window.setTimeout(() => void load(), 0)
    const id = window.setInterval(() => void load(), 15_000)
    return () => {
      window.clearTimeout(start)
      window.clearInterval(id)
    }
  }, [load])

  const latest = sessions[0]

  return (
    <section>
      <div className="flex items-center justify-between section-head">
        <div className="label m-0">Free time</div>
        <Link
          href="/admin/freetime"
          className="text-[12px] text-muted no-underline hover:text-secondary"
          onClick={onNavigate}
        >
          Open Free time →
        </Link>
      </div>
      <div className="surface p-3 space-y-2">
        {latest ? (
          <>
            <div className="flex items-center justify-between gap-2">
              <div className="flex flex-wrap gap-1 min-w-0">
                {freetimeChipLabels(latest)
                  .slice(0, CHIP_LIMIT)
                  .map((label) => (
                    <span key={label} className="chip chip-info max-w-[7rem] truncate">
                      {label}
                    </span>
                  ))}
              </div>
              <span
                className="mono text-[10px] text-faint shrink-0"
                title={formatClockTs(latest.ts)}
              >
                {formatRelativeTs(latest.ts)}
              </span>
            </div>
            <p className="text-[11.5px] text-secondary m-0 leading-snug line-clamp-2 break-words">
              {freetimeBody(latest)}
            </p>
          </>
        ) : (
          <p className="text-[11px] mono text-faint m-0">No free-time sessions yet.</p>
        )}
      </div>
    </section>
  )
}
