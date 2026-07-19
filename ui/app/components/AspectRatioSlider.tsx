'use client'

import { cn } from '@/lib/utils'
import { IMAGE_ASPECT_OPTIONS, type ImageAspect } from '../lib/image-aspect'

type Props = {
  value: ImageAspect
  onChange: (next: ImageAspect) => void
  className?: string
  disabled?: boolean
}

/** Compact 3-position control: landscape · square · portrait. */
export function AspectRatioSlider({ value, onChange, className, disabled }: Props) {
  const index = Math.max(0, IMAGE_ASPECT_OPTIONS.findIndex((o) => o.id === value))
  const current = IMAGE_ASPECT_OPTIONS[index] ?? IMAGE_ASPECT_OPTIONS[1]

  return (
    <div
      className={cn('flex shrink-0 items-center gap-2', disabled && 'pointer-events-none opacity-40', className)}
      title={`Image aspect: ${current.label} (${current.krea})`}
    >
      <span className="hidden text-[10px] font-medium uppercase tracking-wider xl:inline" style={{ color: 'rgba(232,228,221,0.35)' }}>
        Aspect
      </span>
      <div
        role="radiogroup"
        aria-label="Image aspect ratio"
        className="relative flex h-9 items-center rounded-full border p-0.5"
        style={{ borderColor: 'rgba(232,228,221,0.12)', background: 'rgba(0,0,0,0.35)' }}
      >
        <div
          aria-hidden
          className="pointer-events-none absolute top-0.5 bottom-0.5 w-[calc((100%-4px)/3)] rounded-full transition-transform duration-200 ease-out"
          style={{
            transform: `translateX(${index * 100}%)`,
            background: 'rgba(255,200,100,0.18)',
            boxShadow: 'inset 0 0 0 1px rgba(255,200,100,0.25)',
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
                'relative z-10 flex h-8 w-8 items-center justify-center rounded-full transition-colors sm:w-9',
                selected ? 'text-amber-100' : 'text-zinc-500 hover:text-zinc-300',
              )}
            >
              <AspectIcon aspect={opt.id} active={selected} />
            </button>
          )
        })}
      </div>
      <span className="hidden w-16 text-[11px] tabular-nums xl:inline" style={{ color: 'rgba(232,228,221,0.4)' }}>
        {current.label}
      </span>
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
        active ? 'border-amber-300/95 bg-amber-300/25' : 'border-current',
        box,
      )}
    />
  )
}
