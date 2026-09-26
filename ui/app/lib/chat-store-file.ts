/**
 * Shared UI chat store on disk (single conversation + image prefs).
 * Ground truth for every device hitting :2050 — same transcript, same settings.
 *
 * Path: run/ui_chat.json (Next cwd is usually ui/).
 *
 * Messages are written by the Python turn job (server-owned). The Next UI
 * primarily GETs; PUTs are for image prefs (and explicit Clear).
 */

import { mkdir, readFile, rename, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { isImageAspect, type ImageAspect } from './image-aspect'
import {
  isImageCount,
  normalizeImageCount,
  type ImageCount,
} from './image-count'

/**
 * Mind snapshot shape (mirrors TurnMind in stream.ts without importing the
 * client module — this file is used by the server route).
 */
export type StoredMind = {
  active: boolean
  stage: string | null
  stageLabel: string | null
  stimulus: string | null
  encoder: Record<string, unknown> | null
  emotion: Record<string, unknown> | null
  memory: { type: 'rag' | 'kag'; text: string; bucket?: string }[]
  context: Record<string, unknown> | null
  reasoning: Record<string, unknown> | null
  completed: boolean
  skipped: boolean
}

/** Serialize store writes so concurrent PUTs don't clobber. */
let writeChain: Promise<unknown> = Promise.resolve()

function withStoreLock<T>(fn: () => Promise<T>): Promise<T> {
  const next = writeChain.then(fn, fn)
  writeChain = next.then(
    () => undefined,
    () => undefined,
  )
  return next
}

export function withChatStoreLock<T>(fn: () => Promise<T>): Promise<T> {
  return withStoreLock(fn)
}

export type StoredChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  images?: string[]
  /** True while a photo for this bubble is still rendering. */
  imagePending?: boolean
  /** Pillar mind snapshot for this assistant turn (optional). */
  mind?: StoredMind
}

export type ChatStore = {
  updatedAt: number
  /**
   * Monotonic token advanced only by client PUTs.
   * Clients send the revision they last observed; mismatch → 409, disk wins.
   */
  putRevision: number
  messages: StoredChatMessage[]
  /** Global UI pref: image generation aspect. Synced across devices. */
  imageAspect?: ImageAspect
  /** Global UI pref: pic count (auto | 0–5). Synced across devices. */
  imageCount?: ImageCount
}

const EMPTY: ChatStore = {
  updatedAt: 0,
  putRevision: 0,
  messages: [],
}

function normalizePutRevision(v: unknown): number {
  if (typeof v === 'number' && Number.isFinite(v) && v >= 0) {
    return Math.floor(v)
  }
  return 0
}

function asRecord(v: unknown): Record<string, unknown> | null {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return null
  return v as Record<string, unknown>
}

function sanitizeMind(raw: unknown): StoredMind | undefined {
  if (!raw || typeof raw !== 'object') return undefined
  const m = raw as Partial<StoredMind> & Record<string, unknown>
  const memory: StoredMind['memory'] = []
  if (Array.isArray(m.memory)) {
    for (const x of m.memory) {
      if (
        x &&
        typeof x === 'object' &&
        ((x as { type?: string }).type === 'rag' ||
          (x as { type?: string }).type === 'kag') &&
        typeof (x as { text?: string }).text === 'string'
      ) {
        const item = x as { type: 'rag' | 'kag'; text: string; bucket?: string }
        memory.push({
          type: item.type,
          text: item.text,
          ...(typeof item.bucket === 'string' ? { bucket: item.bucket } : {}),
        })
      }
    }
  }
  return {
    active: Boolean(m.active),
    stage: typeof m.stage === 'string' ? m.stage : null,
    stageLabel: typeof m.stageLabel === 'string' ? m.stageLabel : null,
    stimulus: typeof m.stimulus === 'string' ? m.stimulus : null,
    encoder: asRecord(m.encoder),
    emotion: asRecord(m.emotion),
    memory,
    context: asRecord(m.context),
    reasoning: asRecord(m.reasoning),
    completed: Boolean(m.completed),
    skipped: Boolean(m.skipped),
  }
}

