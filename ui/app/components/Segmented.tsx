'use client'

import { cn } from '@/lib/utils'

/**
 * One filter control. Replaces per-page inline styles on Events, History, and Scene.
 */
export function Segmented<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
  className,
}: {
  value: T
  options: readonly { value: T; label: string }[]
  onChange: (next: T) => void
  ariaLabel: string
  className?: string
}) {
  return (
    <div className={cn('seg', className)} role="radiogroup" aria-label={ariaLabel}>
      {options.map((opt) => {
        const active = value === opt.value
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            data-active={active ? 'true' : 'false'}
            className="seg-item"
            onClick={() => onChange(opt.value)}
          >
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}
