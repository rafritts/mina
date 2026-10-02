/**
 * Where chat photos are rendered.
 * mint — Comfy on restless-mint (via the Krea frontend)
 * grok — `grok -p` Imagine on this machine
 * off  — No images (send_photo is blocked)
 */

export type ImageBackend = 'mint' | 'grok' | 'off'

export const IMAGE_BACKEND_DEFAULT: ImageBackend = 'mint'

export const IMAGE_BACKEND_OPTIONS: readonly {
  value: ImageBackend
  label: string
}[] = [
  { value: 'mint', label: 'Mint' },
  { value: 'grok', label: 'Grok' },
  { value: 'off', label: 'No images' },
]

export type ImageBackendStatus = {
  backend: ImageBackend
  mint: { up: boolean; url: string }
}

export function isImageBackend(v: unknown): v is ImageBackend {
  return v === 'mint' || v === 'grok' || v === 'off'
}

export async function fetchImageBackend(): Promise<ImageBackendStatus | null> {
  try {
    const res = await fetch('/api/image-backend', { cache: 'no-store' })
    if (!res.ok) return null
    const data = (await res.json()) as Partial<ImageBackendStatus> | null
    if (!data || typeof data !== 'object') return null
    const mint = data.mint
    return {
      backend: isImageBackend(data.backend) ? data.backend : IMAGE_BACKEND_DEFAULT,
      mint: {
        up: Boolean(mint && mint.up),
        url: mint && typeof mint.url === 'string' ? mint.url : '',
      },
    }
  } catch {
    return null
  }
}
