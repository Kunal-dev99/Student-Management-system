'use client'

/**
 * Transfer viva tracker — the MPhil → PhD upgrade gate.
 *
 * Lives under Progression because it IS a progression milestone: at 12–14
 * months, every provisionally-registered PhD student sits an upgrade viva
 * whose outcome flips their registration from MPhil to PhD (or ends it).
 * The tracker orders open students by urgency so nothing quietly slips.
 */

import Link from 'next/link'
import { FileText, TrendingUp, Users } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ErrorState } from '@/components/common/ErrorState'
import { useTransferViva, type TransferVivaRow } from '@/features/icr/api'

const STATE_VARIANT: Record<TransferVivaRow['state'], 'destructive' | 'warning' | 'secondary' | 'success'> = {
  overdue: 'destructive',
  'due soon': 'warning',
  scheduled: 'secondary',
  upgraded: 'success',
}

function due(r: TransferVivaRow) {
  if (r.daysUntilDue === null) return '—'
  if (r.state === 'upgraded') return 'passed'
  if (r.daysUntilDue < 0) return `${Math.abs(r.daysUntilDue)} days overdue`
  return `in ${r.daysUntilDue} days`
}

export default function TransferVivaPage() {
  const { data, isLoading, isError, error } = useTransferViva()
  const rows = data?.rows ?? []
  const open = rows.filter((r) => r.state !== 'upgraded')
  const first = rows[0]

  return (
    <>
      <PageHeader
        title="Transfer viva"
        description="The MPhil → PhD upgrade checkpoint at months 12–14 — passing it flips the registration from provisional MPhil to PhD."
      />
      <div className="px-6 pb-6 space-y-4">
        {isError && <ErrorState error={error} />}

        <PageSection icon={FileText} title="What this checkpoint requires" accent="primary">
          {isLoading ? <Skeleton className="h-12 w-full" /> : (
            <div className="grid gap-3 md:grid-cols-2 text-sm">
              <div>
                <p className="text-label mb-1">Upgrade report</p>
                <p className="text-muted-foreground">
                  {first?.requiredDocuments?.upgradeReport ??
                    '2,000–3,000 words: preliminary findings, literature review, project roadmap.'}
                </p>
              </div>
              <div>
                <p className="text-label mb-1 flex items-center gap-1.5"><Users className="h-3.5 w-3.5" /> Panel</p>
                <div className="flex flex-wrap gap-1.5">
                  {(first?.panel?.composition ?? ['primary supervisor', 'co-supervisor', 'independent internal academic assessor'])
                    .map((m) => <Badge key={m} variant="secondary">{m}</Badge>)}
                </div>
              </div>
            </div>
          )}
        </PageSection>

        <PageSection icon={TrendingUp} title={`Upgrade tracker — ${open.length} still to pass`} accent="accent"
          description="Ordered by urgency: overdue first, then due soon. Upgraded students sit at the bottom.">
          {isLoading ? <Skeleton className="h-32 w-full" /> : (
            <div className="card-elevated overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Student</TableHead>
                    <TableHead>Ref</TableHead>
                    <TableHead className="text-right">Months in</TableHead>
                    <TableHead>Viva due</TableHead>
                    <TableHead>Timing</TableHead>
                    <TableHead>Registration</TableHead>
                    <TableHead>State</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((r) => (
                    <TableRow key={r.studentId}>
                      <TableCell className="font-medium">
                        <Link href={`/students/${r.studentId}`} className="hover:text-primary">{r.name}</Link>
                      </TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">{r.studentRef}</TableCell>
                      <TableCell className="text-right num">{r.monthsIn ?? '—'}</TableCell>
                      <TableCell className="num whitespace-nowrap">{r.dueDate ?? '—'}</TableCell>
                      <TableCell className={r.state === 'overdue' ? 'text-destructive text-sm' : 'text-sm text-muted-foreground'}>
                        {due(r)}
                      </TableCell>
                      <TableCell>
                        <Badge variant={r.registration.startsWith('PhD') ? 'success' : 'outline'}>
                          {r.registration}
                        </Badge>
                      </TableCell>
                      <TableCell><Badge variant={STATE_VARIANT[r.state]}>{r.state}</Badge></TableCell>
                    </TableRow>
                  ))}
                  {rows.length === 0 && (
                    <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground py-8">
                      No students at the upgrade gate right now.
                    </TableCell></TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          )}
          <p className="text-helper mt-2">
            The viva decision is recorded on the student&apos;s <b>Progression milestones</b> panel — deciding
            it upgrades the registration shown here.
          </p>
        </PageSection>
      </div>
    </>
  )
}
