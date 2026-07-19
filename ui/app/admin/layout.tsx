'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useStatePoller } from '../lib/hooks/useStatePoller'
import { BUILD_INFO } from '../lib/build-info'
import { formatDistanceToNow } from 'date-fns'
import { BackgroundAmbience } from '../components/BackgroundAmbience'

const NAV = [
  { href: '/admin', label: 'Overview', icon: '◉' },
  { href: '/admin/neuro', label: 'Neuro', icon: '⬡' },
  { href: '/admin/history', label: 'History', icon: '∿' },
  { href: '/admin/control', label: 'Control', icon: '⊕' },
  { href: '/admin/events', label: 'Events', icon: '≋' },
  { href: '/admin/system', label: 'System', icon: '◈' },
]

const CHAT_LINK = { href: '/', label: 'Chat', icon: '◈' }
const VIEWER_LINK = { href: '/viewer', label: 'Viewer', icon: '⊙' }

function computeDominantState(state: { second_order?: Record<string, number>; third_order?: Record<string, number>; sleeping?: boolean }): string {
  if (state.sleeping) return 'Sleeping'
  const so = state.second_order ?? {}
  const to = state.third_order ?? {}
  if ((to.anxiety ?? 0) > 65) return 'Anxious'
  if ((so.energy ?? 50) > 70 && (so.mood_valence ?? 50) > 65) return 'Elevated'
  if ((so.cognitive_clarity ?? 50) > 65 && (so.energy ?? 50) > 55) return 'Focused'
  if ((so.social_warmth ?? 50) > 65) return 'Warm'
  if ((so.mood_valence ?? 50) < 35) return 'Low'
  if ((so.energy ?? 50) < 30) return 'Depleted'
  return 'Resting'
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const { state, lastUpdate } = useStatePoller()

  const dominantState = state ? computeDominantState(state) : '—'
  const lastUpdateStr = lastUpdate ? formatDistanceToNow(lastUpdate, { addSuffix: true }) : '—'
  // Chemicals that naturally sit at zero — low value is not an alert for these
  const FLOOR_ZERO = new Set(['bac', 'sleep_pressure', 'anandamide', 'two_ag'])
  const hasAlerts = state ? Object.entries(state.chemicals).some(([k, v]) =>
    v.normalized > 0.85 || (!FLOOR_ZERO.has(k) && v.normalized < 0.1)
  ) : false

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: '#07070a' }}>
      <BackgroundAmbience />

      {/* Desktop sidebar — hidden on mobile */}
      <aside
        className="hidden sm:flex w-52 flex-shrink-0 flex-col border-r relative z-10"
        style={{
          borderColor: 'rgba(232,228,221,0.08)',
          background: 'rgba(4,4,4,0.75)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
        }}
      >
        {/* Logo */}
        <div className="px-5 py-5 border-b" style={{ borderColor: 'rgba(232,228,221,0.06)' }}>
          <div className="text-sm font-medium tracking-widest uppercase" style={{ color: 'rgba(232,228,221,0.55)' }}>Mina</div>
          <div className="text-xs mt-0.5 value-mono" style={{ color: 'rgba(232,228,221,0.25)' }}>admin</div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
          {NAV.map(({ href, label, icon }) => {
            const active = href === '/admin' ? pathname === '/admin' : pathname.startsWith(href)
            return (
              <Link
                key={href}
                href={href}
                className="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-all duration-150"
                style={{
                  color: active ? '#f0ebe2' : 'rgba(232,228,221,0.42)',
                  background: active ? 'rgba(255,200,100,0.08)' : 'transparent',
                  borderLeft: active ? '2px solid rgba(255,200,100,0.4)' : '2px solid transparent',
                }}
              >
                <span className="text-xs w-4 text-center" style={{ color: active ? 'rgba(255,200,100,0.8)' : 'rgba(232,228,221,0.25)' }}>{icon}</span>
                {label}
              </Link>
            )
          })}
        </nav>

        {/* Chat + Viewer shortcuts */}
        <div className="px-3 pb-2 space-y-0.5">
          <Link
            href={CHAT_LINK.href}
            className="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-all duration-150"
            style={{ color: 'rgba(232,228,221,0.42)', borderLeft: '2px solid transparent' }}
          >
            <span className="text-xs w-4 text-center" style={{ color: 'rgba(232,228,221,0.25)' }}>{CHAT_LINK.icon}</span>
            {CHAT_LINK.label}
          </Link>
          <Link
            href={VIEWER_LINK.href}
            className="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-all duration-150"
            style={{ color: 'rgba(232,228,221,0.42)', borderLeft: '2px solid transparent' }}
          >
            <span className="text-xs w-4 text-center" style={{ color: 'rgba(232,228,221,0.25)' }}>{VIEWER_LINK.icon}</span>
            {VIEWER_LINK.label}
          </Link>
        </div>

        {/* Status */}
        <div className="px-4 py-3 border-t space-y-1" style={{ borderColor: 'rgba(232,228,221,0.06)' }}>
          <div className="flex items-center gap-2">
            <div className={`w-1.5 h-1.5 rounded-full ${state?.sleeping ? 'bg-blue-400' : 'bg-emerald-400'}`} style={{ boxShadow: state?.sleeping ? '0 0 6px rgba(96,165,250,0.8)' : '0 0 6px rgba(52,211,153,0.8)' }} />
            <span className="text-xs value-mono" style={{ color: 'rgba(232,228,221,0.35)' }}>
              {state?.sleeping ? 'sleeping' : 'awake'}
            </span>
            {hasAlerts && <div className="w-1.5 h-1.5 rounded-full bg-red-400 ml-auto" style={{ boxShadow: '0 0 6px rgba(248,113,113,0.8)' }} />}
          </div>
          <div className="text-xs value-mono" style={{ color: 'rgba(232,228,221,0.2)' }}>{lastUpdateStr}</div>
          <div
            className="text-[10px] value-mono truncate"
            title={`${BUILD_INFO.builtAt} · GET /api/build must match`}
            style={{ color: 'rgba(232,228,221,0.18)' }}
          >
            build {BUILD_INFO.id}
          </div>
        </div>
      </aside>

      {/* Main content area */}
      <div className="flex-1 flex flex-col overflow-hidden relative z-10">
        {/* Topbar */}
        <header
          className="h-12 flex items-center justify-between px-4 sm:px-6 border-b flex-shrink-0"
          style={{
            borderColor: 'rgba(232,228,221,0.06)',
            background: 'rgba(4,4,4,0.6)',
            backdropFilter: 'blur(20px)',
            WebkitBackdropFilter: 'blur(20px)',
          }}
        >
          <div className="flex items-center gap-3">
            {/* Mobile logo */}
            <span className="sm:hidden text-xs tracking-widest uppercase" style={{ color: 'rgba(232,228,221,0.4)' }}>Mina</span>
            <span className="text-sm font-medium" style={{ color: '#f0ebe2' }}>{dominantState}</span>
            {state?.sleeping && (
              <span className="text-xs px-2 py-0.5 rounded-full border value-mono hidden sm:inline" style={{ color: 'rgba(147,197,253,0.8)', borderColor: 'rgba(147,197,253,0.2)', background: 'rgba(147,197,253,0.06)' }}>
                sleeping
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            {hasAlerts && (
              <div className="flex items-center gap-1">
                <div className="w-1.5 h-1.5 rounded-full bg-red-400" style={{ boxShadow: '0 0 6px rgba(248,113,113,0.8)' }} />
                <span className="text-xs hidden sm:inline" style={{ color: 'rgba(248,113,113,0.7)' }}>alerts</span>
              </div>
            )}
            <span className="text-xs value-mono hidden sm:block" style={{ color: 'rgba(232,228,221,0.25)' }}>
              {lastUpdateStr}
            </span>
            <div className={`w-1.5 h-1.5 rounded-full ${state?.sleeping ? 'bg-blue-400' : 'bg-emerald-400'} sm:hidden`} style={{ boxShadow: state?.sleeping ? '0 0 6px rgba(96,165,250,0.8)' : '0 0 6px rgba(52,211,153,0.8)' }} />
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto pb-16 sm:pb-0">
          {children}
        </main>
      </div>

      {/* Mobile bottom nav */}
      <nav
        className="sm:hidden fixed bottom-0 inset-x-0 z-20 flex items-center justify-around h-16 border-t"
        style={{
          background: 'rgba(4,4,4,0.85)',
          backdropFilter: 'blur(24px)',
          WebkitBackdropFilter: 'blur(24px)',
          borderColor: 'rgba(232,228,221,0.08)',
        }}
      >
        {NAV.map(({ href, label, icon }) => {
          const active = href === '/admin' ? pathname === '/admin' : pathname.startsWith(href)
          return (
            <Link
              key={href}
              href={href}
              className="flex flex-col items-center gap-0.5 px-1 py-1 min-w-0"
              style={{ color: active ? '#f0ebe2' : 'rgba(232,228,221,0.3)' }}
            >
              <span className="text-base" style={{ color: active ? 'rgba(255,200,100,0.9)' : 'rgba(232,228,221,0.3)' }}>{icon}</span>
              <span className="text-[9px] tracking-wide truncate max-w-full">{label}</span>
            </Link>
          )
        })}
      </nav>
    </div>
  )
}
