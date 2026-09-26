import { readFile } from 'node:fs/promises'
import path from 'node:path'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const MIME: Record<string, string> = {
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.png': 'image/png',
  '.webp': 'image/webp',
  '.gif': 'image/gif',
}

/** Durable chat photos live next to the Python process under run/chat-images. */
function chatImagesDir(): string {
  // ui/ is one level under repo root
  return path.resolve(process.cwd(), '..', 'run', 'chat-images')
}

function safeResolve(root: string, rel: string): string | null {
  const base = path.resolve(root)
  const file = path.resolve(base, rel)
  if (!file.startsWith(base + path.sep) && file !== base) return null
  return file
}

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ name: string[] }> },
) {
  const { name } = await ctx.params
  if (!name?.length) return new Response('Not found', { status: 404 })

  const rel = name.join('/')
  const file = safeResolve(chatImagesDir(), rel)
  if (!file) return new Response('Not found', { status: 404 })

  try {
    const buf = await readFile(file)
    const ext = path.extname(file).toLowerCase()
    const type = MIME[ext] ?? 'application/octet-stream'
    return new Response(buf, {
      headers: {
        'Content-Type': type,
        'Cache-Control': 'public, max-age=31536000, immutable',
      },
    })
  } catch {
    return new Response('Not found', { status: 404 })
  }
}
