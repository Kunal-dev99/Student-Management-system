'use client'

/**
 * Weekly Intervention Queue (spec §7).
 *
 * Upgrade of the existing Weekly Review Queue. This one answers three questions per row:
 *   1. Why now — reasons that raised the student
 *   2. Intervention type — the shape of the response
 *   3. Owner — who has to move (student / supervisor / institution)
 *
 * Ranking explanation stays visible on row expand — the spec's "do not force users
 * into chat to understand the queue" rule.
 *
 * Systemic pattern banner surfaces institutional bottlenecks (e.g. "4 waiting on
 * panel confirmation rather than student action") so operators can see when the
 * problem isn't the students.
 *
 * Prepare opens the shared ActionPlanDrawer via the intelligence.stagePlan endpoint —
 * no new server contract needed.
 */
import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import {
  Building2, ChevronDown, ChevronRight, ExternalLink, Filter, Users, User as UserIcon,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { api } from '@/shared/api/client'
import { cn } from '@/lib/utils'
import { AIStateBanner } from './AIStateBanner'
import { ActionPlanDrawer } from './ActionPlanDrawer'
import { intelligenceApi, type InterventionPlan, type ActionType } from './api'
import type { WeeklyQueuePayload } from '@/features/reviews/types'

// ---- Deterministic intervention classifier ---------------------------------

type Owner = 'student' | 'supervisor' | 'institution'
type Intervention =
  | { type: 'supervisor_checkin';    action: ActionType; label: string; owner: Owner }
  | { type: 'funding_review';        action: ActionType; label: string; owner: Owner }
  | { type: 'evidence_review';       action: ActionType; label: string; owner: Owner }
  | { type: 'institutional_unblock'; action: ActionType; label: string; owner: Owner }
  | { type: 'follow_up';             action: ActionType; label: string; owner: Owner }

/**
 * Classify from the free-text reasons the deterministic scorer emitted. Kept transparent
 * so the ranking explanation shown on row expand is honest: this is a keyword mapping,
 * not a model call.
 */
function classify(reasons: string[]): Intervention {
  const joined = reasons.join(' ').toLowerCase()
  if (/\bpanel\b|nomination|registry|awaiting confirm|examin/.test(joined))
    return { type: 'institutional_unblock', action: 'create_task', label: 'Institutional unblock', owner: 'institution' }
  if (/\bfund|stipend|scholar|coverage\b/.test(joined))
    return { type: 'funding_review', action: 'request_funding_review', label: 'Funding review', owner: 'institution' }
  if (/supervis|meeting/.test(joined))
    return { type: 'supervisor_checkin', action: 'prepare_meeting_brief', label: 'Supervisor check-in', owner: 'supervisor' }
  if (/milestone|review|evidence|thesis|corrections?/.test(joined))
    return { type: 'evidence_review', action: 'open_review_evidence_check', label: 'Evidence review', owner: 'supervisor' }
  // Lifecycle timing signals from the deterministic scorer — a student past their
  // expected end date needs the supervisor to plan a completion route (or the
  // institution to extend), not a passive follow-up task assigned to the student.
  if (/past expected end/.test(joined))
    return { type: 'evidence_review', action: 'schedule_reassessment', label: 'Completion planning', owner: 'supervisor' }
  if (/expected end in/.test(joined))
    return { type: 'supervisor_checkin', action: 'schedule_reassessment', label: 'Pre-completion check-in', owner: 'supervisor' }
  return { type: 'follow_up', action: 'create_task', label: 'Follow-up', owner: 'student' }
}

const OWNER_BADGE: Record<Owner, { icon: typeof UserIcon; label: string; tone: 'secondary' | 'warning' | 'outline' }> = {
  student:     { icon: UserIcon,   label: 'Student',     tone: 'outline' },
  supervisor:  { icon: Users,      label: 'Supervisor',  tone: 'secondary' },
  institution: { icon: Building2,  label: 'Institution', tone: 'warning' },
}

// ---- Component -------------------------------------------------------------

const TOP_N = 12

export function WeeklyInterventionQueue() {
  const [payload, setPayload] = useState<WeeklyQueuePayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [ownerFilter, setOwnerFilter] = useState<'all' | Owner>('all')
  const [typeFilter, setTypeFilter] = useState<'all' | Intervention['type']>('all')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [preparingId, setPreparingId] = useState<string | null>(null)
  const [openPlan, setOpenPlan] = useState<InterventionPlan | null>(null)

  // Reuse the existing weekly queue endpoint. Non-streamed variant is fine — the strip
  // is a heavier read that runs less often than the SSE trace view.
  const refresh = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const r = await api.get<WeeklyQueuePayload>(`/reviews/weekly?top_n=${TOP_N}`)
      setPayload(r)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => { void refresh() }, [refresh])

  const rows = useMemo(() => {
    if (!payload) return []
    return payload.candidates.map((c, idx) => {
      const iv = classify(c.reasons)
      const pick = payload.picks.find((p) => p.id === c.student_id)
      return { ...c, priority: idx + 1, iv, aiReasoning: pick?.reasoning ?? null }
    })
  }, [payload])

  const filtered = useMemo(() => rows.filter((r) => {
    if (ownerFilter !== 'all' && r.iv.owner !== ownerFilter) return false
    if (typeFilter !== 'all' && r.iv.type !== typeFilter) return false
    return true
  }), [rows, ownerFilter, typeFilter])

  // Systemic pattern: any intervention type held by ≥3 rows AND driven by institution.
  const systemic = useMemo(() => {
    const bucket = new Map<string, number>()
    rows.forEach((r) => { if (r.iv.owner === 'institution') bucket.set(r.iv.label, (bucket.get(r.iv.label) ?? 0) + 1) })
    return Array.from(bucket.entries()).filter(([, n]) => n >= 3)
  }, [rows])

  const institutionCount = rows.filter((r) => r.iv.owner === 'institution').length

  async function prepare(row: typeof rows[number]) {
    setPreparingId(row.student_id)
    try {
      const staged = await intelligenceApi.stagePlan({
        caseRef: `student:${row.student_id}`,
        studentId: row.student_id,
        rationale: row.aiReasoning ?? row.reasons.join('; ') ?? row.iv.label,
        sourceSignal: { intervention: row.iv.type, reasons: row.reasons, score: row.score },
        actions: [{
          actionType: row.iv.action,
          targetRef: { kind: 'student', id: row.student_id, label: row.person_name },
        }],
      })
      setOpenPlan(staged)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setPreparingId(null)
    }
  }

  function toggle(id: string) {
    setExpanded((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  return (
    <div className="space-y-4">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-page-title">Weekly Intervention Queue</h1>
          <p className="text-helper mt-1">
            {loading ? 'Loading candidates…'
              : rows.length === 0 ? 'No students meet the review threshold this week.'
              : <>This week: <strong>{rows.length}</strong> students need review. <strong>{institutionCount}</strong> are driven by institutional blockers.</>}
          </p>
        </div>
        <Button size="sm" variant="secondary" onClick={() => void refresh()}>Refresh</Button>
      </header>

      {systemic.map(([label, n]) => (
        <div key={label} className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30 px-3 py-2 text-sm">
          <Building2 className="h-4 w-4 mt-0.5 text-amber-700 dark:text-amber-300 shrink-0" aria-hidden />
          <div>
            <p className="font-medium text-amber-900 dark:text-amber-100">Systemic pattern detected</p>
            <p className="text-xs text-amber-800 dark:text-amber-200 mt-0.5">
              {n} cases in this queue map to <strong>{label}</strong> — waiting on institutional action, not student action.
            </p>
          </div>
        </div>
      ))}

      {error ? (
        <AIStateBanner state="error" detail={error} action={{ label: 'Retry', onClick: () => void refresh() }} />
      ) : null}

      <Card>
        <CardContent className="p-3 flex flex-wrap items-center gap-2 border-b">
          <Filter className="h-4 w-4 text-muted-foreground" aria-hidden />
          <span className="text-xs text-muted-foreground">Filter:</span>
          <Select value={ownerFilter} onValueChange={(v) => setOwnerFilter(v as typeof ownerFilter)}>
            <SelectTrigger className="h-8 w-40"><SelectValue placeholder="Owner" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Any owner</SelectItem>
              <SelectItem value="student">Student</SelectItem>
              <SelectItem value="supervisor">Supervisor</SelectItem>
              <SelectItem value="institution">Institution</SelectItem>
            </SelectContent>
          </Select>
          <Select value={typeFilter} onValueChange={(v) => setTypeFilter(v as typeof typeFilter)}>
            <SelectTrigger className="h-8 w-56"><SelectValue placeholder="Intervention type" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Any intervention</SelectItem>
              <SelectItem value="supervisor_checkin">Supervisor check-in</SelectItem>
              <SelectItem value="funding_review">Funding review</SelectItem>
              <SelectItem value="evidence_review">Evidence review</SelectItem>
              <SelectItem value="institutional_unblock">Institutional unblock</SelectItem>
              <SelectItem value="follow_up">Follow-up</SelectItem>
            </SelectContent>
          </Select>
          <span className="ml-auto text-xs text-muted-foreground">
            {filtered.length} of {rows.length}
          </span>
        </CardContent>

        <CardContent className="p-0">
          {loading ? (
            <div className="p-6 space-y-2">
              <Skeleton className="h-6 w-full" /><Skeleton className="h-6 w-full" /><Skeleton className="h-6 w-full" />
            </div>
          ) : filtered.length === 0 ? (
            <p className="p-6 text-sm text-muted-foreground text-center">No rows match these filters.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-14">#</TableHead>
                  <TableHead>Student</TableHead>
                  <TableHead>Why now</TableHead>
                  <TableHead>Intervention</TableHead>
                  <TableHead>Owner</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((row) => {
                  const isOpen = expanded.has(row.student_id)
                  const OwnerIcon = OWNER_BADGE[row.iv.owner].icon
                  return (
                    <Fragment key={row.student_id}>
                      <TableRow>
                        <TableCell className="num text-muted-foreground">
                          <button type="button" onClick={() => toggle(row.student_id)}
                                  className="inline-flex items-center gap-1 hover:text-foreground"
                                  aria-expanded={isOpen} aria-label={`Expand row ${row.priority}`}>
                            {isOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                            {row.priority}
                          </button>
                        </TableCell>
                        <TableCell>
                          <Link href={`/students/${row.student_id}`} className="font-medium hover:underline">
                            {row.person_name}
                          </Link>
                          <span className="block text-xs text-muted-foreground num">{row.student_ref}</span>
                        </TableCell>
                        <TableCell className="text-sm max-w-xs">
                          <span className="line-clamp-2">{row.reasons.join(' · ')}</span>
                        </TableCell>
                        <TableCell><Badge variant="secondary">{row.iv.label}</Badge></TableCell>
                        <TableCell>
                          <Badge variant={OWNER_BADGE[row.iv.owner].tone} className="gap-1">
                            <OwnerIcon className="h-3 w-3" aria-hidden />
                            {OWNER_BADGE[row.iv.owner].label}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <Button size="sm" onClick={() => void prepare(row)}
                                  disabled={preparingId === row.student_id}>
                            {preparingId === row.student_id ? 'Preparing…' : row.iv.owner === 'institution' ? 'Open' : 'Prepare'}
                          </Button>
                        </TableCell>
                      </TableRow>
                      {isOpen ? (
                        <TableRow className="bg-muted/30">
                          <TableCell />
                          <TableCell colSpan={5} className="text-xs space-y-2 py-3">
                            <div>
                              <p className="font-medium text-muted-foreground mb-1">Ranking explanation</p>
                              <p className="text-foreground">
                                Score {row.score} · reasons: {row.reasons.map((r) => (
                                  <Badge key={r} variant="outline" className="mr-1">{r}</Badge>
                                ))}
                              </p>
                            </div>
                            {row.aiReasoning ? (
                              <div>
                                <p className="font-medium text-muted-foreground mb-1">
                                  Why the model surfaced this
                                </p>
                                <p>{row.aiReasoning}</p>
                              </div>
                            ) : null}
                            <div>
                              <Link href={`/students/${row.student_id}`}
                                    className={cn('inline-flex items-center gap-1 text-primary hover:underline')}>
                                Open student record <ExternalLink className="h-3 w-3" aria-hidden />
                              </Link>
                            </div>
                          </TableCell>
                        </TableRow>
                      ) : null}
                    </Fragment>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <ActionPlanDrawer
        open={openPlan !== null}
        onOpenChange={(o) => !o && setOpenPlan(null)}
        plan={openPlan}
        onConfirmed={() => void refresh()}
      />
    </div>
  )
}
