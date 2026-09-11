'use client'

/**
 * Supervisor's "My students" — the caseload with the two things a supervisor actually
 * needs at a glance: the next milestone and any open flags. Flagged students land at the
 * top so the reader's eye goes to what needs attention.
 */

import { useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, Calendar, ChevronRight, Sparkles, UsersRound } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { MeetingBriefDrawer } from '@/features/meeting-brief/MeetingBriefDrawer'
import { RelationshipBadge } from '@/features/relationship/RelationshipBadge'
import { useMyStudents, type MyStudentRow } from './api'

export function MyStudents() {
  const { data, isLoading, error } = useMyStudents()
  const [briefFor, setBriefFor] = useState<MyStudentRow | null>(null)

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    )
  }
  if (error || !data) {
    return (
      <div className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm">
        Could not load your caseload.
      </div>
    )
  }

  const { students, summary } = data
  const flagged = students.filter((s) => s.openFlags.length > 0)
  const clear = students.filter((s) => s.openFlags.length === 0)

  return (
    <div className="space-y-6">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-page-title flex items-center gap-2">
            <UsersRound className="h-6 w-6 text-primary" />
            My students
          </h1>
          <p className="text-helper mt-1">
            Your caseload with next milestones and open flags. Flagged students first.
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="text-muted-foreground">
            <span className="num font-medium text-foreground">{summary.total}</span> total
          </span>
          {summary.flagged > 0 && (
            <span className="text-[hsl(var(--warning))]">
              <span className="num font-medium">{summary.flagged}</span> need attention
            </span>
          )}
        </div>
      </header>

      {students.length === 0 && (
        <div className="rounded-md border border-border bg-card px-4 py-8 text-center">
          <p className="text-helper">No active students on your caseload.</p>
        </div>
      )}

      {flagged.length > 0 && (
        <section>
          <p className="text-label mb-2 text-[hsl(var(--warning))] flex items-center gap-1.5">
            <AlertTriangle className="h-3 w-3" />
            Need attention
          </p>
          <div className="space-y-2">
            {flagged.map((s) => (
              <StudentRow key={s.studentId} student={s} onOpenBrief={setBriefFor} highlight />
            ))}
          </div>
        </section>
      )}

      {clear.length > 0 && (
        <section>
          <p className="text-label mb-2">On track</p>
          <div className="space-y-2">
            {clear.map((s) => (
              <StudentRow key={s.studentId} student={s} onOpenBrief={setBriefFor} />
            ))}
          </div>
        </section>
      )}

      {briefFor && (
        <MeetingBriefDrawer
          studentId={briefFor.studentId}
          studentName={briefFor.personName}
          open={!!briefFor}
          onOpenChange={(open) => !open && setBriefFor(null)}
        />
      )}
    </div>
  )
}

function StudentRow({
  student, onOpenBrief, highlight,
}: {
  student: MyStudentRow
  onOpenBrief: (s: MyStudentRow) => void
  highlight?: boolean
}) {
  return (
    <div
      className={cn(
        'rounded-md border px-4 py-3 grid gap-3 md:grid-cols-[minmax(0,2fr)_minmax(0,2fr)_auto] items-center',
        highlight
          ? 'border-[hsl(var(--warning))]/30 bg-[hsl(var(--warning))]/[0.04]'
          : 'border-border bg-card',
      )}
    >
      {/* Left — name, ref, role, relationship signal */}
      <div className="min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="font-medium text-sm truncate">{student.personName}</p>
          <Badge variant="secondary" className="text-[10px] uppercase">{student.role}</Badge>
          <RelationshipBadge studentId={student.studentId} />
        </div>
        <p className="text-xs text-muted-foreground num mt-0.5">{student.studentRef}</p>
        {student.lastMeetingOn && (
          <p className="text-xs text-muted-foreground mt-0.5">
            Last met <span className="num">{student.lastMeetingOn}</span>
          </p>
        )}
      </div>

      {/* Middle — next milestone + flags */}
      <div className="min-w-0 space-y-1">
        {student.nextMilestone ? (
          <div className="flex items-center gap-1.5 text-sm">
            <Calendar className="h-3 w-3 text-muted-foreground shrink-0" />
            <span className="truncate">{student.nextMilestone.name}</span>
            {student.nextMilestone.dueDate && (
              <span
                className={cn(
                  'num text-xs',
                  (student.nextMilestone.daysUntilDue ?? 999) < 0
                    ? 'text-destructive font-medium'
                    : (student.nextMilestone.daysUntilDue ?? 999) <= 14
                    ? 'text-[hsl(var(--warning))]'
                    : 'text-muted-foreground',
                )}
              >
                · {student.nextMilestone.dueDate}
              </span>
            )}
          </div>
        ) : (
          <div className="text-xs text-muted-foreground">No open milestones</div>
        )}
        {student.openFlags.length > 0 && (
          <ul className="text-xs text-[hsl(var(--warning))] space-y-0.5">
            {student.openFlags.map((f, i) => (
              <li key={i} className="flex items-start gap-1">
                <span>·</span>
                <span>{f}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Right — actions */}
      <div className="flex items-center gap-2 justify-end">
        <Button
          size="sm"
          variant="secondary"
          onClick={() => onOpenBrief(student)}
          className="h-8"
        >
          <Sparkles className="h-3.5 w-3.5 mr-1 text-primary" />
          Brief
        </Button>
        <Button
          size="sm"
          variant="ghost"
          asChild
          className="h-8"
        >
          <Link href={`/students/${student.studentId}`}>
            Open <ChevronRight className="h-3.5 w-3.5 ml-0.5" />
          </Link>
        </Button>
      </div>
    </div>
  )
}
