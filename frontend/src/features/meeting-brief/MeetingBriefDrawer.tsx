'use client'

/**
 * Meeting-brief drawer — "Prepare for meeting" opens this beside the supervision record.
 *
 * A supervisor reads it in fifteen seconds. Deterministic evidence (last meeting date,
 * agreed actions, changes since, open flags) renders as the primary content and cannot
 * be invented; the AI-authored paragraph sits above it with a sparkle chip; three
 * rule-based questions close it out.
 *
 * The reveal is paced by real server work — the reasoning trace ticks through fetch →
 * compare → write → lay out, with the evidence appearing after the second step.
 */

import { useCallback, useMemo, useState } from 'react'
import {
  AlertTriangle, Calendar, Clock, FileText, Sparkles, X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { api } from '@/shared/api/client'
import { AiSparkle } from '@/features/ai/AiSparkle'
import { ReasoningTrace, useReasoningTrace } from '@/features/ai/ReasoningTrace'
import type { MeetingBriefPayload } from './types'

export function MeetingBriefDrawer({
  studentId, studentName, open, onOpenChange,
}: {
  studentId: string
  studentName?: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [payload, setPayload] = useState<MeetingBriefPayload | null>(null)
  const [runId, setRunId] = useState(0)

  const fetcher = useCallback(
    (signal: AbortSignal) =>
      api.raw(`/meeting-brief/${studentId}/stream`, {
        headers: { Accept: 'text/event-stream' },
        signal,
      }),
    [studentId],
  )

  const { steps, running, error } = useReasoningTrace<MeetingBriefPayload>({
    // Only stream when the drawer is open — otherwise a mounted-but-hidden drawer would
    // fire a request on every parent render.
    fetcher: open ? fetcher : null,
    key: `${studentId}:${runId}:${open ? 1 : 0}`,
    onPartial: setPayload,
    onResult: setPayload,
  })

  const handleRerun = () => { setPayload(null); setRunId((r) => r + 1) }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-xl p-0 overflow-y-auto">
        <SheetHeader className="border-b border-border px-6 py-4">
          <div className="flex items-center justify-between">
            <SheetTitle className="flex items-center gap-2 text-base font-medium">
              <Sparkles className="h-4 w-4 text-primary" />
              Meeting brief
              {payload && <span className="text-muted-foreground">· {payload.student.name}</span>}
              {!payload && studentName && <span className="text-muted-foreground">· {studentName}</span>}
            </SheetTitle>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="ghost" onClick={handleRerun} disabled={running}>
                Regenerate
              </Button>
              <Button size="icon" variant="ghost" onClick={() => onOpenChange(false)} aria-label="Close">
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </SheetHeader>

        <div className="px-6 py-5 space-y-5">
          {running && (
            <section className="rounded-lg border border-primary/15 bg-gradient-to-br from-primary/[0.04] via-transparent to-primary/[0.02] px-5 py-4">
              <ReasoningTrace steps={steps} running={running} />
            </section>
          )}

          {error && (
            <div className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm">
              Could not build the brief: {error}
            </div>
          )}

          {/* Skeleton placeholders reserve the layout so nothing jumps when the partial
              payload lands. The trace fades away when running becomes false. */}
          {!payload && !error && <BriefSkeleton />}

          {payload && (
            <>
              <BriefParagraph payload={payload} />
              <EvidenceCards payload={payload} />
              <SuggestedQuestions questions={payload.suggestedQuestions} />
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}

function BriefSkeleton() {
  return (
    <div className="space-y-5 animate-pulse">
      <section className="rounded-md border border-border bg-card px-4 py-3.5">
        <div className="h-3 w-32 bg-muted rounded mb-3" />
        <div className="space-y-2">
          <div className="h-3 w-full bg-muted rounded" />
          <div className="h-3 w-11/12 bg-muted rounded" />
          <div className="h-3 w-9/12 bg-muted rounded" />
        </div>
      </section>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="rounded-md border border-border bg-card px-3 py-2">
            <div className="h-2.5 w-16 bg-muted rounded mb-2" />
            <div className="h-4 w-20 bg-muted rounded" />
          </div>
        ))}
      </div>
    </div>
  )
}

function BriefParagraph({ payload }: { payload: MeetingBriefPayload }) {
  return (
    <section className="rounded-lg border border-primary/25 bg-gradient-to-br from-primary/[0.04] via-transparent to-transparent px-5 py-4 shadow-sm">
      <div className="flex items-center gap-2 mb-2.5">
        <p className="text-label">The brief</p>
        <AiSparkle source={payload.provenance.source} model={payload.provenance.model} />
      </div>
      <p className="text-[15px] leading-relaxed text-foreground">{payload.paragraph}</p>
    </section>
  )
}

function EvidenceCards({ payload }: { payload: MeetingBriefPayload }) {
  const hasFlags = payload.openFlags.length > 0
  return (
    <section className="space-y-4">
      {/* Meta row — the "at a glance" data. The open-flags tile only appears when
          there are any; showing a "0" would just add visual noise. */}
      <div className={`grid gap-3 ${hasFlags ? 'grid-cols-3' : 'grid-cols-2'}`}>
        <MetaCard
          icon={Calendar}
          label="Last met"
          value={payload.lastMeetingOn ?? '—'}
          hint={payload.daysSinceLast != null ? `${payload.daysSinceLast} days ago` : undefined}
        />
        <MetaCard
          icon={Clock}
          label="Next scheduled"
          value={payload.nextMeetingOn ?? 'Not set'}
        />
        {hasFlags && (
          <MetaCard
            icon={AlertTriangle}
            label="To raise"
            value={String(payload.openFlags.length)}
            tone="warning"
          />
        )}
      </div>

      {payload.lastMeetingActions && (
        <div className="rounded-md border-l-2 border-primary/50 bg-muted/40 pl-3 pr-3 py-2.5">
          <p className="text-label mb-1 flex items-center gap-1.5">
            <FileText className="h-3 w-3" /> What you agreed last time
          </p>
          <p className="text-sm text-foreground leading-relaxed">{payload.lastMeetingActions}</p>
        </div>
      )}

      {payload.changes.length > 0 && (
        <div>
          <p className="text-label mb-2">What's changed since</p>
          <ul className="space-y-1.5">
            {payload.changes.map((c, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                <span
                  className={`mt-1.5 h-1.5 w-1.5 rounded-full shrink-0 ${
                    c.kind === 'milestone'
                      ? 'bg-primary'
                      : c.kind === 'funding'
                      ? 'bg-[hsl(var(--info))]'
                      : 'bg-muted-foreground'
                  }`}
                />
                <span className="min-w-0">
                  <span className="font-medium">{c.label}</span>
                  {c.detail && <span className="text-muted-foreground"> — {c.detail}</span>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {hasFlags && (
        <div className="rounded-md border border-[hsl(var(--warning))]/30 bg-[hsl(var(--warning))]/5 px-3 py-2.5">
          <p className="text-label mb-1.5 flex items-center gap-1.5 text-[hsl(var(--warning))]">
            <AlertTriangle className="h-3 w-3" /> Worth raising
          </p>
          <ul className="space-y-1">
            {payload.openFlags.map((f, i) => (
              <li key={i} className="text-sm text-foreground">
                {f.charAt(0).toUpperCase() + f.slice(1)}.
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

function SuggestedQuestions({ questions }: { questions: string[] }) {
  if (questions.length === 0) return null
  return (
    <section className="rounded-md border border-border/70 bg-card px-4 py-3">
      <p className="text-label mb-2.5">Openers you could use</p>
      <ul className="space-y-2">
        {questions.map((q, i) => (
          <li key={i} className="flex items-start gap-2.5 text-sm leading-relaxed">
            <span className="mt-0.5 text-primary/70 font-mono text-xs shrink-0">
              {String(i + 1).padStart(2, '0')}
            </span>
            <span>{q}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function MetaCard({
  icon: Icon, label, value, hint, tone,
}: {
  icon: typeof Calendar
  label: string
  value: string
  hint?: string
  tone?: 'warning' | 'neutral'
}) {
  return (
    <div className={`rounded-md border px-3 py-2 ${
      tone === 'warning'
        ? 'border-[hsl(var(--warning))]/30 bg-[hsl(var(--warning))]/5'
        : 'border-border bg-card'
    }`}>
      <div className="flex items-center gap-1.5">
        <Icon className={`h-3 w-3 ${tone === 'warning' ? 'text-[hsl(var(--warning))]' : 'text-muted-foreground'}`} />
        <p className="text-label">{label}</p>
      </div>
      <p className="mt-1 text-sm font-medium num">{value}</p>
      {hint && <p className="text-xs text-muted-foreground num mt-0.5">{hint}</p>}
    </div>
  )
}
