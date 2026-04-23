'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useStatePoller } from '../lib/hooks/useStatePoller'
import { formatDistanceToNow } from 'date-fns'

const NAV = [
  { href: '/admin', label: 'Overview', icon: '◉' },
  { href: '/admin/neuro', label: 'Neuro', icon: '⬡' },
  { href: '/admin/physiology', label: 'Physiology', icon: '◈' },
  { href: '/admin/history', label: 'History', icon: '∿' },
  { href: '/admin/control', label: 'Control', icon: '⊕' },
  { href: '/admin/substances', label: 'Substances', icon: '◎' },
  { href: '/admin/events', label: 'Events', icon: '≋' },
  { href: '/admin/system', label: 'System', icon: '◈' },
]

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

  const hasAlerts = state ? Object.entries(state.chemicals).some(([, v]) => v.normalized > 0.85 || v.normalized < 0.1) : false

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: '#07070a' }}>
      {/* Sidebar */}
      <aside className="w-52 flex-shrink-0 flex flex-col border-r" style={{ borderColor: 'rgba(232,228,221,0.06)', background: '#080810' }}>
        {/* Logo */}
        <div className="px-5 py-5 border-b" style={{ borderColor: 'rgba(232,228,221,0.06)' }}>
          <div className="text-sm font-medium tracking-widest uppercase" style={{ color: 'rgba(232,228,221,0.45)' }}>Mina</div>
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
                  color: active ? '#e8e4dd' : 'rgba(232,228,221,0.4)',
                  background: active ? 'rgba(232,228,221,0.06)' : 'transparent',
                }}
              >
                <span className="text-xs w-4 text-center" style={{ color: active ? '#e8e4dd' : 'rgba(232,228,221,0.25)' }}>{icon}</span>
                {label}
              </Link>
            )
          })}
        </nav>

        {/* Bottom status */}
        <div className="px-4 py-3 border-t space-y-1" style={{ borderColor: 'rgba(232,228,221,0.06)' }}>
          <div className="flex items-center gap-2">
            <div className={`w-1.5 h-1.5 rounded-full ${state?.sleeping ? 'bg-blue-400' : 'bg-emerald-400'}`} />
            <span className="text-xs value-mono" style={{ color: 'rgba(232,228,221,0.35)' }}>
              {state?.sleeping ? 'sleeping' : 'awake'}
            </span>
            {hasAlerts && <div className="w-1.5 h-1.5 rounded-full bg-red-400 ml-auto" />}
          </div>
          <div className="text-xs value-mono" style={{ color: 'rgba(232,228,221,0.2)' }}>{lastUpdateStr}</div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Topbar */}
        <header className="h-12 flex items-center justify-between px-6 border-b flex-shrink-0" style={{ borderColor: 'rgba(232,228,221,0.06)', background: 'rgba(8,8,16,0.8)' }}>
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium" style={{ color: '#e8e4dd' }}>{dominantState}</span>
            {state?.sleeping && (
              <span className="text-xs px-2 py-0.5 rounded-full border value-mono" style={{ color: 'rgba(147,197,253,0.8)', borderColor: 'rgba(147,197,253,0.2)', background: 'rgba(147,197,253,0.06)' }}>
                sleeping
              </span>
            )}
          </div>
          <div className="flex items-center gap-4">
            {hasAlerts && (
              <div className="flex items-center gap-1">
                <div className="w-1.5 h-1.5 rounded-full bg-red-400" />
                <span className="text-xs" style={{ color: 'rgba(248,113,113,0.7)' }}>alerts</span>
              </div>
            )}
            <span className="text-xs value-mono" style={{ color: 'rgba(232,228,221,0.25)' }}>
              {lastUpdateStr}
            </span>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  )
}
