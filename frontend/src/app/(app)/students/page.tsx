'use client'

import Link from 'next/link'
import { PageHeader } from '@/components/common/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { useStudents } from '@/features/students/api'

export default function StudentsPage() {
  const { data, isLoading, isError, error } = useStudents()
  return (
    <>
      <PageHeader title="Students" description="The core PGR student record." />
      <div className="px-6 pb-6 space-y-4">
        <div className="card-elevated overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Student ref</TableHead><TableHead>Status</TableHead>
                <TableHead>Mode</TableHead><TableHead>Start</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && <TableRow><TableCell colSpan={4}><Skeleton className="h-5 w-full" /></TableCell></TableRow>}
              {isError && <TableRow><TableCell colSpan={4} className="text-[hsl(var(--destructive))]">{(error as Error)?.message}</TableCell></TableRow>}
              {data?.data.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="font-medium">
                    <Link href={`/students/${s.id}`} className="hover:text-primary font-mono text-sm">{s.studentRef}</Link>
                  </TableCell>
                  <TableCell><Badge variant="success">{s.status}</Badge></TableCell>
                  <TableCell className="text-muted-foreground">{s.studyMode.replace(/_/g, ' ')}</TableCell>
                  <TableCell className="text-muted-foreground num">{s.startDate ?? '—'}</TableCell>
                </TableRow>
              ))}
              {data && data.data.length === 0 && (
                <TableRow><TableCell colSpan={4} className="text-muted-foreground text-center py-8">
                  No students yet. Accept an offer in Recruitment to create one.
                </TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </div>
        {data?.page.total != null && <p className="text-helper">{data.page.total} total</p>}
      </div>
    </>
  )
}
