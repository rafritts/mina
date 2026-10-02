'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Menu } from 'lucide-react'
import { usePathname } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { clearRemoteTranscript, fetchRemoteChatStore } from '../../lib/chat-store-api'
import { useStatePoller } from '../../lib/hooks/useStatePoller'
import { presenceLabel } from '../../lib/presence'
import { ChatContextModal } from '../ChatContextModal'
import { AppHeader } from './AppHeader'
import { AppRoot } from './AppRoot'
import { PresenceSheet } from './PresenceSheet'
import { PrimaryNav } from './PrimaryNav'
import { ToolsSheet } from './ToolsSheet'
import {
  WorkspaceChromeContext,
  type StatusOverride,
  type WorkspaceChromeApi,
} from './workspace-chrome'

export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const { state, error, lastUpdate } = useStatePoller()

  const [navPath, setNavPath] = useState<string | null>(null)
  const navOpen = navPath === pathname
  const [presenceOpen, setPresenceOpen] = useState(false)
  const [toolsOpen, setToolsOpen] = useState(false)
  const [sceneOpen, setSceneOpen] = useState(false)
  const [statusOverride, setStatusOverride] = useState<StatusOverride>(null)
  const [clearDisabled, setClearDisabled] = useState(false)
  const [chatOwnsClear, setChatOwnsClear] = useState(false)
  const [remoteEmpty, setRemoteEmpty] = useState(true)

  const clearRef = useRef<(() => void) | null>(null)

  const setClearHandler = useCallback((fn: (() => void) | null) => {
    clearRef.current = fn
    setChatOwnsClear(Boolean(fn))
  }, [])

  const chrome = useMemo<WorkspaceChromeApi>(
    () => ({
      setStatusOverride,
      setClearHandler,
      setClearDisabled,
    }),
    [setClearHandler],
  )

  useEffect(() => {
    const onResize = () => {
      if (window.innerWidth >= 640) setNavPath(null)
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  useEffect(() => {
    if (chatOwnsClear) return
    let cancelled = false
    void fetchRemoteChatStore().then((store) => {
      if (cancelled) return
      setRemoteEmpty(!store || store.messages.length === 0)
    })
    return () => {
      cancelled = true
    }
  }, [pathname, chatOwnsClear])

  const overlayOpen = navOpen || presenceOpen || toolsOpen || sceneOpen
  useEffect(() => {
    if (!overlayOpen) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [overlayOpen])

  useEffect(() => {
    if (!navOpen && !presenceOpen && !toolsOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      setNavPath(null)
      setPresenceOpen(false)
      setToolsOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [navOpen, presenceOpen, toolsOpen])

  const onClear = () => {
    if (clearRef.current) {
      clearRef.current()
      return
    }
    void clearRemoteTranscript().then((ok) => {
      if (ok) setRemoteEmpty(true)
    })
  }

  let status: 'live' | 'busy' | 'sleep' | 'off' = 'off'
  let statusLabel = '…'
  if (statusOverride === 'thinking') {
    status = 'busy'
    statusLabel = 'Thinking'
  } else if (statusOverride === 'offline') {
    status = 'off'
    statusLabel = 'Offline'
  } else {
    status = error ? 'off' : state?.sleeping ? 'sleep' : state ? 'live' : 'off'
    statusLabel = state ? presenceLabel(state) : status === 'off' ? 'Offline' : '…'
  }

  const clearIsDisabled = chatOwnsClear ? clearDisabled : remoteEmpty

  const actions = (
    <>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={() => {
          setNavPath(null)
          setPresenceOpen(false)
          setToolsOpen(false)
          setSceneOpen(true)
        }}
      >
        Scene
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={onClear}
        disabled={clearIsDisabled}
      >
        Clear
      </Button>
      <Button
        type="button"
        variant="outline"
        size="sm"
        aria-haspopup="dialog"
        aria-expanded={toolsOpen}
        onClick={() => {
          setNavPath(null)
          setPresenceOpen(false)
          setSceneOpen(false)
          setToolsOpen(true)
        }}
      >
        Tools
      </Button>
    </>
  )

  return (
    <WorkspaceChromeContext.Provider value={chrome}>
      <AppRoot>
        <AppHeader
          status={status}
          statusLabel={statusLabel}
          statusExpanded={presenceOpen}
          onStatusClick={() => {
            setNavPath(null)
            setToolsOpen(false)
            setSceneOpen(false)
            setPresenceOpen(true)
          }}
          menu={
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="nav-menu-btn"
              aria-label="Open menu"
              aria-expanded={navOpen}
              aria-haspopup="dialog"
              onClick={() => {
                setPresenceOpen(false)
                setToolsOpen(false)
                setSceneOpen(false)
                setNavPath(pathname)
              }}
            >
              <Menu className="h-4 w-4" aria-hidden />
            </Button>
          }
          actions={actions}
        />

        <div className="app-body">
          <aside className="primary-nav">
            <nav className="flex-1 overflow-y-auto p-2 space-y-0.5" aria-label="Primary">
              <PrimaryNav />
            </nav>
          </aside>
          <div className="shell-main">{children}</div>
        </div>

        {navOpen && (
          <div className="nav-drawer-backdrop">
            <div className="nav-drawer" role="dialog" aria-modal="true" aria-label="Primary">
              <div className="flex items-center justify-between gap-2 border-b border-[var(--border)] px-3 py-3">
                <span className="label">Menu</span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  aria-label="Close menu"
                  onClick={() => setNavPath(null)}
                >
                  ✕
                </Button>
              </div>
              <nav className="flex-1 overflow-y-auto p-2 space-y-0.5" aria-label="Primary">
                <PrimaryNav onNavigate={() => setNavPath(null)} />
              </nav>
            </div>
            <button
              type="button"
              className="flex-1 border-0 bg-transparent cursor-default"
              aria-label="Close menu"
              onClick={() => setNavPath(null)}
            />
          </div>
        )}

        <PresenceSheet
          open={presenceOpen}
          onClose={() => setPresenceOpen(false)}
          state={state}
          error={error}
          lastUpdate={lastUpdate}
        />
        <ToolsSheet open={toolsOpen} onClose={() => setToolsOpen(false)} />
        <ChatContextModal open={sceneOpen} onClose={() => setSceneOpen(false)} />
      </AppRoot>
    </WorkspaceChromeContext.Provider>
  )
}
