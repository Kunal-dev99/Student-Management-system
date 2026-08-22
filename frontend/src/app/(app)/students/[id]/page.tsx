'use client'

import Link from 'next/link'
import { useParams } from 'next/navigation'
import { ArrowLeft, GraduationCap, User, History } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useStudent, useStudentSummary } from '@/features/students/api'
import { LifecyclePanel } from '@/features/lifecycle/LifecyclePanel'
import { SupervisorsPanel } from '@/features/supervision/SupervisorsPanel'
import { SupervisionMeetingsPanel } from '@/features/supervision-meetings/SupervisionMeetingsPanel'
import { MilestonesPanel } from '@/features/progression/MilestonesPanel'
import { FundingPanel } from '@/features/funding/FundingPanel'
import { FundingLineagePanel } from '@/features/funding/FundingLineagePanel'
import { ThesisCompletionPanel } from '@/features/completion/ThesisCompletionPanel'
import { RelationshipGraph } from '@/features/research/RelationshipGraph'
import { StudentPredictionsPanel } from '@/features/pattern-lab/StudentPredictionsPanel'
import { DocumentsPanel } from '@/components/documents/DocumentsPanel'
import { useAudit } from '@/features/audit/api'
import { useAuth } from '@/shared/auth/AuthContext'

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return <div><p className="text-label">{label}</p><p className="text-sm mt-0.5">{value || '—'}</p></div>
}

function HistorySection({ studentId }: { studentId: string }) {
  const { data, isLoading } = useAudit({ entityType: 'student', entityId: studentId, limit: 50 })
  return (
    <PageSection icon={History} title="History" accent="primary">
      {isLoading ? <Skeleton className="h-16 w-full" /> : (
        data && data.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow><TableHead>Time</TableHead><TableHead>Actor</TableHead><TableHead>Action</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {data.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="num text-xs text-muted-foreground whitespace-nowrap">{row.createdAt?.replace('T', ' ').slice(0, 19)}</TableCell>
                  <TableCell className="text-sm">{row.actorEmail ?? '—'}</TableCell>
                  <TableCell className="text-sm">{row.action ?? row.method ?? '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : <p className="text-helper">No recorded history for this student.</p>
      )}
    </PageSection>
  )
}

export default function StudentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { hasPermission } = useAuth()
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
              <div>
                <p className="text-label">Status</p>
                <p className="mt-0.5">
                  <Badge variant={s && ['suspended', 'on_leave'].includes(s.status) ? 'warning' : 'success'}>
                    {s?.status}
                  </Badge>
                </p>
              </div>
              <Field label="Study mode" value={s?.studyMode.replace(/_/g, ' ')} />
              <Field label="Start date" value={s?.startDate} />
              <Field label="Expected end" value={s?.expectedEndDate} />
              <Field label="Research topic" value={s?.project?.researchTopic} />
            </div>
          )}
        </PageSection>

        <LifecyclePanel studentId={id} student={s} />

        {/* PL-5 advisory predictions — renders nothing without ml.read, on a
            403, or when no production model has scored this student. */}
        <StudentPredictionsPanel studentId={id} />

        <SupervisorsPanel studentId={id} />

        <SupervisionMeetingsPanel studentId={id} />

        <MilestonesPanel studentId={id} />

        <FundingPanel studentId={id} />

        <FundingLineagePanel studentId={id} />

        <ThesisCompletionPanel studentId={id} />

        {/* Everything above as one picture: award, funder, funding, project,
            supervisors. Folded away by default — this record is already long. */}
        <RelationshipGraph
          studentId={id}
          defaultOpen={false}
          title="Relationship map"
          description="This student's funder, award, funding, project and supervisors, drawn as one picture."
        />

        <DocumentsPanel ownerType="student" ownerId={id} />

        {hasPermission('audit.read') && <HistorySection studentId={id} />}

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
