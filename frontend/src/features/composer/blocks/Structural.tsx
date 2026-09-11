'use client'

/** Blocks that frame an answer rather than plot it: figures, prose, warnings, next steps. */

import { AlertTriangle, ArrowRight, Info } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { TONE_CLASS, TONE_SURFACE } from '../chartTheme'
import { CountUp } from '../reveal'
import type { ActionCard, AlertBanner, ComposerAction, KpiRow, Narrative } from '../types'

export function KpiRowBlock({ block }: { block: KpiRow }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
      {block.items.map((item) => (
        <div key={item.label}
             className={cn('rounded-md border px-3 py-2.5', TONE_SURFACE[item.tone ?? 'neutral'])}>
          <p className="text-label">{item.label}</p>
          <div className="mt-0.5 flex items-baseline gap-2">
            <span className="num text-2xl font-semibold">
              <CountUp value={item.value} />
            </span>
            {item.delta && (
              <span className={cn('num text-xs', TONE_CLASS[item.tone ?? 'neutral'])}>
                {item.delta}
              </span>
            )}
          </div>
          {item.hint && <p className="text-xs text-muted-foreground mt-0.5">{item.hint}</p>}
        </div>
      ))}
    </div>
  )
}

export function NarrativeBlock({ block }: { block: Narrative }) {
  return (
    <p className={cn('text-sm leading-relaxed', block.tone && block.tone !== 'neutral'
      ? TONE_CLASS[block.tone] : 'text-foreground')}>
      {block.body}
    </p>
  )
}

export function AlertBannerBlock({ block }: { block: AlertBanner }) {
  const tone = block.tone ?? 'warning'
  const Icon = tone === 'info' ? Info : AlertTriangle
  return (
    <div className={cn('flex items-start gap-2.5 rounded-md border px-3 py-2.5',
                       TONE_SURFACE[tone])}>
      <Icon className={cn('h-4 w-4 mt-0.5 shrink-0', TONE_CLASS[tone])} />
      <div className="min-w-0">
        {block.title && <p className="text-sm font-medium">{block.title}</p>}
        <p className="text-sm text-muted-foreground">{block.body}</p>
      </div>
    </div>
  )
}

export function ActionCardBlock({
  block, onAction,
}: { block: ActionCard; onAction: (action: ComposerAction) => void }) {
  return (
    <div className="rounded-md border border-border bg-surface-2 px-4 py-3">
      {block.body && <p className="text-sm text-muted-foreground mb-3">{block.body}</p>}
      <div className="flex flex-wrap gap-2">
        {block.actions.map((action) => (
          <Button
            key={`${action.tool}-${action.label}`}
            size="sm"
            variant={action.tone === 'danger' ? 'destructive' : 'secondary'}
            onClick={() => onAction(action)}
          >
            {action.label}
            <ArrowRight className="h-3.5 w-3.5 ml-1" />
          </Button>
        ))}
      </div>
    </div>
  )
}
