'use client'

/**
 * W5 — Workforce lens: institution-wide supervisor capacity, availability, pending requests.
 * Admin surface, mounted separately from the supervisor's own caseload page (/supervision).
 */

import Link from 'next/link'
import { ArrowUpRight, UsersRound } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { ErrorState } from '@/components/common/ErrorState'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useSupervisorWorkforce, type WorkforceRow } from '@/features/supervision/w2_api'

function Tile({ label, value, sub, tone }: { label: string; value: string | number; sub?: string; tone?: 'error' | 'warning' | 'success' }) {
  const toneClass =
    tone === 'error' ? 'text-[hsl(var(--destructive))]'
      : tone === 'warning' ? 'text-[hsl(var(--warning))]'
        : tone === 'success' ? 'text-[hsl(var(--success))]'
          : 'text-foreground'
  return (
    <div className="card-elevated rounded-md border border-border bg-surface-2 px-4 py-3">
      <p className="text-label">{label}</p>
      <p className={`text-lg num font-semibold mt-1 ${toneClass}`}>{value}</p>
      {sub ? <p className="text-helper mt-0.5">{sub}</p> : null}
    </div>
  )
}

function StatusBadges({ row }: { row: WorkforceRow }) {
  return (
    <div className="flex flex-wrap items-center gap-1">
      {row.overCapacity ? <Badge variant="destructive">over cap</Badge> : null}
      {row.onSabbatical ? <Badge variant="warning">sabbatical</Badge> : null}
      {!row.acceptingNew ? <Badge variant="outline">not accepting</Badge> : null}
      {row.availability === 'on_leave' ? <Badge variant="warning">on leave</Badge> : null}
      {row.pendingRequests > 0 ? <Badge variant="secondary">{row.pendingRequests} pending</Badge> : null}
      {!row.hasProfile ? <Badge variant="outline">no profile</Badge> : null}
    </div>
  )
}

export default function WorkforcePage() {
  const { data, isLoading, isError, error } = useSupervisorWorkforce()

  return (
    <>
      <PageHeader
        title="Supervisor workforce"
        description="W5 — institution-wide capacity, availability, and assignment backlog across every supervisor we manage."
      />
      <div className="px-6 pb-6 space-y-4">
        {isLoading ? <Skeleton className="h-32 w-full" />
          : isError ? <ErrorState error={error} />
          : data ? (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Tile label="Supervisors" value={data.totals.supervisors} sub={`default cap ${data.totals.defaultCap}`} />
                <Tile label="Over capacity" value={data.totals.overCapacity}
                      tone={data.totals.overCapacity ? 'error' : undefined} />
                <Tile label="On sabbatical" value={data.totals.onSabbatical}
                      tone={data.totals.onSabbatical ? 'warning' : undefined} />
                <Tile label="Not accepting new" value={data.totals.notAcceptingNew} />
                <Tile label="Unavailable (any reason)" value={data.totals.unavailable} />
                <Tile label="Pending assignment requests" value={data.totals.pendingRequests}
                      tone={data.totals.pendingRequests > 0 ? 'warning' : undefined} />
                <Tile label="Active supervisees" value={data.totals.totalActiveSupervisees} />
                <Tile
                  label="Utilisation"
                  value={`${data.totals.utilisationPct}%`}
                  sub={`${data.totals.totalActiveSupervisees} / ${data.totals.totalCapacity}`}
                  tone={data.totals.utilisationPct >= 100 ? 'error'
                    : data.totals.utilisationPct >= 85 ? 'warning' : 'success'}
                />
              </div>

              <PageSection
                icon={UsersRound}
                title={`Supervisors (${data.supervisors.length})`}
                accent={data.totals.overCapacity > 0 ? 'danger' : 'primary'}
                attention={data.totals.overCapacity > 0}
                description="Over-capacity rows are listed first, then alphabetical."
              >
                {data.supervisors.length === 0 ? (
                  <p className="text-helper">Nobody supervises anyone yet — no profiles, no active relationships, no pending requests.</p>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Supervisor</TableHead>
                        <TableHead className="text-right">Caseload</TableHead>
                        <TableHead className="text-right">Cap</TableHead>
                        <TableHead className="text-right">Headroom</TableHead>
                        <TableHead>Status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.supervisors.map((row) => (
                        <TableRow key={row.personId}>
                          <TableCell>
                            <div className="flex flex-col">
                              <Link href={row.link}
                                className="text-sm font-medium text-primary hover:underline inline-flex items-center gap-1 w-fit">
                                {row.personName}
                                <ArrowUpRight className="h-3.5 w-3.5" />
                              </Link>
                              <span className="text-helper">{row.email ?? '—'}</span>
                            </div>
                          </TableCell>
                          <TableCell className="text-right num">
                            {row.caseload}
                            <span className="text-helper ml-1">
                              ({row.primary}P / {row.co}C)
                            </span>
                          </TableCell>
                          <TableCell className="text-right num">{row.maxStudents}</TableCell>
                          <TableCell className={`text-right num ${row.headroom < 0 ? 'text-[hsl(var(--destructive))]' : ''}`}>
                            {row.headroom > 0 ? `+${row.headroom}` : row.headroom}
                          </TableCell>
                          <TableCell><StatusBadges row={row} /></TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </PageSection>
            </>
          ) : null}
      </div>
    </>
  )
}
