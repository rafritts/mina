import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

export type ChipTone = 'neutral' | 'success' | 'warning' | 'error' | 'info'

const VARIANT = {
  neutral: 'outline',
  success: 'success',
  warning: 'warning',
  error: 'destructive',
  info: 'info',
} as const

export function chipTone(color?: string): ChipTone {
  if (color === 'success' || color === 'warning' || color === 'error' || color === 'info') {
    return color
  }
  return 'neutral'
}

/** Status chip. Badge is the primitive; tones match the Mina chip scale. */
export function Chip({
  tone = 'neutral',
  className,
  children,
}: {
  tone?: ChipTone
  className?: string
  children: React.ReactNode
}) {
  return (
    <Badge variant={VARIANT[tone]} className={cn(className)}>
      {children}
    </Badge>
  )
}
