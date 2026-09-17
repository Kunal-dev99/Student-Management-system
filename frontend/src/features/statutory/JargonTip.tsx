'use client'

/**
 * A small `?` icon that, on hover / focus, explains a piece of statutory jargon in plain English.
 * The dictionary lives in ``jargon.ts`` — static, deterministic, no runtime LLM call.
 *
 * Usage:
 *   <span>HUSID <JargonTip term="HUSID" /></span>
 *   <span>Coding frame <JargonTip term="coding frame" /></span>
 */
import { HelpCircle } from 'lucide-react'

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

import { jargonFor } from './jargon'

export function JargonTip({ term, className }: { term: string; className?: string }) {
  const text = jargonFor(term)
  if (!text) return null   // silently no-op when we haven't defined an explainer yet
  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            aria-label={`What is ${term}?`}
            className={
              'inline-flex align-middle text-muted-foreground hover:text-foreground cursor-help ' +
              (className ?? '')
            }
            // We want the tooltip on hover / focus, but the button itself shouldn't do anything on
            // click — a click is fine (it opens the tooltip too) but we don't want it to submit
            // a surrounding form.
            onClick={(e) => { e.preventDefault(); e.stopPropagation() }}
          >
            <HelpCircle className="h-3.5 w-3.5" />
          </button>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs text-xs leading-relaxed">
          {text}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
