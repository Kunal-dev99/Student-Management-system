'use client'

/**
 * Small badge that renders a relationship trajectory signal. Fetches lazily per student
 * id (cached), pops a detail dialog on click with the reasoning + the evidence sample
 * that drove it — grounding through transparency.
 */

import { useState } from 'react'
import {
  AlertTriangle, ArrowUpRight, Calendar, Check, Info, MessageSquare,
  MoonStar, Sparkles, type LucideIcon,
} from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import { useRelationshipSignal, type RelationshipLabel } from './api'

/**
 * The pill text is what a colleague would say — no clinical labels, no jargon. The reader
 * sees the recommended posture at a glance, and only clicks in for the "why".
 * "Steady" gets no chip at all: it's the "nothing to say" state, and a chip for it is
 * just visual noise.
 */
interface LabelPresentation {
  chip: string
  icon: LucideIcon
  tone: string
  legend: string
}

const PRESENTATION: Record<RelationshipLabel, LabelPresentation> = {
  thriving: {
    chip: 'Going well',
    icon: ArrowUpRight,
    tone: 'border-[hsl(var(--success))]/40 bg-[hsl(var(--success))]/10 text-[hsl(var(--success))]',
    legend: 'Positive momentum in recent messages and meetings.',
  },
  // Steady = "nothing needs your attention". Kept as a soft chip so the reader always
  // sees the signal is running — the absence of a chip would just look like a bug.
  steady: {
    chip: 'On track',
    icon: Check,
    tone: 'border-border/70 bg-muted text-muted-foreground',
    legend: 'Business as usual — nothing stands out either way.',
  },
  drifting: {
    chip: 'Been quiet — check in',
    icon: MoonStar,
    tone: 'border-[hsl(var(--warning))]/40 bg-[hsl(var(--warning))]/10 text-[hsl(var(--warning))]',
    legend: 'Missed touchpoints or delays showing up recently — a nudge could help.',
  },
  strained: {
    chip: 'Worth a chat',
    icon: AlertTriangle,
    tone: 'border-destructive/40 bg-destructive/10 text-destructive',
    legend: 'Direct signals of frustration or breakdown — worth checking in.',
  },
}

export function RelationshipBadge({ studentId }: { studentId: string }) {
  const { data, isLoading } = useRelationshipSignal(studentId)
  const [open, setOpen] = useState(false)

  // Placeholder while the signal loads — a subtle "…" chip so the reader knows the
  // classifier is looking; better than the badge popping into existence a beat later.
  if (isLoading || !data) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-border/70 bg-muted px-2 py-0.5 text-[10.5px] text-muted-foreground">
        <Sparkles className="h-3 w-3 opacity-50 animate-pulse" />
        Reading…
      </span>
    )
  }
  // Defensive: if the backend ever returns a label outside the mapped set (a model tweak,
  // a rule-based fallback returning a new value), fall back to the neutral "steady" chip
  // rather than crashing the whole page.
  const presentation = PRESENTATION[data.label] ?? PRESENTATION.steady
  const Icon = presentation.icon

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={cn(
          'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10.5px] font-medium transition-colors hover:opacity-80',
          presentation.tone,
        )}
        title="Signal from recent messages and meetings — click to see why"
      >
        <Icon className="h-3 w-3" />
        {presentation.chip}
      </button>
      <RelationshipDetailDialog
        open={open}
        onOpenChange={setOpen}
        signal={data}
        presentation={presentation}
      />
    </>
  )
}

function RelationshipDetailDialog({
  open, onOpenChange, signal, presentation,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  signal: NonNullable<ReturnType<typeof useRelationshipSignal>['data']>
  presentation: LabelPresentation
}) {
  const Icon = presentation.icon
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Icon className="h-4 w-4 text-primary" />
            {presentation.chip}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className={cn(
            'rounded-md border px-3 py-2 text-sm',
            presentation.tone,
          )}>
            <p className="text-foreground opacity-90">{signal.reasoning}</p>
          </div>

          <div className="text-xs text-muted-foreground flex items-center gap-2">
            <Info className="h-3 w-3" />
            {presentation.legend}
            {' '}
            <span>
              — from {signal.evidenceTotals.messages} message(s) and{' '}
              {signal.evidenceTotals.meetings} meeting(s) in the last 90 days.
              {signal.provenance.source === 'fallback' && ' Rule-based (model unavailable).'}
            </span>
          </div>

          <div>
            <p className="text-label mb-2">Evidence</p>
            <ul className="space-y-2 max-h-[320px] overflow-y-auto pr-1">
              {signal.evidence.length === 0 ? (
                <li className="text-helper text-sm">
                  No messages or meetings on record in the last 90 days.
                </li>
              ) : (
                signal.evidence.map((e, i) => (
                  <li
                    key={i}
                    className="border border-border/60 rounded-md px-3 py-2 text-sm"
                  >
                    <div className="flex items-center gap-2 mb-1 text-xs text-muted-foreground">
                      {e.kind === 'meeting'
                        ? <Calendar className="h-3 w-3" />
                        : <MessageSquare className="h-3 w-3" />}
                      <span className="uppercase font-medium">{e.author}</span>
                      <span className="num">{new Date(e.at).toLocaleDateString()}</span>
                    </div>
                    <p className="whitespace-pre-wrap">{e.text}</p>
                  </li>
                ))
              )}
            </ul>
          </div>

          <p className="text-xs text-muted-foreground pt-2 border-t border-border">
            This signal is not a diagnosis. It is a soft cue drawn from recent messages
            and meetings — for your judgement, not for automated action.
          </p>
        </div>
      </DialogContent>
    </Dialog>
  )
}
