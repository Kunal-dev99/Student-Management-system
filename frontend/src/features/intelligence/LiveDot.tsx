'use client'

/**
 * Shared "this came from a live model" indicator — a small pulsing dot, not a
 * flat circle. Every surface that shows an engine/provenance badge should use
 * this instead of hand-rolling its own `<span className="rounded-full ...">`,
 * so a real model answer reads the same "alive" way everywhere in the app: the
 * pulse is real signal (a live model answered this exact call), not decoration.
 *
 * `live=false` renders a flat, non-animated dot — used for rule-based /
 * fallback provenance, where looking inert is the correct, honest signal.
 */
import { cn } from '@/lib/utils'

export interface LiveDotProps {
  live: boolean
  className?: string
}

export function LiveDot({ live, className }: LiveDotProps) {
  if (!live) {
    return <span className={cn('inline-block h-1.5 w-1.5 rounded-full bg-muted-foreground', className)} aria-hidden />
  }
  return (
    <span className={cn('relative inline-flex h-1.5 w-1.5', className)} aria-hidden>
      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-500/70" />
      <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
    </span>
  )
}
