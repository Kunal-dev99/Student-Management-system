'use client'

/**
 * Weekly supervisor review queue.
 *
 * Deterministic candidate table on the right — the app would show this exact table with
 * no AI at all. AI picks and per-pick reasoning on the left, marked with the sparkle.
 * Turn the model off and the layout stays; the picks are just the top rows of the table
 * with rule-based reasons, and the chip flips to "generated offline".
 */

import { useCallback, useMemo, useState } from 'react'
import Link from 'next/link'
import { useQueryClient } from '@tanstack/react-query'
import { ChevronRight } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '@/shared/api/client'
import { AiCard } from '@/features/ai/AiCard'
import { EvidenceBeside } from '@/features/ai/EvidenceBeside'
import { ReasoningTrace, useReasoningTrace } from '@/features/ai/ReasoningTrace'
import type { WeeklyQueuePayload } from './types'

const TOP_N = 5

export function WeeklyReviewQueue() {
  const [runId, setRunId] = useState(0)

  // Hydrate from React Query cache if we've been here before this session — that gives
  // an instant paint on repeat visits. First-ever visit lands as null and the SSE trace
  // below fills the screen while the real call runs.
  const qc = useQueryClient()
  const cached = qc.getQueryData<WeeklyQueuePayload>(['reviews', 'weekly', TOP_N]) ?? null
  const [payload, setPayload] = useState<WeeklyQueuePayload | null>(cached)

  // Whenever a stream returns a fresh payload, write it to the query cache so navigating
  // away and back re-hydrates instantly.
  const setAndCache = useCallback((p: WeeklyQueuePayload) => {
    setPayload(p)
    qc.setQueryData(['reviews', 'weekly', TOP_N], p)
  }, [qc])

  const fetcher = useCallback(
    (signal: AbortSignal) =>
      api.raw(`/reviews/weekly/stream?top_n=${TOP_N}`, {
        headers: { Accept: 'text/event-stream' },
        signal,
      }),
    [],
  )

  // Always stream — that gives the trace pane something to render from t=0. If we
  // hydrated a cached payload above, it renders alongside the trace and the reader
  // sees content immediately while the fresh call refines it.
  const { steps, running, error } = useReasoningTrace<WeeklyQueuePayload>({
    fetcher,
    key: runId,
    onPartial: setAndCache,
    onResult: setAndCache,
  })

  const picksById = useMemo(() => {
    if (!payload) return new Map<string, WeeklyQueuePayload['candidates'][number]>()
    return new Map(payload.candidates.map((c) => [c.student_id, c]))
  }, [payload])

  return (
    <div className="space-y-4">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-page-title">Weekly review queue</h1>
          <p className="text-helper mt-1">
            Deterministic risk score decides who's here; the AI picks the priorities and writes one
            sentence per pick. Turn the model off and this page still works.
          </p>
        </div>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => { setPayload(null); setRunId((r) => r + 1) }}
        >
          Run again
        </Button>
      </header>

      {/* Trace lives above the layout while the model call is still in flight — after
          the provisional payload arrives the evidence table is already visible below,
          so this reads as "the picks are still being written" rather than "loading". */}
      {running && (
        <section className="rounded-lg border border-primary/15 bg-gradient-to-br from-primary/[0.03] via-transparent to-primary/[0.02] px-5 py-4">
          <ReasoningTrace steps={steps} running={running} />
        </section>
      )}

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm">
          Could not build the queue: {error}
        </div>
      )}

      {payload && (
        <EvidenceBeside
          prose={
            <AiCard
              title={`Top ${payload.picks.length} to review this week`}
              source={payload.provenance.source}
              model={payload.provenance.model}
            >
              {payload.picks.length === 0 ? (
                <p className="text-helper">
                  No active students match the review criteria this week.
                </p>
              ) : (
                <ol className="space-y-3">
                  {payload.picks.map((pick, i) => {
                    const row = picksById.get(pick.id)
                    if (!row) return null
                    return (
                      <li key={pick.id} className="border-b border-border/60 pb-3 last:border-b-0">
                        <div className="flex items-baseline justify-between gap-3">
                          <p className="font-medium">
                            <span className="text-muted-foreground mr-2 num">{i + 1}.</span>
                            {row.person_name}
                            <span className="text-helper ml-2 num">{row.student_ref}</span>
                          </p>
                          <Badge variant="secondary" className="num shrink-0">score {row.score}</Badge>
                        </div>
                        <p className="text-sm mt-1.5 text-foreground">{pick.reasoning}</p>
                        <Button
                          asChild
                          size="sm"
                          variant="ghost"
                          className="h-7 mt-1.5 -ml-2 text-primary"
                        >
                          <Link href={`/students/${row.student_id}`}>
                            Open student record <ChevronRight className="h-3.5 w-3.5 ml-1" />
                          </Link>
                        </Button>
                      </li>
                    )
                  })}
                </ol>
              )}
              {payload.provenance.source === 'fallback' && (
                <p className="text-helper mt-3 text-xs">
                  Model unavailable — picks and reasoning are rule-based ({payload.provenance.reason}).
                </p>
              )}
            </AiCard>
          }
          evidence={
            <div className="overflow-x-auto -mr-2">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Student</TableHead>
                    <TableHead className="w-16 text-right">Score</TableHead>
                    <TableHead>Reasons</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {payload.candidates.map((row) => {
                    const picked = payload.picks.some((p) => p.id === row.student_id)
                    return (
                      <TableRow key={row.student_id} className={picked ? 'bg-primary/[0.04]' : undefined}>
                        <TableCell className="font-medium">
                          {row.person_name}
                          <span className="block text-xs text-muted-foreground num">{row.student_ref}</span>
                        </TableCell>
                        <TableCell className="text-right num">{row.score}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {row.reasons.join(' · ')}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                  {payload.candidates.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={3} className="text-helper text-center py-6">
                        No students matched any risk rule this week.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          }
        />
      )}
    </div>
  )
}
