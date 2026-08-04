'use client'

import { cn } from '@/lib/utils'

export function AppRoot({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className={cn('app-root', className)}>
      <div className="app-frame">{children}</div>
    </div>
  )
}
