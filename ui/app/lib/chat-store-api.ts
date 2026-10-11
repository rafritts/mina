/**
 * Client helpers for the shared server chat store (GET/PUT /api/chat-store).
 */

import type { ChatStore, StoredChatMessage } from './chat-store-file'

export type RemoteChatStore = ChatStore

export type PushChatStoreResult =
  | { ok: true; store: RemoteChatStore }
  | { ok: false; conflict: boolean; store: RemoteChatStore | null }

function normalizeRemote(data: ChatStore): RemoteChatStore {
  return {
    updatedAt: typeof data.updatedAt === 'number' ? data.updatedAt : 0,
    putRevision:
      typeof data.putRevision === 'number' && Number.isFinite(data.putRevision)
        ? Math.max(0, Math.floor(data.putRevision))
        : 0,
    messages: Array.isArray(data.messages) ? data.messages : [],
  }
}

export async function fetchRemoteChatStore(): Promise<RemoteChatStore | null> {
  try {
    const res = await fetch('/api/chat-store', { cache: 'no-store' })
    if (!res.ok) return null
    const data = (await res.json()) as ChatStore
    if (!data || !Array.isArray(data.messages)) return null
    return normalizeRemote(data)
  } catch {
    return null
  }
}

export async function pushRemoteChatStore(
  messages: StoredChatMessage[],
  opts: { baseRevision: number },
): Promise<PushChatStoreResult> {
  try {
    const baseRevision =
      typeof opts.baseRevision === 'number' && Number.isFinite(opts.baseRevision)
        ? Math.max(0, Math.floor(opts.baseRevision))
        : 0

    const res = await fetch('/api/chat-store', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages,
        baseRevision,
      }),
    })

    if (res.status === 409) {
      const data = (await res.json()) as ChatStore
      if (!data || !Array.isArray(data.messages)) {
        return { ok: false, conflict: false, store: null }
      }
      return { ok: false, conflict: true, store: normalizeRemote(data) }
    }
    if (!res.ok) return { ok: false, conflict: false, store: null }
    const data = (await res.json()) as ChatStore
    if (!data || !Array.isArray(data.messages)) {
      return { ok: false, conflict: false, store: null }
    }
    return { ok: true, store: normalizeRemote(data) }
  } catch {
    return { ok: false, conflict: false, store: null }
  }
}

/** Empty the shared transcript view. Does not call `/api/conversation/erase`. */
export async function clearRemoteTranscript(): Promise<boolean> {
  const remote = await fetchRemoteChatStore()
  const result = await pushRemoteChatStore([], {
    baseRevision: remote?.putRevision ?? 0,
  })
  return result.ok || Boolean(result.conflict && result.store)
}
