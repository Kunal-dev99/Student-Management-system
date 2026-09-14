'use client'

/**
 * One-paragraph LLM narration with an explicit provenance badge.
 *
 * Design rule (spec §22 + §25): the deterministic facts always render first and
 * synchronously; the paragraph is optional and self-labels its source so the user
 * can see whether they're reading model prose or a rule-based sentence.
 *
 * Visual rule added once we confirmed these are genuinely reasoned answers (not
 * static/fallback text): a REAL model answer should visibly feel alive — a
 * thinking pulse while waiting, a typewriter reveal, a soft living glow once
 * settled. A rule-based fallback stays deliberately calm and flat. That contrast
 * is itself useful signal: if a box looks "alive", the words in it came from a
 * live model; if it looks plain, they didn't.
 */
import { Bot, ShieldCheck, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTypewriter, TypingCursor } from './useTypewriter'

export interface Narration {
  body: string
  source: 'model' | 'fallback'
  model?: string | null
}

export interface NarratedParagraphProps {
  narration: Narration | null | undefined
  loading?: boolean
  className?: string
}

export function NarratedParagraph({ narration, loading, className }: NarratedParagraphProps) {
  const isModel = narration?.source === 'model'
  const typed = useTypewriter(isModel ? narration!.body : '', 3, 14)
  const stillTyping = isModel && typed.length < (narration?.body.length ?? 0)

  if (loading) {
    return (
      <div
        className={cn(
          'flex items-center gap-2 rounded-md border border-primary/20 px-3 py-2.5',
          'bg-gradient-to-r from-primary/[0.06] via-primary/[0.02] to-transparent',
          className,
        )}
        aria-busy
        aria-live="polite"
      >
        <span className="relative flex h-2 w-2 shrink-0">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary/60" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-primary" />
        </span>
        <span className="text-xs text-muted-foreground italic">Thinking…</span>
      </div>
    )
  }
  if (!narration) return null

  if (!isModel) {
    // Deliberately flat/plain — see file docstring. This is a rule-based sentence,
    // not a live reasoned answer, and it should never be dressed up to look like one.
    return (
      <div className={cn('rounded-md border bg-muted/30 px-3 py-2', className)}>
        <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-muted-foreground mb-1">
          <ShieldCheck className="h-3 w-3" />
          <span>Rule-based narration</span>
        </div>
        <p className="text-sm leading-relaxed text-foreground">{narration.body}</p>
      </div>
    )
  }

  return (
    <div
      className={cn(
        'rounded-md border border-primary/20 px-3 py-2',
        'bg-gradient-to-br from-primary/[0.05] via-transparent to-primary/[0.02]',
        className,
      )}
    >
      <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-primary/80 mb-1">
        <Bot className="h-3 w-3" />
        <span>AI narration</span>
        {narration.model ? (
          <span className="inline-flex items-center gap-1 opacity-70 normal-case tracking-normal">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-500/70" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
            </span>
            {narration.model}
          </span>
        ) : null}
      </div>
      <p className="text-sm leading-relaxed text-foreground">
        {typed}
        {stillTyping ? <TypingCursor /> : (
          <Sparkles className="inline-block h-3 w-3 ml-1.5 -mt-0.5 text-primary/50" aria-hidden />
        )}
      </p>
    </div>
  )
}
