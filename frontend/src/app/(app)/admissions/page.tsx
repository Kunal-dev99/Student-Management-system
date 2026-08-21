'use client'

import Link from 'next/link'
import { FileCheck2 } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { useApplications } from '@/features/recruitment/api'
import { StagePill } from '@/features/recruitment/StatusPills'

// Stages where an admissions decision (offer / issue / accept) is relevant.
const ACTIONABLE = new Set([
  'under_assessment', 'shortlisted', 'interview', 'selected', 'offer_made', 'offer_accepted',
])

export default function AdmissionsPage() {
  const { data, isLoading } = useApplications()
  const rows = (data?.data ?? []).filter((a) => ACTIONABLE.has(a.currentStage))

  return (
    <>
      <PageHeader title="Admissions" description="Offers, acceptance, and onboarding." />
      <div className="px-6 pb-6 space-y-4">
        <PageSection icon={FileCheck2} title="Applications awaiting an admissions decision" accent="primary">
          <p className="text-helper mb-3">
            Offer actions (create → issue → accept) live on each application. Accepting an offer
            creates the student on the same person record.
          </p>
          <div className="card-elevated overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Application</TableHead><TableHead>Stage</TableHead><TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {isLoading && <TableRow><TableCell colSpan={3}><Skeleton className="h-5 w-full" /></TableCell></TableRow>}
                {rows.map((a) => (
                  <TableRow key={a.id}>
                    <TableCell className="font-mono text-sm">{a.id.slice(0, 8)}…</TableCell>
                    <TableCell><StagePill stage={a.currentStage} /></TableCell>
                    <TableCell className="text-right">
                      <Link href={`/recruitment/applications/${a.id}`}>
                        <Button size="sm" variant="secondary">Manage</Button>
                      </Link>
                    </TableCell>
                  </TableRow>
                ))}
                {data && rows.length === 0 && (
                  <TableRow><TableCell colSpan={3} className="text-muted-foreground text-center py-8">
                    Nothing awaiting a decision. Advance an application in Recruitment first.
                  </TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </PageSection>
      </div>
    </>
  )
}
