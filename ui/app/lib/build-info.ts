/**
 * Build identity baked in at `next build` / `next dev` start
 * (see next.config.ts env injection).
 *
 * Visible in the UI chrome and at GET /api/build.
 * If the chip ≠ curl /api/build → stale client JS.
 * If both lag a just-finished build → process still on old .next.
 */

export type BuildInfo = {
  /** Short unique id: `<git>-<nonce>` */
  id: string
  git: string
  builtAt: string
}

export const BUILD_INFO: BuildInfo = {
  id: process.env.NEXT_PUBLIC_MINA_BUILD_ID ?? 'dev',
  git: process.env.NEXT_PUBLIC_MINA_BUILD_GIT ?? 'unknown',
  builtAt: process.env.NEXT_PUBLIC_MINA_BUILD_AT ?? 'unknown',
}
