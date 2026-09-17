'use client'

import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useState } from 'react'
import { ArrowLeft, GraduationCap, Sparkles, User, History } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { MeetingBriefDrawer } from '@/features/meeting-brief/MeetingBriefDrawer'
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
import { ClassificationCard } from '@/features/completion/ClassificationCard'
import { TaughtRecordPanel } from '@/features/taught/TaughtRecordPanel'
import { SupervisorRequestsCard } from '@/features/supervision/SupervisorRequestsCard'
import { RelationshipGraph } from '@/features/research/RelationshipGraph'
import { DocumentsPanel } from '@/components/documents/DocumentsPanel'
import { useAudit } from '@/features/audit/api'
import { useAuth } from '@/shared/auth/AuthContext'
import { JourneyTracker } from '@/features/students/JourneyTracker'
import { IntelligenceStrip, EngagementPanel, TwinTimeline, RiskStoryline, InsightsPanel } from '@/features/intelligence'
import { STUDENT_PANELS as P } from '@/config/studentPanels'

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

// Which page tab a click on a journey-stage segment should switch to. Kept as a data map so
// the mapping is discoverable in one place (and adding a stage tomorrow is a one-line change).
// Stages not listed here leave the tab as-is — the journey tracker still expands its own detail.
type StudentTab = 'journey' | 'record' | 'supervision' | 'progression' | 'programme' | 'funding' | 'archive'

const STAGE_TO_TAB: Record<string, StudentTab> = {
  applicant: 'journey',
  registered: 'journey',
  alumni: 'journey',
  milestones: 'progression',
  taught: 'programme',
  award: 'programme',
  thesis: 'programme',
  examination: 'programme',
  completion: 'programme',
}

const TAB_DEFS: { key: StudentTab; label: string }[] = [
  { key: 'journey',      label: 'Journey' },
  { key: 'record',       label: 'Record' },
  { key: 'supervision',  label: 'Supervision' },
  { key: 'progression',  label: 'Progression' },
  { key: 'programme',    label: 'Programme' },
  { key: 'funding',      label: 'Funding' },
  { key: 'archive',      label: 'Documents & History' },
]

function TabsBar({ active, onSelect }: { active: StudentTab; onSelect: (t: StudentTab) => void }) {
  return (
    <div className="border-b border-border flex flex-wrap gap-x-1 gap-y-0" role="tablist" aria-label="Student sections">
      {TAB_DEFS.map((t) => {
        const isActive = active === t.key
        return (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onSelect(t.key)}
            className={
              'px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ' +
              (isActive
                ? 'border-primary text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border')
            }
          >
            {t.label}
          </button>
        )
      })}
    </div>
  )
}

/** Tab panel wrapper — all panels stay MOUNTED across tab switches (only `hidden` toggles) so
 *  each section's internal hooks, queries and edit-in-place state survive without a re-fetch or
 *  re-init. The earlier statutory-page refactor unmounted panels on tab change and hit stale
 *  query / stale-state bugs; this pattern avoids that entirely. */
function TabPanel({
  tab, active, children,
}: { tab: StudentTab; active: StudentTab; children: React.ReactNode }) {
  const isActive = tab === active
  return (
    <div role="tabpanel" aria-hidden={!isActive} hidden={!isActive} className="space-y-4">
      {children}
    </div>
  )
}

