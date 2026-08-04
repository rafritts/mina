'use client'

import Link from 'next/link'

/** Substance dosing UI removed — chemistry is edited via Control → Chemistry / presets. */
export default function SubstancesPage() {
  return (
    <div className="p-8 max-w-lg mx-auto space-y-4">
      <h1 className="text-sm tracking-widest uppercase" style={{ color: 'rgba(232,228,221,0.4)' }}>
        Substances
      </h1>
      <p className="text-sm leading-relaxed" style={{ color: 'rgba(232,228,221,0.55)' }}>
        Substance dosing is turned off for now. Shape her mental state from the
        Experience control half — chemistry sliders, mood presets, and time advance.
      </p>
      <Link
        href="/"
        className="inline-block text-xs px-3 py-2 rounded-md border"
        style={{ borderColor: 'rgba(251,191,36,0.3)', color: 'rgba(251,191,36,0.85)' }}
      >
        ← Back to Experience
      </Link>
    </div>
  )
}
