'use client'

import { useState } from 'react'
import { CalendarClock, Check } from 'lucide-react'
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
import { useSupervisors } from '@/features/supervision/api'
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
                      ) : (
                        <Button size="sm" variant="ghost" disabled={confirm.isPending}
                          onClick={async () => { try { await confirm.mutateAsync(m.id); toast({ title: 'Meeting confirmed' }) } catch (e) { err(e) } }}>
                          Confirm
                        </Button>
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
        <div className="flex flex-wrap items-end gap-2">
          <Input type="date" className="w-40 h-8" value={metOn} onChange={(e) => setMetOn(e.target.value)} />
          <div className="min-w-[180px]">
            <Select value={supervisorPersonId} onValueChange={setSupervisorPersonId}>
              <SelectTrigger className="h-8"><SelectValue placeholder="Supervisor (optional)" /></SelectTrigger>
              <SelectContent>
                {supervisors.data?.map((s) => (
                  <SelectItem key={s.id} value={s.supervisorPersonId}>{s.supervisorName}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Select value={format} onValueChange={(v) => setFormat(v as MeetingFormat)}>
            <SelectTrigger className="w-36 h-8"><SelectValue /></SelectTrigger>
            <SelectContent>
              {FORMATS.map((f) => <SelectItem key={f} value={f}>{f.replace(/_/g, ' ')}</SelectItem>)}
            </SelectContent>
          </Select>
          <Input type="number" className="w-32 h-8" placeholder="Minutes" value={duration}
            onChange={(e) => setDuration(e.target.value)} />
          <Input type="date" className="w-40 h-8" value={nextMeetingOn}
            onChange={(e) => setNextMeetingOn(e.target.value)} title="Next meeting" />
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
    </PageSection>
  )
}
