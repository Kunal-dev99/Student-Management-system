'use client'

import { useState } from 'react'
import { CalendarClock, Check, Sparkles } from 'lucide-react'
import { CommitmentReviewDrawer } from '@/features/intelligence/CommitmentReviewDrawer'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useToast } from '@/components/ui/use-toast'
import { useAuth } from '@/shared/auth/AuthContext'
import { useSupervisors } from '@/features/supervision/api'
import { useStudentSummary } from '@/features/students/api'
import {
  useConfirmMeeting, useRecordMeeting, useSupervisionCompliance, useSupervisionMeetings,
  type MeetingFormat,
} from './api'

const FORMATS: MeetingFormat[] = ['in_person', 'online', 'hybrid']

function truncate(value: string | null, max = 60) {
  if (!value) return '—'
  return value.length > max ? `${value.slice(0, max)}…` : value
}

export function SupervisionMeetingsPanel({ studentId }: { studentId: string }) {
  const { toast } = useToast()
  const { principal } = useAuth()
  const summary = useStudentSummary(studentId)
  // "Confirm" records the STUDENT's acknowledgment of the meeting note, so it is
  // offered to that student (their own record) and to admin roles fixing records —
  // not to the supervisor who wrote the note.
  const roles = principal?.roles ?? []
  const isAdmin = roles.includes('Institution Administrator') || roles.includes('PGR Administrator')
  const canConfirm = isAdmin ||
    (!!principal?.personId && principal.personId === summary.data?.personId)
  const meetings = useSupervisionMeetings(studentId)
  const compliance = useSupervisionCompliance(studentId)
  const supervisors = useSupervisors(studentId)
  const record = useRecordMeeting(studentId)
  const confirm = useConfirmMeeting(studentId)

  const [supervisorPersonId, setSupervisorPersonId] = useState('')
  const [metOn, setMetOn] = useState('')
  const [format, setFormat] = useState<MeetingFormat>('in_person')
  const [duration, setDuration] = useState('')
  const [notes, setNotes] = useState('')
  const [actions, setActions] = useState('')
  const [nextMeetingOn, setNextMeetingOn] = useState('')
  const [commitmentMeeting, setCommitmentMeeting] = useState<{ id: string; notes: string | null } | null>(null)

  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as Error).message, variant: 'destructive' })
  const c = compliance.data

  return (
    <PageSection icon={CalendarClock} title="Supervision meetings" accent="primary"
      description="Evidence of regular supervisory contact.">
      {/* Compliance banner */}
      {compliance.isLoading ? <Skeleton className="h-8 w-64 mb-4" /> : c && (
        <div className="flex flex-wrap items-center gap-2 mb-4">
          {c.overdue
            ? <Badge variant="warning">Overdue</Badge>
            : <Badge variant="success">Up to date</Badge>}
          <span className="text-helper">
            {c.lastMeetingOn
              ? `Last meeting ${c.lastMeetingOn} — ${c.daysSince} day${c.daysSince === 1 ? '' : 's'} ago.`
              : 'No supervision meeting has been recorded yet.'}
            {' '}Expected at least every {c.expectedIntervalDays} days.
          </span>
        </div>
      )}

      {meetings.isLoading ? <Skeleton className="h-24 w-full" /> : (
        meetings.data && meetings.data.length > 0 ? (
          <div className="mb-4">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Supervisor</TableHead>
                  <TableHead>Format</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Notes</TableHead>
                  <TableHead>Actions agreed</TableHead>
                  <TableHead>Next</TableHead>
                  <TableHead>Confirmed</TableHead>
                  <TableHead>Commitments</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {meetings.data.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell className="num whitespace-nowrap">{m.metOn}</TableCell>
                    <TableCell className="text-sm">{m.supervisorName ?? '—'}</TableCell>
                    <TableCell><Badge variant="secondary">{m.format.replace(/_/g, ' ')}</Badge></TableCell>
                    <TableCell className="num">{m.durationMinutes ? `${m.durationMinutes}m` : '—'}</TableCell>
                    <TableCell className="text-sm" title={m.notes ?? undefined}>{truncate(m.notes)}</TableCell>
                    <TableCell className="text-sm" title={m.actions ?? undefined}>{truncate(m.actions)}</TableCell>
                    <TableCell className="num whitespace-nowrap">{m.nextMeetingOn ?? '—'}</TableCell>
                    <TableCell>
                      {m.studentConfirmed ? (
                        <span className="inline-flex items-center gap-1 text-sm text-[hsl(var(--success))]">
                          <Check className="h-4 w-4" /> confirmed
                        </span>
                      ) : canConfirm ? (
                        <Button size="sm" variant="ghost" disabled={confirm.isPending}
                          onClick={async () => { try { await confirm.mutateAsync(m.id); toast({ title: 'Meeting confirmed' }) } catch (e) { err(e) } }}>
                          Confirm
                        </Button>
                      ) : (
                        <span className="text-helper">awaiting student</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {m.notes ? (
                        <Button size="sm" variant="ghost" className="h-7"
                          onClick={() => setCommitmentMeeting({ id: m.id, notes: m.notes })}>
                          <Sparkles className="h-3.5 w-3.5 mr-1.5 text-primary" /> Review
                        </Button>
                      ) : (
                        <span className="text-helper">no notes</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : <p className="text-helper mb-4">No supervision meetings recorded yet.</p>
      )}

      {/* Record a meeting */}
      <div className="pt-3 border-t border-border space-y-2">
        <div className="text-sm font-medium">Record a meeting</div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">This meeting on</label>
            <Input type="date" className="w-40 h-8" value={metOn} onChange={(e) => setMetOn(e.target.value)} />
          </div>
          <div className="space-y-1 min-w-[180px]">
            <label className="text-xs text-muted-foreground">Supervisor</label>
            <Select value={supervisorPersonId} onValueChange={setSupervisorPersonId}>
              <SelectTrigger className="h-8"><SelectValue placeholder="Supervisor (optional)" /></SelectTrigger>
              <SelectContent>
                {supervisors.data?.map((s) => (
                  <SelectItem key={s.id} value={s.supervisorPersonId}>{s.supervisorName}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">Format</label>
            <Select value={format} onValueChange={(v) => setFormat(v as MeetingFormat)}>
              <SelectTrigger className="w-36 h-8"><SelectValue /></SelectTrigger>
              <SelectContent>
                {FORMATS.map((f) => <SelectItem key={f} value={f}>{f.replace(/_/g, ' ')}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">Duration (min)</label>
            <Input type="number" className="w-28 h-8" placeholder="e.g. 45" value={duration}
              onChange={(e) => setDuration(e.target.value)} />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">Next meeting on (optional)</label>
            <Input type="date" className="w-40 h-8" value={nextMeetingOn}
              onChange={(e) => setNextMeetingOn(e.target.value)} />
          </div>
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          <Textarea className="min-h-[64px]" placeholder="Discussion notes" value={notes}
            onChange={(e) => setNotes(e.target.value)} />
          <Textarea className="min-h-[64px]" placeholder="Actions agreed" value={actions}
            onChange={(e) => setActions(e.target.value)} />
        </div>
        <Button size="sm" disabled={!metOn || record.isPending}
          onClick={async () => {
            try {
              await record.mutateAsync({
                supervisorPersonId: supervisorPersonId || undefined,
                metOn,
                format,
                durationMinutes: duration ? Number(duration) : undefined,
                notes: notes || undefined,
                actions: actions || undefined,
                nextMeetingOn: nextMeetingOn || undefined,
              })
              toast({ title: 'Meeting recorded' })
              setMetOn(''); setDuration(''); setNotes(''); setActions(''); setNextMeetingOn('')
            } catch (e) { err(e) }
          }}>
          Record meeting
        </Button>
      </div>

      {commitmentMeeting ? (
        <CommitmentReviewDrawer
          open={!!commitmentMeeting}
          onOpenChange={(o) => !o && setCommitmentMeeting(null)}
          meetingId={commitmentMeeting.id}
          studentId={studentId}
          notes={commitmentMeeting.notes}
        />
      ) : null}
    </PageSection>
  )
}
