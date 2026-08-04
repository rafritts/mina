'use client'

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { Button } from '@/components/ui/button'
import { BUILD_INFO } from '../lib/build-info'
import {
  IMAGE_ASPECT_DEFAULT,
  type ImageAspect,
} from '../lib/image-aspect'
import {
  IMAGE_COUNT_DEFAULT,
  type ImageCount,
} from '../lib/image-count'
import {
  EMPTY_TURN_MIND,
  reduceTurnMind,
  useStream,
  type StreamEvent,
  type TurnMind,
} from '../lib/stream'
import { AspectRatioSlider } from './AspectRatioSlider'
import { ImageCountSelector } from './ImageCountSelector'
import { ThoughtStream } from './ThoughtStream'
import { ControlPane } from './ControlPane'

type Role = 'user' | 'assistant'

interface ChatMessage {
  id: string
  role: Role
  content: string
  images?: string[]
}

const STORAGE_KEY = 'mina-chat-messages'
const PREFS_KEY = 'mina-chat-image-prefs'

const HOST_IMAGE_MD =
  /!\[([^\]]*)\]\((\/images\/[^)\s]+|\/api\/generate\/[^)\s]+)\)/g
const HOST_IMAGE_BARE =
  /(?<![(/])(\/images\/[A-Za-z0-9._-]+\.(?:png|jpe?g|webp|gif))/g

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
        image failed: {src}
      </div>
    )
  }
  return (
    <figure className="my-2">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt={alt}
        className="max-w-full rounded-xl border"
        style={{ borderColor: 'rgba(232,228,221,0.1)', maxHeight: '26rem' }}
        loading="lazy"
        onError={() => setFailed(true)}
      />
    </figure>
  )
}

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
    /* ignore */
  }
}