export default function StudentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { hasPermission } = useAuth()
  const student = useStudent(id)
  const summary = useStudentSummary(id)
  const s = student.data
  const isTaught = summary.data?.programmeType === 'taught'
  const [briefOpen, setBriefOpen] = useState(false)
  const [tab, setTab] = useState<StudentTab>('journey')

  return (
    <>
      <PageHeader title={summary.data?.personName ?? 'Student'} />
      <div className="px-6 pb-6 space-y-4">
        <div className="flex items-center justify-between">
          <Link href="/students" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-4 w-4" /> Back to students
          </Link>
          {P.meetingBrief && (
            <Button size="sm" variant="secondary" onClick={() => setBriefOpen(true)}>
              <Sparkles className="h-3.5 w-3.5 mr-1.5 text-primary" />
              Prepare for meeting
            </Button>
          )}
        </div>

        {P.meetingBrief && (
          <MeetingBriefDrawer
            studentId={id}
            studentName={summary.data?.personName}
            open={briefOpen}
            onOpenChange={setBriefOpen}
          />
        )}

        {/* Lifecycle "circle" stays above the tabs. Clicking a stage still expands the stage
            detail inside the tracker AND jumps the tab bar below to the corresponding tab. */}
        {P.journeyTracker && (
          <JourneyTracker
            student={s}
            onStageSelect={(stageKey) => {
              const target = STAGE_TO_TAB[stageKey]
              if (target) setTab(target)
            }}
          />
        )}

        <TabsBar active={tab} onSelect={setTab} />

        {/* --- Journey tab: lifecycle changes + the AI overview strip --------------------- */}
        <TabPanel tab="journey" active={tab}>
          {P.lifecycle && <LifecyclePanel studentId={id} student={s} />}
          {P.intelligenceStrip && <IntelligenceStrip studentId={id} studentName={summary.data?.personName ?? undefined} />}
          {P.insights && <InsightsPanel studentId={id} />}
          {P.twinTimeline && <TwinTimeline studentId={id} />}
          {P.riskStoryline && <RiskStoryline studentId={id} />}
        </TabPanel>

        {/* --- Record tab: the identity/core fields + person link -------------------------- */}
        <TabPanel tab="record" active={tab}>
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
          {P.person && (
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
          )}
        </TabPanel>

        {/* --- Supervision tab ------------------------------------------------------------- */}
        <TabPanel tab="supervision" active={tab}>
          {P.supervisors && <SupervisorsPanel studentId={id} />}
          {P.supervisionMeetings && <SupervisionMeetingsPanel studentId={id} />}
          {P.engagement && <EngagementPanel studentId={id} />}
          {P.supervisorRequests && <SupervisorRequestsCard studentId={id} />}
        </TabPanel>

        {/* --- Progression tab ------------------------------------------------------------- */}
        <TabPanel tab="progression" active={tab}>
          {P.milestones && <MilestonesPanel studentId={id} />}
        </TabPanel>

        {/* --- Programme tab: taught rec OR thesis+classification depending on programme --- */}
        <TabPanel tab="programme" active={tab}>
          {/* ICR G1 — taught students run modules/assessments/award; research students run
              thesis+examination+classification. Kept exactly as it worked pre-tabs. */}
          {P.taughtOrThesis && (isTaught
            ? <TaughtRecordPanel studentId={id} programmeId={summary.data?.programmeId ?? null} />
            : (
              <>
                <ThesisCompletionPanel studentId={id} />
                <ClassificationCard studentId={id} />
              </>
            ))}
        </TabPanel>

        {/* --- Funding tab ----------------------------------------------------------------- */}
        <TabPanel tab="funding" active={tab}>
          {/* Money sections need funding.read — supervisors don't hold it, so the sections
              disappear rather than rendering permission errors. */}
          {P.funding && hasPermission('funding.read') && <FundingPanel studentId={id} />}
          {P.fundingLineage && hasPermission('funding.read') && <FundingLineagePanel studentId={id} />}
          {P.relationshipGraph && hasPermission('funding.read') && (
            <RelationshipGraph
              studentId={id}
              defaultOpen={false}
              title="Relationship map"
              description="This student's funder, award, funding, project and supervisors, drawn as one picture."
            />
          )}
        </TabPanel>

        {/* --- Documents & History tab ----------------------------------------------------- */}
        <TabPanel tab="archive" active={tab}>
          {P.documents && <DocumentsPanel ownerType="student" ownerId={id} />}
          {P.history && hasPermission('audit.read') && <HistorySection studentId={id} />}
        </TabPanel>
      </div>
    </>
  )
}
