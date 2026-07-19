import { type NextRequest } from 'next/server'
import http from 'node:http'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

// Stream proxy to sim backend. Use node:http for port compatibility.
const BACKEND_HOST = process.env.MINA_BACKEND_HOST ?? '127.0.0.1'
const BACKEND_PORT = Number(process.env.MINA_BACKEND_PORT ?? '5100')

export function GET(request: NextRequest) {
  const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>()
  const writer = writable.getWriter()
  const cookie = request.headers.get('cookie') ?? ''

  const req = http.get(
    {
      host: BACKEND_HOST,
      port: BACKEND_PORT,
      path: '/api/stream',
      headers: { Accept: 'text/event-stream', Cookie: cookie },
    },
    (res) => {
      res.on('data', (chunk: Buffer) => {
        writer.write(new Uint8Array(chunk)).catch(() => req.destroy())
      })
      res.on('end', () => writer.close())
      res.on('error', (err) => writer.abort(err))
    },
  )

  req.on('error', (err) => writer.abort(err))

  // Abort the upstream request when the client disconnects
  request.signal.addEventListener('abort', () => {
    req.destroy()
    writer.abort(new Error('client disconnected'))
  })

  return new Response(readable, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      'X-Accel-Buffering': 'no',
      Connection: 'keep-alive',
    },
  })
}
