'use client'

/** Effective dating, Phase 5 — on a signed-off return: the students whose history changed inside
 *  the return's year after it was signed off, so Registry can decide whether to resubmit.
 *  Unsigning and signing off again moves the baseline (the new sign-off is what was attested). */

import Link from 'next/link'
import { useState } from 'react'
import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { inclusiveEnd, useRetrospectiveChanges } from '@/features/history/api'

const FACT_LABEL: Record<string, string> = {
  status: 'Status', programme: 'Programme', intensity: 'Intensity',
  fee_status: 'Fee status', location: 'Location', custom: 'Custom attribute',
  uoa: 'Unit of assessment', supervisor_uoa: 'Supervisor UOA',
  module: 'Module', funding: 'Funding', supervision: 'Supervision',
}

export function RetrospectiveChangesPanel({ profileId }: { profileId: string }) {
  const q = useRetrospectiveChanges(profileId)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  if (q.isLoading) return <Skeleton className="h-16 w-full" />
  const d = q.data
  if (!d || !d.signedOff) return null

  if (d.students.length === 0) {
    return (
      <p className="flex items-center gap-1.5 text-sm text-muted-foreground p-3 rounded-md border border-border">
        <CheckCircle2 className="h-4 w-4 text-[hsl(var(--success))]" />
        No changes recorded since sign-off fall inside {d.academicYear}. The signed-off return still matches the record.
      </p>
    )
  }

  const toggle = (id: string) => setExpanded((prev) => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id); else next.add(id)
    return next
  })

  return (
    <div className="rounded-md border border-[hsl(var(--warning)/0.35)] p-3 space-y-2">
      <p className="flex items-start gap-1.5 text-sm">
        <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0 text-[hsl(var(--warning))]" />
        <span>
          <span className="font-medium">
            {d.students.length} student{d.students.length === 1 ? '' : 's'} changed since sign-off
          </span>{' '}
          ({d.changeCount} change{d.changeCount === 1 ? '' : 's'} dated inside {d.academicYear}, recorded after{' '}
          {d.signedOffAt ? new Date(d.signedOffAt).toLocaleDateString() : 'sign-off'}). The return may need resubmitting.
        </span>
      </p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Student</TableHead>
            <TableHead>What changed</TableHead>
            <TableHead className="text-right">Changes</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {d.students.map((s) => {
            const open = expanded.has(s.studentId)
            const shown = open ? s.changes : s.changes.slice(0, 2)
            return (
              <TableRow key={s.studentId}>
                <TableCell className="align-top whitespace-nowrap">
                  <Link href={`/students/${s.studentId}`} className="font-medium text-primary hover:underline">
                    {s.name || s.studentRef}
                  </Link>
                  <span className="block font-mono text-xs text-muted-foreground">{s.studentRef}</span>
                </TableCell>
                <TableCell className="text-sm space-y-0.5">
                  {shown.map((c, i) => (
                    <p key={i} className={c.superseded ? 'line-through opacity-60' : undefined}>
                      <Badge variant="secondary" className="mr-1.5">{FACT_LABEL[c.fact] ?? c.fact}</Badge>
                      {(c.value ?? '—').toString().replace(/_/g, ' ')}{' '}
                      <span className="num text-muted-foreground">
                        {c.validFrom} → {inclusiveEnd(c.validTo) ?? 'current'}
                      </span>
                      {c.recordedAt && (
                        <span className="text-xs text-muted-foreground"> · recorded {c.recordedAt.slice(0, 10)}</span>
                      )}
                    </p>
                  ))}
                  {s.changes.length > 2 && (
                    <Button size="sm" variant="ghost" className="h-6 px-1.5 text-xs" onClick={() => toggle(s.studentId)}>
                      {open ? 'Show fewer' : `Show all ${s.changes.length}`}
                    </Button>
                  )}
                </TableCell>
                <TableCell className="num text-right align-top">{s.changes.length}</TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
