'use client'

/**
 * W2 — global assignment-request queue, filterable by state.
 */

import { useState } from 'react'
import Link from 'next/link'
import { ClipboardList } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  useAssignmentQueue, type AssignmentRequestState,
} from '@/features/supervision/w2_api'

const STATES: (AssignmentRequestState | 'all')[] = [
  'all', 'requested', 'academic_review', 'approved', 'rejected', 'withdrawn',
]

export default function AssignmentQueuePage() {
  const [filter, setFilter] = useState<AssignmentRequestState | 'all'>('requested')
  const q = useAssignmentQueue(filter === 'all' ? undefined : filter)
  return (
    <>
      <PageHeader title="Supervisor assignment queue"
        description="W2 — pending and decided supervisor assignment requests across the institution." />
      <div className="px-6 pb-6 space-y-4">
        <PageSection icon={ClipboardList} title="Requests" accent="primary">
          <div className="flex flex-wrap items-center gap-1.5 mb-3">
            <span className="text-label mr-1">State:</span>
            {STATES.map((s) => (
              <button
                key={s}
                onClick={() => setFilter(s)}
                className={`px-2.5 py-1 rounded-full text-xs border transition ${
                  filter === s ? 'bg-primary text-primary-foreground border-primary'
                    : 'bg-transparent text-muted-foreground border-border hover:text-foreground'
                }`}
              >{s.replace(/_/g,' ')}</button>
            ))}
          </div>
          {q.isLoading ? <Skeleton className="h-24 w-full" /> : q.data && q.data.requests.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Student</TableHead>
                  <TableHead>Supervisor</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>State</TableHead>
                  <TableHead>Match</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {q.data.requests.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="font-mono text-xs">
                      <Link href={`/students/${r.studentId}`} className="hover:text-primary">
                        {r.studentId.slice(0,8)}…
                      </Link>
                    </TableCell>
                    <TableCell className="font-mono text-xs">{r.proposedSupervisorPersonId.slice(0,8)}…</TableCell>
                    <TableCell><Badge variant="secondary">{r.proposedRole}</Badge></TableCell>
                    <TableCell><Badge>{r.state.replace(/_/g,' ')}</Badge></TableCell>
                    <TableCell className="num">{r.matchScore ?? '—'}</TableCell>
                    <TableCell className="text-helper num">{new Date(r.createdAt).toLocaleDateString()}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-helper">No requests in this state.</p>
          )}
        </PageSection>
      </div>
    </>
  )
}
