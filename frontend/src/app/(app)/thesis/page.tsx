'use client'

import { useState } from 'react'
import Link from 'next/link'
import { AlertOctagon, ArrowUpRight, BookOpenCheck, CalendarClock, ClipboardCheck } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { api } from '@/shared/api/client'

const SECTION_CAP = 10

function ShowMoreButton({ total, expanded, onToggle }: { total: number; expanded: boolean; onToggle: () => void }) {
  if (total <= SECTION_CAP) return null
  return (
    <Button size="sm" variant="ghost" className="mt-1.5" onClick={onToggle}>
      {expanded ? 'Show fewer' : `Show all ${total}`}
    </Button>
  )
}

interface ByStatus { [k: string]: number }
interface PendingNom { id: string; examinerName: string; type: string; conflictOfInterest: boolean; conflictNote: string | null }
interface AwaitingRow { thesisId: string; studentId: string; studentRef: string; personName: string; thesisTitle: string | null; link: string; pendingNominations: PendingNom[]; hasConflict: boolean }
interface VivaRow { thesisId: string; studentId: string; studentRef: string; personName: string; vivaDate: string; vivaFormat: string | null; vivaLocation: string | null; daysUntil: number; link: string }
interface CorrectionRow { correctionId: string; thesisId: string; studentId: string; studentRef: string; personName: string; kind: string; deadline: string; daysLeft: number; overdue: boolean; link: string }

interface Pipeline {
  byStatus: ByStatus
  totals: {
    thesesTotal: number
    awaitingExaminerApproval: number
    upcomingVivas: number
    correctionsOpen: number
    correctionsOverdue: number
    vivaWindowDays: number
  }
  awaitingExaminerApproval: AwaitingRow[]
  upcomingVivas: VivaRow[]
  correctionsOpen: CorrectionRow[]
}

const STAGE_LABEL: Record<string, string> = {
  preparation: 'Preparation',
  intention_to_submit: 'Intention',
  submitted: 'Submitted',
  under_examination: 'Examining',
  corrections: 'Corrections',
  resubmission: 'Resubmission',
  approved: 'Approved',
  failed: 'Failed',
}
const STAGE_ORDER = [
  'preparation', 'intention_to_submit', 'submitted', 'under_examination',
  'corrections', 'resubmission', 'approved', 'failed',
]

function Tile({ label, value, tone }: { label: string; value: number | string; tone?: 'error' | 'warning' | 'success' }) {
  const toneCls =
    tone === 'error' ? 'text-[hsl(var(--destructive))]'
      : tone === 'warning' ? 'text-[hsl(var(--warning))]'
        : tone === 'success' ? 'text-[hsl(var(--success))]'
          : 'text-foreground'
  return (
    <div className="flex h-[70px] flex-col justify-between rounded-md bg-surface-2 px-3 py-2">
      <p className="truncate text-[10px] font-medium uppercase tracking-wide text-muted-foreground" title={label}>
        {label}
      </p>
      <p className={`text-lg num font-semibold leading-none ${toneCls}`}>{value}</p>
    </div>
  )
}

function PersonLink({ href, name, sub }: { href: string; name: string; sub?: string }) {
  return (
    <Link href={href}
      className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline">
      {name}
      <ArrowUpRight className="h-3.5 w-3.5" />
      {sub && <span className="text-helper ml-1 font-mono">{sub}</span>}
    </Link>
  )
}

