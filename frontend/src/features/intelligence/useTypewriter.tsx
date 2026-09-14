'use client'

/**
 * Shared "the AI is writing this" reveal. Extracted from InsightsPanel so every
 * narration surface (Strip, Evidence Drawer, Scenario sensitivity, Risk Storyline)
 * gets the same living feel instead of dumping the full paragraph in one frame like
 * a static label.
 */
import { useEffect, useState } from 'react'

/** Reveal `text` character-by-character. Respects prefers-reduced-motion. */
export function useTypewriter(text: string, speed = 3, intervalMs = 16): string {
  const [out, setOut] = useState('')
  useEffect(() => {
    if (!text) { setOut(''); return }
    if (typeof window !== 'undefined' &&
        window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      setOut(text); return
    }
    setOut('')
    let i = 0
    const id = window.setInterval(() => {
      i += speed
      if (i >= text.length) { setOut(text); window.clearInterval(id) }
      else setOut(text.slice(0, i))
    }, intervalMs)
    return () => window.clearInterval(id)
  }, [text, speed, intervalMs])
  return out
}

/** Blinking cursor shown while `useTypewriter` is still revealing. */
export function TypingCursor() {
  return <span className="inline-block h-[0.9em] w-[2px] bg-primary/80 align-[-2px] animate-pulse ml-0.5" aria-hidden />
}
