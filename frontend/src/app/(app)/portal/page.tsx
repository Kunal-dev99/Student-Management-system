'use client'

import { Activity, GraduationCap, Milestone, Wallet, BookOpenCheck } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { useMyJourney } from '@/features/portal/api'

function money(a: string | null, c: string | null) {
  return a ? `${c ?? ''} ${Number(a).toLocaleString()}`.trim() : '—'
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

  const { person, student, milestones, funding, thesis } = data

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
            {milestones.length ? milestones.map((m) => (
              <div key={m.id} className="flex items-center justify-between border-b border-border/60 last:border-0 py-1.5">
                <span className="text-sm">{m.name}</span>
                <Badge variant={m.status === 'decided' ? 'success' : 'secondary'}>{m.status.replace(/_/g, ' ')}</Badge>
              </div>
            )) : <p className="text-helper">No milestones yet.</p>}
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
