/**
 * UI image aspect preference (Kairu-compatible).
 * Sent as image_aspect on chat; host forces Krea aspect_ratio.
 */

export type ImageAspect = 'landscape' | 'square' | 'portrait'

export const IMAGE_ASPECT_DEFAULT: ImageAspect = 'square'

export type ImageAspectOption = {
  id: ImageAspect
  label: string
  krea: string
}

export const IMAGE_ASPECT_OPTIONS: ImageAspectOption[] = [
  { id: 'landscape', label: 'Landscape', krea: '16:9 (Widescreen)' },
  { id: 'square', label: 'Square', krea: '1:1 (Square)' },
  { id: 'portrait', label: 'Portrait', krea: '2:3 (Portrait Photo)' },
]

export function isImageAspect(v: unknown): v is ImageAspect {
  return v === 'landscape' || v === 'square' || v === 'portrait'
}

export function imageAspectOption(aspect: ImageAspect): ImageAspectOption {
  return (
    IMAGE_ASPECT_OPTIONS.find((o) => o.id === aspect) ??
    IMAGE_ASPECT_OPTIONS.find((o) => o.id === IMAGE_ASPECT_DEFAULT)!
  )
}
