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
  isImageAspect,
  type ImageAspect,
} from '../lib/image-aspect'
import {
  IMAGE_COUNT_DEFAULT,
  isImageCount,
  normalizeImageCount,
  type ImageCount,
} from '../lib/image-count'
import {
  defaultImageAspect,
  defaultImageCount,
  fetchRemoteChatStore,
  pushRemoteChatStore,
} from '../lib/chat-store-api'
import type { StoredChatMessage } from '../lib/chat-store-file'
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

/** Legacy browser-only keys — migrated once into the shared server store. */
const LEGACY_STORAGE_KEY = 'mina-chat-messages'
const LEGACY_PREFS_KEY = 'mina-chat-prefs'
const CONTROL_PREF_KEY = 'mina-control-open'

const SAVE_DEBOUNCE_MS = 400
const POLL_MS = 4000

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

function loadLegacyLocalMessages(): ChatMessage[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = localStorage.getItem(LEGACY_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as ChatMessage[]
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function loadLegacyLocalPrefs(): {
  imageCount?: ImageCount
  imageAspect?: ImageAspect
} {
  if (typeof window === 'undefined') return {}
  try {
    const raw = localStorage.getItem(LEGACY_PREFS_KEY)
    if (!raw) return {}
    const p = JSON.parse(raw) as {
      imageCount?: ImageCount
      imageAspect?: ImageAspect
    }
    return {
      ...(p.imageCount !== undefined && isImageCount(p.imageCount)
        ? { imageCount: normalizeImageCount(p.imageCount) }
        : {}),
      ...(p.imageAspect !== undefined && isImageAspect(p.imageAspect)
        ? { imageAspect: p.imageAspect }
        : {}),
    }
  } catch {
    return {}
  }
}

function clearLegacyLocal() {
  try {
    localStorage.removeItem(LEGACY_STORAGE_KEY)
    localStorage.removeItem(LEGACY_PREFS_KEY)
  } catch {
    /* ignore */
  }
}

function toStored(msgs: ChatMessage[]): StoredChatMessage[] {
  return msgs.map((m) => ({
    id: m.id,
    role: m.role,
    content: m.content,
    ...(m.images?.length ? { images: m.images } : {}),
    ...(m.mind ? { mind: m.mind as StoredChatMessage['mind'] } : {}),
  }))
}

function fromStored(msgs: StoredChatMessage[]): ChatMessage[] {
  return msgs.map((m) => ({
    id: m.id,
    role: m.role,
    content: m.content,
    ...(m.images?.length ? { images: m.images } : {}),
    ...(m.mind ? { mind: m.mind as TurnMind } : {}),
  }))
}

export function ChatApp() {
  // Shell renders immediately; hydrate from shared server store only.
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hydrated, setHydrated] = useState(false)
  const [imageCount, setImageCount] = useState<ImageCount>(IMAGE_COUNT_DEFAULT)
  const [imageAspect, setImageAspect] = useState<ImageAspect>(IMAGE_ASPECT_DEFAULT)
  /** Layout-only — device-local (phone drawer vs desktop pane). */
  const [controlOpen, setControlOpen] = useState(true)
  const [contextOpen, setContextOpen] = useState(false)
  const [mind, setMind] = useState<TurnMind>(EMPTY_TURN_MIND)

  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const sendingRef = useRef(false)
  const mindRef = useRef<TurnMind>(EMPTY_TURN_MIND)
  const messagesRef = useRef<ChatMessage[]>([])
  const imageAspectRef = useRef<ImageAspect>(IMAGE_ASPECT_DEFAULT)
  const imageCountRef = useRef<ImageCount>(IMAGE_COUNT_DEFAULT)
  /** Last putRevision from this machine’s disk store. */
  const serverPutRevisionRef = useRef(0)
  const serverUpdatedAtRef = useRef(0)
  /** True after local edits until a successful push. */
  const dirtyRef = useRef(false)
  /** Skip dirty mark when applying remote / hydrate. */
  const skipDirtyRef = useRef(false)
  /** Bumps on each local change so in-flight saves don't clear newer dirty. */
  const changeSeqRef = useRef(0)

  useEffect(() => {
    messagesRef.current = messages
  }, [messages])
  useEffect(() => {
    imageAspectRef.current = imageAspect
  }, [imageAspect])
  useEffect(() => {
    imageCountRef.current = imageCount
  }, [imageCount])

  const applyRemote = useCallback(
    (
      store: {
        messages: StoredChatMessage[]
        updatedAt: number
        putRevision: number
        imageAspect?: ImageAspect
        imageCount?: ImageCount
      },
    ) => {
      skipDirtyRef.current = true
      setMessages(fromStored(store.messages))
      serverUpdatedAtRef.current = store.updatedAt
      serverPutRevisionRef.current = store.putRevision
      if (store.imageAspect && isImageAspect(store.imageAspect)) {
        setImageAspect(store.imageAspect)
      }
      if (store.imageCount !== undefined && isImageCount(store.imageCount)) {
        setImageCount(normalizeImageCount(store.imageCount))
      }
      dirtyRef.current = false
    },
    [],
  )

  const flushRemoteStore = useCallback(
    async (list?: ChatMessage[]): Promise<boolean> => {
      const nextList = list ?? messagesRef.current
      if (list) messagesRef.current = list
      const result = await pushRemoteChatStore(
        toStored(nextList),
        imageAspectRef.current,
        imageCountRef.current,
        { baseRevision: serverPutRevisionRef.current },
      )
      if (result.ok) {
        serverUpdatedAtRef.current = result.store.updatedAt
        serverPutRevisionRef.current = result.store.putRevision
        // Server may have sanitized; keep revision in sync only.
        return true
      }
      if (result.conflict && result.store) {
        // Disk won. If this tab still has a longer unflushed extension, rebase once.
        const remote = result.store
        serverUpdatedAtRef.current = remote.updatedAt
        serverPutRevisionRef.current = remote.putRevision
        const local = messagesRef.current
        const remoteMsgs = remote.messages
        const localExtends =
          local.length > remoteMsgs.length &&
          remoteMsgs.every(
            (rm, i) =>
              local[i]?.id === rm.id && local[i]?.content === rm.content,
          )
        if (localExtends && !sendingRef.current) {
          const retry = await pushRemoteChatStore(
            toStored(local),
            imageAspectRef.current,
            imageCountRef.current,
            { baseRevision: remote.putRevision },
          )
          if (retry.ok) {
            serverUpdatedAtRef.current = retry.store.updatedAt
            serverPutRevisionRef.current = retry.store.putRevision
            dirtyRef.current = false
            return true
          }
          if (retry.conflict && retry.store) {
            applyRemote(retry.store)
            return true
          }
        }
        applyRemote(remote)
        return true
      }
      return false
    },
    [applyRemote],
  )

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

  // Hydrate from shared server store (phone / tablet / desktop same file).
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const remote = await fetchRemoteChatStore()
        if (cancelled) return

        // Device-local control drawer preference
        try {
          const raw = localStorage.getItem(CONTROL_PREF_KEY)
          if (raw === '0') setControlOpen(false)
          else if (raw === '1') setControlOpen(true)
        } catch {
          /* ignore */
        }
        if (typeof window !== 'undefined' && window.innerWidth < 960) {
          setControlOpen(false)
        }

        if (remote && (remote.messages.length > 0 || remote.putRevision > 0)) {
          applyRemote({
            messages: remote.messages,
            updatedAt: remote.updatedAt,
            putRevision: remote.putRevision,
            imageAspect: remote.imageAspect ?? defaultImageAspect(),
            imageCount: remote.imageCount ?? defaultImageCount(),
          })
          // Drop any leftover browser-only transcript once server owns it.
          clearLegacyLocal()
          return
        }

        // First boot: migrate this browser's localStorage into the shared store.
        const legacyMsgs = loadLegacyLocalMessages()
        const legacyPrefs = loadLegacyLocalPrefs()
        const aspect = legacyPrefs.imageAspect ?? defaultImageAspect()
        const count = legacyPrefs.imageCount ?? defaultImageCount()
        setImageAspect(aspect)
        setImageCount(count)
        imageAspectRef.current = aspect
        imageCountRef.current = count

        if (legacyMsgs.length > 0) {
          setMessages(legacyMsgs)
          messagesRef.current = legacyMsgs
          dirtyRef.current = true
          changeSeqRef.current += 1
          const pushed = await pushRemoteChatStore(
            toStored(legacyMsgs),
            aspect,
            count,
            { baseRevision: remote?.putRevision ?? 0 },
          )
          if (pushed.ok) {
            serverUpdatedAtRef.current = pushed.store.updatedAt
            serverPutRevisionRef.current = pushed.store.putRevision
            dirtyRef.current = false
            clearLegacyLocal()
          } else if (pushed.conflict && pushed.store) {
            applyRemote(pushed.store)
            clearLegacyLocal()
          }
        } else if (remote) {
          applyRemote({
            messages: remote.messages,
            updatedAt: remote.updatedAt,
            putRevision: remote.putRevision,
            imageAspect: aspect,
            imageCount: count,
          })
        }
      } catch {
        if (cancelled) return
        // Offline hydrate: best-effort legacy so the UI isn't empty.
        const legacyMsgs = loadLegacyLocalMessages()
        if (legacyMsgs.length) setMessages(legacyMsgs)
        const legacyPrefs = loadLegacyLocalPrefs()
        if (legacyPrefs.imageAspect) setImageAspect(legacyPrefs.imageAspect)
        if (legacyPrefs.imageCount) setImageCount(legacyPrefs.imageCount)
      } finally {
        if (!cancelled) setHydrated(true)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [applyRemote])

  // Dirty tracking for push (remote apply sets skipDirtyRef)
  useEffect(() => {
    if (!hydrated) return
    if (skipDirtyRef.current) {
      skipDirtyRef.current = false
      return
    }
    dirtyRef.current = true
    changeSeqRef.current += 1
  }, [messages, imageAspect, imageCount, hydrated])

  // Debounced push to shared file.
  useEffect(() => {
    if (!hydrated) return
    if (!dirtyRef.current) return

    const seq = changeSeqRef.current
    const delay = sending ? 150 : SAVE_DEBOUNCE_MS
    const t = setTimeout(async () => {
      const ok = await flushRemoteStore()
      if (!ok) return
      if (changeSeqRef.current === seq) {
        dirtyRef.current = false
      }
    }, delay)

    return () => clearTimeout(t)
  }, [messages, imageAspect, imageCount, hydrated, sending, flushRemoteStore])

  // Push on tab hide so a refresh doesn't drop the last bubble.
  useEffect(() => {
    if (!hydrated) return
    const onHide = () => {
      if (!dirtyRef.current) return
      void flushRemoteStore()
    }
    window.addEventListener('pagehide', onHide)
    window.addEventListener('beforeunload', onHide)
    return () => {
      window.removeEventListener('pagehide', onHide)
      window.removeEventListener('beforeunload', onHide)
    }
  }, [hydrated, flushRemoteStore])

  // Poll for updates from other devices (server wins when we're clean).
  useEffect(() => {
    if (!hydrated) return

    let timer: ReturnType<typeof setTimeout> | null = null
    let cancelled = false

    const tick = async () => {
      if (cancelled || document.visibilityState !== 'visible') return
      try {
        if (sendingRef.current || dirtyRef.current) return
        const remote = await fetchRemoteChatStore()
        if (cancelled || !remote) return
        if (
          remote.putRevision !== serverPutRevisionRef.current ||
          remote.updatedAt > serverUpdatedAtRef.current
        ) {
          applyRemote(remote)
        }
      } finally {
        if (!cancelled) {
          timer = setTimeout(() => void tick(), POLL_MS)
        }
      }
    }

    const onVis = () => {
      if (document.visibilityState === 'visible') void tick()
    }
    document.addEventListener('visibilitychange', onVis)
    timer = setTimeout(() => void tick(), POLL_MS)

    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [hydrated, applyRemote])

  // Device-local control pane preference only.
  useEffect(() => {
    if (!hydrated) return
    try {
      localStorage.setItem(CONTROL_PREF_KEY, controlOpen ? '1' : '0')
    } catch {
      /* ignore */
    }
  }, [controlOpen, hydrated])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending, mind])

  useEffect(() => {
    const onErase = () => {
      setMessages([])
      messagesRef.current = []
      setMind(EMPTY_TURN_MIND)
      mindRef.current = EMPTY_TURN_MIND
      dirtyRef.current = true
      changeSeqRef.current += 1
      void flushRemoteStore([])
    }
    window.addEventListener('mina:erase-chat', onErase)
    return () => window.removeEventListener('mina:erase-chat', onErase)
  }, [flushRemoteStore])

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
    messagesRef.current = []
    setError(null)
    setMind(EMPTY_TURN_MIND)
    mindRef.current = EMPTY_TURN_MIND
    dirtyRef.current = true
    changeSeqRef.current += 1
    void flushRemoteStore([])
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
