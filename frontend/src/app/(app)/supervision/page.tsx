'use client'

import Link from 'next/link'
import { UsersRound, AlertTriangle } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/shared/auth/AuthContext'
import { useSupervisorDashboard } from '@/features/reporting/api'

export default function SupervisionPage() {
  const { principal } = useAuth()
  const { data, isLoading } = useSupervisorDashboard()
  const caseload = data?.caseload ?? []

  return (
    <>
      <PageHeader title="Supervision" description="Your supervisory caseload." />
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