export default function ThesisPage() {
  const q = useQuery({
    queryKey: ['thesis-pipeline'],
    queryFn: () => api.get<Pipeline>('/reports/thesis-pipeline'),
  })
  const data = q.data
  const t = data?.totals
  const [expandExaminer, setExpandExaminer] = useState(false)
  const [expandVivas, setExpandVivas] = useState(false)
  const [expandCorrections, setExpandCorrections] = useState(false)

  return (
    <>
      <PageHeader title="Thesis pipeline" />
      <div className="px-6 pb-6 space-y-4">
        {q.isLoading || !data ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <>
            {/* Stage counts strip */}
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-2">
              {STAGE_ORDER.map((s) => (
                <Tile key={s} label={STAGE_LABEL[s]} value={data.byStatus[s] ?? 0}
                      tone={s === 'approved' ? 'success' : s === 'failed' ? 'error' : undefined} />
              ))}
            </div>

            {/* Actionable totals */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <Tile label="Total theses" value={t!.thesesTotal} />
              <Tile label="Examiners pending" value={t!.awaitingExaminerApproval}
                    tone={t!.awaitingExaminerApproval > 0 ? 'warning' : undefined} />
              <Tile label={`Vivas · next ${t!.vivaWindowDays}d`} value={t!.upcomingVivas} />
              <Tile label="Corrections open" value={t!.correctionsOpen}
                    tone={t!.correctionsOverdue > 0 ? 'error' : t!.correctionsOpen > 0 ? 'warning' : undefined} />
            </div>

            {/* Awaiting examiner approval */}
            <PageSection
              icon={ClipboardCheck}
              title={`Awaiting examiner approval (${data.awaitingExaminerApproval.length})`}
              accent={data.awaitingExaminerApproval.length ? 'warning' : 'primary'}
              attention={data.awaitingExaminerApproval.length > 0}
              description="Nominations still pending approval. Conflict-of-interest cases show first."
            >
              {data.awaitingExaminerApproval.length === 0 ? (
                <p className="text-helper">Nothing pending.</p>
              ) : (
                <ul className="divide-y divide-border/40 rounded-md border border-border/40">
                  {data.awaitingExaminerApproval.slice(0, expandExaminer ? undefined : SECTION_CAP).map((r) => (
                    <li key={r.thesisId} className="px-3 py-2 space-y-1">
                      <div className="flex items-center justify-between gap-2">
                        <PersonLink href={r.link} name={r.personName} sub={r.studentRef} />
                        {r.hasConflict && <Badge variant="destructive">conflict flagged</Badge>}
                      </div>
                      <ul className="text-xs text-muted-foreground space-y-0.5">
                        {r.pendingNominations.map((n) => (
                          <li key={n.id}>
                            — {n.examinerName} · {n.type}
                            {n.conflictOfInterest && (
                              <span className="ml-2 text-[hsl(var(--destructive))]">CoI: {n.conflictNote}</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ul>
              )}
              <ShowMoreButton total={data.awaitingExaminerApproval.length} expanded={expandExaminer}
                onToggle={() => setExpandExaminer((v) => !v)} />
            </PageSection>

            {/* Upcoming vivas */}
            <PageSection
              icon={CalendarClock}
              title={`Upcoming vivas (${data.upcomingVivas.length})`}
              accent="primary"
              description={`Vivas scheduled in the next ${t!.vivaWindowDays} days.`}
            >
              {data.upcomingVivas.length === 0 ? (
                <p className="text-helper">No vivas in window.</p>
              ) : (
                <ul className="divide-y divide-border/40 rounded-md border border-border/40">
                  {data.upcomingVivas.slice(0, expandVivas ? undefined : SECTION_CAP).map((v) => (
                    <li key={v.thesisId} className="flex items-center justify-between gap-3 px-3 py-2">
                      <div>
                        <PersonLink href={v.link} name={v.personName} sub={v.studentRef} />
                        <p className="text-helper">
                          {v.vivaFormat?.replace(/_/g, ' ') ?? 'format tbc'}{v.vivaLocation ? ` · ${v.vivaLocation}` : ''}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm num font-medium">{v.vivaDate}</p>
                        <p className="text-helper">
                          {v.daysUntil === 0 ? 'today'
                            : v.daysUntil === 1 ? 'tomorrow'
                            : `in ${v.daysUntil}d`}
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              <ShowMoreButton total={data.upcomingVivas.length} expanded={expandVivas}
                onToggle={() => setExpandVivas((v) => !v)} />
            </PageSection>

            {/* Corrections */}
            <PageSection
              icon={AlertOctagon}
              title={`Corrections open (${data.correctionsOpen.length})`}
              accent={t!.correctionsOverdue > 0 ? 'danger' : data.correctionsOpen.length ? 'warning' : 'primary'}
              attention={t!.correctionsOverdue > 0}
              description={t!.correctionsOverdue > 0
                ? `${t!.correctionsOverdue} overdue.`
                : 'Sorted by days-left ascending — overdue first.'}
            >
              {data.correctionsOpen.length === 0 ? (
                <p className="text-helper">No corrections outstanding.</p>
              ) : (
                <ul className="divide-y divide-border/40 rounded-md border border-border/40">
                  {data.correctionsOpen.slice(0, expandCorrections ? undefined : SECTION_CAP).map((c) => (
                    <li key={c.correctionId} className="flex items-center justify-between gap-3 px-3 py-2">
                      <div>
                        <PersonLink href={c.link} name={c.personName} sub={c.studentRef} />
                        <p className="text-helper">
                          <Badge variant={c.kind === 'major' ? 'warning' : 'secondary'}>{c.kind}</Badge>
                          <span className="ml-2">deadline {c.deadline}</span>
                        </p>
                      </div>
                      <div className="text-right">
                        {c.overdue
                          ? <Badge variant="destructive">{Math.abs(c.daysLeft)}d overdue</Badge>
                          : <Badge variant={c.daysLeft <= 14 ? 'warning' : 'secondary'}>{c.daysLeft}d left</Badge>}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              <ShowMoreButton total={data.correctionsOpen.length} expanded={expandCorrections}
                onToggle={() => setExpandCorrections((v) => !v)} />
            </PageSection>
          </>
        )}
      </div>
    </>
  )
}
