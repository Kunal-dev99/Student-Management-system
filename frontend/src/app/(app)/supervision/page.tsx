'use client'

import Link from 'next/link'
import { UsersRound, AlertTriangle, ArrowRight, ClipboardList, LayoutGrid } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/shared/auth/AuthContext'
import { useSupervisorDashboard } from '@/features/reporting/api'
import { useCaseload } from '@/features/supervision/api'
import { ADMIN_ROLES } from '@/shared/auth/routeAccess'

export default function SupervisionPage() {
  const { principal } = useAuth()
  const isAdmin = (principal?.roles ?? []).some((r) => ADMIN_ROLES.includes(r))
  const { data, isLoading } = useSupervisorDashboard()
  const caseload = data?.caseload ?? []
  // The dashboard read-model carries milestone/funding/risk; the supervision module carries
  // the meeting-log health (Phase 4B.5). Join them by studentId.
  const meetingHealth = useCaseload(principal?.personId)
  const health = new Map((meetingHealth.data ?? []).map((c) => [c.studentId, c]))

  // Admins don't have a personal caseload — send them straight to the two admin surfaces
  // instead of showing an empty "no caseload" panel.
  if (isAdmin && !principal?.personId) {
    return (
      <>
        <PageHeader title="Supervision" />
        <div className="px-6 pb-6 grid gap-3 md:grid-cols-2">
          <Link href="/supervision/requests"
            className="group rounded-lg border border-border bg-surface-2 p-4 transition-all hover:border-primary/50 hover:shadow-sm">
            <div className="flex items-center gap-2">
              <ClipboardList className="h-5 w-5 text-primary" />
              <p className="text-sm font-medium">Assignment requests</p>
            </div>
            <p className="text-helper mt-1">
              Approve or reject new supervisor assignments through the review workflow.
            </p>
            <p className="mt-2 inline-flex items-center gap-1 text-xs text-primary">
              Open queue <ArrowRight className="h-3 w-3" />
            </p>
          </Link>
          <Link href="/supervision/workforce"
            className="group rounded-lg border border-border bg-surface-2 p-4 transition-all hover:border-primary/50 hover:shadow-sm">
            <div className="flex items-center gap-2">
              <LayoutGrid className="h-5 w-5 text-primary" />
              <p className="text-sm font-medium">Workforce lens</p>
            </div>
            <p className="text-helper mt-1">
              Supervisor capacity across the institution. Over-capacity first.
            </p>
            <p className="mt-2 inline-flex items-center gap-1 text-xs text-primary">
              Open lens <ArrowRight className="h-3 w-3" />
            </p>
          </Link>
        </div>
      </>
    )
  }

  return (
    <>
      <PageHeader title="Supervision" />
      <div className="px-6 pb-6">
        <PageSection icon={UsersRound} title="My caseload" accent="primary">
          {!principal?.personId ? (
            <p className="text-helper">
              Your account isn’t linked to a supervisor person record, so there’s no caseload to show.
              Supervisors see the students they currently supervise here, with milestone, funding, and
              risk at a glance. (You can still assign supervisors from a student’s page.)
            </p>
          ) : isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : caseload.length > 0 ? (
            <div className="card-elevated overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Student</TableHead>
                    <TableHead>Current milestone</TableHead>
                    <TableHead>Funding</TableHead>
                    <TableHead>Last meeting</TableHead>
                    <TableHead>Supervision record</TableHead>
                    <TableHead>Risk</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {caseload.map((c) => (
                    <TableRow key={c.studentId}>
                      <TableCell>
                        <Link href={`/students/${c.studentId}`} className="font-medium hover:text-primary">{c.personName}</Link>
                        <span className="text-helper font-mono ml-2">{c.studentRef}</span>
                      </TableCell>
                      <TableCell>
                        {c.currentMilestone ? (
                          <span className="flex items-center gap-2 text-sm">{c.currentMilestone}
                            <Badge variant="secondary">{(c.milestoneStatus ?? '').replace(/_/g, ' ')}</Badge>
                          </span>
                        ) : <span className="text-muted-foreground text-sm">—</span>}
                      </TableCell>
                      <TableCell>
                        <Badge variant={c.funding === 'active' ? 'success' : 'warning'}>{c.funding}</Badge>
                      </TableCell>
                      <TableCell className="num whitespace-nowrap">
                        {health.get(c.studentId)?.lastMeetingOn ?? '—'}
                      </TableCell>
                      <TableCell>
                        {health.get(c.studentId)?.meetingOverdue
                          ? <Badge variant="warning">meetings overdue</Badge>
                          : <Badge variant="success">up to date</Badge>}
                      </TableCell>
                      <TableCell>
                        {c.risk ? (
                          <span className="flex items-center gap-1.5 text-sm text-[hsl(var(--warning))]" title={c.riskReasons.join(', ')}>
                            <AlertTriangle className="h-4 w-4" /> {c.riskReasons.join(', ')}
                          </span>
                        ) : <Badge variant="success">ok</Badge>}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <p className="text-helper">You have no students assigned right now.</p>
          )}
        </PageSection>
      </div>
    </>
  )
}
