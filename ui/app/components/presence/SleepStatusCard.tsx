import type { StateData } from '../../lib/api'
import { sleepStatusLines } from '../../lib/presence'

/**
 * One sleep-card vocabulary for the Presence sheet (compact) and Overview (page).
 * Copy comes from `sleepStatusLines` in both places.
 */
export function SleepStatusCard({
  state,
  density = 'page',
}: {
  state: StateData
  density?: 'compact' | 'page'
}) {
  const sleep = sleepStatusLines(state)
  const compact = density === 'compact'

  return (
    <div
      className={
        compact
          ? 'surface flex items-center justify-between gap-3 px-3 py-2'
          : 'surface p-3.5 flex items-start justify-between gap-3'
      }
      data-tone={state.sleeping ? 'sleep' : 'live'}
      aria-live="polite"
    >
      <div className="min-w-0">
        <div className={compact ? 'text-[13px] font-medium' : 'text-sm font-medium'}>
          {sleep.title}
        </div>
        <p
          className={
            compact
              ? 'text-[11px] text-muted m-0 mt-0.5 leading-snug'
              : 'text-xs text-muted m-0 mt-0.5 leading-snug'
          }
        >
          {sleep.detail}
        </p>
        {sleep.sinceLabel && (
          <p
            className={
              compact
                ? 'text-[11px] mono text-secondary m-0 mt-1 leading-snug'
                : 'text-xs mono text-secondary m-0 mt-1.5 leading-snug'
            }
          >
            {sleep.sinceLabel}
          </p>
        )}
      </div>
      <span className="status-pill shrink-0" data-tone={state.sleeping ? 'sleep' : 'live'}>
        <span className="dot" />
        {state.sleeping ? 'Sleeping' : 'Awake'}
      </span>
    </div>
  )
}
