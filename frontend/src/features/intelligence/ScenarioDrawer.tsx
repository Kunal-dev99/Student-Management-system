'use client'

/**
 * Scenario preview drawer (spec §6). Side-effect-free by construction — the endpoint
 * uses a read-only session server-side, and the drawer's persistent banner reminds the
 * user before they touch anything.
 */
import { useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from '@/components/ui/sheet'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { intelligenceApi, type ScenarioResult, type ScenarioChangeKind } from './api'
import { LiveDot } from './LiveDot'

type ChangeType = ScenarioChangeKind

export interface ScenarioDrawerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  studentId: string
  studentName?: string
}

const AMOUNT_HELP: Record<ChangeType, string> = {
  suspend_for_weeks:             'Number of weeks',
  extend_expected_end_by_months: 'Number of months',
  shift_next_milestone_by_days:  'Number of days (negative to pull earlier)',
  change_study_mode:             'Target study mode',
}

export function ScenarioDrawer({ open, onOpenChange, studentId, studentName }: ScenarioDrawerProps) {
  const [changeType, setChangeType] = useState<ChangeType>('suspend_for_weeks')
  const [amount, setAmount] = useState('12')
  const [mode, setMode] = useState<'full_time' | 'part_time'>('part_time')
  const [result, setResult] = useState<ScenarioResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Reset the amount to something sensible when the user picks a different change type.
  function pickChangeType(v: ChangeType) {
    setChangeType(v)
    setError(null)
    setAmount(v === 'suspend_for_weeks' ? '12'
            : v === 'extend_expected_end_by_months' ? '6'
            : v === 'shift_next_milestone_by_days' ? '14'
            : '12')  // ignored for change_study_mode
  }

  async function run() {
    setLoading(true); setError(null); setResult(null)  // clear stale result
    try {
      const params: Record<string, unknown> = {}
      if (changeType === 'suspend_for_weeks') params.weeks = Number(amount)
      else if (changeType === 'extend_expected_end_by_months') params.months = Number(amount)
      else if (changeType === 'shift_next_milestone_by_days') params.days = Number(amount)
      else if (changeType === 'change_study_mode') params.mode = mode
      const r = await intelligenceApi.scenarioPreview({
        studentId, change: changeType, params, includeSensitivity: true,
      })
      setResult(r)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-2xl overflow-y-auto">
        <SheetHeader>
          <SheetTitle>Scenario preview{studentName ? ` — ${studentName}` : ''}</SheetTitle>
          <SheetDescription>Preview only — nothing has changed.</SheetDescription>
        </SheetHeader>

        <div className="mt-3 flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30 px-3 py-2 text-xs text-amber-900 dark:text-amber-200">
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" aria-hidden />
          <span>No state changes, no notifications, no outbox events. Model sensitivity is not a causal prediction.</span>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3">
          <div className="col-span-2 sm:col-span-1">
            <Label>Change type</Label>
            <Select value={changeType} onValueChange={(v) => pickChangeType(v as ChangeType)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="suspend_for_weeks">Suspend for N weeks</SelectItem>
                <SelectItem value="extend_expected_end_by_months">Extend expected end by N months</SelectItem>
                <SelectItem value="shift_next_milestone_by_days">Shift next milestone by N days</SelectItem>
                <SelectItem value="change_study_mode">Change study mode</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="col-span-2 sm:col-span-1">
            <Label>{changeType === 'change_study_mode' ? 'Target mode' : 'Amount'}</Label>
            {changeType === 'change_study_mode' ? (
              <Select value={mode} onValueChange={(v) => setMode(v as 'full_time' | 'part_time')}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="full_time">Full-time</SelectItem>
                  <SelectItem value="part_time">Part-time</SelectItem>
                </SelectContent>
              </Select>
            ) : (
              <Input type="number" value={amount}
                     onChange={(e) => setAmount(e.target.value)}
                     placeholder="e.g. 12" />
            )}
            <p className="text-[11px] text-muted-foreground mt-1">{AMOUNT_HELP[changeType]}</p>
          </div>
          <div className="col-span-2">
            <Button size="sm" onClick={run} disabled={loading}>
              {loading ? 'Computing…' : 'Preview'}
            </Button>
          </div>
        </div>

        {error ? <p className="mt-3 text-sm text-destructive">{error}</p> : null}

        {loading ? (
          <div className="mt-4 space-y-2"><Skeleton className="h-16 w-full" /><Skeleton className="h-16 w-full" /></div>
        ) : result ? (
          <div className="mt-4 space-y-4">
            {(() => {
              // Compose a one-sentence plain-English summary from the deterministic diff.
              // Kept client-side + deterministic on purpose — this is a factual restatement,
              // not an LLM opinion; adding a Groq call here would only add latency.
              const d = result.deterministicDiff
              const parts: string[] = []
              if (d.expectedEndBefore && d.expectedEndAfter && d.expectedEndBefore !== d.expectedEndAfter) {
                parts.push(`expected end moves from ${d.expectedEndBefore} to ${d.expectedEndAfter}`)
              }
              const n = d.milestonesShifted?.length ?? 0
              if (n) parts.push(`${n} milestone${n === 1 ? '' : 's'} shift`)
              const fb = d.fundingCoverageBefore as {coversExpectedEnd?: boolean}
              const fa = d.fundingCoverageAfter as {coversExpectedEnd?: boolean}
              if (fb && fa && fb.coversExpectedEnd !== fa.coversExpectedEnd) {
                parts.push(fa.coversExpectedEnd
                  ? 'funding now covers the expected end'
                  : 'funding no longer covers the expected end')
              }
              const line = parts.length
                ? `This scenario would ${parts.join(', ')}.`
                : 'This scenario would not move any deterministic date.'
              return (
                <div className="rounded-md border bg-muted/30 px-3 py-2">
                  <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-0.5">
                    In plain English
                  </p>
                  <p className="text-sm">{line}</p>
                </div>
              )
            })()}
            <section className="rounded-md border p-3">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Rule impact (deterministic)</h4>
              <dl className="grid grid-cols-[10rem_1fr_auto_1fr] gap-x-3 gap-y-2 text-sm items-baseline">
                <dt className="text-xs text-muted-foreground uppercase tracking-wide">Field</dt>
                <dt className="text-xs text-muted-foreground">Current</dt>
                <dt />
                <dt className="text-xs text-muted-foreground">Scenario</dt>

                {(() => {
                  const b = result.deterministicDiff.expectedEndBefore
                  const a = result.deterministicDiff.expectedEndAfter
                  const same = (b ?? '') === (a ?? '')
                  return (
                    <>
                      <dt className="text-muted-foreground">Expected end</dt>
                      <dd>{b ?? '—'}</dd>
                      <dd className="text-muted-foreground">→</dd>
                      <dd className={same ? 'text-muted-foreground' : 'font-medium'}>
                        {a ?? '—'} {same ? '(unchanged)' : null}
                      </dd>
                    </>
                  )
                })()}

                {(() => {
                  const b = result.deterministicDiff.fundingCoverageBefore as {
                    activeCount?: number; latestEnd?: string | null; coversExpectedEnd?: boolean
                  }
                  const a = result.deterministicDiff.fundingCoverageAfter as typeof b
                  if (!b || !a) return null
                  const summary = (x: typeof b) =>
                    `${x.activeCount ?? 0} active · ends ${x.latestEnd ?? '—'} · ` +
                    `${x.coversExpectedEnd ? 'covers' : 'does not cover'} expected end`
                  const same = b.activeCount === a.activeCount
                              && b.latestEnd === a.latestEnd
                              && b.coversExpectedEnd === a.coversExpectedEnd
                  return (
                    <>
                      <dt className="text-muted-foreground">Funding coverage</dt>
                      <dd className="text-xs">{summary(b)}</dd>
                      <dd className="text-muted-foreground">→</dd>
                      <dd className={cn('text-xs', same ? 'text-muted-foreground' : 'font-medium')}>
                        {summary(a)} {same ? '(unchanged)' : null}
                      </dd>
                    </>
                  )
                })()}

                {result.deterministicDiff.milestonesShifted?.length ? (
                  <>
                    <dt className="text-muted-foreground col-span-4 mt-1">
                      Milestones shifted ({result.deterministicDiff.milestonesShifted.length})
                    </dt>
                    {result.deterministicDiff.milestonesShifted.map((m, i) => {
                      const before = (m as {before?: string}).before ?? '—'
                      const after  = (m as {after?: string}).after  ?? '—'
                      const label  = (m as {name?: string; milestoneId?: string}).name
                                  ?? (m as {milestoneId?: string}).milestoneId ?? 'milestone'
                      return (
                        <div key={i} className="col-span-4 grid grid-cols-[10rem_1fr_auto_1fr] gap-x-3 text-xs">
                          <span className="truncate">{String(label)}</span>
                          <span>{before}</span>
                          <span className="text-muted-foreground">→</span>
                          <span>{after}</span>
                        </div>
                      )
                    })}
                  </>
                ) : null}
              </dl>
            </section>

            <section className="rounded-md border p-3">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Model sensitivity</h4>
              {result.modelSensitivity.length > 0 ? (
                <dl className="grid grid-cols-4 gap-2 text-sm">
                  <dt className="text-muted-foreground text-xs">Target</dt>
                  <dt className="text-muted-foreground text-xs">Baseline</dt>
                  <dt className="text-muted-foreground text-xs">Scenario</dt>
                  <dt className="text-muted-foreground text-xs text-right">Δpp</dt>
                  {result.modelSensitivity.map((m) => (
                    <div key={m.target} className="col-span-4 grid grid-cols-4 gap-2">
                      <dd className="truncate">{m.target}</dd>
                      <dd>{(m.baselineProbability * 100).toFixed(0)}%</dd>
                      <dd>{(m.sensitivityProbability * 100).toFixed(0)}%</dd>
                      <dd className="text-right">{m.deltaPp > 0 ? '+' : ''}{m.deltaPp.toFixed(1)}</dd>
                    </div>
                  ))}
                </dl>
              ) : result.qualitativeSensitivity.length > 0 ? (
                // No quantitative re-run pipeline yet for this target — the LLM reads
                // the same deterministic diff shown above and judges a DIRECTION, never
                // a number. Visually distinct (dashed border, no % columns) so it can
                // never be mistaken for the real model's own re-scored probability.
                <div className="space-y-2">
                  {result.qualitativeSensitivity.map((q) => (
                    <div
                      key={q.target}
                      className={cn(
                        'rounded border p-2',
                        q.engine === 'model'
                          ? 'border-primary/20 bg-gradient-to-br from-primary/[0.05] via-transparent to-transparent'
                          : 'border-dashed',
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-medium">{q.target.replace(/_/g, ' ')}</span>
                        <Badge
                          variant={
                            q.direction === 'likely_increase' ? 'destructive'
                            : q.direction === 'likely_decrease' ? 'success'
                            : 'secondary'
                          }
                        >
                          {q.direction.replace(/_/g, ' ')}
                        </Badge>
                      </div>
                      {q.baselineProbability !== null ? (
                        <p className="text-xs text-muted-foreground mt-0.5">
                          Currently scored at {(q.baselineProbability * 100).toFixed(0)}%
                        </p>
                      ) : null}
                      <p className="text-sm mt-1">{q.rationale}</p>
                      <p className="text-[10px] text-muted-foreground mt-1 inline-flex items-center gap-1">
                        <LiveDot live={q.engine === 'model'} />
                        {q.engine === 'model' ? `LLM judgment · ${q.model}` : 'rule-based judgment'} — not a re-run of the trained model
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No live models scored for this student.</p>
              )}
              <p className="text-[11px] text-muted-foreground mt-2">
                Model sensitivity is not a causal prediction. Funding is not assumed to extend.
              </p>
            </section>

            {result.deterministicDiff.assumptions?.length ? (
              <section className="text-xs text-muted-foreground">
                <p className="font-medium mb-1">Assumptions</p>
                <ul className="list-disc pl-4 space-y-0.5">
                  {result.deterministicDiff.assumptions.map((a) => <li key={a}>{a}</li>)}
                </ul>
              </section>
            ) : null}

            {result.missingData?.length ? (
              <section className="text-xs text-muted-foreground">
                <p className="font-medium mb-1">Missing information</p>
                <ul className="list-disc pl-4 space-y-0.5">
                  {result.missingData.map((m) => <li key={m}>{m}</li>)}
                </ul>
              </section>
            ) : null}
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  )
}
