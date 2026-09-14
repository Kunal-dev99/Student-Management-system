'use client'

/**
 * Case Insights — reasoning-trace pane + typewriter reveal of the LLM output.
 *
 * This is where the AI should FEEL like it's thinking, not just returning JSON:
 *   1. Open the SSE stream to `/intelligence/students/{id}/insights/stream`.
 *   2. Render each reasoning step as it lands (real server work — no fake steps).
 *   3. When the final payload arrives, reveal the situation / observations /
 *      suggested next steps with a typewriter animation so the eye tracks the
 *      writing.
 *
 * Deliberately OPT-IN, not auto-run on mount. Two reasons:
 *   - The Strip above already gives a one-line narration for free on every page
 *     view. If this panel also fired automatically it would (a) cost a second
 *     unsolicited Groq call on every visit and (b) restate the same headline
 *     fact in more words a few pixels below it — redundant, not "more AI".
 *   - Making it opt-in is what makes the Strip's "Explain" button MEAN something:
 *     it's the moment the reader asks for the deeper reasoning, not a re-render
 *     of what they already saw.
 *
 * The Reasoning trace framework (`useReasoningTrace`) already exists in
 * `src/features/ai/ReasoningTrace.tsx` — we reuse it wholesale.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Brain, Lightbulb, Sparkles, Waypoints } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { api } from '@/shared/api/client'
import { ReasoningTrace, useReasoningTrace } from '@/features/ai/ReasoningTrace'
import { AIStateBanner } from './AIStateBanner'
import { useTypewriter, TypingCursor } from './useTypewriter'
import { LiveDot } from './LiveDot'

interface InsightsData {
  studentId: string
  engineUsed: string
  situation: string
  observations: string[]
  suggestedNext: string[]
}

export interface InsightsPanelProps {
  studentId: string
  className?: string
}

export function InsightsPanel({ studentId, className }: InsightsPanelProps) {
  const [runId, setRunId] = useState(0)
  const [data, setData] = useState<InsightsData | null>(null)
  // Gate the stream behind an explicit start — see the file-level note on why
  // this must NOT auto-fire on mount.
  const [started, setStarted] = useState(false)
  const rootRef = useRef<HTMLDivElement | null>(null)

  function start() {
    setData(null)
    setStarted(true)
    setRunId((r) => r + 1)
  }

  // Explain button in the Intelligence strip fires this event — we scroll into
  // view and (re)start the stream so the reader sees the model "think" from scratch.
  useEffect(() => {
    function onExplain(e: Event) {
      const detail = (e as CustomEvent).detail as { studentId?: string } | null
      if (detail?.studentId && detail.studentId !== studentId) return
      rootRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      start()
    }
    window.addEventListener('intelligence:explain', onExplain)
    return () => window.removeEventListener('intelligence:explain', onExplain)
  }, [studentId])  // eslint-disable-line react-hooks/exhaustive-deps

  const fetcher = useCallback(
    (signal: AbortSignal) =>
      api.raw(`/intelligence/students/${studentId}/insights/stream`, {
        headers: { Accept: 'text/event-stream' },
        signal,
      }),
    [studentId],
  )

  const { steps, running, error } = useReasoningTrace<InsightsData>({
    // Passing null keeps the hook from opening the stream until the reader (or
    // the Explain button) actually asks for it.
    fetcher: started ? fetcher : null,
    key: `${studentId}-${runId}`,
    onResult: setData,
  })

  // Typewriter each section independently, cascading so the eye lands on one at a time.
  const situationText = useTypewriter(data?.situation ?? '', 3, 14)
  const observationsReady = situationText === (data?.situation ?? '')
  const [obsIdx, setObsIdx] = useState(0)
  useEffect(() => { setObsIdx(0) }, [data])
  useEffect(() => {
    if (!observationsReady || !data) return
    if (obsIdx < data.observations.length) {
      const t = window.setTimeout(() => setObsIdx((i) => i + 1), 220)
      return () => window.clearTimeout(t)
    }
  }, [observationsReady, obsIdx, data])
  const suggestionsReady = observationsReady && data ? obsIdx >= data.observations.length : false

  const isModel = data && data.engineUsed !== 'fallback_rules'

  return (
    <Card ref={rootRef as never} className={className}>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-primary">
            <Brain className="h-3.5 w-3.5" />
            AI Case Insights
          </div>
          <div className="flex items-center gap-3">
            {data ? (
              <span className="text-[10px] font-mono text-muted-foreground inline-flex items-center gap-1">
                <LiveDot live={!!isModel} />
                {isModel ? `synthesised by ${data.engineUsed}` : 'rule-based synthesis'}
              </span>
            ) : null}
            {started ? (
              <Button size="sm" variant="ghost" onClick={start} disabled={running}>
                Regenerate
              </Button>
            ) : null}
          </div>
        </div>

        {/* Not started yet — an explicit CTA, not a silent background call. This is
            also what the strip's "Explain" button ultimately triggers. */}
        {!started ? (
          <div className="flex items-center justify-between gap-3 rounded-md border border-dashed px-3 py-3">
            <p className="text-sm text-muted-foreground">
              Ask the model to read this student's full case and explain what it notices.
            </p>
            <Button size="sm" onClick={start}>
              <Brain className="h-3.5 w-3.5 mr-1.5" /> Generate insights
            </Button>
          </div>
        ) : null}

        {/* Reasoning trace — visible during the model call, subsides after result lands. */}
        {started && (running || (!data && !error)) && (
          <div className="rounded-md border border-primary/15 bg-gradient-to-br from-primary/[0.03] via-transparent to-primary/[0.02] px-4 py-3">
            <ReasoningTrace steps={steps} running={running} />
          </div>
        )}

        {error ? (
          <AIStateBanner state="error" detail={error} action={{ label: 'Retry', onClick: start }} />
        ) : data ? (
          <>
            <section>
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1 inline-flex items-center gap-1">
                <Sparkles className="h-3 w-3" /> Situation
              </p>
              <p className="text-sm leading-relaxed">
                {situationText}
                {situationText.length < (data.situation?.length ?? 0) ? <TypingCursor /> : null}
              </p>
            </section>

            {observationsReady && data.observations.length > 0 ? (
              <section>
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1 inline-flex items-center gap-1">
                  <Waypoints className="h-3 w-3" /> What the model noticed
                </p>
                <ul className="space-y-1">
                  {data.observations.slice(0, obsIdx).map((o, i) => (
                    <li key={i} className="text-sm flex items-baseline gap-2 animate-in fade-in slide-in-from-left-1 duration-300">
                      <span className="h-1 w-1 rounded-full bg-primary mt-1.5 shrink-0" aria-hidden />
                      <span>{o}</span>
                    </li>
                  ))}
                  {obsIdx < data.observations.length ? (
                    <li className="text-sm text-muted-foreground flex items-baseline gap-2">
                      <span className="h-1 w-1 rounded-full bg-muted-foreground mt-1.5 shrink-0 animate-pulse" aria-hidden />
                      <span className="italic">writing…</span>
                    </li>
                  ) : null}
                </ul>
                <p className="text-[10px] text-muted-foreground mt-1.5">
                  Cross-signal patterns — never causal claims. Treat as leads to look at.
                </p>
              </section>
            ) : null}

            {suggestionsReady && data.suggestedNext.length > 0 ? (
              <section className="animate-in fade-in duration-500">
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1 inline-flex items-center gap-1">
                  <Lightbulb className="h-3 w-3" /> Suggested next steps
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {data.suggestedNext.map((s, i) => (
                    <Badge key={i} variant="secondary" className="font-normal">{s}</Badge>
                  ))}
                </div>
                <p className="text-[10px] text-muted-foreground mt-1.5">
                  Drawn from the allow-listed action taxonomy. A human still confirms.
                </p>
              </section>
            ) : null}
          </>
        ) : null}
      </CardContent>
    </Card>
  )
}
