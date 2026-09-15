'use client'

import { useState } from 'react'
import Link from 'next/link'
import { PageHeader } from '@/components/common/PageHeader'
import { SearchInput } from '@/components/common/SearchInput'
import { FilterChips } from '@/components/common/FilterChips'
import { Pagination } from '@/components/common/Pagination'
import { Badge, type BadgeProps } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { useCan } from '@/shared/auth/Can'
import { EnrolStudentDialog } from '@/features/students/EnrolStudentDialog'
import { CohortImportDialog } from '@/features/students/CohortImportDialog'
import { useStudents, type StudentStatus } from '@/features/students/api'

const PAGE_SIZE = 50

const STATUS_FILTERS: { value: StudentStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'active', label: 'Active' },
  { value: 'registered', label: 'Registered' },
  { value: 'prospective', label: 'Prospective' },
  { value: 'on_leave', label: 'On leave' },
  { value: 'suspended', label: 'Suspended' },
  { value: 'completed', label: 'Completed' },
  { value: 'withdrawn', label: 'Withdrawn' },
  { value: 'terminated', label: 'Terminated' },
]

const STATUS_TONE: Record<StudentStatus, BadgeProps['variant']> = {
  prospective: 'secondary',
  registered: 'info',
  active: 'success',
  on_leave: 'warning',
  suspended: 'warning',
  completed: 'success',
  withdrawn: 'destructive',
  terminated: 'destructive',
}

export default function StudentsPage() {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<StudentStatus | 'all'>('all')
  const [offset, setOffset] = useState(0)

  // Any change to search/status starts back at page 1 — an offset carried over from a
  // wider result set could otherwise land past the end of a narrower one.
  const handleSearch = (v: string) => { setSearch(v); setOffset(0) }
  const handleStatus = (v: StudentStatus | 'all') => { setStatus(v); setOffset(0) }

  const canEnrol = useCan('student.write')

  const { data, isLoading, isError, error } = useStudents({
    search, status, limit: PAGE_SIZE, offset,
  })

  return (
    <>
      <PageHeader
        title="Students"
        actions={canEnrol ? (
          <div className="flex items-center gap-2">
            <CohortImportDialog />
            <EnrolStudentDialog />
          </div>
        ) : undefined}
      />
      <div className="px-6 pb-6 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <SearchInput
            value={search}
            onChange={handleSearch}
            placeholder="Search by name or student ref…"
          />
          <FilterChips
            label="Status:"
            options={STATUS_FILTERS}
            value={status}
            onChange={handleStatus}
          />
        </div>

        <div className="card-elevated overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead><TableHead>Student ref</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Mode</TableHead><TableHead>Start</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && <TableRow><TableCell colSpan={5}><Skeleton className="h-5 w-full" /></TableCell></TableRow>}
              {isError && <TableRow><TableCell colSpan={5} className="text-[hsl(var(--destructive))]">{(error as Error)?.message}</TableCell></TableRow>}
              {data?.data.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="font-medium">
                    <Link href={`/students/${s.id}`} className="hover:text-primary">{s.personName ?? '—'}</Link>
                  </TableCell>
                  <TableCell>
                    <Link href={`/students/${s.id}`} className="hover:text-primary font-mono text-sm text-muted-foreground">{s.studentRef}</Link>
                  </TableCell>
                  <TableCell><Badge variant={STATUS_TONE[s.status]}>{s.status.replace(/_/g, ' ')}</Badge></TableCell>
                  <TableCell className="text-muted-foreground">{s.studyMode.replace(/_/g, ' ')}</TableCell>
                  <TableCell className="text-muted-foreground num">{s.startDate ?? '—'}</TableCell>
                </TableRow>
              ))}
              {data && data.data.length === 0 && (
                <TableRow><TableCell colSpan={5} className="text-muted-foreground text-center py-8">
                  {search || status !== 'all'
                    ? 'No students match this search/filter.'
                    : 'No students yet. Use “Enrol student” to add an accepted student, or accept an offer in Recruitment.'}
                </TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </div>

        <Pagination
          offset={offset}
          limit={PAGE_SIZE}
          total={data?.page.total}
          onOffsetChange={setOffset}
        />
      </div>
    </>
  )
}
