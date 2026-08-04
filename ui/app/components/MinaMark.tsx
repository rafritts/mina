import { cn } from '@/lib/utils'

type Props = {
  className?: string
  /** Accessible name. Omit when adjacent text already names Mina. */
  title?: string
}

/** Mina brand mark — deco chevron M in a diamond frame. */
export function MinaMark({ className, title }: Props) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 32 32"
      fill="none"
      className={cn('shrink-0', className)}
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      {title ? <title>{title}</title> : null}
      <rect width="32" height="32" fill="#0b0b0d" />
      <path
        d="M16 2.5L29.5 16 16 29.5 2.5 16 16 2.5z"
        stroke="#d4a574"
        strokeWidth="1.2"
        opacity="0.85"
      />
      <path
        d="M16 5.5L26.5 16 16 26.5 5.5 16 16 5.5z"
        stroke="#d4a574"
        strokeWidth="0.75"
        opacity="0.35"
      />
      <path
        d="M9 26V7l7 13 7-13v19"
        stroke="#e8bc8a"
        strokeWidth="2.3"
        strokeLinecap="butt"
        strokeLinejoin="miter"
        strokeMiterlimit={12}
      />
    </svg>
  )
}
