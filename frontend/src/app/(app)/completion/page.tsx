'use client'

import Link from 'next/link'
import { Award } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { useStudents } from '@/features/students/api'

export default function CompletionPage() {
  const { data, isLoading } = useStudents()
  return (
    <>
      <PageHeader title="Completion & graduation" description="Confirm completion and graduate." />
      <div className="px-6 pb-6 space-y-4">
        <PageSection icon={Award} title="Students" accent="primary">
          <p className="text-helper mb-3">
            Confirm completion and graduate on the student’s page. Graduation records the award,
            closes funding, marks the student completed, and opens the <span className="font-medium">alumni</span> identity.
          </p>
          <div className="card-elevated overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow><TableHead>Student</TableHead><TableHead>Status</TableHead><TableHead></TableHead></TableRow>
              </TableHeader>
              <TableBody>
                {isLoading && <TableRow><TableCell colSpan={3}><Skeleton className="h-5 w-full" /></TableCell></TableRow>}
                {data?.data.map((s) => (
                  <TableRow key={s.id}>
                    <TableCell className="font-mono text-sm">{s.studentRef}</TableCell>
                    <TableCell><Badge variant={s.status === 'completed' ? 'success' : 'secondary'}>{s.status}</Badge></TableCell>
                    <TableCell className="text-right">
                      <Link href={`/students/${s.id}`}><Button size="sm" variant="secondary">Open</Button></Link>
                    </TableCell>
                  </TableRow>
                ))}
                {data && data.data.length === 0 && (
                  <TableRow><TableCell colSpan={3} className="text-muted-foreground text-center py-8">No students yet.</TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </PageSection>
      </div>
    </>
  )
}
