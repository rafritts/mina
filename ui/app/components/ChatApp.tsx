'use client'

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react'
import { Check, Pencil, RotateCcw, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  fetchRemoteChatStore,
  pushRemoteChatStore,
} from '../lib/chat-store-api'
import type { StoredChatMessage } from '../lib/chat-store-file'
import { stripImageMarkup } from '../lib/plain-text'
import {
  EMPTY_TURN_MIND,
  reduceTurnMind,
  useStream,
  type StreamEvent,
  type TurnMind,
} from '../lib/stream'
import { ThoughtStream } from './ThoughtStream'
import { useWorkspaceChrome } from './shell/workspace-chrome'
import { MinaMark } from './MinaMark'

type Role = 'user' | 'assistant'

interface ChatMessage {
  id: string
  role: Role
  content: string
  /** Pillar thought process captured for this turn (assistant only). */
  mind?: TurnMind
}

/** Legacy browser-only keys — migrated once into the shared server store. */
const LEGACY_STORAGE_KEY = 'mina-chat-messages'
const LEGACY_PREFS_KEY = 'mina-chat-prefs'

const POLL_MS = 4000

function renderMessageBody(content: string) {
  return (
    <span className="whitespace-pre-wrap">{stripImageMarkup(content)}</span>
  )
}

/** Last user bubble only — inline edit, then re-run the tip turn. */
function UserMessage({
  content,
  canEdit,
  onEdit,
}: {
  content: string
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
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="msg-action-btn"
            onClick={save}
            disabled={!draft.trim()}
          >
            <Check className="msg-action-icon" aria-hidden />
            Save
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="msg-action-btn"
            onClick={cancel}
          >
            <X className="msg-action-icon" aria-hidden />
            Cancel
          </Button>
          <span className="msg-edit-hint">⌘/Ctrl+Enter</span>
        </div>
      </div>
    )
  }

  return (
    <div className="msg-user-wrap">
      <div className="msg msg-user">
        {renderMessageBody(content)}
      </div>
      {canEdit ? (
        <div className="msg-actions msg-actions-user">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="msg-action-btn"
            onClick={() => {
              setDraft(content)
              setEditing(true)
            }}
            title="Edit message"
            aria-label="Edit message"
          >
            <Pencil className="msg-action-icon" aria-hidden />
            Edit
          </Button>
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
    content: stripImageMarkup(m.content),
    ...(m.mind ? { mind: m.mind as StoredChatMessage['mind'] } : {}),
  }))
}

