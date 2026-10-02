'use client'

import { useCallback, useEffect, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { AspectRatioSlider } from '../AspectRatioSlider'
import { ImageCountSelector } from '../ImageCountSelector'
import { fetchRemoteChatStore, pushRemoteChatStore } from '../../lib/chat-store-api'
import { IMAGE_ASPECT_DEFAULT, type ImageAspect } from '../../lib/image-aspect'
import {
  IMAGE_BACKEND_OPTIONS,
  fetchImageBackend,
  isImageBackend,
  type ImageBackend,
  type ImageBackendStatus,
} from '../../lib/image-backend'
import { IMAGE_COUNT_DEFAULT, type ImageCount } from '../../lib/image-count'

/**
 * Photo source, count, and aspect. Count and aspect stay in the composer too;
 * this copy writes the same chat-store prefs and tells Chat to adopt them.
 */
export function PhotoSettings() {
  const [backend, setBackend] = useState<ImageBackend>('mint')
  const [health, setHealth] = useState<ImageBackendStatus | null>(null)
  const [count, setCount] = useState<ImageCount>(IMAGE_COUNT_DEFAULT)
  const [aspect, setAspect] = useState<ImageAspect>(IMAGE_ASPECT_DEFAULT)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    const [status, store] = await Promise.all([
      fetchImageBackend(),
      fetchRemoteChatStore(),
    ])
    if (status) {
      setHealth(status)
      if (isImageBackend(status.backend)) setBackend(status.backend)
    }
    if (store) {
      if (store.imageCount !== undefined) setCount(store.imageCount)
      if (store.imageAspect) setAspect(store.imageAspect)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const tick = async () => {
      if (!cancelled) await refresh()
    }
    void tick()
    const id = window.setInterval(() => void tick(), 4000)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [refresh])

  const chooseBackend = async (next: ImageBackend) => {
    if (next === backend) return
    if (next === 'mint' && health && !health.mint.up) return
    setError(null)
    try {
      const res = await fetch('/api/image-backend', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ backend: next }),
      })
      const data = (await res.json()) as ImageBackendStatus & { error?: string }
      const mint = data.mint ?? { up: false, url: health?.mint.url ?? '' }
      setHealth({
        backend: isImageBackend(data.backend) ? data.backend : backend,
        mint: {
          up: Boolean(mint.up),
          url: typeof mint.url === 'string' ? mint.url : '',
        },
      })
      if (!res.ok) {
        setError(data.error ?? 'Could not change image source')
        if (isImageBackend(data.backend)) setBackend(data.backend)
        return
      }
      if (isImageBackend(data.backend)) setBackend(data.backend)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not change image source')
    }
  }

  const saveCountAspect = async (nextCount: ImageCount, nextAspect: ImageAspect) => {
    const remote = await fetchRemoteChatStore()
    if (!remote) {
      setError('Could not save photo settings')
      return
    }
    const result = await pushRemoteChatStore(remote.messages, nextAspect, nextCount, {
      baseRevision: remote.putRevision ?? 0,
    })
    if (!result.ok && !result.store) {
      setError('Could not save photo settings')
      return
    }
    window.dispatchEvent(
      new CustomEvent('mina:image-prefs', {
        detail: { imageCount: nextCount, imageAspect: nextAspect },
      }),
    )
  }

  const mintUp = Boolean(health?.mint.up)
  const mintUrl = health?.mint.url

  return (
    <section>
      <div className="label section-head">Photos</div>
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="seg" role="radiogroup" aria-label="Image source">
            {IMAGE_BACKEND_OPTIONS.map((opt) => {
              const selected = backend === opt.value
              const disabled = opt.value === 'mint' && !mintUp
              return (
                <button
                  key={opt.value}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  aria-label={
                    opt.value === 'mint'
                      ? `Mint, ${health ? (mintUp ? 'up' : 'down') : 'checking'}`
                      : opt.label
                  }
                  data-active={selected ? 'true' : 'false'}
                  disabled={disabled}
                  className="seg-item"
                  onClick={() => void chooseBackend(opt.value)}
                >
                  {opt.label}
                </button>
              )
            })}
          </div>
          {health ? (
            <Badge variant={mintUp ? 'success' : 'destructive'}>
              {mintUp ? 'Mint up' : 'Mint down'}
            </Badge>
          ) : (
            <span className="text-[11px] text-muted">Checking Mint…</span>
          )}
        </div>
        {mintUrl ? (
          <p className="m-0 text-[11px] mono text-muted">{mintUrl}</p>
        ) : null}
        {error ? <p className="m-0 text-[11.5px] text-[var(--danger)]">{error}</p> : null}
        <div className="flex flex-wrap items-center gap-2">
          <ImageCountSelector
            value={count}
            onChange={(next) => {
              setCount(next)
              void saveCountAspect(next, aspect)
            }}
          />
          <AspectRatioSlider
            value={aspect}
            onChange={(next) => {
              setAspect(next)
              void saveCountAspect(count, next)
            }}
            disabled={count === 0}
          />
        </div>
      </div>
    </section>
  )
}
