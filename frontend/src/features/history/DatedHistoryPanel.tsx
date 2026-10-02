'use client'

/** Effective dating, Phase 5 — the student's history tab.
 *
 *  One timeline of every dated fact (status, programme, study intensity, modules, funding,
 *  supervision), each with who recorded it and when, flagged when it was recorded after a
 *  signed-off return already covered that period. Above it, "as of" shows the record as it stood
 *  on any past date. */

import { useMemo, useState } from 'react'
import { AlertTriangle, CalendarClock, History as HistoryIcon } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  type HistoryEntry, type HistoryFact, inclusiveEnd, todayIso, useStudentAsOf, useStudentHistory,
} from './api'

const FACT_LABEL: Record<HistoryFact, string> = {
  status: 'Status',
  programme: 'Programme',
  intensity: 'Study intensity',
  expected_end: 'Expected end',
  fee_status: 'Fee status',
  fee_eligibility: 'Fee eligibility',
  outside_uk: 'Outside the UK',
  location: 'Location',
  uoa: 'Unit of assessment',
  module: 'Module',
  funding: 'Funding',
  supervision: 'Supervision',
  custom: 'Custom attribute',
  supervisor_uoa: 'Supervisor UOA',
}

const FACT_TONE: Record<HistoryFact, 'secondary' | 'info' | 'success' | 'warning' | 'outline'> = {
  status: 'info',
  programme: 'success',
  intensity: 'secondary',
  expected_end: 'info',
  fee_status: 'outline',
  fee_eligibility: 'outline',
  outside_uk: 'outline',
  location: 'outline',
  uoa: 'outline',
  module: 'outline',
  funding: 'warning',
  supervision: 'secondary',
  custom: 'outline',
  supervisor_uoa: 'outline',
}

const ORIGIN_LABEL: Record<string, string> = {
  initial: 'at enrolment',
  change: 'change',
  correction: 'correction',
  backfill: 'rebuilt from older data',
}

const pretty = (s: string | null | undefined) => (s ?? '—').replace(/_/g, ' ')

function when(iso: string | null): string {
  if (!iso) return '—'
  return iso.replace('T', ' ').slice(0, 16)
}

function AsOfView({ studentId }: { studentId: string }) {
  const [date, setDate] = useState('')
  const asOf = useStudentAsOf(studentId, date || null)
  const a = asOf.data
  return (
    <PageSection icon={CalendarClock} title="As of a date"
      description="See the record as it stood on a past day — what a return for that day would have used.">
      <div className="flex flex-wrap items-end gap-2 mb-3">
        <div className="flex flex-col gap-1">
          <label htmlFor="as-of-date" className="text-label">Date</label>
          <Input id="as-of-date" type="date" className="h-8 w-40" value={date} max={todayIso()}
            onChange={(e) => setDate(e.target.value)} />
        </div>
        {date && <Button size="sm" variant="ghost" onClick={() => setDate('')}>Clear</Button>}
      </div>
      {!date ? (
        <p className="text-helper">Pick a date to see the student&apos;s status, programme, intensity, fee status, location, modules, funding and supervisors on that day.</p>
      ) : asOf.isLoading ? <Skeleton className="h-16 w-full" /> : a ? (
        a.beforeStart && !a.status ? (
          <p className="text-helper">The student hadn&apos;t started yet on {a.asOf}.</p>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div><p className="text-label">Status</p><p className="text-sm mt-0.5">{pretty(a.status)}</p></div>
            <div><p className="text-label">Programme</p><p className="text-sm mt-0.5">{a.programmeName ?? '—'}</p></div>
            <div>
              <p className="text-label">Study intensity</p>
              <p className="text-sm mt-0.5 num">{a.intensityPct != null ? `${a.intensityPct}% (${pretty(a.studyMode)})` : '—'}</p>
            </div>
            <div>
              <p className="text-label">Supervisors</p>
              <p className="text-sm mt-0.5">
                {a.supervisors.length ? a.supervisors.map((s) => `${s.name} (${pretty(s.role)})`).join(', ') : '—'}
              </p>
            </div>
            <div className="col-span-2">
              <p className="text-label">Funding</p>
              <p className="text-sm mt-0.5">
                {a.funding.length
                  ? a.funding.map((f) => [pretty(f.type), f.source, f.contributionPct != null ? `${f.contributionPct}%` : null]
                    .filter(Boolean).join(' · ')).join('; ')
                  : '—'}
              </p>
            </div>
            <div>
              <p className="text-label">Fee status</p>
              <p className="text-sm mt-0.5">{a.feeStatus ? pretty(a.feeStatus) : '—'}</p>
            </div>
            <div>
              <p className="text-label">Location of study</p>
              <p className="text-sm mt-0.5">{a.studyLocation ?? '—'}</p>
            </div>
            <div>
              <p className="text-label">Unit of assessment</p>
              <p className="text-sm mt-0.5">{a.uoa ?? '—'}</p>
            </div>
            <div>
              <p className="text-label">Expected end (as held then)</p>
              <p className="text-sm mt-0.5 num">{a.expectedEndDate ?? '—'}</p>
            </div>
            <div>
              <p className="text-label">Fee eligibility</p>
              <p className="text-sm mt-0.5">{a.feeEligibility ? pretty(a.feeEligibility) : '—'}</p>
            </div>
            <div>
              <p className="text-label">Primarily outside the UK</p>
              <p className="text-sm mt-0.5">{a.primarilyOutsideUk == null ? '—' : a.primarilyOutsideUk ? 'Yes' : 'No'}</p>
            </div>
            {a.custom.length > 0 && (
              <div className="col-span-2">
                <p className="text-label">Dated custom attributes</p>
                <p className="text-sm mt-0.5">{a.custom.map((c) => `${c.label}: ${c.value}`).join('; ')}</p>
              </div>
            )}
            <div className="col-span-2">
              <p className="text-label">Modules</p>
              <p className="text-sm mt-0.5">
                {a.modules.length ? a.modules.map((m) => `${m.code} (${pretty(m.status)})`).join(', ') : '—'}
              </p>
            </div>
          </div>
        )
      ) : null}
    </PageSection>
  )
}

