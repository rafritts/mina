'use client'

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { BUILD_INFO } from '../lib/build-info'
import { useStatePoller } from '../lib/hooks/useStatePoller'
import {
  IMAGE_ASPECT_DEFAULT,
  type ImageAspect,
} from '../lib/image-aspect'
import {
  IMAGE_COUNT_DEFAULT,
  type ImageCount,
} from '../lib/image-count'
import { AspectRatioSlider } from './AspectRatioSlider'
import { ImageCountSelector } from './ImageCountSelector'

type Role = 'user' | 'assistant'

interface ChatMessage {
  id: string
  role: Role
  content: string
  /** Host photo paths e.g. /images/abc.png (also may appear as markdown in content). */
  images?: string[]
}

const STORAGE_KEY = 'mina-chat-messages'
const PREFS_KEY = 'mina-chat-image-prefs'

const HOST_IMAGE_MD =
  /!\[([^\]]*)\]\((\/images\/[^)\s]+|\/api\/generate\/[^)\s]+)\)/g
const HOST_IMAGE_BARE = /(?<![(/])(\/images\/[A-Za-z0-9._-]+\.(?:png|jpe?g|webp|gif))/g

function extractImageUrls(content: string, extra?: string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  const add = (u: string) => {
    if (!u || seen.has(u)) return
    if (!u.startsWith('/images/') && !u.startsWith('/api/generate/')) return
    seen.add(u)
    out.push(u)
  }
  for (const u of extra ?? []) add(u)
  let m: RegExpExecArray | null
  const md = new RegExp(HOST_IMAGE_MD.source, 'g')
  while ((m = md.exec(content)) !== null) add(m[2])
  const bare = new RegExp(HOST_IMAGE_BARE.source, 'g')
  while ((m = bare.exec(content)) !== null) add(m[1])
  return out
}

function stripHostImageMarkdown(content: string): string {
  return content
    .replace(new RegExp(HOST_IMAGE_MD.source, 'g'), '')
    .replace(new RegExp(HOST_IMAGE_BARE.source, 'g'), '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function ChatImage({ src, alt }: { src: string; alt: string }) {
  const [failed, setFailed] = useState(false)
  if (failed) {
    return (
      <div
        className="my-2 rounded-md border px-3 py-2 text-[11px] value-mono"
        style={{ borderColor: 'rgba(248,113,113,0.3)', color: 'rgba(248,113,113,0.85)' }}
      >
        image failed to load: {src}
      </div>
    )
  }
  return (
    <figure className="my-2">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt={alt}
        className="max-w-full rounded-md border"
        style={{ borderColor: 'rgba(232,228,221,0.12)', maxHeight: '28rem' }}
        loading="lazy"
        onError={() => setFailed(true)}
      />
      {alt && alt !== 'photo' && (
        <figcaption className="mt-1 text-[11px]" style={{ color: 'rgba(232,228,221,0.4)' }}>
          {alt}
        </figcaption>
      )}
    </figure>
  )
}

/** Split text into prose + host images (markdown and/or structured list). */
function renderMessageBody(content: string, images?: string[]) {
  const urls = extractImageUrls(content, images)
  const prose = stripHostImageMarkdown(content)
  const nodes: ReactNode[] = []
  if (prose) {
    nodes.push(
      <span key="prose" className="whitespace-pre-wrap">
        {prose}
      </span>,
    )
  }
  urls.forEach((src, i) => {
    nodes.push(<ChatImage key={`img-${i}-${src}`} src={src} alt="photo" />)
  })
  if (!nodes.length) {
    return <span className="whitespace-pre-wrap">{content}</span>
  }
  return nodes
}

function loadMessages(): ChatMessage[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as ChatMessage[]
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function saveMessages(msgs: ChatMessage[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(msgs))
  } catch {
    /* ignore quota */
  }
}

const KEY_CHEMS = [
  'dopamine',
  'serotonin',
  'norepinephrine',
  'oxytocin',
  'cortisol',
  'endorphins',
  'adenosine',
  'epinephrine',
] as const

const SECOND_ORDER = [
  'energy',
  'mood_valence',
  'social_warmth',
  'cognitive_clarity',
  'arousal',
  'hedonic_tone',
] as const

function fmt(n: number | undefined, digits = 0): string {
  if (n == null || Number.isNaN(n)) return '—'
  return n.toFixed(digits)
}

function NeuroPanel() {
  const { state, error } = useStatePoller(3000)

  return (
    <aside
      className="flex h-full w-full flex-col border-l overflow-y-auto"
      style={{
        borderColor: 'rgba(232,228,221,0.08)',
        background: 'rgba(4,4,4,0.55)',
      }}
    >
      <div className="px-4 py-3 border-b flex items-center justify-between" style={{ borderColor: 'rgba(232,228,221,0.08)' }}>
        <div>
          <div className="text-xs tracking-widest uppercase" style={{ color: 'rgba(232,228,221,0.45)' }}>
            Neurosim
          </div>
          <div className="text-[11px] value-mono mt-0.5" style={{ color: 'rgba(232,228,221,0.3)' }}>
            {state ? (state.sleeping ? 'sleeping' : 'awake') : error ? 'offline' : 'connecting…'}
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <Link
            href="/admin/context"
            className="text-[11px] px-2 py-1 rounded border transition-colors hover:bg-white/5"
            style={{ borderColor: 'rgba(232,228,221,0.15)', color: 'rgba(232,228,221,0.55)' }}
          >
            Context
          </Link>
          <Link
            href="/admin"
            className="text-[11px] px-2 py-1 rounded border transition-colors hover:bg-white/5"
            style={{ borderColor: 'rgba(232,228,221,0.15)', color: 'rgba(232,228,221,0.55)' }}
          >
            Admin →
          </Link>
        </div>
      </div>

      {!state ? (
        <div className="p-4 text-xs value-mono" style={{ color: 'rgba(232,228,221,0.3)' }}>
          {error ?? 'Waiting for sim…'}
          <p className="mt-2 text-[11px] leading-relaxed" style={{ color: 'rgba(232,228,221,0.25)' }}>
            Run <code className="value-mono">uv run python main.py</code> so the sim process is up on :5100.
          </p>
        </div>
      ) : (
        <div className="p-4 space-y-5">
          <section>
            <h3 className="text-[10px] uppercase tracking-widest mb-2" style={{ color: 'rgba(232,228,221,0.3)' }}>
              State
            </h3>
            <div className="space-y-1.5">
              {SECOND_ORDER.map((key) => {
                const v = state.second_order[key] ?? 0
                return (
                  <div key={key} className="flex items-center gap-2">
                    <span className="text-[11px] w-24 truncate" style={{ color: 'rgba(232,228,221,0.45)' }}>
                      {key.replace(/_/g, ' ')}
                    </span>
                    <div className="flex-1 h-1 rounded-full overflow-hidden" style={{ background: 'rgba(232,228,221,0.08)' }}>
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${Math.min(100, Math.max(0, v))}%`,
                          background: 'rgba(255,200,100,0.45)',
                        }}
                      />
                    </div>
                    <span className="text-[11px] value-mono w-8 text-right" style={{ color: 'rgba(232,228,221,0.55)' }}>
                      {fmt(v)}
                    </span>
                  </div>
                )
              })}
            </div>
          </section>

          <section>
            <h3 className="text-[10px] uppercase tracking-widest mb-2" style={{ color: 'rgba(232,228,221,0.3)' }}>
              Chemicals
            </h3>
            <div className="space-y-1.5">
              {KEY_CHEMS.map((key) => {
                const entry = state.chemicals[key]
                if (!entry) return null
                const pct = Math.min(100, Math.max(0, entry.normalized * 100))
                return (
                  <div key={key} className="flex items-center gap-2">
                    <span className="text-[11px] w-24 truncate" style={{ color: 'rgba(232,228,221,0.45)' }}>
                      {key}
                    </span>
                    <div className="flex-1 h-1 rounded-full overflow-hidden" style={{ background: 'rgba(232,228,221,0.08)' }}>
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${pct}%`,
                          background: 'rgba(147,197,253,0.45)',
                        }}
                      />
                    </div>
                    <span className="text-[11px] value-mono w-10 text-right" style={{ color: 'rgba(232,228,221,0.55)' }}>
                      {fmt(entry.normalized * 10, 1)}
                    </span>
                  </div>
                )
              })}
            </div>
            <p className="text-[10px] value-mono mt-2" style={{ color: 'rgba(232,228,221,0.2)' }}>
              scale 0–10 (decoder)
            </p>
          </section>
        </div>
      )}
    </aside>
  )
}

