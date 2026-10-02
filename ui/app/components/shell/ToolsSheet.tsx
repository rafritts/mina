'use client'

import { useCallback, useState } from 'react'
import { apiFetch } from '../../lib/api'
import { clearRemoteTranscript } from '../../lib/chat-store-api'
import { PRESETS } from '../../lib/presets'
import { cn } from '@/lib/utils'
import { Sheet } from './Sheet'

export function ToolsSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [toast, setToast] = useState<{ text: string; ok: boolean } | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [advanceHours, setAdvanceHours] = useState('1')

  const showToast = useCallback((text: string, ok: boolean) => {
    setToast({ text, ok })
    window.setTimeout(() => setToast(null), 2800)
  }, [])

  const applyPreset = async (name: string, values: Record<string, number>) => {
    setBusy(`preset:${name}`)
    try {
      await apiFetch('/api/state', { method: 'PATCH', body: JSON.stringify(values) })
      showToast(`Applied “${name}”`, true)
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Failed', false)
    } finally {
      setBusy(null)
    }
  }

  const advance = async () => {
    setBusy('advance')
    try {
      await apiFetch('/api/state/advance', {
        method: 'POST',
        body: JSON.stringify({ hours: parseFloat(advanceHours) || 1 }),
      })
      showToast(`Advanced ${advanceHours}h`, true)
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Failed', false)
    } finally {
      setBusy(null)
    }
  }

  const resetBaseline = async () => {
    if (!confirm('Reset chemistry to baseline? Keeps chat & memory.')) return
    setBusy('reset')
    try {
      await apiFetch('/api/state/reset', { method: 'POST' })
      showToast('Reset to baseline', true)
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Failed', false)
    } finally {
      setBusy(null)
    }
  }

  const runHeartbeat = async () => {
    setBusy('heartbeat')
    try {
      const r = await apiFetch<{ ok: boolean; message?: string }>('/api/heartbeat', {
        method: 'POST',
      })
      showToast(r.message ?? 'Heartbeat done', r.ok)
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Failed', false)
    } finally {
      setBusy(null)
    }
  }

  const eraseHistory = async () => {
    if (
      !confirm(
        'Erase conversation history?\n\nClears the transcript, scene, diary, RAG, who you are to her, and free-time sessions.',
      )
    ) {
      return
    }
    setBusy('erase')
    try {
      await apiFetch('/api/conversation/erase', { method: 'POST' })
      const ev = new CustomEvent('mina:erase-chat', { cancelable: true })
      window.dispatchEvent(ev)
      if (!ev.defaultPrevented) {
        await clearRemoteTranscript()
      }
      showToast('History erased', true)
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Failed', false)
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <Sheet open={open} onClose={onClose} title="Tools">
        <div className="p-4 space-y-5">
          <section>
            <div className="label section-head">Mood presets</div>
            <div className="grid grid-cols-2 gap-2">
              {PRESETS.map((preset) => (
                <button
                  key={preset.name}
                  type="button"
                  disabled={busy === `preset:${preset.name}`}
                  onClick={() => void applyPreset(preset.name, preset.values)}
                  className="surface-interactive p-2.5 text-left"
                >
                  <div className="text-[12.5px] font-medium">{preset.name}</div>
                  <div className="text-[10.5px] text-muted leading-snug mt-0.5">
                    {preset.description}
                  </div>
                </button>
              ))}
            </div>
          </section>

          <section>
            <div className="label section-head">Time</div>
            <div className="flex items-center gap-2">
              <input
                type="number"
                className="field w-20 mono text-sm"
                value={advanceHours}
                onChange={(e) => setAdvanceHours(e.target.value)}
                min={0.25}
                max={168}
                step={0.25}
                aria-label="Hours to advance"
              />
              <span className="text-[11.5px] text-muted">hours</span>
              <button
                type="button"
                className="btn btn-soft btn-sm ml-auto"
                onClick={() => void advance()}
                disabled={busy === 'advance'}
              >
                {busy === 'advance' ? '…' : 'Advance'}
              </button>
            </div>
          </section>

          <section className="space-y-2">
            <div className="label section-head">Actions</div>
            <button
              type="button"
              className="btn btn-soft btn-block"
              onClick={() => void runHeartbeat()}
              disabled={busy === 'heartbeat'}
            >
              {busy === 'heartbeat' ? 'Running freetime…' : 'Run freetime heartbeat'}
            </button>
            <button
              type="button"
              className="btn btn-danger btn-block"
              onClick={() => void resetBaseline()}
              disabled={busy === 'reset'}
            >
              {busy === 'reset' ? 'Resetting…' : 'Reset chemistry to baseline'}
            </button>
            <button
              type="button"
              className="btn btn-danger btn-block"
              onClick={() => void eraseHistory()}
              disabled={busy === 'erase'}
            >
              {busy === 'erase' ? 'Erasing…' : 'Erase conversation history'}
            </button>
          </section>
        </div>
      </Sheet>
      {toast && open ? (
        <div className={cn('toast', toast.ok ? 'toast-ok' : 'toast-err')}>{toast.text}</div>
      ) : null}
    </>
  )
}
