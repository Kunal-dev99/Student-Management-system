'use client'

/**
 * PGR Intelligence strip (spec §4).
 *
 * Contract:
 *   - Renders deterministically BEFORE any narrative call completes. The
 *     Attention/Trend/Blocker banner and the four verbs are visible immediately from
 *     the Twin snapshot; the LLM narration is a separate lazy section below.
 *   - Never blocks the student record. If the twin fetch fails, the strip still
 *     shows a rule-based fallback line ("Intelligence unavailable"); the record
 *     below it renders regardless.
 *   - Four verbs: Explain / Evidence / Simulate / Prepare action.
 *
 * The strip is a compact entry point — deeper detail lives in the drawers.
 */
import { useEffect, useState } from 'react'
import { Activity, FileSearch, PlayCircle, Sparkles, Wand2 } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { AIStateBanner } from './AIStateBanner'
import { NarratedParagraph } from './NarratedParagraph'
import { LiveDot } from './LiveDot'
import { EvidenceDrawer } from './EvidenceDrawer'
import { ScenarioDrawer } from './ScenarioDrawer'
import { ActionPlanDrawer } from './ActionPlanDrawer'
import { intelligenceApi, type PressurePoint, type StudentTwinSnapshot, type InterventionPlan, type CaseContext } from './api'
import { ApiError } from '@/shared/api/client'

type Attention = 'LOW' | 'MEDIUM' | 'HIGH'

interface StripState {
  attention: Attention
  primaryBlocker: string
  currentStateLines: string[]
  nextPressure: PressurePoint | null
  nextMove: string
}

/** Deterministic derivation from Twin — no LLM required for any of these values. */
function deriveState(snap: StudentTwinSnapshot | null): StripState {
  if (!snap) return { attention: 'LOW', primaryBlocker: '—', currentStateLines: [], nextPressure: null, nextMove: '—' }
  const points = snap.pressurePoints ?? []
  const totalWeight = points.reduce((s, p) => s + p.weight, 0)
  const attention: Attention = totalWeight >= 12 ? 'HIGH' : totalWeight >= 6 ? 'MEDIUM' : 'LOW'
  const top = points[0] ?? null
  const primaryBlocker = top ? top.label : 'No material pressure'
  const currentStateLines = points.slice(0, 3).map((p) => p.label)
  const nextPressure = top
  const move = top?.kind === 'supervision_gap' ? 'Supervisor check-in'
             : top?.kind === 'funding_expiring' || top?.kind === 'no_active_funding' ? 'Funding review'
             : top?.kind?.startsWith('milestone') ? 'Review evidence'
             : 'Reassess'
  return { attention, primaryBlocker, currentStateLines, nextPressure, nextMove: move }
}

function attentionTone(a: Attention): string {
  return a === 'HIGH' ? 'bg-destructive/15 text-destructive border-destructive/30'
       : a === 'MEDIUM' ? 'bg-amber-100 text-amber-900 border-amber-300 dark:bg-amber-950/30 dark:text-amber-200 dark:border-amber-800'
       : 'bg-emerald-100 text-emerald-900 border-emerald-300 dark:bg-emerald-950/30 dark:text-emerald-200 dark:border-emerald-800'
}

export interface IntelligenceStripProps {
  studentId: string
  studentName?: string
  /** When true, also fetches the LLM-narrated state paragraph. Off by default so the strip stays cheap. */
  narrate?: boolean
  className?: string
}

