/**
 * UI total pic-count preference for this reply (Kairu-compatible).
 * - auto: at most 1 unless she decides more is warranted / user asks
 * - 0: text only
 * - 1–5: hard cap on send_photo this turn
 */

export type ImageCount = 'auto' | 0 | 1 | 2 | 3 | 4 | 5

export const IMAGE_COUNT_DEFAULT: ImageCount = 'auto'

export type ImageCountOption = {
  id: ImageCount
  label: string
  short: string
}

export const IMAGE_COUNT_OPTIONS: ImageCountOption[] = [
  { id: 'auto', label: 'Auto', short: 'Auto' },
  { id: 0, label: 'None', short: '0' },
  { id: 1, label: '1 pic', short: '1' },
  { id: 2, label: '2 pics', short: '2' },
  { id: 3, label: '3 pics', short: '3' },
  { id: 4, label: '4 pics', short: '4' },
  { id: 5, label: '5 pics', short: '5' },
]

export function isImageCount(v: unknown): v is ImageCount {
  if (v === 'auto') return true
  if (typeof v === 'number' && Number.isInteger(v) && v >= 0 && v <= 5) return true
  if (typeof v === 'string' && /^[0-5]$/.test(v)) return true
  return false
}

export function normalizeImageCount(v: unknown): ImageCount {
  if (v === 'auto' || v === null || v === undefined || v === '') return 'auto'
  if (typeof v === 'number' && Number.isInteger(v) && v >= 0 && v <= 5) return v as ImageCount
  if (typeof v === 'string' && /^[0-5]$/.test(v)) return Number(v) as ImageCount
  return IMAGE_COUNT_DEFAULT
}

export function imageCountOption(count: ImageCount): ImageCountOption {
  return (
    IMAGE_COUNT_OPTIONS.find((o) => o.id === count) ??
    IMAGE_COUNT_OPTIONS.find((o) => o.id === IMAGE_COUNT_DEFAULT)!
  )
}
