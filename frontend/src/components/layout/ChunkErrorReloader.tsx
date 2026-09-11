'use client'

import { useEffect } from 'react'

/**
 * Auto-recover from stale JS chunks after a redeploy.
 *
 * Next.js hashes each lazy-loaded route into its filename. When the server
 * rebuilds, the old hashes disappear — but a browser tab that was loaded
 * before the rebuild still holds references to the old chunk names. The
 * next client-side navigation then throws `ChunkLoadError` → the whole
 * page unmounts under React's error boundary → the user sees a blank
 * screen. This listens for that specific error and hard-reloads once so
 * the tab picks up the current build's chunks.
 *
 * Guarded by a session-storage flag so a genuinely broken chunk (rather
 * than a stale reference) can't cause an infinite reload loop.
 */
export function ChunkErrorReloader() {
  useEffect(() => {
    const RELOAD_FLAG = 'chunk-reload-attempted'

    const isChunkError = (msg: unknown) =>
      typeof msg === 'string' &&
      (msg.includes('ChunkLoadError') || msg.includes('Loading chunk'))

    const recover = () => {
      try {
        if (sessionStorage.getItem(RELOAD_FLAG)) return
        sessionStorage.setItem(RELOAD_FLAG, '1')
      } catch {
        // sessionStorage can throw in private mode — fall through and reload once.
      }
      window.location.reload()
    }

    const onError = (event: ErrorEvent) => {
      if (isChunkError(event.message) || isChunkError(event.error?.name)) recover()
    }
    const onRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason
      if (isChunkError(reason?.message) || isChunkError(reason?.name)) recover()
    }

    // Clear the flag on a successful load so future stale-chunk events can recover.
    try {
      if (sessionStorage.getItem(RELOAD_FLAG)) {
        // Give the app a moment to settle before clearing.
        setTimeout(() => sessionStorage.removeItem(RELOAD_FLAG), 5000)
      }
    } catch { /* ignore */ }

    window.addEventListener('error', onError)
    window.addEventListener('unhandledrejection', onRejection)
    return () => {
      window.removeEventListener('error', onError)
      window.removeEventListener('unhandledrejection', onRejection)
    }
  }, [])

  return null
}
