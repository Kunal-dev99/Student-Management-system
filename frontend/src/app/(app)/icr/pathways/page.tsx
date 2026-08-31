'use client'

/** Pathways — the non-clinical and clinical tracks, each against its own clock. */

import { useState } from 'react'
import Link from 'next/link'
import { GitFork } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ErrorState } from '@/components/common/ErrorState'
import { useIcrPathways, type PathwayRow } from '@/features/icr/api'

type Filter = 'all' | 'nonclinical' | 'clinical'

function Elapsed({ r }: { r: PathwayRow }) {
  const pct = r.monthsIn != null ? Math.min(100, Math.round((r.monthsIn / r.limitMonths) * 100)) : 0
  const near = (r.monthsRemaining ?? 99) <= 6
  return (
    <div className="min-w-[120px]">
      <div className="flex items-baseline justify-between text-xs">
        <span className="num">{r.monthsIn ?? '—'} / {r.limitMonths} mo</span>
        {near && <span className="text-[hsl(var(--warning))] font-medium">{r.monthsRemaining} left</span>}
      </div>
      <div className="mt-1 h-1.5 w-full rounded bg-surface-3 overflow-hidden">
        <div className={`h-full rounded ${near ? 'bg-[hsl(var(--warning))]' : 'bg-primary'}`}
          style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export default function IcrPathwaysPage() {
  const { data, isLoading, isError, error } = useIcrPathways()
  const [filter, setFilter] = useState<Filter>('all')
  const all = data?.rows ?? []
  const rows = all.filter((r) =>
    filter === 'all' ? true : filter === 'clinical' ? r.clinical : !r.clinical)

  return (
    <>
      <PageHeader
        title="ICR pathways"
        description="Non-clinical PhD (4-year) and clinical MD(Res) (2–3 year) — separate curricula, separate clocks."
      />
      <div className="px-6 pb-6 space-y-4">
        {isError && <ErrorState error={error} />}
        <PageSection icon={GitFork} title={`Cohort — ${rows.length} students`} accent="primary"
          description="Progress is measured against each pathway's own hard submission limit."
          actions={
            <div className="flex gap-1.5">
              {(['all', 'nonclinical', 'clinical'] as Filter[]).map((f) => (
                <Button key={f} size="sm" variant={filter === f ? 'default' : 'outline'}
                  onClick={() => setFilter(f)}>
                  {f === 'all' ? 'All' : f === 'clinical' ? 'Clinical' : 'Non-clinical'}
                </Button>
              ))}
            </div>
          }>
          {isLoading ? <Skeleton className="h-32 w-full" /> : (
            <div className="card-elevated overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Student</TableHead>
                    <TableHead>Pathway</TableHead>
                    <TableHead>Registration</TableHead>
                    <TableHead>Elapsed</TableHead>
                    <TableHead className="text-right">Checkpoints</TableHead>
                    <TableHead>30-month barrier</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((r) => (
                    <TableRow key={r.studentId} className="hover:bg-surface-2 cursor-pointer"
                              onClick={() => (window.location.href = `/icr/students/${r.studentId}`)}>
                      <TableCell className="font-medium">
                        <Link href={`/students/${r.studentId}`} className="hover:text-primary">{r.name}</Link>
                        <span className="block font-mono text-[11px] text-muted-foreground">{r.studentRef}</span>
                      </TableCell>
                      <TableCell>
                        <Badge variant={r.clinical ? 'info' : 'secondary'}>{r.pathway}</Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant={r.registration.startsWith('PhD') ? 'success' : 'outline'}>
                          {r.registration}
                        </Badge>
                      </TableCell>
                      <TableCell><Elapsed r={r} /></TableCell>
                      <TableCell className="text-right num">
                        {r.checkpointsPassed}/{r.checkpointsTotal}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {r.dataBarrier ? r.dataBarrier.replace(/_/g, ' ') : '—'}
                      </TableCell>
                      <TableCell><Badge variant="success">{r.status}</Badge></TableCell>
                    </TableRow>
                  ))}
                  {rows.length === 0 && (
                    <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground py-8">
                      No students on this pathway yet.
                    </TableCell></TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          )}
        </PageSection>
      </div>
    </>
  )
}
