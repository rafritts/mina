'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { PRIMARY_NAV, isPrimaryNavActive } from './primary-nav'

export function PrimaryNav({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname()

  return (
    <>
      {PRIMARY_NAV.map((item) => {
        const active = isPrimaryNavActive(pathname, item)
        return (
          <Link
            key={item.href}
            href={item.href}
            className="side-link"
            data-active={active ? 'true' : 'false'}
            aria-current={active ? 'page' : undefined}
            onClick={onNavigate}
          >
            {item.label}
          </Link>
        )
      })}
    </>
  )
}
