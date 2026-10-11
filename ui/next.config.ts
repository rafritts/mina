import { execSync } from 'node:child_process'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import type { NextConfig } from 'next'

const backendHost = process.env.MINA_BACKEND_HOST ?? '127.0.0.1'
const backendPort = process.env.MINA_BACKEND_PORT ?? '5100'

type BuildInfo = { id: string; git: string; builtAt: string }

/**
 * One id per build. Prefer ui/.mina-build.json from scripts/write-build-info.mjs
 * so every Next worker shares the same value (next.config can load many times).
 */
function loadBuildInfo(): BuildInfo {
  const path = join(__dirname, '.mina-build.json')
  if (existsSync(path)) {
    try {
      const parsed = JSON.parse(readFileSync(path, 'utf8')) as BuildInfo
      if (parsed?.id && parsed?.git && parsed?.builtAt) return parsed
    } catch {
      /* rewrite below */
    }
  }
  let git = 'unknown'
  try {
    git = execSync('git rev-parse --short HEAD', {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim()
  } catch {
    /* not a git checkout */
  }
  const builtAt = new Date().toISOString()
  const info: BuildInfo = {
    id: `${git}-${Date.now().toString(36)}`,
    git,
    builtAt,
  }
  try {
    writeFileSync(path, `${JSON.stringify(info, null, 2)}\n`, 'utf8')
  } catch {
    /* read-only fs — env injection still works for this process */
  }
  return info
}

const buildInfo = loadBuildInfo()

const nextConfig: NextConfig = {
  env: {
    NEXT_PUBLIC_MINA_BUILD_ID: buildInfo.id,
    NEXT_PUBLIC_MINA_BUILD_GIT: buildInfo.git,
    NEXT_PUBLIC_MINA_BUILD_AT: buildInfo.builtAt,
  },
  async rewrites() {
    return [
      {
        // Admin/state poller still hits /api/*; route handlers take precedence
        // where defined (chat, stream, catch-all proxy).
        source: '/api/state',
        destination: `http://${backendHost}:${backendPort}/api/state`,
      },
      {
        source: '/api/history',
        destination: `http://${backendHost}:${backendPort}/api/history`,
      },
      {
        source: '/api/events',
        destination: `http://${backendHost}:${backendPort}/api/events`,
      },
      {
        source: '/api/tokens',
        destination: `http://${backendHost}:${backendPort}/api/tokens`,
      },
      {
        source: '/api/heartbeat',
        destination: `http://${backendHost}:${backendPort}/api/heartbeat`,
      },
      {
        source: '/api/heartbeat/status',
        destination: `http://${backendHost}:${backendPort}/api/heartbeat/status`,
      },
      {
        source: '/api/substance',
        destination: `http://${backendHost}:${backendPort}/api/substance`,
      },
      {
        source: '/api/billing',
        destination: `http://${backendHost}:${backendPort}/api/billing`,
      },
      {
        source: '/api/obs',
        destination: `http://${backendHost}:${backendPort}/api/obs`,
      },
      {
        source: '/api/conversation/erase',
        destination: `http://${backendHost}:${backendPort}/api/conversation/erase`,
      },
      {
        // Server-owned turn status (POST submit goes through /api/chat route)
        source: '/api/turn',
        destination: `http://${backendHost}:${backendPort}/api/turn`,
      },
    ]
  },
  async headers() {
    return [
      {
        // Never cache HTML routes — always serve the latest build
        source: '/(.*)',
        headers: [
          { key: 'Cache-Control', value: 'no-cache, no-store, must-revalidate' },
        ],
      },
    ]
  },
}

export default nextConfig
