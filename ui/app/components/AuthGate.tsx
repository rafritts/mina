'use client'

import { useEffect, useState } from 'react'
import { getToken, setToken } from '../lib/api'

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const [authed, setAuthed] = useState(false)
  const [input, setInput] = useState('')
  const [checking, setChecking] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    // Check URL param first
    const params = new URLSearchParams(window.location.search)
    const urlToken = params.get('token')
    if (urlToken) {
      setToken(urlToken)
      window.history.replaceState({}, '', window.location.pathname)
      setAuthed(true)
      setChecking(false)
      return
    }
    // Check localStorage
    const stored = getToken()
    if (stored) {
      setAuthed(true)
    }
    setChecking(false)
  }, [])

  if (checking) return null

  if (!authed) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#07070a' }}>
        <div className="gallery-card rounded-xl p-8 w-80 space-y-4">
          <div className="text-sm tracking-widest uppercase" style={{ color: 'rgba(232,228,221,0.45)' }}>Mina Admin</div>
          <input
            type="password"
            placeholder="Access token"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') {
                setToken(input)
                setAuthed(true)
              }
            }}
            className="w-full bg-transparent border rounded px-3 py-2 text-sm value-mono outline-none"
            style={{ borderColor: 'rgba(232,228,221,0.15)', color: '#e8e4dd' }}
            autoFocus
          />
          {error && <p className="text-xs text-red-400">{error}</p>}
          <button
            onClick={() => { setToken(input); setAuthed(true) }}
            className="w-full py-2 rounded text-sm transition-colors"
            style={{ background: 'rgba(232,228,221,0.08)', color: '#e8e4dd' }}
          >
            Enter
          </button>
        </div>
      </div>
    )
  }

  return <>{children}</>
}
