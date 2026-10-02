'use client'

import { createContext, useContext } from 'react'

/** Chat home overrides the shared presence label. */
export type StatusOverride = 'thinking' | 'offline' | null

export type WorkspaceChromeApi = {
  setStatusOverride: (value: StatusOverride) => void
  /** Chat registers its local clear so the header button stays in sync while `/` is mounted. */
  setClearHandler: (fn: (() => void) | null) => void
  setClearDisabled: (disabled: boolean) => void
}

export const WorkspaceChromeContext = createContext<WorkspaceChromeApi | null>(null)

export function useWorkspaceChrome(): WorkspaceChromeApi | null {
  return useContext(WorkspaceChromeContext)
}
