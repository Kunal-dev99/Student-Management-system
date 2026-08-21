'use client'

import Link from 'next/link'
import { useParams } from 'next/navigation'
import { ArrowLeft, GraduationCap, User } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { useStudent, useStudentSummary } from '@/features/students/api'
import { SupervisorsPanel } from '@/features/supervision/SupervisorsPanel'
import { MilestonesPanel } from '@/features/progression/MilestonesPanel'
import { FundingPanel } from '@/features/funding/FundingPanel'
import { ThesisCompletionPanel } from '@/features/completion/ThesisCompletionPanel'

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return <div><p className="text-label">{label}</p><p className="text-sm mt-0.5">{value || '—'}</p></div>
}

export default function StudentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const student = useStudent(id)
  const summary = useStudentSummary(id)
  const s = student.data

  return (
    <>
      <PageHeader title={summary.data?.personName ?? 'Student'} description="PGR student record." />
      <div className="px-6 pb-6 space-y-4">
        <Link href="/students" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> Back to students
        </Link>

        <PageSection icon={GraduationCap} title="Record" accent="primary">
          {student.isLoading ? <Skeleton className="h-20 w-full" /> : (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <div><p className="text-label">Student ref</p><p className="text-sm mt-0.5 font-mono">{s?.studentRef}</p></div>
              <div><p className="text-label">Status</p><p className="mt-0.5"><Badge variant="success">{s?.status}</Badge></p></div>
              <Field label="Study mode" value={s?.studyMode.replace(/_/g, ' ')} />
              <Field label="Start date" value={s?.startDate} />
              <Field label="Expected end" value={s?.expectedEndDate} />
              <Field label="Research topic" value={s?.project?.researchTopic} />
            </div>
          )}
        </PageSection>

        <SupervisorsPanel studentId={id} />

        <MilestonesPanel studentId={id} />

        <FundingPanel studentId={id} />

        <ThesisCompletionPanel studentId={id} />

        <PageSection icon={User} title="Person" accent="accent">
          {summary.isLoading ? <Skeleton className="h-8 w-48" /> : (
            <p className="text-sm">
              This student is{' '}
              <Link href={`/persons/${summary.data?.personId}`} className="font-medium text-primary hover:underline">
                {summary.data?.personName}
              </Link>{' '}
              — the same person record carried over from their application (one <span className="font-mono text-xs">person_id</span> across identities).
            </p>
          )}
        </PageSection>
      </div>
    </>
  )
}
