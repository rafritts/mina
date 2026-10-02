export type PrimaryNavItem = {
  href: string
  label: string
  /** Exact pathname match. Prefix match would light Overview on every /admin route. */
  exact?: boolean
}

/**
 * One list for Chat and instrumentation. Order is conversation, state, traces, ops.
 * Routes stay on /admin/* — only the Turn trace label differs from the old page name.
 */
export const PRIMARY_NAV: PrimaryNavItem[] = [
  { href: '/', label: 'Chat', exact: true },
  { href: '/admin', label: 'Overview', exact: true },
  { href: '/admin/neuro', label: 'Chemistry' },
  { href: '/admin/freetime', label: 'Free time' },
  { href: '/admin/context', label: 'Turn trace' },
  { href: '/admin/history', label: 'History' },
  { href: '/admin/events', label: 'Events' },
  { href: '/admin/system', label: 'System' },
]

export function isPrimaryNavActive(pathname: string, item: PrimaryNavItem): boolean {
  if (item.exact) return pathname === item.href
  return pathname === item.href || pathname.startsWith(`${item.href}/`)
}
