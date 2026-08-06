'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useStatePoller } from '../lib/hooks/useStatePoller'
import { presenceLabel } from '../lib/presence'
import { AppRoot } from '../components/shell/AppRoot'
import { AppHeader } from '../components/shell/AppHeader'
import { cn } from '@/lib/utils'

const NAV = [
  { href: '/admin', label: 'Overview', exact: true },
  { href: '/admin/neuro', label: 'Chemistry' },
  { href: '/admin/context', label: 'Context' },
  { href: '/admin/history', label: 'History' },
  { href: '/admin/events', label: 'Events' },
  { href: '/admin/system', label: 'System' },
]

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const { state, lastUpdate, error } = useStatePoller()

  const status = error
    ? 'off'
    : state?.sleeping
      ? 'sleep'
      : state
        ? 'live'
        : 'off'
  const age = lastUpdate
    ? `${Math.max(0, Math.round((Date.now() - lastUpdate) / 1000))}s`
    : '—'

  return (
    <AppRoot>
      <AppHeader
        status={status}
        statusLabel={state ? presenceLabel(state) : status === 'off' ? 'Offline' : '…'}
        actions={
          <span className="hidden sm:inline mono text-[10px] text-faint">
            poll {age}
          </span>
        }
      />

      <div className="app-body">
        <aside className="lab-sidebar">
          <div className="px-4 py-4 border-b border-[var(--border)]">
            <div className="label">Lab</div>
            <div className="text-sm font-medium mt-0.5">Instrumentation</div>
          </div>

          <nav className="flex-1 overflow-y-auto p-2 space-y-0.5" aria-label="Lab">
            {NAV.map((item) => {
              const active = item.exact
                ? pathname === item.href
                : pathname.startsWith(item.href)
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className="side-link"
                  data-active={active ? 'true' : 'false'}
                >
                  {item.label}
                </Link>
              )
            })}
          </nav>

          <div className="p-3 border-t border-[var(--border)]">
            <Link href="/" className="side-link">
              ← Back to Chat
            </Link>
          </div>
        </aside>

        <main
          className={cn(
            'lab-main',
            // room for mobile bottom nav
            'pb-16 sm:pb-0',
          )}
        >
          {children}
        </main>
      </div>

      <nav className="lab-mobile-nav" aria-label="Lab mobile">
        {NAV.map((item) => {
          const active = item.exact
            ? pathname === item.href
            : pathname.startsWith(item.href)
          return (
            <Link
              key={item.href}
              href={item.href}
              className="flex-1 flex flex-col items-center justify-center gap-0.5 text-[10px] no-underline"
              style={{
                color: active ? 'var(--accent-bright)' : 'var(--text-faint)',
              }}
            >
              {item.label}
            </Link>
          )
        })}
      </nav>
    </AppRoot>
  )
}
