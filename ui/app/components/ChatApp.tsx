'use client'

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
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
import { AppRoot } from './shell/AppRoot'
import { AppHeader } from './shell/AppHeader'

type Role = 'user' | 'assistant'

interface ChatMessage {
  id: string
  role: Role
  content: string
  images?: string[]
  /** Pillar thought process captured for this turn (assistant only). */
  mind?: TurnMind
}

const STORAGE_KEY = 'mina-chat-messages'
const PREFS_KEY = 'mina-chat-prefs'

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
      <div className="alert alert-error my-2 text-[11px] mono">
        Image failed to load
      </div>
    )
  }
  return (
    <figure className="my-2.5">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt={alt}
        className="max-w-full rounded-xl border border-[var(--border)]"
        style={{ maxHeight: '26rem' }}
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

function hasMindContent(mind: TurnMind | undefined): boolean {
  if (!mind) return false
  return Boolean(
    mind.emotion ||
      mind.context ||
      mind.reasoning ||
      mind.memory.length > 0 ||
      mind.active,
  )
}

function snapshotMind(mind: TurnMind): TurnMind {
  return {
    ...mind,
    active: true,
    completed: true,
    memory: [...mind.memory],
  }
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

  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const sendingRef = useRef(false)
  const mindRef = useRef<TurnMind>(EMPTY_TURN_MIND)

  const onStreamEvent = useCallback((event: StreamEvent) => {
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
      setMind((prev) => {
        const next = reduceTurnMind(prev, event)
        mindRef.current = next
        return next
      })
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
    if (typeof window !== 'undefined' && window.innerWidth < 960) {
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
      mindRef.current = EMPTY_TURN_MIND
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

    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setSending(true)
    sendingRef.current = true
    setError(null)
    setMind(EMPTY_TURN_MIND)
    mindRef.current = EMPTY_TURN_MIND

    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }

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
      if (!res.ok) throw new Error(data.error ?? `HTTP ${res.status}`)

      let reply = (data.reply ?? '').trim() || '(empty reply)'
      const images = extractImageUrls(reply, data.images)
      for (const url of images) {
        if (!reply.includes(url)) reply = `${reply}\n\n![photo](${url})`
      }

      const captured = hasMindContent(mindRef.current)
        ? snapshotMind(mindRef.current)
        : undefined

      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: 'assistant',
          content: reply,
          images: images.length ? images : undefined,
          mind: captured,
        },
      ])
      setMind(EMPTY_TURN_MIND)
      mindRef.current = EMPTY_TURN_MIND
    } catch (e) {
      // Keep partial mind as an orphaned note on a synthetic error-adjacent message?
      // Prefer: leave mind visible until clear — attach to empty assistant if we have content.
      const captured = hasMindContent(mindRef.current)
        ? snapshotMind(mindRef.current)
        : undefined
      if (captured) {
        setMessages((prev) => [
          ...prev,
          {
            id: `a-err-${Date.now()}`,
            role: 'assistant',
            content: '(no reply — see mind above)',
            mind: captured,
          },
        ])
      }
      setError(e instanceof Error ? e.message : 'Send failed')
      setMind(EMPTY_TURN_MIND)
      mindRef.current = EMPTY_TURN_MIND
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

  const autoResize = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }

  const clearView = () => {
    if (sending) return
    setMessages([])
    setError(null)
    setMind(EMPTY_TURN_MIND)
    mindRef.current = EMPTY_TURN_MIND
    saveMessages([])
  }

  const status = sending ? 'busy' : connected ? 'live' : 'off'

  // Newest assistant message with mind opens by default once
  const lastAssistantWithMindId = [...messages]
    .reverse()
    .find((m) => m.role === 'assistant' && hasMindContent(m.mind))?.id

  const headerActions = (
    <>
      <button
        type="button"
        className="btn btn-ghost btn-sm"
        onClick={clearView}
        disabled={sending || messages.length === 0}
      >
        Clear
      </button>
      <button
        type="button"
        className="btn btn-soft btn-sm"
        onClick={() => setControlOpen((o) => !o)}
        style={
          controlOpen
            ? {
                background: 'var(--accent-dim)',
                borderColor: 'var(--accent-border)',
                color: 'var(--accent-bright)',
              }
            : undefined
        }
      >
        Control
      </button>
    </>
  )

  return (
    <AppRoot>
      <AppHeader status={status} actions={headerActions} />

      <div className="app-body">
        <section className="flex flex-1 min-w-0 flex-col">
          <div className="flex-1 overflow-y-auto px-3 sm:px-6 py-5">
            <div className="mx-auto max-w-2xl space-y-5">
              {!hydrated ? null : messages.length === 0 && !sending ? (
                <div className="empty">
                  <div className="empty-mark">M</div>
                  <h1 className="empty-title">Say something real.</h1>
                  <p className="empty-desc">
                    Each reply keeps the mind that made it — open any turn to see
                    feeling, memory, and strategy again.
                  </p>
                </div>
              ) : (
                messages.map((m) => {
                  if (m.role === 'user') {
                    return (
                      <div key={m.id} className="msg-row msg-row-user">
                        <div className="msg msg-user">
                          {renderMessageBody(m.content, m.images)}
                        </div>
                      </div>
                    )
                  }

                  // Assistant turn: mind (collapsible) + reply
                  return (
                    <div key={m.id} className="assistant-turn space-y-2">
                      {hasMindContent(m.mind) && m.mind && (
                        <ThoughtStream
                          mind={m.mind}
                          collapsible
                          defaultOpen={m.id === lastAssistantWithMindId}
                        />
                      )}
                      <div className="msg-row msg-row-assistant">
                        <div className="msg msg-assistant">
                          <div className="msg-label">Mina</div>
                          {renderMessageBody(m.content, m.images)}
                        </div>
                      </div>
                    </div>
                  )
                })
              )}

              {/* Live mind while pipeline runs — becomes the message mind when reply lands */}
              {sending && (
                <div className="assistant-turn space-y-2">
                  {mind.active || hasMindContent(mind) ? (
                    <ThoughtStream mind={mind} live />
                  ) : (
                    <div className="mind">
                      <div className="mind-head">
                        <span className="status-pill" data-tone="busy">
                          <span className="dot dot-pulse" />
                          Starting
                        </span>
                        <span className="label">Live</span>
                      </div>
                      <div className="mind-body">
                        <p className="m-0 text-center text-[12px] mono text-faint py-1">
                          Pipeline starting…
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {error && <div className="alert alert-error">{error}</div>}

              <div ref={bottomRef} />
            </div>
          </div>

          <div
            className="shrink-0 border-t border-[var(--border)] px-3 sm:px-6 py-3 backdrop-blur-md"
            style={{ background: 'color-mix(in srgb, var(--bg) 90%, transparent)' }}
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
              <div className="composer">
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
                  className="field-area"
                  aria-label="Message Mina"
                />
                <button
                  type="button"
                  className="btn btn-primary btn-lg shrink-0 self-end mb-0.5"
                  onClick={() => void send()}
                  disabled={sending || !input.trim()}
                >
                  {sending ? '…' : 'Send'}
                </button>
              </div>
              <p className="text-center text-[10px] mono text-faint m-0">
                Enter to send · Shift+Enter for newline
              </p>
            </div>
          </div>
        </section>

        {controlOpen && (
          <div className="hidden lg:flex h-full shrink-0">
            <ControlPane streamConnected={connected} />
          </div>
        )}
      </div>

      {controlOpen && (
        <div className="lg:hidden control-drawer-backdrop">
          <button
            type="button"
            className="flex-1 border-0 bg-transparent cursor-default"
            aria-label="Close control"
            onClick={() => setControlOpen(false)}
          />
          <ControlPane
            streamConnected={connected}
            onClose={() => setControlOpen(false)}
            className="w-[min(100%,22.5rem)] shadow-2xl"
          />
        </div>
      )}
    </AppRoot>
  )
}