function EntryRow({ e }: { e: HistoryEntry }) {
  const end = inclusiveEnd(e.validTo)
  return (
    <TableRow className={e.superseded ? 'opacity-60' : undefined}>
      <TableCell className="whitespace-nowrap">
        <Badge variant={FACT_TONE[e.fact]}>{FACT_LABEL[e.fact]}</Badge>
      </TableCell>
      <TableCell className="text-sm">
        <span className={e.superseded ? 'line-through' : undefined}>{pretty(e.label)}</span>
        {e.superseded && <span className="text-helper ml-1">(superseded by a correction)</span>}
        {e.reason && <p className="text-helper">{e.reason}</p>}
        {e.retrospective.length > 0 && (
          <p className="flex items-start gap-1 text-xs text-[hsl(var(--warning))] mt-0.5">
            <AlertTriangle className="h-3.5 w-3.5 mt-px shrink-0" />
            Recorded after the {e.retrospective.map((r) => `${r.name} ${r.academicYear}`).join(', ')} return was signed off
          </p>
        )}
      </TableCell>
      <TableCell className="num text-sm whitespace-nowrap">{e.validFrom}</TableCell>
      <TableCell className="num text-sm whitespace-nowrap">{end ?? <span className="text-muted-foreground">current</span>}</TableCell>
      <TableCell className="text-xs text-muted-foreground">
        <span className="num">{when(e.recordedAt)}</span>
        {e.recordedBy && <span className="block">{e.recordedBy}</span>}
        {e.origin && <span className="block">{ORIGIN_LABEL[e.origin] ?? e.origin}</span>}
      </TableCell>
    </TableRow>
  )
}

export function DatedHistoryPanel({ studentId }: { studentId: string }) {
  const [showSuperseded, setShowSuperseded] = useState(false)
  const [facts, setFacts] = useState<Set<HistoryFact>>(new Set())
  const history = useStudentHistory(studentId, showSuperseded)
  const h = history.data

  const present = useMemo(() => {
    const seen = new Set<HistoryFact>()
    h?.entries.forEach((e) => seen.add(e.fact))
    return (Object.keys(FACT_LABEL) as HistoryFact[]).filter((f) => seen.has(f))
  }, [h])
  const rows = useMemo(
    () => (h?.entries ?? []).filter((e) => facts.size === 0 || facts.has(e.fact)),
    [h, facts],
  )
  const toggle = (f: HistoryFact) => setFacts((prev) => {
    const next = new Set(prev)
    if (next.has(f)) next.delete(f); else next.add(f)
    return next
  })

  return (
    <>
      <AsOfView studentId={studentId} />
      <PageSection icon={HistoryIcon} title="Dated history" accent="primary"
        description="Every change with the date it took effect, who recorded it and when. End dates are the last day in force.">
        {h && h.retrospectiveCount > 0 && (
          <p className="flex items-start gap-1.5 text-sm text-[hsl(var(--warning))] mb-3">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            {h.retrospectiveCount} change{h.retrospectiveCount === 1 ? ' was' : 's were'} recorded after a signed-off
            return already covered that period — the return may need resubmitting.
          </p>
        )}
        <div className="flex flex-wrap items-center gap-1.5 mb-3">
          <span className="text-label mr-1">Show</span>
          <Button size="sm" variant={facts.size === 0 ? 'secondary' : 'ghost'} className="h-7"
            onClick={() => setFacts(new Set())}>All</Button>
          {present.map((f) => (
            <Button key={f} size="sm" variant={facts.has(f) ? 'secondary' : 'ghost'} className="h-7"
              aria-pressed={facts.has(f)} onClick={() => toggle(f)}>{FACT_LABEL[f]}</Button>
          ))}
          <label className="ml-auto flex items-center gap-1.5 text-sm text-muted-foreground">
            <input type="checkbox" checked={showSuperseded} onChange={(e) => setShowSuperseded(e.target.checked)} />
            Include corrected rows
          </label>
        </div>
        {history.isLoading ? <Skeleton className="h-32 w-full" /> : rows.length === 0 ? (
          <p className="text-helper">No dated history recorded.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Fact</TableHead>
                <TableHead>Value</TableHead>
                <TableHead>From</TableHead>
                <TableHead>To</TableHead>
                <TableHead>Recorded</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((e, i) => <EntryRow key={`${e.fact}-${e.id ?? i}`} e={e} />)}
            </TableBody>
          </Table>
        )}
      </PageSection>
    </>
  )
}
