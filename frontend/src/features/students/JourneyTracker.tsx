'use client'

/**
 * The whole applicant→alumni journey as one horizontal tracker at the top of the student record.
 *
 * Two things beyond a plain stepper:
 * - The path matches the programme. A **taught** student runs Registered → Taught (modules) →
 *   Award → Alumni; a **research** student runs Progression → Thesis → Examination → Completion →
 *   Alumni. The **Applicant** stage only appears for a student who actually came through the
 *   recruitment funnel (has an application) — a directly-enrolled student (ICR G2) starts at
 *   Registered.
 * - Every stage is clickable: it expands a detail panel ("branch") for that stage — the milestone
 *   list under Progression, the modules under Taught, the thesis versions, and so on.
 *
 * Zero extra network cost: every hook below shares its query key with the panel that already
 * fetches the same data further down the page.
 */

import { useState, type ReactNode } from 'react'
import { Check, Pause, Ban, ChevronDown } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { Student } from '@/features/students/api'
import { useMilestones } from '@/features/progression/api'
import { useThesis } from '@/features/thesis/api'
import { useCompletion } from '@/features/completion/api'
import { useLifecycleEvents } from '@/features/lifecycle/api'
import { useTaughtRecord } from '@/features/taught/api'

type StageState = 'done' | 'current' | 'upcoming'

interface Stage {
  key: string
  label: string
  state: StageState
  note: string | null
  detail: ReactNode
}

const fmt = (iso: string | null | undefined) => (iso ? iso.slice(0, 10) : null)
const num = (s: string | null | undefined) => (s == null ? '—' : String(Number(s)))

const OUTCOME_VARIANT: Record<string, 'success' | 'destructive' | 'warning' | 'secondary'> = {
  passed: 'success', condoned: 'warning', failed: 'destructive', pending: 'secondary',
}

function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline gap-2 py-0.5 text-sm">
      <span className="text-helper w-40 shrink-0">{label}</span>
      <span>{children}</span>
    </div>
  )
}

