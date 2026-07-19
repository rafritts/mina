import { NextResponse } from 'next/server'
import { BUILD_INFO } from '../../lib/build-info'

export const dynamic = 'force-dynamic'

/** Same build identity as the UI chip — use to detect stale shells. */
export async function GET() {
  return NextResponse.json(
    {
      id: BUILD_INFO.id,
      git: BUILD_INFO.git,
      builtAt: BUILD_INFO.builtAt,
    },
    {
      headers: {
        'Cache-Control': 'no-store, no-cache, must-revalidate',
      },
    },
  )
}
