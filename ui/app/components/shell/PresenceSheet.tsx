'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import type { StateData } from '../../lib/api'
import { SECOND_ORDER, THIRD_ORDER } from '../../lib/presence'
import { FeltMetricList } from '../presence/FeltMetricList'
import { FreetimePeek } from '../presence/FreetimePeek'
import { SleepStatusCard } from '../presence/SleepStatusCard'
import { StateNotice, offlineDetail } from '../StateNotice'
import { Sheet } from './Sheet'

function UpdatedAgo({ at }: { at: number | null }) {
  const [now, setNow] = useState<number | null>(null)
  useEffect(() => {
    const tick = () => setNow(Date.now())
    const start = window.setTimeout(tick, 0)
    const id = window.setInterval(tick, 1000)
    return () => {
      window.clearTimeout(start)
      window.clearInterval(id)
    }
  }, [])
  if (at == null || now == null) return <span>—</span>
  const age = Math.max(0, Math.round((now - at) / 1000))
  return <span>updated {age}s ago</span>
}

export function PresenceSheet({
  open,
  onClose,
  state,
  error,
  lastUpdate,
}: {
  open: boolean
  onClose: () => void
  state: StateData | null
  error: string | null
  lastUpdate: number | null
}) {
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="Presence"
      footer={<UpdatedAgo at={lastUpdate} />}
    >
      <div className="p-4 space-y-5">
        {!state ? (
          <StateNotice
            tone={error ? 'error' : 'loading'}
            title={error ? 'Can’t reach the sim' : 'Waiting for the sim'}
            detail={offlineDetail(
              error,
              'Start the backend with uv run python main.py. Presence fills in once state is polling.',
            )}
          />
        ) : (
          <>
            <section>
              <div className="label section-head">Sleep</div>
              <SleepStatusCard state={state} density="compact" />
            </section>

            <section>
              <div className="label section-head">Felt state</div>
              <FeltMetricList
                fields={SECOND_ORDER}
                values={state.second_order}
                variant="bar"
                emptyValue={50}
              />
            </section>

            <section>
              <div className="label section-head">Signals</div>
              <FeltMetricList
                fields={THIRD_ORDER}
                values={state.third_order}
                variant="bar"
                emptyValue={0}
              />
            </section>
          </>
        )}

        <FreetimePeek onNavigate={onClose} />

        <nav className="flex flex-wrap gap-x-4 gap-y-1" aria-label="Presence links">
          <Link
            href="/admin"
            className="text-[12px] text-muted no-underline hover:text-secondary"
            onClick={onClose}
          >
            Overview
          </Link>
        </nav>
      </div>
    </Sheet>
  )
}