export function JourneyTracker({ student }: { student: Student | undefined }) {
  const id = student?.id ?? ''
  const milestonesQ = useMilestones(id)
  const thesisQ = useThesis(id)
  const completionQ = useCompletion(id)
  const eventsQ = useLifecycleEvents(id)
  const taughtQ = useTaughtRecord(id)
  const [expanded, setExpanded] = useState<string | null>(null)

  if (!student) return <Skeleton className="h-20 w-full" />

  const milestones = milestonesQ.data ?? []
  const thesis = thesisQ.data ?? null
  const completion = completionQ.data ?? null
  const events = eventsQ.data ?? []
  const taught = taughtQ.data ?? null
  const isTaught = taught?.programmeType === 'taught'

  const withdrawn = student.status === 'withdrawn' || student.status === 'terminated'
  const suspended = student.status === 'suspended' || student.status === 'on_leave'
  const graduated = completion?.status === 'graduated' || student.status === 'completed'

  const registered = !!student.startDate && student.startDate <= new Date().toISOString().slice(0, 10)
  // The Applicant stage only exists for a funnel entrant. `fromApplication` is undefined on older
  // payloads — treat undefined as "show" (safe default) and only hide on an explicit false.
  const showApplicant = student.fromApplication !== false

  // ---- research signals ----
  const decided = milestones.filter((m) => m.status === 'decided').length
  const milestonesDone = milestones.length > 0 && decided === milestones.length
  const thesisStarted = !!thesis && thesis.status !== 'preparation'
  const thesisApproved = thesis?.status === 'approved'
  const examined = !!thesis?.examination?.outcome
  const completionStarted = !!completion && completion.status !== 'pending'

  // ---- taught signals ----
  const enrolments = taught?.enrolments ?? []
  const modulesComplete =
    enrolments.length > 0 && enrolments.every((e) => e.outcome === 'passed' || e.outcome === 'condoned')
  const award = taught?.award ?? null
  const awardDecided = !!award?.classification

  // ---- detail panels ("branches") ----
  const applicantDetail = (
    <DetailRow label="Entry route">Reached the record through recruitment (application on file).</DetailRow>
  )
  const registeredDetail = (
    <div>
      <DetailRow label="Study mode">{student.studyMode.replace('_', ' ')}</DetailRow>
      <DetailRow label="Start date">{fmt(student.startDate) ?? '—'}</DetailRow>
      <DetailRow label="Expected end">{student.expectedEndDate ?? '—'}</DetailRow>
      {student.originalExpectedEndDate && student.originalExpectedEndDate !== student.expectedEndDate && (
        <DetailRow label="Agreed at registration">{student.originalExpectedEndDate}</DetailRow>
      )}
    </div>
  )
  const progressionDetail = milestones.length === 0 ? (
    <p className="text-helper">No milestones scheduled yet.</p>
  ) : (
    <div>
      {milestones.map((m) => (
        <div key={m.id} className="flex items-center gap-2 py-0.5 text-sm">
          <Badge variant={m.status === 'decided' ? 'success' : m.status === 'overdue' ? 'destructive' : 'secondary'}>
            {m.status.replace('_', ' ')}
          </Badge>
          <span className="font-medium">{m.name}</span>
          {m.dueDate && <span className="text-helper">due {fmt(m.dueDate)}</span>}
        </div>
      ))}
    </div>
  )
  const taughtDetail = enrolments.length === 0 ? (
    <p className="text-helper">No module enrolments yet.</p>
  ) : (
    <div>
      {enrolments.map((e) => (
        <div key={e.id} className="flex items-center gap-2 py-0.5 text-sm">
          <Badge variant={OUTCOME_VARIANT[e.outcome] ?? 'secondary'}>{e.outcome}</Badge>
          <span className="font-mono text-xs">{e.moduleCode}</span>
          <span className="font-medium">{e.moduleTitle}</span>
          <span className="text-helper num">
            mark {num(e.moduleMark)}{e.creditsAwarded != null ? ` · ${e.creditsAwarded} cr` : ''}
          </span>
        </div>
      ))}
      <DetailRow label="Credits">{taught?.creditsEnrolled ?? 0} / {taught?.totalCreditsTarget ?? '—'}</DetailRow>
    </div>
  )
  const awardDetail = award ? (
    <div>
      <DetailRow label="Classification">
        <Badge variant={award.classification === 'fail' ? 'destructive' : 'success'}>{award.classification}</Badge>
      </DetailRow>
      <DetailRow label="Final mark">{num(award.finalMark)}</DetailRow>
      <DetailRow label="Credits achieved">{award.creditsAchieved ?? '—'}</DetailRow>
    </div>
  ) : <p className="text-helper">Award not yet computed.</p>
  const thesisDetail = (
    <div>
      <DetailRow label="Status">{(thesis?.status ?? 'not started').replace(/_/g, ' ')}</DetailRow>
      {thesis?.submittedAt && <DetailRow label="Submitted">{fmt(thesis.submittedAt)}</DetailRow>}
      {thesis?.title && <DetailRow label="Title">{thesis.title}</DetailRow>}
    </div>
  )
  const examinationDetail = (
    <div>
      <DetailRow label="Viva">{thesis?.examination?.vivaDate ? fmt(thesis.examination.vivaDate) : 'to be scheduled'}</DetailRow>
      <DetailRow label="Outcome">{thesis?.examination?.outcome ? thesis.examination.outcome.replace(/_/g, ' ') : '—'}</DetailRow>
    </div>
  )
  const completionDetail = (
    <div>
      <DetailRow label="Status">{(completion?.status ?? 'pending').replace(/_/g, ' ')}</DetailRow>
      {completion?.awardConfirmedAt && <DetailRow label="Award confirmed">{fmt(completion.awardConfirmedAt)}</DetailRow>}
    </div>
  )
  const alumniDetail = (
    <div>
      <DetailRow label="Graduated">{completion?.graduationDate ? fmt(completion.graduationDate) : 'not yet'}</DetailRow>
    </div>
  )

  // ---- assemble the stage list for this programme type ----
  type Def = { key: string; label: string; done: boolean; doneNote: string | null; currentNote: string | null; detail: ReactNode }

  const applicantDef: Def = {
    key: 'applicant', label: 'Applicant', done: true,
    doneNote: 'via application', currentNote: null, detail: applicantDetail,
  }
  const registeredDef: Def = {
    key: 'registered', label: 'Registered', done: registered,
    doneNote: fmt(student.startDate),
    currentNote: student.startDate ? `starts ${fmt(student.startDate)}` : 'start date not set',
    detail: registeredDetail,
  }
  const alumniDef: Def = {
    key: 'alumni', label: 'Alumni', done: graduated,
    doneNote: completion?.graduationDate ? `graduated ${fmt(completion.graduationDate)}` : 'graduated',
    currentNote: null, detail: alumniDetail,
  }

  const taughtDefs: Def[] = [
    {
      key: 'taught', label: 'Taught', done: modulesComplete,
      doneNote: `${enrolments.length} module${enrolments.length === 1 ? '' : 's'} complete`,
      currentNote: enrolments.length ? `${enrolments.filter((e) => e.outcome === 'passed' || e.outcome === 'condoned').length} of ${enrolments.length} modules` : 'no modules yet',
      detail: taughtDetail,
    },
    {
      key: 'award', label: 'Award', done: awardDecided,
      doneNote: award?.classification ?? null,
      currentNote: 'after modules complete', detail: awardDetail,
    },
    alumniDef,
  ]

  const researchDefs: Def[] = [
    {
      key: 'milestones', label: 'Progression', done: milestonesDone,
      doneNote: `${decided} review${decided === 1 ? '' : 's'} passed`,
      currentNote: milestones.length ? `${decided} of ${milestones.length} decided` : 'first review pending',
      detail: progressionDetail,
    },
    {
      key: 'thesis', label: 'Thesis', done: thesisApproved || examined,
      doneNote: thesis?.submittedAt ? `submitted ${fmt(thesis.submittedAt)}` : 'submitted',
      currentNote: thesisStarted ? (thesis?.status ?? '').replace(/_/g, ' ') : 'not started',
      detail: thesisDetail,
    },
    {
      key: 'examination', label: 'Examination', done: examined,
      doneNote: thesis?.examination?.outcome ? thesis.examination.outcome.replace(/_/g, ' ') : null,
      currentNote: thesis?.examination?.vivaDate ? `viva ${fmt(thesis.examination.vivaDate)}` : 'viva to be scheduled',
      detail: examinationDetail,
    },
    {
      key: 'completion', label: 'Completion', done: graduated || completion?.status === 'award_confirmed',
      doneNote: completion?.awardConfirmedAt ? `award confirmed ${fmt(completion.awardConfirmedAt)}` : 'award confirmed',
      currentNote: completionStarted ? (completion?.status ?? '').replace(/_/g, ' ') : 'after thesis approval',
      detail: completionDetail,
    },
    alumniDef,
  ]

  const defs: Def[] = [
    ...(showApplicant ? [applicantDef] : []),
    registeredDef,
    ...(isTaught ? taughtDefs : researchDefs),
  ]

  let currentAssigned = false
  const stages: Stage[] = defs.map((s) => {
    if (s.done || graduated) return { key: s.key, label: s.label, state: 'done', note: s.doneNote, detail: s.detail }
    if (!currentAssigned && !withdrawn && !graduated) {
      currentAssigned = true
      return { key: s.key, label: s.label, state: 'current', note: s.currentNote, detail: s.detail }
    }
    return { key: s.key, label: s.label, state: 'upcoming', note: null, detail: s.detail }
  })

  const activeSuspension = suspended
    ? events.find((e) => e.eventType === 'suspension' && e.status === 'approved' && !e.actualEndDate)
    : undefined
  const withdrawalNote = withdrawn ? 'This student has withdrawn — the journey stops where it stands.' : null
  const expandedStage = stages.find((s) => s.key === expanded) ?? null

  return (
    <div className="card-elevated px-4 py-3 overflow-x-auto">
      <div className="flex items-center gap-2 mb-2.5">
        <p className="text-label">Journey</p>
        {isTaught && <Badge variant="info">taught</Badge>}
        {suspended && (
          <Badge variant="warning" className="gap-1">
            <Pause className="h-3 w-3" />
            paused{activeSuspension ? ` since ${fmt(activeSuspension.startDate)}` : ''}
          </Badge>
        )}
        {withdrawn && <Badge variant="destructive" className="gap-1"><Ban className="h-3 w-3" /> withdrawn</Badge>}
        {graduated && <Badge variant="success">🎓 complete</Badge>}
        {!withdrawn && !graduated && student.expectedEndDate && (
          <span className="text-helper ml-auto whitespace-nowrap">expected end {student.expectedEndDate}</span>
        )}
      </div>
      <div className="flex items-start min-w-[640px]">
        {stages.map((s, i) => {
          const isOpen = expanded === s.key
          return (
            <div key={s.key} className={cn('flex-1 min-w-0', i === stages.length - 1 && 'flex-none')}>
              <div className="flex items-center">
                <button
                  type="button"
                  onClick={() => setExpanded(isOpen ? null : s.key)}
                  aria-expanded={isOpen}
                  title={`${s.label} — click for detail`}
                  className={cn(
                    'h-7 w-7 shrink-0 rounded-full flex items-center justify-center border-2 text-xs font-semibold transition-all hover:scale-110 cursor-pointer',
                    s.state === 'done' && 'bg-[hsl(var(--success))] border-[hsl(var(--success))] text-white',
                    s.state === 'current' && !suspended && 'border-primary text-primary ring-4 ring-primary/15',
                    s.state === 'current' && suspended && 'border-[hsl(var(--warning))] text-[hsl(var(--warning))] ring-4 ring-[hsl(var(--warning)/0.15)]',
                    s.state === 'upcoming' && 'border-border text-muted-foreground/60',
                    withdrawn && s.state !== 'done' && 'opacity-40',
                    isOpen && 'ring-4 ring-primary/30',
                  )}
                >
                  {s.state === 'done' ? <Check className="h-3.5 w-3.5" /> : i + 1}
                </button>
                {i < stages.length - 1 && (
                  <div className={cn('h-0.5 flex-1 mx-1.5 rounded', s.state === 'done' ? 'bg-[hsl(var(--success))]' : 'bg-border')} />
                )}
              </div>
              <button type="button" onClick={() => setExpanded(isOpen ? null : s.key)}
                className="mt-1.5 pr-2 text-left block w-full">
                <p className={cn(
                  'text-xs font-medium leading-tight inline-flex items-center gap-0.5',
                  s.state === 'current' && 'text-primary',
                  s.state === 'upcoming' && 'text-muted-foreground/70',
                )}>
                  {s.label}
                  <ChevronDown className={cn('h-3 w-3 transition-transform', isOpen && 'rotate-180')} />
                </p>
                {s.note && <p className="text-[11px] text-muted-foreground leading-tight mt-0.5 truncate" title={s.note}>{s.note}</p>}
              </button>
            </div>
          )
        })}
      </div>

      {expandedStage && (
        <div className="mt-3 rounded-md border border-border/60 bg-surface-2/40 px-3 py-2">
          <p className="text-label mb-1">{expandedStage.label}</p>
          {expandedStage.detail}
        </div>
      )}

      {withdrawalNote && <p className="text-xs text-muted-foreground mt-2">{withdrawalNote}</p>}
    </div>
  )
}