export function IntelligenceStrip({ studentId, studentName, narrate = true, className }: IntelligenceStripProps) {
  const [snap, setSnap] = useState<StudentTwinSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [narrateLoading, setNarrateLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [openDrawer, setOpenDrawer] = useState<null | 'evidence' | 'scenario' | 'plan'>(null)
  const [plan, setPlan] = useState<InterventionPlan | null>(null)
  const [preparing, setPreparing] = useState(false)
  // The Explain/Evidence buttons kick off a Case Context call that ALSO records
  // evidence claims. The returned artefactId is what makes the Evidence drawer
  // useful — without it, the drawer has nothing to load.
  const [ctx, setCtx] = useState<CaseContext | null>(null)
  const [ctxLoading, setCtxLoading] = useState(false)

  // 1. Deterministic fetch — renders the strip immediately.
  useEffect(() => {
    let cancelled = false
    setLoading(true); setError(null)
    intelligenceApi.twin(studentId, { enableLlm: false })
      .then((s) => { if (!cancelled) setSnap(s) })
      .catch((e: Error) => { if (!cancelled) setError(e.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [studentId])

  // 2. Optional LLM narration — never blocks the deterministic paint.
  useEffect(() => {
    if (!narrate || !snap) return
    let cancelled = false
    setNarrateLoading(true)
    intelligenceApi.twin(studentId, { enableLlm: true })
      .then((s) => { if (!cancelled) setSnap((prev) => prev ? { ...prev, narratedState: s.narratedState } : s) })
      .catch(() => { /* narration is optional; deterministic strip already visible */ })
      .finally(() => { if (!cancelled) setNarrateLoading(false) })
    return () => { cancelled = true }
  }, [narrate, snap?.studentId, studentId]) // eslint-disable-line react-hooks/exhaustive-deps

  const state = deriveState(snap)

  /**
   * Explain: scroll to the AI Case Insights panel below and re-run its stream.
   * This is the real "explanation" surface — the panel shows the model thinking
   * step-by-step and then types out its structured reasoning. A dispatched
   * window event drives it so the strip and the panel stay decoupled.
   */
  function explain() {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('intelligence:explain', { detail: { studentId } }))
    }
  }

  /**
   * Evidence: open the drawer with the source rows. Calls Case Context with
   * `record_evidence=true` so the server persists EvidenceClaim rows we can then
   * list, and with `enable_llm=true` so the drawer also shows a plain-English header.
   */
  async function openEvidence() {
    setOpenDrawer('evidence')
    if (ctx) return  // already loaded
    setCtxLoading(true)
    try {
      const c = await intelligenceApi.caseContext(studentId, {
        enableLlm: true, recordEvidence: true,
      })
      setCtx(c)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setCtxLoading(false)
    }
  }

  async function prepareAction() {
    if (!snap || !state.nextPressure) return
    setPreparing(true)
    try {
      const propose = await intelligenceApi.proposeFromSignal({
        signalKind: state.nextPressure.kind,
        signalDetail: state.nextPressure.label,
        caseRef: `student:${studentId}`,
        studentId,
      })
      const staged = await intelligenceApi.stagePlan({
        caseRef: `student:${studentId}`,
        studentId,
        rationale: propose.rationale,
        sourceSignal: { kind: state.nextPressure.kind, label: state.nextPressure.label },
        actions: [{
          actionType: propose.actionType,
          targetRef: { kind: 'student', id: studentId, label: studentName ?? '' },
        }],
      })
      setPlan(staged)
      setOpenDrawer('plan')
    } catch (e) {
      // A 409 here means the planner's idempotency guard fired — a plan for this
      // exact case + signal + action set already exists (often already confirmed
      // and executed). That's the SYSTEM WORKING AS DESIGNED, not a failure: show
      // the reader the existing plan instead of a raw "conflict" error.
      if (e instanceof ApiError && e.status === 409) {
        try {
          const existing = await intelligenceApi.listInterventionsForStudent(studentId)
          const match = existing.find((p) =>
            p.caseRef === `student:${studentId}` &&
            p.sourceSignal && (p.sourceSignal as { kind?: string }).kind === state.nextPressure?.kind,
          ) ?? existing[0] ?? null
          if (match) {
            setPlan(match)
            setOpenDrawer('plan')
          } else {
            setError('A plan already exists for this signal, but it could not be loaded for review.')
          }
        } catch (e2) {
          setError((e2 as Error).message)
        }
      } else {
        setError((e as Error).message)
      }
    } finally {
      setPreparing(false)
    }
  }

  if (loading) {
    return (
      <Card className={className}>
        <CardContent className="p-4 space-y-3">
          <Skeleton className="h-4 w-64" />
          <Skeleton className="h-8 w-full" />
        </CardContent>
      </Card>
    )
  }

  return (
    <>
      <Card className={cn('border-l-4 border-l-primary', className)}>
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-primary">
              <Sparkles className="h-3.5 w-3.5" />
              PGR Intelligence
            </div>
            {snap?.narratedState?.model ? (
              <span className="text-[10px] font-mono text-muted-foreground inline-flex items-center gap-1">
                <LiveDot live />
                LLM live · {snap.narratedState.model}
              </span>
            ) : narrateLoading ? (
              <span className="text-[10px] font-mono text-muted-foreground inline-flex items-center gap-1">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse" aria-hidden />
                calling LLM…
              </span>
            ) : null}
          </div>

          {error ? (
            <AIStateBanner state="error" detail={error} />
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span>Attention</span>
                <Badge className={cn('border', attentionTone(state.attention))} variant="outline">{state.attention}</Badge>
                <span className="text-muted-foreground">|</span>
                <span>Primary blocker:</span>
                <span className="font-medium">{state.primaryBlocker}</span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-1">
                <section>
                  <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">Current state</p>
                  {state.currentStateLines.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No material pressure</p>
                  ) : (
                    <ul className="space-y-0.5 text-sm">
                      {state.currentStateLines.map((line, i) => <li key={i}>• {line}</li>)}
                    </ul>
                  )}
                </section>
                <section>
                  <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">Next pressure</p>
                  {state.nextPressure ? (
                    <div className="text-sm">
                      <p className="font-medium">{state.nextPressure.label}</p>
                      <p className="text-xs text-muted-foreground">
                        {state.nextPressure.kind.replace(/_/g, ' ')}
                        {state.nextPressure.when ? ` · ${state.nextPressure.when}` : ''}
                      </p>
                    </div>
                  ) : <p className="text-sm text-muted-foreground">—</p>}
                </section>
                <section>
                  <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">Next move</p>
                  <p className="text-sm font-medium">{state.nextMove}</p>
                </section>
              </div>

              <NarratedParagraph narration={snap?.narratedState ?? null} loading={narrateLoading && !snap?.narratedState} />

              {snap?.blockers?.length ? (
                <AIStateBanner state="missing_data" detail={snap.blockers.join(' · ')} />
              ) : null}

              <div className="flex flex-wrap gap-2 pt-1">
                <Button size="sm" variant="ghost" onClick={explain}>
                  <Activity className="h-3.5 w-3.5 mr-1.5" /> Explain
                </Button>
                <Button size="sm" variant="ghost" onClick={openEvidence}>
                  <FileSearch className="h-3.5 w-3.5 mr-1.5" /> Evidence
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setOpenDrawer('scenario')}>
                  <PlayCircle className="h-3.5 w-3.5 mr-1.5" /> Simulate
                </Button>
                <Button size="sm" onClick={prepareAction} disabled={preparing || !state.nextPressure}>
                  <Wand2 className="h-3.5 w-3.5 mr-1.5" />
                  {preparing ? 'Preparing…' : 'Prepare action'}
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <EvidenceDrawer
        open={openDrawer === 'evidence'}
        onOpenChange={(o) => setOpenDrawer(o ? 'evidence' : null)}
        artefactId={ctx?.pendingActionPlanId ?? null}
        loading={ctxLoading}
        title={`Intelligence evidence — ${studentName ?? 'student'}`}
        headline={state.primaryBlocker}
        narratedSummary={ctx?.narratedSummary ?? null}
        missingSources={[
          ...(snap?.blockers?.map((b) => ({ source: b, reason: 'domain data unavailable' })) ?? []),
          ...(ctx?.missingSources ?? []),
        ]}
      />
      <ScenarioDrawer
        open={openDrawer === 'scenario'}
        onOpenChange={(o) => setOpenDrawer(o ? 'scenario' : null)}
        studentId={studentId}
        studentName={studentName}
      />
      <ActionPlanDrawer
        open={openDrawer === 'plan'}
        onOpenChange={(o) => setOpenDrawer(o ? 'plan' : null)}
        plan={plan}
      />
    </>
  )
}
