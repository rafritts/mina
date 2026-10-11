import { NextResponse } from 'next/server'
import {
  readChatStore,
  sanitizeMessages,
  withChatStoreLock,
  writeChatStoreUnlocked,
  type ChatStore,
} from '../../lib/chat-store-file'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET() {
  const store = await readChatStore()
  return NextResponse.json(store, {
    headers: { 'Cache-Control': 'no-store' },
  })
}

export async function PUT(req: Request) {
  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'invalid_json' }, { status: 400 })
  }

  const b = body as Partial<ChatStore> & {
    /** Client's last observed putRevision. Required for a successful write. */
    baseRevision?: number
  }

  if (!Array.isArray(b.messages)) {
    return NextResponse.json({ error: 'messages_required' }, { status: 400 })
  }

  const baseRevision =
    typeof b.baseRevision === 'number' && Number.isFinite(b.baseRevision)
      ? Math.floor(b.baseRevision)
      : null

  // Atomic conflict check + write so two devices cannot both pass the same revision.
  return withChatStoreLock(async () => {
    const existing = await readChatStore()
    const diskRevision = existing.putRevision ?? 0

    // This machine is ground truth. Stale clients (wrong/missing base) get 409
    // and the current disk store — they must re-hydrate, not overwrite.
    if (baseRevision === null || baseRevision !== diskRevision) {
      return NextResponse.json(existing, {
        status: 409,
        headers: {
          'Cache-Control': 'no-store',
          'X-Mina-Conflict': 'put_revision',
        },
      })
    }

    const messages = sanitizeMessages(b.messages)

    const saved = await writeChatStoreUnlocked({
      updatedAt: 0, // server stamps
      putRevision: diskRevision + 1,
      messages,
    })

    return NextResponse.json(saved, {
      headers: { 'Cache-Control': 'no-store' },
    })
  })
}
