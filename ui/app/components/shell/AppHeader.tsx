'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'

type Props = {
  status?: 'live' | 'busy' | 'off'
  statusLabel?: string
  actions?: React.ReactNode
  className?: string
}

const PRIMARY_NAV = [
  { href: '/', label: 'Chat', match: (p: string) => p === '/' },
  { href: '/admin', label: 'Lab', match: (p: string) => p.startsWith('/admin') },
]

export function AppHeader({ status = 'off', statusLabel, actions, className }: Props) {
  const pathname = usePathname()
  const label =
    statusLabel ??
    (status === 'live' ? 'Live' : status === 'busy' ? 'Thinking' : 'Offline')

  return (
    <header className={cn('app-header', className)}>
      <div className="flex items-center gap-4 min-w-0">
        <Link href="/" className="flex items-center gap-2.5 shrink-0 no-underline">
          <span
            className="flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-semibold tracking-wide"
            style={{
              background: 'var(--accent-dim)',
              border: '1px solid var(--accent-border)',
              color: 'var(--accent-bright)',
            }}
          >
            M
          </span>
          <span className="text-sm font-medium tracking-wide text-[var(--text)]">Mina</span>
        </Link>

        <nav className="hidden sm:flex items-center gap-0.5" aria-label="Primary">
          {PRIMARY_NAV.map((item) => {
            const active = item.match(pathname)
            return (
              <Link
                key={item.href}
                href={item.href}
                className="nav-link"
                data-active={active ? 'true' : 'false'}
              >
                {item.label}
              </Link>
            )
          })}
        </nav>
      </div>

      <div className="flex items-center gap-2 min-w-0">
        <span className="status-pill" data-tone={status}>
          <span className={cn('dot', status === 'busy' && 'dot-pulse')} />
          {label}
        </span>
        {actions}
      </div>
    </header>
  )
}
