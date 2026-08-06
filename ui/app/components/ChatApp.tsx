'use client'

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { Check, Pencil, RotateCcw, X } from 'lucide-react'
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
import { ChatContextModal } from './ChatContextModal'
import { Lightbox } from './Lightbox'
import { useStatePoller } from '../lib/hooks/useStatePoller'
import { AppRoot } from './shell/AppRoot'
import { AppHeader } from './shell/AppHeader'
import { MinaMark } from './MinaMark'

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

interface MessageImage {
  src: string
  caption: string
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** Caption from alt when real; backend uses alt "photo" for uncaptioned shots. */
function captionFromAlt(alt: string): string {
  const t = alt.trim()
  if (!t || t.toLowerCase() === 'photo') return ''
  return t
}

/**
 * Pull host images out of reply text and attach captions.
 *
 * send_photo returns `caption\\n\\n![caption](url)` — the caption must not stay
 * as bubble prose; it belongs under the image.
 */
function splitMessageMedia(
  content: string,
  extra?: string[],
): { prose: string; images: MessageImage[] } {
  const images: MessageImage[] = []
  const seen = new Set<string>()
  const add = (src: string, caption: string) => {
    if (!src || seen.has(src)) return
    if (!src.startsWith('/images/') && !src.startsWith('/api/generate/')) return
    seen.add(src)
    images.push({ src, caption })
  }

  let prose = ''
  let last = 0
  const md = new RegExp(HOST_IMAGE_MD.source, 'g')
  let m: RegExpExecArray | null
  while ((m = md.exec(content)) !== null) {
    let before = content.slice(last, m.index)
    const caption = captionFromAlt(m[1] || '')
    if (caption) {
      // Drop the tool-format duplicate line immediately before the image.
      before = before.replace(
        new RegExp(
          `(?:^|\\n)[ \\t]*${escapeRegExp(caption)}[ \\t]*(?:\\n[ \\t]*)*$`,
        ),
        (match) => (match.startsWith('\n') ? '\n' : ''),
      )
    }
    prose += before
    add(m[2], caption)
    last = m.index + m[0].length
  }
  prose += content.slice(last)

  const bare = new RegExp(HOST_IMAGE_BARE.source, 'g')
  prose = prose.replace(bare, (url) => {
    add(url, '')
    return ''
  })

  for (const u of extra ?? []) add(u, '')

  prose = prose.replace(/\n{3,}/g, '\n\n').trim()
  return { prose, images }
}

function extractImageUrls(content: string, extra?: string[]): string[] {
  return splitMessageMedia(content, extra).images.map((img) => img.src)
}

function ChatImage({
  src,
  caption,
  urls,
  index,
}: {
  src: string
  caption: string
  urls: string[]
  index: number
}) {
  const [failed, setFailed] = useState(false)
  const [lightbox, setLightbox] = useState<number | null>(null)

  if (failed) {
    return (
      <div className="alert alert-error my-2 text-[11px] mono">
        Image failed to load
      </div>
    )
  }
  const alt = caption || 'photo'
  return (
    <>
      <figure className="chat-image my-2.5">
        <button
          type="button"
          className="chat-image-btn"
          onClick={() => setLightbox(index)}
          aria-label={caption ? `View image: ${caption}` : 'View image larger'}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={src}
            alt={alt}
            className="max-w-full rounded-xl border border-[var(--border)]"
            style={{ maxHeight: '26rem' }}
            loading="lazy"
            onError={() => setFailed(true)}
          />
          <span className="chat-image-open-hint" aria-hidden>
            Open
          </span>
        </button>
        {caption ? (
          <figcaption className="chat-image-caption">{caption}</figcaption>
        ) : null}
      </figure>
      {lightbox !== null ? (
        <Lightbox
          urls={urls}
          index={lightbox}
          onClose={() => setLightbox(null)}
          onIndex={setLightbox}
        />
      ) : null}
    </>
  )
}

function renderMessageBody(content: string, images?: string[]) {
  const { prose, images: media } = splitMessageMedia(content, images)
  const urls = media.map((img) => img.src)
  const nodes: ReactNode[] = []
  if (prose) {
    nodes.push(
      <span key="prose" className="whitespace-pre-wrap">
        {prose}
      </span>,
    )
  }
  media.forEach((img, i) => {
    nodes.push(
      <ChatImage
        key={`img-${i}-${img.src}`}
        src={img.src}
        caption={img.caption}
        urls={urls}
        index={i}
      />,
    )
  })
  if (!nodes.length) {
    return <span className="whitespace-pre-wrap">{content}</span>
  }
  return nodes
}

/** Last user bubble only — inline edit, then re-run the tip turn. */
function UserMessage({
  content,
  images,
  canEdit,
  onEdit,
}: {
  content: string
  images?: string[]
  canEdit: boolean
  onEdit: (newContent: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(content)
  const taRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (!editing) return
    const el = taRef.current
    if (!el) return
    el.focus()
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`
    const len = el.value.length
    el.setSelectionRange(len, len)
  }, [editing])

  const cancel = () => {
    setEditing(false)
    setDraft(content)
  }

  const save = () => {
    const next = draft.trim()
    if (!next || next === content.trim()) {
      cancel()
      return
    }
    setEditing(false)
    onEdit(next)
  }

  if (editing) {
    return (
      <div className="msg-user-wrap msg-user-wrap-editing">
        <textarea
          ref={taRef}
          className="msg-edit-ta"
          value={draft}
          rows={3}
          onChange={(e) => {
            setDraft(e.target.value)
            const el = e.target
            el.style.height = 'auto'
            el.style.height = `${Math.min(el.scrollHeight, 240)}px`
          }}
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              e.preventDefault()
              cancel()
            }
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              e.preventDefault()
              save()
            }
          }}
        />
        <div className="msg-edit-actions">
          <button
            type="button"
            className="btn btn-soft btn-sm msg-action-btn"
            onClick={save}
            disabled={!draft.trim()}
          >
            <Check className="msg-action-icon" aria-hidden />
            Save
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm msg-action-btn"
            onClick={cancel}
          >
            <X className="msg-action-icon" aria-hidden />
            Cancel
          </button>
          <span className="msg-edit-hint">⌘/Ctrl+Enter</span>
        </div>
      </div>
    )
  }

  return (
    <div className="msg-user-wrap">
      <div className="msg msg-user">
        {renderMessageBody(content, images)}
      </div>
      {canEdit ? (
        <div className="msg-actions msg-actions-user">
          <button
            type="button"
            className="btn btn-ghost btn-sm msg-action-btn"
            onClick={() => {
              setDraft(content)
              setEditing(true)
            }}
            title="Edit message"
            aria-label="Edit message"
          >
            <Pencil className="msg-action-icon" aria-hidden />
            Edit
          </button>
        </div>
      ) : null}
    </div>
  )
}

function hasMindContent(mind: TurnMind | undefined): boolean {
  if (!mind) return false
  return Boolean(
    mind.stimulus ||
      mind.encoder ||
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
  const [contextOpen, setContextOpen] = useState(false)
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
  const { state: simState } = useStatePoller(3000)

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

  /**
   * Run a chat completion for `text`, appending an assistant bubble on success.
   * `history` is prior messages only (not including the user turn being sent).
   * When `redo` is true, the server rewinds the trailing matching turn first.
   * `rewindMessage` is the original user text to match when editing (≠ new text).
   */
  const runCompletion = useCallback(
    async (
      text: string,
      history: ChatMessage[],
      opts?: { redo?: boolean; rewindMessage?: string },
    ) => {
      setSending(true)
      sendingRef.current = true
      setError(null)
      setMind(EMPTY_TURN_MIND)
      mindRef.current = EMPTY_TURN_MIND

      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: text,
            history: history.slice(-12).map((m) => ({
              role: m.role,
              content: m.content,
            })),
            image_count: imageCount,
            image_aspect: imageAspect,
            redo: Boolean(opts?.redo),
            ...(opts?.rewindMessage
              ? { rewind_message: opts.rewindMessage }
              : {}),
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
    },
    [imageCount, imageAspect],
  )

  const send = useCallback(async () => {
    const text = input.trim()
    if (!text || sending) return

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: text,
    }
    // history is prior turns only (before this user message)
    const history = messages

    setMessages((prev) => [...prev, userMsg])
    setInput('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }

    await runCompletion(text, history)
  }, [input, sending, messages, runCompletion])

  /**
   * Redo: drop this assistant bubble (and everything after), re-run from the
   * preceding user message. Server rewinds decoder window / conversation log.
   */
  const handleRedo = useCallback(
    async (messageId: string) => {
      if (sending) return
      const idx = messages.findIndex((m) => m.id === messageId)
      if (idx < 0) return
      const target = messages[idx]
      if (target.role !== 'assistant') return

      let userIdx = -1
      for (let i = idx - 1; i >= 0; i--) {
        if (messages[i].role === 'user') {
          userIdx = i
          break
        }
      }
      if (userIdx < 0) {
        setError('Nothing to regenerate from')
        return
      }

      const userText = messages[userIdx].content
      const history = messages.slice(0, userIdx)
      // Keep user bubble; drop failed/stale assistant and any later messages
      setMessages(messages.slice(0, idx))
      await runCompletion(userText, history, { redo: true })
    },
    [sending, messages, runCompletion],
  )

  /**
   * Edit last user message only: replace text, drop the following assistant
   * (if any), rewind server tip, re-run. No deep history branching.
   */
  const handleEdit = useCallback(
    async (messageId: string, newContent: string) => {
      if (sending) return
      const text = newContent.trim()
      if (!text) return

      const idx = messages.findIndex((m) => m.id === messageId)
      if (idx < 0) return
      const target = messages[idx]
      if (target.role !== 'user') return

      let lastUserIdx = -1
      for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i].role === 'user') {
          lastUserIdx = i
          break
        }
      }
      if (idx !== lastUserIdx) {
        setError('Can only edit the last message')
        return
      }
      if (text === target.content.trim()) return

      const history = messages.slice(0, idx)
      const editedUser: ChatMessage = { ...target, content: text }
      setMessages([...history, editedUser])
      await runCompletion(text, history, {
        redo: true,
        rewindMessage: target.content,
      })
    },
    [sending, messages, runCompletion],
  )

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

  const sleeping = Boolean(simState?.sleeping)
  const status = sending
    ? 'busy'
    : !connected
      ? 'off'
      : sleeping
        ? 'sleep'
        : 'live'

  // Newest archived mind is open; all older ones stay collapsed.
  // While a turn is in flight, the live stream is the open mind — collapse archives.
  const lastAssistantWithMindId = [...messages]
    .reverse()
    .find((m) => m.role === 'assistant' && hasMindContent(m.mind))?.id

  const lastUserMessageId = [...messages]
    .reverse()
    .find((m) => m.role === 'user')?.id

  const headerActions = (
    <>
      <button
        type="button"
        className="btn btn-ghost btn-sm"
        onClick={() => setContextOpen(true)}
      >
        Context
      </button>
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
      <AppHeader
        status={status}
        statusLabel={
          sending
            ? 'Thinking'
            : !connected
              ? 'Offline'
              : sleeping
                ? 'Sleeping'
                : 'Live'
        }
        actions={headerActions}
      />

      <div className="app-body">
        <section className="flex flex-1 min-w-0 flex-col">
          <div className="flex-1 overflow-y-auto px-3 sm:px-6 py-5">
            <div className="mx-auto max-w-2xl space-y-5">
              {!hydrated ? null : messages.length === 0 && !sending ? (
                <div className="empty">
                  <MinaMark className="empty-mark" />
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
                        <UserMessage
                          content={m.content}
                          images={m.images}
                          canEdit={!sending && m.id === lastUserMessageId}
                          onEdit={(next) => void handleEdit(m.id, next)}
                        />
                      </div>
                    )
                  }

                  // Assistant turn: mind (collapsible) + reply + redo
                  return (
                    <div key={m.id} className="assistant-turn space-y-2">
                      {hasMindContent(m.mind) && m.mind && (
                        <ThoughtStream
                          mind={m.mind}
                          collapsible
                          defaultOpen={
                            !sending && m.id === lastAssistantWithMindId
                          }
                        />
                      )}
                      <div className="msg-row msg-row-assistant">
                        <div className="msg-assistant-wrap">
                          <div className="msg msg-assistant">
                            <div className="msg-label">Mina</div>
                            {renderMessageBody(m.content, m.images)}
                          </div>
                          {!sending && (
                            <div className="msg-actions">
                              <button
                                type="button"
                                className="btn btn-ghost btn-sm msg-action-btn"
                                onClick={() => void handleRedo(m.id)}
                                title="Redo response"
                                aria-label="Redo response"
                              >
                                <RotateCcw
                                  className="msg-action-icon"
                                  aria-hidden
                                />
                                Redo
                              </button>
                            </div>
                          )}
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

      <ChatContextModal
        open={contextOpen}
        onClose={() => setContextOpen(false)}
      />
    </AppRoot>
  )
}
