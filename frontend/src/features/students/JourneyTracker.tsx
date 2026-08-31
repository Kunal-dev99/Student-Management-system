'use client'

/**
 * The whole applicant→alumni journey as one horizontal tracker at the top of the
 * student record. Until now this story was pieced together from four separate
 * panels; here it is one glance: done stages carry their dates, the current
 * stage is highlighted, suspensions show as a pause, withdrawal as a stop.
 *
 * Zero extra network cost: every hook below shares its query key with the panel
 * that already fetches the same data further down the page.
 */

import { Check, Pause, Ban } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { Student } from '@/features/students/api'
import { useMilestones } from '@/features/progression/api'
import { useThesis } from '@/features/thesis/api'
import { useCompletion } from '@/features/completion/api'
import { useLifecycleEvents } from '@/features/lifecycle/api'

type StageState = 'done' | 'current' | 'upcoming'

interface Stage {
  key: string
  label: string
  state: StageState
  /** Date shown under a done stage; progress note under the current one. */
  note: string | null
}

const fmt = (iso: string | null | undefined) => (iso ? iso.slice(0, 10) : null)

export function JourneyTracker({ student }: { student: Student | undefined }) {
  const id = student?.id ?? ''
  const milestonesQ = useMilestones(id)
  const thesisQ = useThesis(id)
  const completionQ = useCompletion(id)
  const eventsQ = useLifecycleEvents(id)

  if (!student) return <Skeleton className="h-20 w-full" />

  const milestones = milestonesQ.data ?? []
  const thesis = thesisQ.data ?? null
  const completion = completionQ.data ?? null
  const events = eventsQ.data ?? []

  const withdrawn = student.status === 'withdrawn' || student.status === 'terminated'
  const suspended = student.status === 'suspended' || student.status === 'on_leave'
  // Some records carry status "completed" without a completion row — the student
  // status is authoritative for the journey being finished.
  const graduated = completion?.status === 'graduated' || student.status === 'completed'

  const decided = milestones.filter((m) => m.status === 'decided').length
  const milestonesDone = milestones.length > 0 && decided === milestones.length
  const registered = !!student.startDate && student.startDate <= new Date().toISOString().slice(0, 10)
  const thesisStarted = !!thesis && thesis.status !== 'preparation'
  const thesisApproved = thesis?.status === 'approved'
  const examined = !!thesis?.examination?.outcome
  const completionStarted = !!completion && completion.status !== 'pending'

  // Each stage is done when its evidence exists; the first not-done stage of a
  // live registration is "current". A withdrawn/graduated record has no current.
  const doneFlags: { key: string; label: string; done: boolean; doneNote: string | null; currentNote: string | null }[] = [
    { key: 'applicant', label: 'Applicant', done: true, doneNote: `accepted ${fmt(student.createdAt)}`, currentNote: null },
    { key: 'registered', label: 'Registered', done: registered, doneNote: fmt(student.startDate), currentNote: student.startDate ? `starts ${fmt(student.startDate)}` : 'start date not set' },
    {
      key: 'milestones', label: 'Progression', done: milestonesDone,
      doneNote: `${decided} review${decided === 1 ? '' : 's'} passed`,
      currentNote: milestones.length ? `${decided} of ${milestones.length} decided` : 'first review pending',
    },
    {
      key: 'thesis', label: 'Thesis', done: thesisApproved || examined,
      doneNote: thesis?.submittedAt ? `submitted ${fmt(thesis.submittedAt)}` : 'submitted',
      currentNote: thesisStarted ? (thesis?.status ?? '').replace(/_/g, ' ') : 'not started',
    },
    {
      key: 'examination', label: 'Examination', done: examined,
      doneNote: thesis?.examination?.outcome
        ? thesis.examination.outcome.replace(/_/g, ' ')
        : null,
      currentNote: thesis?.examination?.vivaDate ? `viva ${fmt(thesis.examination.vivaDate)}` : 'viva to be scheduled',
    },
    {
      key: 'completion', label: 'Completion', done: graduated || completion?.status === 'award_confirmed',
      doneNote: completion?.awardConfirmedAt ? `award confirmed ${fmt(completion.awardConfirmedAt)}` : 'award confirmed',
      currentNote: completionStarted ? (completion?.status ?? '').replace(/_/g, ' ') : 'after thesis approval',
    },
    {
      key: 'alumni', label: 'Alumni', done: graduated,
      doneNote: completion?.graduationDate ? `graduated ${fmt(completion.graduationDate)}` : 'graduated',
      currentNote: null,
    },
  ]

  let currentAssigned = false
  const stages: Stage[] = doneFlags.map((s) => {
    if (s.done || graduated) return { key: s.key, label: s.label, state: 'done', note: s.doneNote }
    if (!currentAssigned && !withdrawn && !graduated) {
      currentAssigned = true
      return { key: s.key, label: s.label, state: 'current', note: s.currentNote }
    }
    return { key: s.key, label: s.label, state: 'upcoming', note: null }
  })

  const activeSuspension = suspended
    ? events.find((e) => e.eventType === 'suspension' && e.status === 'approved' && !e.actualEndDate)
    : undefined
  const withdrawalNote = withdrawn
    ? 'This student has withdrawn — the journey stops where it stands.'
    : null

  return (
    <div className="card-elevated px-4 py-3 overflow-x-auto">
      <div className="flex items-center gap-2 mb-2.5">
        <p className="text-label">Journey</p>
        {suspended && (
          <Badge variant="warning" className="gap-1">
            <Pause className="h-3 w-3" />
            paused{activeSuspension ? ` since ${fmt(activeSuspension.startDate)}` : ''}
          </Badge>
        )}
        {withdrawn && (
          <Badge variant="destructive" className="gap-1"><Ban className="h-3 w-3" /> withdrawn</Badge>
        )}
        {graduated && <Badge variant="success">🎓 complete</Badge>}
        {!withdrawn && !graduated && student.expectedEndDate && (
          <span className="text-helper ml-auto whitespace-nowrap">expected end {student.expectedEndDate}</span>
        )}
      </div>
      <div className="flex items-start min-w-[640px]">
        {stages.map((s, i) => (
          <div key={s.key} className={cn('flex-1 min-w-0', i === stages.length - 1 && 'flex-none')}>
            <div className="flex items-center">
              <div
                className={cn(
                  'h-7 w-7 shrink-0 rounded-full flex items-center justify-center border-2 text-xs font-semibold transition-colors',
                  s.state === 'done' && 'bg-[hsl(var(--success))] border-[hsl(var(--success))] text-white',
                  s.state === 'current' && !suspended && 'border-primary text-primary ring-4 ring-primary/15',
                  s.state === 'current' && suspended && 'border-[hsl(var(--warning))] text-[hsl(var(--warning))] ring-4 ring-[hsl(var(--warning)/0.15)]',
                  s.state === 'upcoming' && 'border-border text-muted-foreground/60',
                  withdrawn && s.state !== 'done' && 'opacity-40',
                )}
              >
                {s.state === 'done' ? <Check className="h-3.5 w-3.5" /> : i + 1}
              </div>
              {i < stages.length - 1 && (
                <div className={cn('h-0.5 flex-1 mx-1.5 rounded', s.state === 'done' ? 'bg-[hsl(var(--success))]' : 'bg-border')} />
              )}
            </div>
            <div className="mt-1.5 pr-2">
              <p className={cn(
                'text-xs font-medium leading-tight',
                s.state === 'current' && 'text-primary',
                s.state === 'upcoming' && 'text-muted-foreground/70',
              )}>
                {s.label}
              </p>
              {s.note && <p className="text-[11px] text-muted-foreground leading-tight mt-0.5 truncate" title={s.note}>{s.note}</p>}
            </div>
          </div>
        ))}
      </div>
      {withdrawalNote && <p className="text-xs text-muted-foreground mt-2">{withdrawalNote}</p>}
    </div>
  )
}
