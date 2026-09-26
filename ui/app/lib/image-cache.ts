'use client'

import { useEffect, useState } from 'react'

/**
 * Browser Cache Storage for /images/* so a reload paints from disk
 * instead of re-downloading every photo. Cleared when those URLs
 * leave the transcript.
 */

const CACHE_NAME = 'mina-chat-images'

const blobUrls = new Map<string, string>()
const inflight = new Map<string, Promise<string>>()

function isCacheable(src: string): boolean {
  return src.startsWith('/images/') || src.startsWith('/api/generate/')
}

function cacheKey(src: string): string {
  return new URL(src, window.location.origin).href
}

async function loadIntoCache(src: string): Promise<string> {
  const key = cacheKey(src)
  const cachedBlob = blobUrls.get(key)
  if (cachedBlob) return cachedBlob

  if (typeof caches === 'undefined') return src

  const cache = await caches.open(CACHE_NAME)
  let response = await cache.match(key)
  if (!response) {
    const fetched = await fetch(src)
    if (!fetched.ok) throw new Error(`image ${fetched.status}`)
    await cache.put(key, fetched.clone())
    response = fetched
  }
  const url = URL.createObjectURL(await response.blob())
  blobUrls.set(key, url)
  return url
}

/** Resolved object URL, or null while Cache Storage is opening. */
export function useCachedImage(src: string): {
  src: string | null
  failed: boolean
} {
  const [resolved, setResolved] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    setResolved(null)
    setFailed(false)
    cachedImageSrc(src).then(
      (url) => {
        if (!cancelled) setResolved(url)
      },
      () => {
        if (!cancelled) setFailed(true)
      },
    )
    return () => {
      cancelled = true
    }
  }, [src])

  return { src: resolved, failed }
}

/** Object URL backed by Cache Storage. Falls back to the network src. */
export function cachedImageSrc(src: string): Promise<string> {
  if (!src || !isCacheable(src) || typeof window === 'undefined') {
    return Promise.resolve(src)
  }
  const key = cacheKey(src)
  const ready = blobUrls.get(key)
  if (ready) return Promise.resolve(ready)
  const pending = inflight.get(key)
  if (pending) return pending
  const job = loadIntoCache(src).finally(() => inflight.delete(key))
  inflight.set(key, job)
  return job
}

/** Keep only photos still in the transcript. Empty list drops the cache. */
export async function retainImageCache(srcs: string[]): Promise<void> {
  if (typeof caches === 'undefined') return
  const keep = new Set(srcs.filter(isCacheable).map(cacheKey))
  const cache = await caches.open(CACHE_NAME)
  const keys = await cache.keys()
  await Promise.all(
    keys.map(async (request) => {
      if (keep.has(request.url)) return
      await cache.delete(request)
      const blob = blobUrls.get(request.url)
      if (blob) {
        URL.revokeObjectURL(blob)
        blobUrls.delete(request.url)
      }
    }),
  )
  if (keep.size === 0) {
    for (const url of blobUrls.values()) URL.revokeObjectURL(url)
    blobUrls.clear()
    await caches.delete(CACHE_NAME)
  }
}
