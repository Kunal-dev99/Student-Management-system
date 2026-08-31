'use client'

import { Activity, GraduationCap, Milestone, Wallet, BookOpenCheck, UsersRound } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { useMyJourney } from '@/features/portal/api'

function money(a: string | null, c: string | null) {
  return a ? `${c ?? ''} ${Number(a).toLocaleString()}`.trim() : '—'
}

const OPEN_MILESTONE = new Set(['not_started', 'due', 'submitted', 'under_review', 'overdue'])

/** Overdue / due-soon flag for an undecided milestone. */
function dueness(dueDate: string | null, status: string): 'overdue' | 'due-soon' | null {
  if (!dueDate || !OPEN_MILESTONE.has(status)) return null
  const days = (new Date(dueDate).getTime() - Date.now()) / 86_400_000
  if (days < 0) return 'overdue'
  if (days <= 30) return 'due-soon'
  return null
}

function roleLabel(role: string) {
  return role.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())
}

export default function PortalPage() {
  const { data, isLoading } = useMyJourney()

  if (isLoading) return <><PageHeader title="My journey" description="Your research lifecycle." /><div className="px-6"><Skeleton className="h-40 w-full" /></div></>

  if (!data?.linked) {
    return (
      <>
        <PageHeader title="My journey" description="Your research lifecycle." />
        <div className="px-6 pb-6">
          <PageSection icon={Activity} title="Not linked" accent="primary">
            <p className="text-helper">Your account isn’t linked to a person record yet, so there’s no journey to show.</p>
          </PageSection>
        </div>
      </>
    )
  }

  const { person, student, milestones, funding, supervision, thesis } = data

  return (
    <>
      <PageHeader title={person?.name ?? 'My journey'} description="Your research lifecycle." />
      <div className="px-6 pb-6 space-y-4">
        {student && (
          <PageSection icon={GraduationCap} title="My record" accent="primary">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div><p className="text-label">Student ref</p><p className="text-sm mt-0.5 font-mono">{student.studentRef}</p></div>
              <div><p className="text-label">Status</p><p className="mt-0.5"><Badge variant="success">{student.status}</Badge></p></div>
              <div><p className="text-label">Study mode</p><p className="text-sm mt-0.5">{student.studyMode.replace(/_/g, ' ')}</p></div>
              <div><p className="text-label">Start</p><p className="text-sm mt-0.5 num">{student.startDate ?? '—'}</p></div>
            </div>
          </PageSection>
        )}

        <PageSection icon={Activity} title="My lifecycle" accent="accent">
          {person?.timeline.length ? (
            <ol className="relative border-l border-border ml-2 space-y-3">
              {person.timeline.map((e, i) => (
                <li key={i} className="ml-4">
                  <span className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full bg-primary" />
                  <p className="text-sm font-medium">{e.label}</p>
                  <p className="text-helper num">{e.at}</p>
                </li>
              ))}
            </ol>
          ) : <p className="text-helper">No lifecycle events yet.</p>}
        </PageSection>

        <div className="grid gap-4 md:grid-cols-2">
          <PageSection icon={Milestone} title="My milestones" accent="primary">
            {milestones.length ? milestones.map((m) => {
              const flag = dueness(m.dueDate, m.status)
              return (
                <div key={m.id} className="flex items-center justify-between gap-3 border-b border-border/60 last:border-0 py-1.5">
                  <div className="min-w-0">
                    <p className="text-sm truncate">{m.name}</p>
                    {m.dueDate && (
                      <p className={`text-xs num ${flag === 'overdue' ? 'text-destructive font-medium' : 'text-muted-foreground'}`}>
                        Due {m.dueDate}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {flag === 'overdue' && <Badge variant="destructive">Overdue</Badge>}
                    {flag === 'due-soon' && <Badge variant="warning">Due soon</Badge>}
                    <Badge variant={m.status === 'decided' ? 'success' : 'secondary'}>{m.status.replace(/_/g, ' ')}</Badge>
                  </div>
                </div>
              )
            }) : <p className="text-helper">No milestones yet.</p>}
          </PageSection>

          <PageSection icon={Wallet} title="My funding" accent="primary">
            {funding.length ? funding.map((f) => (
              <div key={f.id} className="flex items-center justify-between border-b border-border/60 last:border-0 py-1.5">
                <span className="text-sm">{f.fundingType.replace(/_/g, ' ')} · <span className="num">{money(f.stipendAmount, f.currency)}</span></span>
                <Badge variant="success">{f.status}</Badge>
              </div>
            )) : <p className="text-helper">No active funding.</p>}
          </PageSection>
        </div>

        {supervision && (
          <PageSection icon={UsersRound} title="My supervision" accent="primary">
            {supervision.team.length ? (
              <div className="space-y-1">
                {supervision.team.map((s) => (
                  <div key={s.id} className="flex items-center justify-between border-b border-border/60 last:border-0 py-1.5">
                    <span className="text-sm">{s.supervisorName}</span>
                    <Badge variant={s.role === 'primary' ? 'success' : 'secondary'}>{roleLabel(s.role)}</Badge>
                  </div>
                ))}
              </div>
            ) : <p className="text-helper">No supervisors assigned yet.</p>}
            {supervision.recentMeetings.length > 0 && (
              <div className="mt-3">
                <p className="text-label mb-1">
                  Recent meetings{supervision.meetingCount > supervision.recentMeetings.length &&
                    ` (last ${supervision.recentMeetings.length} of ${supervision.meetingCount})`}
                </p>
                {supervision.recentMeetings.map((mt) => (
                  <div key={mt.id} className="flex items-center justify-between gap-3 border-b border-border/60 last:border-0 py-1.5">
                    <span className="text-sm truncate">
                      <span className="num">{mt.metOn}</span>
                      {mt.supervisorName && <span className="text-muted-foreground"> · {mt.supervisorName}</span>}
                      {mt.durationMinutes != null && <span className="text-muted-foreground num"> · {mt.durationMinutes} min</span>}
                    </span>
                    <Badge variant={mt.studentConfirmed ? 'success' : 'outline'}>
                      {mt.studentConfirmed ? 'Confirmed' : 'Unconfirmed'}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </PageSection>
        )}

        <PageSection icon={BookOpenCheck} title="My thesis" accent="accent">
          {thesis ? (
            <div className="flex items-center gap-3 text-sm">
              <span>{thesis.title ?? 'Thesis'}</span>
              <Badge variant={thesis.status === 'approved' ? 'success' : 'secondary'}>{thesis.status.replace(/_/g, ' ')}</Badge>
              {thesis.outcome && <Badge variant="outline">{thesis.outcome.replace(/_/g, ' ')}</Badge>}
            </div>
          ) : <p className="text-helper">No thesis record yet.</p>}
        </PageSection>
      </div>
    </>
  )
}