function sanitizeMessage(raw: unknown): StoredChatMessage | null {
  if (!raw || typeof raw !== 'object') return null
  const m = raw as Partial<StoredChatMessage>
  if (m.role !== 'user' && m.role !== 'assistant') return null
  if (typeof m.content !== 'string') return null
  const id =
    typeof m.id === 'string' && m.id.trim()
      ? m.id.trim()
      : `m-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  const images = Array.isArray(m.images)
    ? m.images.filter(
        (u): u is string =>
          typeof u === 'string' &&
          (u.startsWith('/images/') || u.startsWith('/api/generate/')),
      )
    : undefined
  const mind = m.role === 'assistant' ? sanitizeMind(m.mind) : undefined
  const imagePending = m.role === 'assistant' && m.imagePending === true
  return {
    id,
    role: m.role,
    content: m.content,
    ...(images && images.length ? { images } : {}),
    ...(imagePending ? { imagePending: true } : {}),
    ...(mind ? { mind } : {}),
  }
}

export function sanitizeMessages(raw: unknown): StoredChatMessage[] {
  if (!Array.isArray(raw)) return []
  const out: StoredChatMessage[] = []
  for (const item of raw) {
    const m = sanitizeMessage(item)
    if (m) out.push(m)
  }
  return out
}

/** Default: run/ui_chat.json (Next cwd is usually ui/). */
export function chatStorePath(): string {
  const override = process.env.MINA_CHAT_STORE_PATH
  if (override) return override
  // Statically scoped so Turbopack does not NFT-trace the whole monorepo.
  return path.resolve(
    /* turbopackIgnore: true */ process.cwd(),
    '..',
    'run',
    'ui_chat.json',
  )
}

export async function readChatStore(): Promise<ChatStore> {
  const file = chatStorePath()
  try {
    const raw = await readFile(file, 'utf8')
    const parsed = JSON.parse(raw) as ChatStore
    if (!parsed || !Array.isArray(parsed.messages)) return { ...EMPTY }
    const imageAspect = isImageAspect(parsed.imageAspect)
      ? parsed.imageAspect
      : undefined
    const imageCount = isImageCount(parsed.imageCount)
      ? normalizeImageCount(parsed.imageCount)
      : undefined
    return {
      updatedAt: typeof parsed.updatedAt === 'number' ? parsed.updatedAt : 0,
      putRevision: normalizePutRevision(parsed.putRevision),
      messages: sanitizeMessages(parsed.messages),
      ...(imageAspect ? { imageAspect } : {}),
      ...(imageCount !== undefined ? { imageCount } : {}),
    }
  } catch (e) {
    const err = e as NodeJS.ErrnoException
    if (err.code === 'ENOENT') return { ...EMPTY }
    console.error('[chat-store] read failed', err)
    return { ...EMPTY }
  }
}

export async function writeChatStore(store: ChatStore): Promise<ChatStore> {
  return withStoreLock(() => writeChatStoreUnlocked(store))
}

/**
 * Write without taking the lock. Only call from inside `withChatStoreLock`
 * to avoid deadlock.
 */
export async function writeChatStoreUnlocked(
  store: ChatStore,
): Promise<ChatStore> {
  const file = chatStorePath()
  const dir = path.dirname(file)
  await mkdir(dir, { recursive: true })

  const imageAspect = isImageAspect(store.imageAspect)
    ? store.imageAspect
    : undefined
  const imageCount = isImageCount(store.imageCount)
    ? normalizeImageCount(store.imageCount)
    : undefined

  const next: ChatStore = {
    updatedAt: Date.now(),
    putRevision: normalizePutRevision(store.putRevision),
    messages: sanitizeMessages(store.messages ?? []),
    ...(imageAspect ? { imageAspect } : {}),
    ...(imageCount !== undefined ? { imageCount } : {}),
  }

  const tmp = `${file}.${process.pid}.${Date.now()}.tmp`
  await writeFile(tmp, `${JSON.stringify(next, null, 2)}\n`, 'utf8')
  await rename(tmp, file)
  return next
}
