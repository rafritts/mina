'use client'

import { cn } from '@/lib/utils'
import {
  IMAGE_COUNT_OPTIONS,
  imageCountOption,
  type ImageCount,
} from '../lib/image-count'

type Props = {
  value: ImageCount
  onChange: (next: ImageCount) => void
  className?: string
  disabled?: boolean
}

export function ImageCountSelector({ value, onChange, className, disabled }: Props) {
  const current = imageCountOption(value)

  return (
    <div
      className={cn(
        'flex shrink-0 items-center gap-1.5',
        disabled && 'pointer-events-none opacity-40',
        className,
      )}
      title={`Pictures this reply: ${current.label}`}
    >
      <span className="label hidden xl:inline">Pics</span>
      <label className="relative block">
        <span className="sr-only">Total pictures this reply</span>
        <select
          value={value === 'auto' ? 'auto' : String(value)}
          disabled={disabled}
          aria-label="Total pictures this reply"
          onChange={(e) => {
            const raw = e.target.value
            if (raw === 'auto') {
              onChange('auto')
              return
            }
            const n = Number(raw)
            if (Number.isInteger(n) && n >= 0 && n <= 5) onChange(n as ImageCount)
          }}
          className={cn(
            'h-9 w-[4.75rem] cursor-pointer appearance-none rounded-full border border-[var(--border)]',
            'bg-[var(--surface)] py-0 pl-2.5 pr-6 text-center text-[11px] font-medium mono text-[var(--text-secondary)]',
            'disabled:cursor-not-allowed',
          )}
        >
          {IMAGE_COUNT_OPTIONS.map((opt) => (
            <option
              key={String(opt.id)}
              value={opt.id === 'auto' ? 'auto' : String(opt.id)}
              className="bg-[var(--bg-elevated)] text-[var(--text)]"
            >
              {opt.short}
            </option>
          ))}
        </select>
        <span
          aria-hidden
          className="pointer-events-none absolute inset-y-0 right-2 flex items-center text-faint"
        >
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
            <path
              d="M2.5 3.5L5 6.5L7.5 3.5"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
      </label>
    </div>
  )
}
