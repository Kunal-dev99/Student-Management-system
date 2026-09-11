'use client'

/**
 * The one visual grammar for AI-produced content in the app.
 *
 * A small sparkle icon and a "drafted just now" chip mark every element the AI touched.
 * Same treatment everywhere — the reader learns it once and recognises AI vs deterministic
 * content in one glance. When the payload's provenance is "fallback" the chip flips to
 * "generated offline" so the state is honest rather than hidden.
 */

import { Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface AiSparkleProps {
  source: 'model' | 'fallback'
  model?: string | null
  className?: string
}

export function AiSparkle({ source, model, className }: AiSparkleProps) {
  const isModel = source === 'model'
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10.5px] font-medium',
        isModel
          ? 'bg-primary/10 text-primary border border-primary/30'
          : 'bg-muted text-muted-foreground border border-border',
        className,
      )}
      title={isModel && model ? `Drafted by ${model}` : 'Generated offline — model unavailable'}
    >
      <Sparkles className="h-3 w-3" />
      {isModel ? 'Drafted just now' : 'Generated offline'}
    </span>
  )
}
