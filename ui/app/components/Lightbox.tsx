'use client'

import { useCallback, useEffect } from 'react'
import { createPortal } from 'react-dom'
import {
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  X,
} from 'lucide-react'
import { cn } from '@/lib/utils'

type Props = {
  urls: string[]
  index: number
  onClose: () => void
  onIndex: (i: number) => void
}

export function Lightbox({ urls, index, onClose, onIndex }: Props) {
  const url = urls[index]
  const hasMany = urls.length > 1

  const prev = useCallback(() => {
    onIndex((index - 1 + urls.length) % urls.length)
  }, [index, onIndex, urls.length])

  const next = useCallback(() => {
    onIndex((index + 1) % urls.length)
  }, [index, onIndex, urls.length])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowLeft' && hasMany) prev()
      if (e.key === 'ArrowRight' && hasMany) next()
    }
    window.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [onClose, prev, next, hasMany])

  // Only opened by user click — document is always available.
  if (!url || typeof document === 'undefined') return null

  return createPortal(
    <div
      className="lightbox"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Image viewer"
    >
      <div aria-hidden className="lightbox-glow" />

      <div
        className="lightbox-toolbar"
        onClick={(e) => e.stopPropagation()}
      >
        <span className="lightbox-counter">
          {hasMany ? `${index + 1} / ${urls.length}` : 'Image'}
        </span>
        <div className="lightbox-actions">
          <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className="lightbox-icon-btn"
            title="Open original"
          >
            <ExternalLink className="h-5 w-5" />
          </a>
          <a
            href={url}
            download
            className="lightbox-icon-btn"
            title="Download"
          >
            <Download className="h-5 w-5" />
          </a>
          <button
            type="button"
            onClick={onClose}
            className="lightbox-icon-btn"
            title="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      </div>

      {hasMany ? (
        <>
          <button
            type="button"
            className="lightbox-nav lightbox-nav-prev"
            onClick={(e) => {
              e.stopPropagation()
              prev()
            }}
            aria-label="Previous image"
          >
            <ChevronLeft className="h-6 w-6 sm:h-7 sm:w-7" />
          </button>
          <button
            type="button"
            className="lightbox-nav lightbox-nav-next"
            onClick={(e) => {
              e.stopPropagation()
              next()
            }}
            aria-label="Next image"
          >
            <ChevronRight className="h-6 w-6 sm:h-7 sm:w-7" />
          </button>
        </>
      ) : null}

      <div
        className="lightbox-stage"
        onClick={(e) => e.stopPropagation()}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          key={url}
          src={url}
          alt=""
          className="lightbox-img"
        />
      </div>

      {hasMany ? (
        <div
          className="lightbox-dots"
          onClick={(e) => e.stopPropagation()}
        >
          {urls.map((_, i) => (
            <button
              key={i}
              type="button"
              aria-label={`Go to image ${i + 1}`}
              onClick={() => onIndex(i)}
              className={cn(
                'lightbox-dot',
                i === index && 'lightbox-dot-active',
              )}
            />
          ))}
        </div>
      ) : null}
    </div>,
    document.body,
  )
}
