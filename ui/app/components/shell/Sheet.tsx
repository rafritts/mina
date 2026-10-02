'use client'

import { useSyncExternalStore } from 'react'
import { createPortal } from 'react-dom'

const emptySubscribe = () => () => {}

export function Sheet({
  open,
  onClose,
  title,
  children,
  footer,
}: {
  open: boolean
  onClose: () => void
  title: string
  children: React.ReactNode
  footer?: React.ReactNode
}) {
  const mounted = useSyncExternalStore(emptySubscribe, () => true, () => false)
  if (!open || !mounted) return null

  return createPortal(
    <div className="sheet-backdrop">
      <button
        type="button"
        className="flex-1 border-0 bg-transparent cursor-default"
        aria-label={`Close ${title}`}
        onClick={onClose}
      />
      <div className="sheet-panel" role="dialog" aria-modal="true" aria-label={title}>
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-[var(--border)] px-4 py-3">
          <div className="text-sm font-medium truncate">{title}</div>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={onClose}
            aria-label={`Close ${title}`}
          >
            ✕
          </button>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto">{children}</div>
        {footer ? (
          <div className="shrink-0 border-t border-[var(--border)] px-4 py-2 flex justify-between text-[10px] mono text-faint">
            {footer}
          </div>
        ) : null}
      </div>
    </div>,
    document.body,
  )
}
