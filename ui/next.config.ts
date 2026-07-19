import type { NextConfig } from 'next'

const backendHost = process.env.MINA_BACKEND_HOST ?? '127.0.0.1'
const backendPort = process.env.MINA_BACKEND_PORT ?? '5100'

const nextConfig: NextConfig = {
  output: 'standalone',
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
    ]
  },
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'Cache-Control', value: 'no-cache, no-store, must-revalidate' },
        ],
      },
    ]
  },
}

export default nextConfig