export function ChatApp() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hydrated, setHydrated] = useState(false)
  const [imageCount, setImageCount] = useState<ImageCount>(IMAGE_COUNT_DEFAULT)
  const [imageAspect, setImageAspect] = useState<ImageAspect>(IMAGE_ASPECT_DEFAULT)
  const [controlOpen, setControlOpen] = useState(true)
  const [mind, setMind] = useState<TurnMind>(EMPTY_TURN_MIND)
  const [lastMind, setLastMind] = useState<TurnMind | null>(null)
  const [showLastMind, setShowLastMind] = useState(false)

  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const sendingRef = useRef(false)

  const onStreamEvent = useCallback((event: StreamEvent) => {
    // Only accumulate turn mind while a send is in flight
    if (!sendingRef.current) return
    if (
      event.type === 'stimulus_land' ||
      event.type === 'stage' ||
      event.type === 'emotion_pillar' ||
      event.type === 'context_pillar' ||
      event.type === 'reasoning' ||
      event.type === 'rag_hit' ||
      event.type === 'kag_selection' ||
      event.type === 'response_complete' ||
      event.type === 'encoder'
    ) {
      setMind((prev) => reduceTurnMind(prev, event))
    }
  }, [])

  const { connected } = useStream(onStreamEvent)

  useEffect(() => {
    setMessages(loadMessages())
    try {
      const raw = localStorage.getItem(PREFS_KEY)
      if (raw) {
        const p = JSON.parse(raw) as {
          imageCount?: ImageCount
          imageAspect?: ImageAspect
          controlOpen?: boolean
        }
        if (p.imageCount !== undefined) setImageCount(p.imageCount)
        if (p.imageAspect !== undefined) setImageAspect(p.imageAspect)
        if (p.controlOpen !== undefined) setControlOpen(p.controlOpen)
      }
    } catch {
      /* ignore */
    }
    // Desktop default: control open; mobile can toggle
    if (typeof window !== 'undefined' && window.innerWidth < 900) {
      setControlOpen(false)
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
      localStorage.setItem(
        PREFS_KEY,
        JSON.stringify({ imageCount, imageAspect, controlOpen }),
      )
    } catch {
      /* ignore */
    }
  }, [imageCount, imageAspect, controlOpen, hydrated])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending, mind])

  useEffect(() => {
    const onErase = () => {
      setMessages([])
      saveMessages([])
      setMind(EMPTY_TURN_MIND)
      setLastMind(null)
    }
    window.addEventListener('mina:erase-chat', onErase)
    return () => window.removeEventListener('mina:erase-chat', onErase)
  }, [])

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
    sendingRef.current = true
    setError(null)
    setMind(EMPTY_TURN_MIND)
    setShowLastMind(false)
    setLastMind(null)

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
      setMind((prev) => {
        const finished = { ...prev, active: true, completed: true }
        setLastMind(finished)
        return EMPTY_TURN_MIND
      })
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Send failed'
      setError(msg)
      setMind((prev) => {
        if (prev.active) setLastMind(prev)
        return EMPTY_TURN_MIND
      })
    } finally {
      setSending(false)
      sendingRef.current = false
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
    setLastMind(null)
    saveMessages([])
  }

  const autoResize = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }

  return (
    <div className="mina-shell flex h-screen overflow-hidden">
      {/* Ambient backdrop */}
      <div className="mina-ambience" aria-hidden />

      {/* ── Experience half ── */}
      <div className="relative flex flex-1 flex-col min-w-0 z-10">
        <header
          className="h-14 flex items-center justify-between px-4 sm:px-5 border-b flex-shrink-0"
          style={{
            borderColor: 'rgba(232,228,221,0.07)',
            background: 'rgba(6,6,8,0.72)',
            backdropFilter: 'blur(16px)',
          }}
        >
          <div className="flex items-center gap-3 min-w-0">
            <div className="flex items-center gap-2.5">
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center text-[11px] tracking-widest font-medium"
                style={{
                  background:
                    'radial-gradient(circle at 30% 30%, rgba(251,191,36,0.25), rgba(232,228,221,0.06))',
                  border: '1px solid rgba(251,191,36,0.2)',
                  color: 'rgba(251,191,36,0.9)',
                }}
              >
                M
              </div>
              <div className="min-w-0">
                <div
                  className="text-sm font-medium tracking-wide"
                  style={{ color: '#f0ebe2' }}
                >
                  Mina
                </div>
                <div
                  className="text-[10px] value-mono flex items-center gap-1.5"
                  style={{ color: 'rgba(232,228,221,0.35)' }}
                >
                  <span
                    className="w-1 h-1 rounded-full"
                    style={{
                      background: connected
                        ? 'rgba(52,211,153,0.9)'
                        : 'rgba(232,228,221,0.25)',
                    }}
                  />
                  {sending ? 'thinking' : connected ? 'here' : 'connecting'}
                  <span className="hidden sm:inline opacity-50">·</span>
                  <span
                    className="hidden sm:inline truncate"
                    title={BUILD_INFO.builtAt}
                  >
                    {BUILD_INFO.id}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            {lastMind && !sending && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowLastMind((v) => !v)}
                className="text-[11px] hidden sm:inline-flex"
                style={{ color: 'rgba(232,228,221,0.45)' }}
              >
                {showLastMind ? 'Hide mind' : 'Last mind'}
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={clearView}
              disabled={sending || messages.length === 0}
              className="text-[11px]"
              style={{ color: 'rgba(232,228,221,0.4)' }}
              title="Clear this panel only"
            >
              Clear
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setControlOpen((o) => !o)}
              className="text-[11px]"
              style={{
                color: controlOpen
                  ? 'rgba(251,191,36,0.85)'
                  : 'rgba(232,228,221,0.45)',
              }}
            >
              {controlOpen ? 'Control ◂' : 'Control ▸'}
            </Button>
          </div>
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-3 sm:px-6 py-5">
          <div className="mx-auto max-w-2xl space-y-4">
            {!hydrated ? null : messages.length === 0 && !sending ? (
              <div className="pt-16 sm:pt-24 text-center space-y-4">
                <div
                  className="inline-flex w-14 h-14 rounded-full items-center justify-center text-lg"
                  style={{
                    background:
                      'radial-gradient(circle at 35% 30%, rgba(251,191,36,0.2), rgba(8,8,10,0.9))',
                    border: '1px solid rgba(251,191,36,0.18)',
                    color: 'rgba(251,191,36,0.75)',
                    boxShadow: '0 0 40px rgba(251,191,36,0.08)',
                  }}
                >
                  M
                </div>
                <div>
                  <p className="text-base" style={{ color: 'rgba(232,228,221,0.65)' }}>
                    Say something real.
                  </p>
                  <p
                    className="text-[12px] mt-2 max-w-sm mx-auto leading-relaxed"
                    style={{ color: 'rgba(232,228,221,0.32)' }}
                  >
                    Each message runs her full mind: chemistry, feeling, memory,
                    strategy — then the reply. Watch the pillars fill in as she thinks.
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
                    className={`max-w-[min(36rem,92%)] rounded-2xl px-4 py-3 text-[14px] leading-[1.65] ${
                      m.role === 'user' ? 'rounded-br-md' : 'rounded-bl-md'
                    }`}
                    style={
                      m.role === 'user'
                        ? {
                            background:
                              'linear-gradient(145deg, rgba(251,191,36,0.12), rgba(251,191,36,0.06))',
                            border: '1px solid rgba(251,191,36,0.16)',
                            color: '#f5f0e6',
                          }
                        : {
                            background: 'rgba(232,228,221,0.035)',
                            border: '1px solid rgba(232,228,221,0.08)',
                            color: '#e8e4dd',
                          }
                    }
                  >
                    {m.role === 'assistant' && (
                      <div
                        className="text-[9px] tracking-[0.18em] uppercase mb-1.5"
                        style={{ color: 'rgba(232,228,221,0.3)' }}
                      >
                        mina
                      </div>
                    )}
                    {renderMessageBody(m.content, m.images)}
                  </div>
                </div>
              ))
            )}

            {/* Live mind / last mind */}
            {sending && mind.active && (
              <div className="pt-1">
                <ThoughtStream mind={mind} />
              </div>
            )}
            {sending && !mind.active && (
              <div className="flex justify-start">
                <div
                  className="rounded-2xl rounded-bl-md px-4 py-3 text-xs value-mono flex items-center gap-2"
                  style={{
                    background: 'rgba(232,228,221,0.03)',
                    border: '1px solid rgba(232,228,221,0.08)',
                    color: 'rgba(232,228,221,0.4)',
                  }}
                >
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-40" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-400/80" />
                  </span>
                  starting pipeline…
                </div>
              </div>
            )}
            {!sending && showLastMind && lastMind && (
              <div className="pt-1 opacity-90">
                <ThoughtStream mind={{ ...lastMind, active: true, completed: true }} />
              </div>
            )}

            {error && (
              <div
                className="rounded-xl px-3.5 py-2.5 text-xs"
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
        </div>

        {/* Composer */}
        <div
          className="border-t p-3 sm:p-4 flex-shrink-0"
          style={{
            borderColor: 'rgba(232,228,221,0.07)',
            background: 'rgba(6,6,8,0.82)',
            backdropFilter: 'blur(16px)',
          }}
        >
          <div className="mx-auto max-w-2xl space-y-2.5">
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
            <div
              className="flex gap-2 items-end rounded-2xl border p-2"
              style={{
                background: 'rgba(232,228,221,0.03)',
                borderColor: 'rgba(232,228,221,0.1)',
                boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.02)',
              }}
            >
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => {
                  setInput(e.target.value)
                  autoResize()
                }}
                onKeyDown={onKeyDown}
                placeholder="Message Mina…"
                rows={1}
                disabled={sending}
                className="flex-1 resize-none bg-transparent px-2.5 py-2.5 text-[14px] leading-relaxed outline-none disabled:opacity-50"
                style={{
                  color: '#e8e4dd',
                  minHeight: '2.75rem',
                  maxHeight: '12rem',
                }}
              />
              <Button
                onClick={() => void send()}
                disabled={sending || !input.trim()}
                className="h-10 px-4 rounded-xl self-end mb-0.5 font-medium"
                style={{
                  background: sending || !input.trim()
                    ? 'rgba(232,228,221,0.06)'
                    : 'linear-gradient(145deg, rgba(251,191,36,0.85), rgba(217,119,6,0.9))',
                  color: sending || !input.trim() ? 'rgba(232,228,221,0.3)' : '#1a1205',
                  border: 'none',
                }}
              >
                {sending ? '…' : 'Send'}
              </Button>
            </div>
            <p
              className="text-[10px] text-center value-mono"
              style={{ color: 'rgba(232,228,221,0.2)' }}
            >
              Enter send · Shift+Enter newline · pillars stream live while she thinks
            </p>
          </div>
        </div>
      </div>

      {/* ── Control half ── */}
      {controlOpen && (
        <div
          className="hidden md:flex flex-col flex-shrink-0 h-full z-10"
          style={{
            width: 'min(420px, 38vw)',
            background: 'rgba(5,5,7,0.92)',
            backdropFilter: 'blur(20px)',
          }}
        >
          <ControlPane streamConnected={connected} />
        </div>
      )}

      {/* Mobile control drawer */}
      {controlOpen && (
        <div className="md:hidden fixed inset-0 z-40 flex">
          <button
            type="button"
            className="flex-1 bg-black/50"
            aria-label="Close control"
            onClick={() => setControlOpen(false)}
          />
          <div
            className="w-[min(100%,22rem)] h-full shadow-2xl"
            style={{ background: 'rgba(5,5,7,0.98)' }}
          >
            <ControlPane streamConnected={connected} />
          </div>
        </div>
      )}
    </div>
  )
}
