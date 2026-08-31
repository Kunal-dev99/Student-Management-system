'use client'

/** ICR funding pillars — which funders carry the cohort. */

import { Wallet } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ErrorState } from '@/components/common/ErrorState'
import { useIcrFunding } from '@/features/icr/api'

const money = (v: string | null) =>
  v == null ? '—' : `GBP ${Number(v).toLocaleString()}`

export default function IcrFundingPage() {
  const { data, isLoading, isError, error } = useIcrFunding()
  const funders = data?.funders ?? []
  const total = funders.reduce((n, f) => n + Number(f.committedStipend ?? 0), 0)

  return (
    <>
      <PageHeader
        title="ICR funding pillars"
        description="Diversified capital: health charities, research councils and corporate partnerships carrying the cohort."
      />
      <div className="px-6 pb-6 space-y-4">
        {isError && <ErrorState error={error} />}

        <PageSection icon={Wallet} title="Funders" accent="primary"
          description="Committed stipend is the sum of current arrangements on ICR students.">
          {isLoading ? <Skeleton className="h-28 w-full" /> : (
            <>
              <div className="grid gap-2 sm:grid-cols-3 mb-4">
                <div className="rounded-md border border-border bg-surface-2 px-3 py-2.5">
                  <p className="text-label">Funded students</p>
                  <p className="text-2xl font-semibold num mt-0.5">{data?.totalStudents ?? 0}</p>
                </div>
                <div className="rounded-md border border-border bg-surface-2 px-3 py-2.5">
                  <p className="text-label">Funding pillars</p>
                  <p className="text-2xl font-semibold num mt-0.5">{funders.length}</p>
                </div>
                <div className="rounded-md border border-border bg-surface-2 px-3 py-2.5">
                  <p className="text-label">Committed stipend / yr</p>
                  <p className="text-2xl font-semibold num mt-0.5">
                    {total ? `GBP ${total.toLocaleString()}` : '—'}
                  </p>
                </div>
              </div>
              <div className="card-elevated overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Funder</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead className="text-right">Students</TableHead>
                      <TableHead className="text-right">Committed stipend</TableHead>
                      <TableHead className="text-right">Share of cohort</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {funders.map((f) => {
                      const share = data?.totalStudents
                        ? Math.round((f.students / data.totalStudents) * 100) : 0
                      return (
                        <TableRow key={f.name}>
                          <TableCell className="font-medium">{f.name}</TableCell>
                          <TableCell>
                            {f.funderType && <Badge variant="outline">{f.funderType.replace(/_/g, ' ')}</Badge>}
                          </TableCell>
                          <TableCell className="text-right num">{f.students}</TableCell>
                          <TableCell className="text-right num">{money(f.committedStipend)}</TableCell>
                          <TableCell className="text-right">
                            <div className="flex items-center justify-end gap-2">
                              <span className="num text-sm text-muted-foreground">{share}%</span>
                              <div className="h-1.5 w-16 rounded bg-surface-3 overflow-hidden">
                                <div className="h-full rounded bg-primary" style={{ width: `${share}%` }} />
                              </div>
                            </div>
                          </TableCell>
                        </TableRow>
                      )
                    })}
                    {funders.length === 0 && (
                      <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground py-8">
                        No funding arrangements on ICR students yet.
                      </TableCell></TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
              <p className="text-helper mt-2">
                Stipends run on the platform&apos;s existing arrangement machinery — instalment schedules,
                bitemporal history and the nine integrity rules apply here unchanged, including
                &ldquo;funding ends before the submission limit&rdquo;.
              </p>
            </>
          )}
        </PageSection>
      </div>
    </>
  )
}
