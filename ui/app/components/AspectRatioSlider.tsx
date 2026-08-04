'use client'

import { cn } from '@/lib/utils'
import { IMAGE_ASPECT_OPTIONS, type ImageAspect } from '../lib/image-aspect'

type Props = {
  value: ImageAspect
  onChange: (next: ImageAspect) => void
  className?: string
  disabled?: boolean
}

export function AspectRatioSlider({ value, onChange, className, disabled }: Props) {
  const index = Math.max(0, IMAGE_ASPECT_OPTIONS.findIndex((o) => o.id === value))
  const current = IMAGE_ASPECT_OPTIONS[index] ?? IMAGE_ASPECT_OPTIONS[1]

  return (
    <div
      className={cn(
        'flex shrink-0 items-center gap-2',
        disabled && 'pointer-events-none opacity-40',
        className,
      )}
      title={`Image aspect: ${current.label}`}
    >
      <span className="label hidden xl:inline">Aspect</span>
      <div
        role="radiogroup"
        aria-label="Image aspect ratio"
        className="relative flex h-9 items-center rounded-full border border-[var(--border)] bg-[var(--surface)] p-0.5"
      >
        <div
          aria-hidden
          className="pointer-events-none absolute top-0.5 bottom-0.5 w-[calc((100%-4px)/3)] rounded-full transition-transform duration-200 ease-out"
          style={{
            transform: `translateX(${index * 100}%)`,
            background: 'var(--accent-dim)',
            boxShadow: 'inset 0 0 0 1px var(--accent-border)',
          }}
        />
        {IMAGE_ASPECT_OPTIONS.map((opt) => {
          const selected = opt.id === value
          return (
            <button
              key={opt.id}
              type="button"
              role="radio"
              aria-checked={selected}
              aria-label={opt.label}
              disabled={disabled}
              onClick={() => onChange(opt.id)}
              className={cn(
                'relative z-10 flex h-8 w-8 items-center justify-center rounded-full border-0 bg-transparent transition-colors sm:w-9 cursor-pointer',
                selected ? 'text-[var(--accent-bright)]' : 'text-[var(--text-faint)] hover:text-[var(--text-muted)]',
              )}
            >
              <AspectIcon aspect={opt.id} active={selected} />
            </button>
          )
        })}
      </div>
      <span className="hidden w-16 text-[11px] mono text-muted xl:inline">{current.label}</span>
    </div>
  )
}

function AspectIcon({ aspect, active }: { aspect: ImageAspect; active: boolean }) {
  const box =
    aspect === 'landscape' ? 'h-2.5 w-4' : aspect === 'portrait' ? 'h-4 w-2.5' : 'h-3 w-3'
  return (
    <span
      className={cn(
        'block rounded-[2px] border-2 transition',
        active
          ? 'border-[var(--accent-bright)] bg-[var(--accent-dim)]'
          : 'border-current',
        box,
      )}
    />
  )
}