export function ChatApp() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [erasing, setErasing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hydrated, setHydrated] = useState(false)
  const [imageCount, setImageCount] = useState<ImageCount>(IMAGE_COUNT_DEFAULT)
  const [imageAspect, setImageAspect] = useState<ImageAspect>(IMAGE_ASPECT_DEFAULT)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    setMessages(loadMessages())
    try {
      const raw = localStorage.getItem(PREFS_KEY)
      if (raw) {
        const p = JSON.parse(raw) as { imageCount?: ImageCount; imageAspect?: ImageAspect }
        if (p.imageCount !== undefined) setImageCount(p.imageCount)
        if (p.imageAspect !== undefined) setImageAspect(p.imageAspect)
      }
    } catch {
      /* ignore */
    }
    setHydrated(true)
  }, [])

  useEffect(() => {
    if (!hydrated) return
    saveMessages(messages)
  }, [messages, hydrated])

  useEffect(() => {
    if (!hydrated) return
    try {
      localStorage.setItem(PREFS_KEY, JSON.stringify({ imageCount, imageAspect }))
    } catch {
      /* ignore */
    }
  }, [imageCount, imageAspect, hydrated])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending])

  const send = useCallback(async () => {
    const text = input.trim()
    if (!text || sending) return

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: text,
    }

    const nextHistory = [...messages, userMsg]
    setMessages(nextHistory)
    setInput('')
    setSending(true)
    setError(null)

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          history: messages.slice(-12).map((m) => ({ role: m.role, content: m.content })),
          image_count: imageCount,
          image_aspect: imageAspect,
        }),
      })
      const data = (await res.json()) as {
        reply?: string
        images?: string[]
        error?: string
      }
      if (!res.ok) {
        throw new Error(data.error ?? `HTTP ${res.status}`)
      }
      let reply = (data.reply ?? '').trim() || '(empty reply)'
      const images = extractImageUrls(reply, data.images)
      // Ensure markdown carries the paths so reloads from localStorage still show photos
      for (const url of images) {
        if (!reply.includes(url)) {
          reply = `${reply}\n\n![photo](${url})`
        }
      }
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: 'assistant',
          content: reply,
          images: images.length ? images : undefined,
        },
      ])
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Send failed'
      setError(msg)
      // keep the user message; they can retry or edit
    } finally {
      setSending(false)
      textareaRef.current?.focus()
    }
  }, [input, sending, messages, imageCount, imageAspect])

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void send()
    }
  }

  const clearView = () => {
    if (sending) return
    setMessages([])
    setError(null)
    saveMessages([])
  }

  const eraseHistory = async () => {
    if (sending || erasing) return
    const ok = window.confirm(
      'Erase chat history?\n\n' +
        'This wipes conversation logs, her rolling chat window, turn dumps, ' +
        'and short-term sliding memory.\n\n' +
        'Keeps: chemistry, long-term RAG, knowledge (KAG), relationships.',
    )
    if (!ok) return
    setErasing(true)
    setError(null)
    try {
      const res = await fetch('/api/conversation/erase', { method: 'POST' })
      const data = (await res.json().catch(() => ({}))) as { ok?: boolean; error?: string }
      if (!res.ok) {
        throw new Error(data.error ?? `HTTP ${res.status}`)
      }
      setMessages([])
      saveMessages([])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erase failed')
    } finally {
      setErasing(false)
    }
  }

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: '#07070a' }}>
      {/* Chat column */}
      <div className="flex flex-1 flex-col min-w-0">
        <header
          className="h-12 flex items-center justify-between px-4 border-b flex-shrink-0"
          style={{
            borderColor: 'rgba(232,228,221,0.08)',
            background: 'rgba(4,4,4,0.7)',
          }}
        >
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium tracking-widest uppercase" style={{ color: 'rgba(232,228,221,0.7)' }}>
              Mina
            </span>
            <span className="text-[11px] value-mono hidden sm:inline" style={{ color: 'rgba(232,228,221,0.3)' }}>
              chat
            </span>
            <span
              className="text-[10px] value-mono hidden sm:inline"
              title={`${BUILD_INFO.builtAt} · GET /api/build must match`}
              style={{ color: 'rgba(232,228,221,0.22)' }}
            >
              build {BUILD_INFO.id}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/admin"
              className="text-[11px] px-2 py-1 rounded border sm:hidden"
              style={{ borderColor: 'rgba(232,228,221,0.15)', color: 'rgba(232,228,221,0.5)' }}
            >
              Sim
            </Link>
            <Button
              variant="ghost"
              size="sm"
              onClick={clearView}
              disabled={sending || erasing || messages.length === 0}
              className="text-[11px]"
              style={{ color: 'rgba(232,228,221,0.45)' }}
              title="Clear this panel only (does not change what Mina remembers)"
            >
              Clear view
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void eraseHistory()}
              disabled={sending || erasing}
              className="text-[11px]"
              style={{ color: 'rgba(248,113,113,0.75)' }}
              title="Wipe conversation logs, window, and short-term memory on the server"
            >
              {erasing ? 'Erasing…' : 'Erase history'}
            </Button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
          {!hydrated ? null : messages.length === 0 ? (
            <div className="h-full flex items-center justify-center">
              <div className="text-center max-w-sm space-y-2">
                <p className="text-sm" style={{ color: 'rgba(232,228,221,0.45)' }}>
                  Say something.
                </p>
                <p className="text-[11px] leading-relaxed" style={{ color: 'rgba(232,228,221,0.25)' }}>
                  Each message runs the full pipeline (encoder → chemistry → pillars → reply).
                  Turns can take a while.
                </p>
              </div>
            </div>
          ) : (
            messages.map((m) => (
              <div
                key={m.id}
                className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className="max-w-[min(36rem,90%)] rounded-lg px-3.5 py-2.5 text-sm leading-relaxed"
                  style={
                    m.role === 'user'
                      ? {
                          background: 'rgba(255,200,100,0.1)',
                          border: '1px solid rgba(255,200,100,0.18)',
                          color: '#f0ebe2',
                        }
                      : {
                          background: 'rgba(232,228,221,0.04)',
                          border: '1px solid rgba(232,228,221,0.08)',
                          color: '#e8e4dd',
                        }
                  }
                >
                  {m.role === 'assistant' && (
                    <div className="text-[10px] tracking-widest uppercase mb-1.5" style={{ color: 'rgba(232,228,221,0.3)' }}>
                      mina
                    </div>
                  )}
                  {renderMessageBody(m.content, m.images)}
                </div>
              </div>
            ))
          )}

          {sending && (
            <div className="flex justify-start">
              <div
                className="rounded-lg px-3.5 py-2.5 text-xs value-mono"
                style={{
                  background: 'rgba(232,228,221,0.04)',
                  border: '1px solid rgba(232,228,221,0.08)',
                  color: 'rgba(232,228,221,0.4)',
                }}
              >
                {imageCount !== 0 ? 'thinking / maybe generating…' : 'thinking…'}
              </div>
            </div>
          )}

          {error && (
            <div
              className="rounded-lg px-3 py-2 text-xs"
              style={{
                background: 'rgba(248,113,113,0.08)',
                border: '1px solid rgba(248,113,113,0.25)',
                color: '#f87171',
              }}
            >
              {error}
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        <div
          className="border-t p-3 flex-shrink-0"
          style={{ borderColor: 'rgba(232,228,221,0.08)', background: 'rgba(4,4,4,0.75)' }}
        >
          <div className="max-w-3xl mx-auto space-y-2">
            <div className="flex flex-wrap items-center gap-2 px-0.5">
              <ImageCountSelector
                value={imageCount}
                onChange={setImageCount}
                disabled={sending}
              />
              <AspectRatioSlider
                value={imageAspect}
                onChange={setImageAspect}
                disabled={sending || imageCount === 0}
              />
            </div>
            <div className="flex gap-2 items-end">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder="Message Mina…"
                rows={1}
                disabled={sending}
                className="flex-1 resize-none rounded-lg border px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-white/20 disabled:opacity-50"
                style={{
                  background: 'rgba(232,228,221,0.04)',
                  borderColor: 'rgba(232,228,221,0.12)',
                  color: '#e8e4dd',
                  minHeight: '2.5rem',
                  maxHeight: '8rem',
                }}
              />
              <Button
                onClick={() => void send()}
                disabled={sending || !input.trim()}
                className="h-10 px-4"
              >
                {sending ? '…' : 'Send'}
              </Button>
            </div>
            <p className="text-[10px] text-center value-mono" style={{ color: 'rgba(232,228,221,0.2)' }}>
              Enter to send · Shift+Enter for newline · pics via comfy-fe (Krea)
            </p>
          </div>
        </div>
      </div>

      {/* Neuro column — desktop */}
      <div className="hidden md:block w-72 flex-shrink-0 h-full">
        <NeuroPanel />
      </div>
    </div>
  )
}
