'use client'

import Link from 'next/link'
import { cn } from '@/lib/utils'
import { MinaMark } from '@/app/components/MinaMark'

type Status = 'live' | 'busy' | 'sleep' | 'off'

type Props = {
  status?: Status
  statusLabel?: string
  onStatusClick?: () => void
  statusExpanded?: boolean
  menu?: React.ReactNode
  actions?: React.ReactNode
  className?: string
}

const DEFAULT_LABEL: Record<Status, string> = {
  live: 'Present',
  busy: 'Thinking',
  sleep: 'Sleeping',
  off: 'Offline',
}

export function AppHeader({
  status = 'off',
  statusLabel,
  onStatusClick,
  statusExpanded = false,
  menu,
  actions,
  className,
}: Props) {
  const label = statusLabel ?? DEFAULT_LABEL[status]

  return (
    <header className={cn('app-header', className)}>
      <div className="flex items-center gap-2 sm:gap-3 min-w-0">
        {menu}
        <Link href="/" aria-label="Mina" className="flex items-center gap-2 shrink-0 no-underline">
          <MinaMark className="h-7 w-7" />
          <span className="wordmark-name text-sm font-medium tracking-wide text-[var(--text)]">Mina</span>
        </Link>
      </div>

      <div className="flex items-center gap-1.5 sm:gap-2 min-w-0">
        <button
          type="button"
          className="status-pill"
          data-tone={status}
          onClick={onStatusClick}
          aria-haspopup="dialog"
          aria-expanded={statusExpanded}
          aria-label={`Presence: ${label}`}
        >
          <span className={cn('dot', status === 'busy' && 'dot-pulse')} />
          {label}
        </button>
        {actions}
      </div>
    </header>
  )
}