function fromStored(msgs: StoredChatMessage[]): ChatMessage[] {
  return msgs.map((m) => ({
    id: m.id,
    role: m.role,
    content: stripImageMarkup(m.content),
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
  const [mind, setMind] = useState<TurnMind>(EMPTY_TURN_MIND)

  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const sendingRef = useRef(false)
  const mindRef = useRef<TurnMind>(EMPTY_TURN_MIND)
  const messagesRef = useRef<ChatMessage[]>([])
  /** Last putRevision from this machine’s disk store. */
  const serverPutRevisionRef = useRef(0)
  const serverUpdatedAtRef = useRef(0)
  /** True while a clear is pushing, so a poll does not restore the old list. */
  const dirtyRef = useRef(false)

  useEffect(() => {
    messagesRef.current = messages
  }, [messages])

  const applyRemote = useCallback(
    (
      store: {
        messages: StoredChatMessage[]
        updatedAt: number
        putRevision: number
      },
    ) => {
      setMessages(fromStored(store.messages))
      serverUpdatedAtRef.current = store.updatedAt
      serverPutRevisionRef.current = store.putRevision
      dirtyRef.current = false
    },
    [],
  )

  /**
   * Push an explicit message list (Clear). Messages are otherwise server-owned.
   */
  const flushRemoteStore = useCallback(
    async (list?: ChatMessage[]): Promise<boolean> => {
      const remote = await fetchRemoteChatStore()
      const baseRevision =
        remote?.putRevision ?? serverPutRevisionRef.current
      const messages =
        list !== undefined
          ? toStored(list)
          : remote?.messages ?? toStored(messagesRef.current)

      const result = await pushRemoteChatStore(messages, { baseRevision })
      if (result.ok) {
        serverUpdatedAtRef.current = result.store.updatedAt
        serverPutRevisionRef.current = result.store.putRevision
        if (list !== undefined || remote) {
          applyRemote(result.store)
        }
        dirtyRef.current = false
        return true
      }
      if (result.conflict && result.store) {
        applyRemote(result.store)
        return true
      }
      return false
    },
    [applyRemote],
  )

  const pullChatStore = useCallback(async () => {
    const remote = await fetchRemoteChatStore()
    if (!remote) return
    if (
      remote.putRevision === serverPutRevisionRef.current &&
      remote.updatedAt <= serverUpdatedAtRef.current
    ) {
      return
    }
    // A clear is in flight. Take the server list once it lands, but do not
    // mark the view clean until that push finishes.
    if (dirtyRef.current) {
      setMessages(fromStored(remote.messages))
      messagesRef.current = fromStored(remote.messages)
      serverUpdatedAtRef.current = remote.updatedAt
      serverPutRevisionRef.current = remote.putRevision
      return
    }
    applyRemote(remote)
  }, [applyRemote])

  const onStreamEvent = useCallback(
    (event: StreamEvent) => {
      if (event.type === 'turn_status') {
        const st = event.payload.status
        if (st === 'running') {
          setSending(true)
          sendingRef.current = true
          setError(null)
        } else if (st === 'idle' || st === 'error') {
          setSending(false)
          sendingRef.current = false
          if (st === 'error' && event.payload.error) {
            setError(event.payload.error)
          }
          setMind(EMPTY_TURN_MIND)
          mindRef.current = EMPTY_TURN_MIND
          void pullChatStore()
        }
        return
      }

      // Live mind is purely observational — only while a turn is running.
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
        if (event.type === 'response_complete') {
          // Transcript is written server-side; pull it.
          void pullChatStore()
        }
      }
    },
    [pullChatStore],
  )

  const { connected } = useStream(onStreamEvent)
  const chrome = useWorkspaceChrome()

  // Observe server turn status (survives mobile background / reconnect).
  useEffect(() => {
    if (!hydrated) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null

    const tick = async () => {
      if (cancelled) return
      try {
        const res = await fetch('/api/turn', { cache: 'no-store' })
        if (res.ok) {
          const data = (await res.json()) as {
            status?: string
            error?: string | null
          }
          if (cancelled) return
          const running = data.status === 'running'
          if (running !== sendingRef.current) {
            setSending(running)
            sendingRef.current = running
            if (running) {
              setError(null)
            } else {
              setMind(EMPTY_TURN_MIND)
              mindRef.current = EMPTY_TURN_MIND
              void pullChatStore()
            }
          }
          if (data.status === 'error' && data.error) {
            setError(data.error)
          }
        }
      } catch {
        /* ignore transient */
      } finally {
        if (!cancelled) {
          const delay = sendingRef.current ? 800 : 2500
          timer = setTimeout(() => void tick(), delay)
        }
      }
    }

    void tick()
    const onVis = () => {
      if (document.visibilityState === 'visible') void tick()
    }
    document.addEventListener('visibilitychange', onVis)
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [hydrated, pullChatStore])

  // Hydrate from shared server store (phone / tablet / desktop same file).
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const remote = await fetchRemoteChatStore()
        if (cancelled) return

        if (remote && (remote.messages.length > 0 || remote.putRevision > 0)) {
          applyRemote({
            messages: remote.messages,
            updatedAt: remote.updatedAt,
            putRevision: remote.putRevision,
          })
          // Drop any leftover browser-only transcript once server owns it.
          clearLegacyLocal()
          return
        }

        // First boot: migrate this browser's localStorage into the shared store.
        const legacyMsgs = loadLegacyLocalMessages()

        if (legacyMsgs.length > 0) {
          setMessages(legacyMsgs)
          messagesRef.current = legacyMsgs
          dirtyRef.current = true
          const pushed = await pushRemoteChatStore(toStored(legacyMsgs), {
            baseRevision: remote?.putRevision ?? 0,
          })
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
          })
        }
      } catch {
        if (cancelled) return
        // Offline hydrate: best-effort legacy so the UI isn't empty.
        const legacyMsgs = loadLegacyLocalMessages()
        if (legacyMsgs.length) setMessages(legacyMsgs)
      } finally {
        if (!cancelled) setHydrated(true)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [applyRemote])

  // Poll transcript from disk. Fast while a turn is running so mobile resume
  // and multi-device stay in sync without owning the process.
  useEffect(() => {
    if (!hydrated) return

    let timer: ReturnType<typeof setTimeout> | null = null
    let cancelled = false

    const tick = async () => {
      if (cancelled) return
      try {
        if (document.visibilityState === 'visible' || sendingRef.current) {
          await pullChatStore()
        }
      } finally {
        if (!cancelled) {
          const delay = sendingRef.current ? 700 : POLL_MS
          timer = setTimeout(() => void tick(), delay)
        }
      }
    }

    const onVis = () => {
      if (document.visibilityState === 'visible') void tick()
    }
    document.addEventListener('visibilitychange', onVis)
    timer = setTimeout(() => void tick(), 400)

    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [hydrated, pullChatStore])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending, mind])

  useEffect(() => {
    const onErase = (e: Event) => {
      if (e.cancelable) e.preventDefault()
      setMessages([])
      messagesRef.current = []
      setMind(EMPTY_TURN_MIND)
      mindRef.current = EMPTY_TURN_MIND
      dirtyRef.current = true
      void flushRemoteStore([])
    }
    window.addEventListener('mina:erase-chat', onErase)
    return () => window.removeEventListener('mina:erase-chat', onErase)
  }, [flushRemoteStore])

  /**
   * Submit a turn. Server owns the entire pipeline + durable transcript.
   * This only asks the backend to accept the job (202) — never waits for a reply.
   */
  const submitTurn = useCallback(
    async (
      text: string,
      opts?: { redo?: boolean; rewindMessage?: string },
    ) => {
      const message = stripImageMarkup(text)
      if (!message) return

      setError(null)
      setMind(EMPTY_TURN_MIND)
      mindRef.current = EMPTY_TURN_MIND

      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message,
            redo: Boolean(opts?.redo),
            ...(opts?.rewindMessage
              ? { rewind_message: stripImageMarkup(opts.rewindMessage) }
              : {}),
          }),
        })
        const data = (await res.json()) as {
          ok?: boolean
          turn_id?: string
          status?: string
          error?: string
        }
        if (!res.ok) {
          throw new Error(data.error ?? `HTTP ${res.status}`)
        }
        // Accepted — observe from here on (status poll + chat-store + SSE).
        setSending(true)
        sendingRef.current = true
        void pullChatStore()
      } catch (e) {
        setSending(false)
        sendingRef.current = false
        setError(e instanceof Error ? e.message : 'Send failed')
      } finally {
        textareaRef.current?.focus()
      }
    },
    [pullChatStore],
  )

  const send = useCallback(async () => {
    const text = input.trim()
    if (!text || sending) return

    setInput('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }

    // No local bubble — server writes the user message before the job starts.
    await submitTurn(text)
  }, [input, sending, submitTurn])

  /**
   * Redo: server rewinds pipeline + UI transcript, re-runs from the user text.
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
      await submitTurn(userText, { redo: true })
    },
    [sending, messages, submitTurn],
  )

  /**
   * Edit last user message: server rewinds tip, replaces user text, re-runs.
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

      await submitTurn(text, {
        redo: true,
        rewindMessage: target.content,
      })
    },
    [sending, messages, submitTurn],
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

  const clearView = useCallback(() => {
    if (sendingRef.current) return
    setMessages([])
    messagesRef.current = []
    setError(null)
    setMind(EMPTY_TURN_MIND)
    mindRef.current = EMPTY_TURN_MIND
    dirtyRef.current = true
    void flushRemoteStore([])
  }, [flushRemoteStore])

  const clearViewRef = useRef(clearView)
  useLayoutEffect(() => {
    clearViewRef.current = clearView
  }, [clearView])

  useLayoutEffect(() => {
    if (!chrome) return
    chrome.setClearHandler(() => clearViewRef.current())
    return () => chrome.setClearHandler(null)
  }, [chrome])

  useLayoutEffect(() => {
    if (!chrome) return
    chrome.setClearDisabled(sending || messages.length === 0)
  }, [chrome, sending, messages.length])

  useLayoutEffect(() => {
    if (!chrome) return
    chrome.setStatusOverride(sending ? 'thinking' : !connected ? 'offline' : null)
    return () => chrome.setStatusOverride(null)
  }, [chrome, sending, connected])

  // Newest archived mind is open; all older ones stay collapsed.
  // While a turn is in flight, the live stream is the open mind — collapse archives.
  const lastAssistantWithMindId = [...messages]
    .reverse()
    .find((m) => m.role === 'assistant' && hasMindContent(m.mind))?.id

  const lastUserMessageId = [...messages]
    .reverse()
    .find((m) => m.role === 'user')?.id

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <section className="flex flex-1 min-h-0 min-w-0 flex-col">
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
                            {renderMessageBody(m.content)}
                          </div>
                          {!sending && (
                            <div className="msg-actions">
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                className="msg-action-btn"
                                onClick={() => void handleRedo(m.id)}
                                title="Redo response"
                                aria-label="Redo response"
                              >
                                <RotateCcw
                                  className="msg-action-icon"
                                  aria-hidden
                                />
                                Redo
                              </Button>
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
                <Button
                  type="button"
                  size="lg"
                  className="shrink-0 self-end mb-0.5"
                  onClick={() => void send()}
                  disabled={sending || !input.trim()}
                >
                  {sending ? '…' : 'Send'}
                </Button>
              </div>
              <p className="text-center text-[10px] mono text-faint m-0">
                Enter to send · Shift+Enter for newline
              </p>
            </div>
          </div>
        </section>
    </div>
  )
}
