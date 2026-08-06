import { type NextRequest } from 'next/server'
import http from 'node:http'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'
export const maxDuration = 600

const BACKEND_HOST = process.env.MINA_BACKEND_HOST ?? '127.0.0.1'
const BACKEND_PORT = Number(process.env.MINA_BACKEND_PORT ?? '5100')

/**
 * POST /api/chat
 * Body: {
 *   message: string
 *   history?: { role: string; content: string }[]
 *   image_count?: "auto" | 0 | 1..5
 *   image_aspect?: "landscape" | "square" | "portrait"
 *   redo?: boolean — drop trailing matching turn server-side before re-running
 *   rewind_message?: string — original user text to match when editing (defaults to message)
 * }
 */
export async function POST(request: NextRequest) {
  let body: {
    message?: string
    history?: { role: string; content: string }[]
    image_count?: string | number
    image_aspect?: string
    redo?: boolean
    rewind_message?: string
  }
  try {
    body = await request.json()
  } catch {
    return Response.json({ error: 'Invalid JSON' }, { status: 400 })
  }

  const message = (body.message ?? '').trim()
  if (!message) {
    return Response.json({ error: 'Empty message' }, { status: 400 })
  }

  const history = Array.isArray(body.history) ? body.history : []
  const messages = [
    ...history.map((m) => ({ role: m.role, content: m.content })),
    { role: 'user', content: message },
  ]

  const rewindMessage = (body.rewind_message ?? '').trim()
  const payload = JSON.stringify({
    model: 'mina',
    messages,
    stream: false,
    image_count: body.image_count ?? 'auto',
    image_aspect: body.image_aspect ?? 'square',
    redo: Boolean(body.redo),
    ...(rewindMessage ? { rewind_message: rewindMessage } : {}),
  })

  try {
    const upstream = await postJson('/v1/chat/completions', payload)
    if (upstream.status >= 400) {
      let errText = upstream.body
      try {
        const parsed = JSON.parse(upstream.body) as { error?: string }
        if (parsed.error) errText = parsed.error
      } catch {
        /* keep raw */
      }
      return Response.json({ error: errText }, { status: upstream.status })
    }

    const data = JSON.parse(upstream.body) as {
      choices?: { message?: { content?: string } }[]
      images?: string[]
    }
    const reply = data.choices?.[0]?.message?.content ?? ''
    const images = Array.isArray(data.images)
      ? data.images.filter((u): u is string => typeof u === 'string' && u.startsWith('/images/'))
      : []
    return Response.json({ reply, images })
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Backend unreachable'
    return Response.json(
      { error: `Sim backend offline (${BACKEND_HOST}:${BACKEND_PORT}): ${msg}` },
      { status: 503 },
    )
  }
}

function postJson(path: string, body: string): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    const req = http.request(
      {
        host: BACKEND_HOST,
        port: BACKEND_PORT,
        path,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(body),
        },
        timeout: 0,
      },
      (res) => {
        const chunks: Buffer[] = []
        res.on('data', (c: Buffer) => chunks.push(c))
        res.on('end', () => {
          resolve({
            status: res.statusCode ?? 500,
            body: Buffer.concat(chunks).toString('utf8'),
          })
        })
        res.on('error', reject)
      },
    )
    req.on('error', reject)
    req.write(body)
    req.end()
  })
}
