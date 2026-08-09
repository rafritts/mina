import { type NextRequest } from 'next/server'
import http from 'node:http'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'
/** Submit only — pipeline runs server-side; no long wait for the reply. */
export const maxDuration = 30

const BACKEND_HOST = process.env.MINA_BACKEND_HOST ?? '127.0.0.1'
const BACKEND_PORT = Number(process.env.MINA_BACKEND_PORT ?? '5100')

/**
 * POST /api/chat
 *
 * Submits a turn to the sim backend. The backend owns the full pipeline and
 * durable transcript. This route returns as soon as the turn is accepted
 * (202) — client disconnect cannot cancel work already accepted.
 *
 * Body: {
 *   message: string
 *   history?: ignored (server owns transcript)
 *   image_count?: "auto" | 0 | 1..5
 *   image_aspect?: "landscape" | "square" | "portrait"
 *   redo?: boolean
 *   rewind_message?: string
 * }
 *
 * Response 202: { ok, turn_id, status: "running", accepted: true }
 * Response 409: turn already in progress
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

  const rewindMessage = (body.rewind_message ?? '').trim()
  const payload = JSON.stringify({
    message,
    image_count: body.image_count ?? 'auto',
    image_aspect: body.image_aspect ?? 'square',
    redo: Boolean(body.redo),
    ...(rewindMessage ? { rewind_message: rewindMessage } : {}),
  })

  try {
    const upstream = await postJson('/api/turn', payload)
    let parsed: unknown = null
    try {
      parsed = JSON.parse(upstream.body) as unknown
    } catch {
      parsed = { error: upstream.body || 'Bad upstream response' }
    }
    return Response.json(parsed, { status: upstream.status })
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
        timeout: 15_000,
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
    req.on('timeout', () => {
      req.destroy()
      reject(new Error('upstream timeout'))
    })
    req.write(body)
    req.end()
  })
}
