import { type NextRequest } from 'next/server'
import http from 'node:http'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

// Proxy all /api/* requests to the backend on port 2049.
// Must use node:http — fetch() blocks port 2049 (NFS port restriction).
function proxyRequest(request: NextRequest, path: string): Promise<Response> {
  return new Promise((resolve, reject) => {
    const url = new URL(request.url)
    const backendPath = `/api/${path}${url.search}`

    const options = {
      host: '127.0.0.1',
      port: 2049,
      path: backendPath,
      method: request.method,
      headers: {
        'Content-Type': 'application/json',
        Cookie: request.headers.get('cookie') ?? '',
      },
    }

    const req = http.request(options, (res) => {
      const chunks: Buffer[] = []
      res.on('data', (chunk: Buffer) => chunks.push(chunk))
      res.on('end', () => {
        const body = Buffer.concat(chunks)
        const headers: Record<string, string> = {}
        for (const [k, v] of Object.entries(res.headers)) {
          if (typeof v === 'string') headers[k] = v
          else if (Array.isArray(v)) headers[k] = v.join(', ')
        }
        // Don't forward transfer-encoding — Next.js handles it
        delete headers['transfer-encoding']
        resolve(new Response(body, { status: res.statusCode ?? 200, headers }))
      })
      res.on('error', reject)
    })

    req.on('error', reject)

    // Forward request body for POST/PATCH
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      request.text().then((body) => {
        if (body) req.write(body)
        req.end()
      }).catch(() => req.end())
    } else {
      req.end()
    }
  })
}

export async function GET(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params
  return proxyRequest(request, path.join('/'))
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params
  return proxyRequest(request, path.join('/'))
}

export async function PATCH(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params
  return proxyRequest(request, path.join('/'))
}

export async function DELETE(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params
  return proxyRequest(request, path.join('/'))
}

export async function PUT(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params
  return proxyRequest(request, path.join('/'))
}
