'use client'

import { useState } from 'react'
import { CalendarRange, Plus } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useToast } from '@/components/ui/use-toast'
import { ApiError } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import type { Student } from '@/features/students/api'
import { IntensityImpactView } from './IntensityImpactView'
import {
  useApproveLifecycleEvent, useIntensityImpact, useLifecycleEvents, useRecordReturn,
  useRejectLifecycleEvent, useRequestLifecycleEvent, useStudentIntensity,
  type LifecycleEvent, type LifecycleEventStatus, type LifecycleEventType, type StudyMode,
} from './api'

const EVENT_LABELS: Record<LifecycleEventType, string> = {
  suspension: 'Suspension',
  extension: 'Extension',
  mode_change: 'Mode change',
  intensity_change: 'Intensity change',
}

const STATUS_VARIANT: Record<LifecycleEventStatus, 'success' | 'warning' | 'destructive' | 'secondary'> = {
  requested: 'warning',
  approved: 'success',
  rejected: 'destructive',
  cancelled: 'secondary',
}

/** Statuses where the student is off the clock and a return can be recorded. */
const PAUSED = ['suspended', 'on_leave']
const HEALTHY = ['active', 'registered']

function dayDelta(from: string, to: string): number {
  return Math.round((Date.parse(to) - Date.parse(from)) / 86_400_000)
}

function eventDates(e: LifecycleEvent): string {
  if (e.eventType === 'extension') {
    return `${e.extensionDays ?? 0} day${e.extensionDays === 1 ? '' : 's'} from ${e.startDate}`
  }
  const end = e.actualEndDate ?? e.endDate
  return end ? `${e.startDate} → ${end}${e.actualEndDate ? ' (actual)' : ''}` : e.startDate
}

/** Small note dialog shared by Approve and Reject — the note is optional in both cases. */
function DecisionDialog({
  label, variant, title, pending, onConfirm, impactNote, intensityEventId,
}: {
  label: string
  variant: 'default' | 'outline'
  title: string
  pending: boolean
  onConfirm: (note: string | undefined) => Promise<boolean>
  impactNote?: string
  intensityEventId?: string
}) {
  const [open, setOpen] = useState(false)
  const [note, setNote] = useState('')
  // Lazy: only fetch the AI narration once the dialog is actually open.
  const impactQ = useIntensityImpact(intensityEventId ?? '', open)
  const narrated = impactQ.data
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant={variant}>{label}</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>{title}</DialogTitle></DialogHeader>
        {(impactNote || intensityEventId) && (
          <div className="rounded-md border border-[hsl(var(--warning)/0.3)] bg-[hsl(var(--warning)/0.08)] p-3 text-sm">
            {narrated
              ? <IntensityImpactView impact={narrated} />
              : (
                <>
                  <p className="font-medium mb-0.5">What this will do</p>
                  <p key={intensityEventId && impactQ.isFetching ? 'load' : 'note'} className="text-muted-foreground">
                    {intensityEventId && impactQ.isFetching ? 'Summarising…' : impactNote}
                  </p>
                </>
              )}
          </div>
        )}
        <div className="space-y-1.5">
          <Label htmlFor="decision-note">Note (optional)</Label>
          <Textarea id="decision-note" className="min-h-[72px]" value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Recorded against the decision for audit." />
        </div>
        <DialogFooter>
          <Button disabled={pending} onClick={async () => {
            const ok = await onConfirm(note.trim() || undefined)
            if (ok) { setOpen(false); setNote('') }
          }}>
            {pending ? 'Saving…' : label}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function RequestDialog({ studentId }: { studentId: string }) {
  const { toast } = useToast()
  const request = useRequestLifecycleEvent(studentId)
  const [open, setOpen] = useState(false)
  const [eventType, setEventType] = useState<LifecycleEventType>('suspension')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [extensionDays, setExtensionDays] = useState('')
  const [newMode, setNewMode] = useState<StudyMode>('part_time')
  const [intensityPct, setIntensityPct] = useState('')
  const [reason, setReason] = useState('')

  const reset = () => {
    setEventType('suspension'); setStartDate(''); setEndDate('')
    setExtensionDays(''); setNewMode('part_time'); setIntensityPct(''); setReason('')
  }

  const intensityValid = Number(intensityPct) >= 1 && Number(intensityPct) <= 100
  const complete =
    !!reason.trim() && !!startDate &&
    (eventType !== 'suspension' || !!endDate) &&
    (eventType !== 'extension' || Number(extensionDays) > 0) &&
    (eventType !== 'intensity_change' || intensityValid)

  const submit = async () => {
    try {
      await request.mutateAsync({
        eventType,
        reason: reason.trim(),
        startDate,
        endDate: eventType === 'suspension' ? endDate : undefined,
        extensionDays: eventType === 'extension' ? Number(extensionDays) : undefined,
        newMode: eventType === 'mode_change' ? newMode : undefined,
        intensityPct: eventType === 'intensity_change' ? Number(intensityPct) : undefined,
      })
      toast({
        title: 'Request submitted',
        description: 'Nothing has changed yet — the dates move only once this is approved.',
      })
      setOpen(false); reset()
    } catch (e) {
      toast({ title: 'Could not submit request', description: (e as ApiError).message, variant: 'destructive' })
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) reset() }}>
      <DialogTrigger asChild>
        <Button size="sm"><Plus className="h-4 w-4 mr-1" /> Request…</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Request a lifecycle change</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Type</Label>
            <Select value={eventType} onValueChange={(v) => setEventType(v as LifecycleEventType)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {(Object.keys(EVENT_LABELS) as LifecycleEventType[]).map((t) => (
                  <SelectItem key={t} value={t}>{EVENT_LABELS[t]}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {eventType === 'suspension' && (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="lc-start">Start date</Label>
                <Input id="lc-start" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="lc-end">Planned end date</Label>
                <Input id="lc-end" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
              </div>
            </div>
          )}

          {eventType === 'extension' && (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="lc-eff">Effective date</Label>
                <Input id="lc-eff" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="lc-days">Extension (days)</Label>
                <Input id="lc-days" type="number" min={1} value={extensionDays}
                  onChange={(e) => setExtensionDays(e.target.value)} placeholder="90" />
              </div>
            </div>
          )}

          {eventType === 'mode_change' && (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="lc-from">Effective date</Label>
                <Input id="lc-from" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label>New study mode</Label>
                <Select value={newMode} onValueChange={(v) => setNewMode(v as StudyMode)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="full_time">full time</SelectItem>
                    <SelectItem value="part_time">part time</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}

          {eventType === 'intensity_change' && (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="lc-ieff">Effective date</Label>
                <Input id="lc-ieff" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="lc-pct">Study intensity (% FTE)</Label>
                <Input id="lc-pct" type="number" min={1} max={100} value={intensityPct}
                  onChange={(e) => setIntensityPct(e.target.value)} placeholder="e.g. 50" />
              </div>
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="lc-reason">Reason</Label>
            <Textarea id="lc-reason" className="min-h-[72px]" value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why this change is needed — recorded permanently." />
          </div>

          <p className="text-helper">
            Requesting changes nothing. The student&apos;s status, expected end date and milestone
            due dates move only when an approver signs this off.
          </p>
        </div>
        <DialogFooter>
          <Button onClick={submit} disabled={!complete || request.isPending}>
            {request.isPending ? 'Submitting…' : 'Submit request'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ReturnDialog({ studentId }: { studentId: string }) {
  const { toast } = useToast()
  const recordReturn = useRecordReturn(studentId)
  const [open, setOpen] = useState(false)
  const [returnedOn, setReturnedOn] = useState('')

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">Record return</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Record return from suspension</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="lc-returned">Returned on (optional — defaults to today)</Label>
            <Input id="lc-returned" type="date" value={returnedOn}
              onChange={(e) => setReturnedOn(e.target.value)} />
          </div>
          <p className="text-helper">
            Returning early or late corrects the days already applied, so the expected end date
            reflects the suspension that actually happened.
          </p>
        </div>
        <DialogFooter>
          <Button disabled={recordReturn.isPending} onClick={async () => {
            try {
              const res = await recordReturn.mutateAsync({ returnedOn: returnedOn || undefined })
              toast({ title: 'Return recorded', description: res.recalculation?.note })
              setOpen(false); setReturnedOn('')
            } catch (e) {
              toast({ title: 'Could not record return', description: (e as ApiError).message, variant: 'destructive' })
            }
          }}>
            {recordReturn.isPending ? 'Saving…' : 'Record return'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** ICR G4/G6 — a compact FTE-% timeline: one segment per intensity period, width ∝ its duration.
 * Falls back to a plain chip when there is no real registration span (e.g. no expected end date),
 * so it never draws a misleading one-day bar. */
function IntensityStrip({ studentId }: { studentId: string }) {
  const { data } = useStudentIntensity(studentId)
  if (!data) return null

  const current = data.currentPct
  // Only worth showing once intensity is (or is scheduled to be) something other than full-time.
  const varied = new Set(data.periods.map((p) => p.pct)).size > 1 || (current ?? 100) !== 100
  if (!varied) return null

  // Real (non-negative) span per period; drop zero-width ones from the bar.
  const drawable = data.periods
    .map((p) => ({ ...p, span: Math.max(0, dayDelta(p.from, p.to)) }))
    .filter((p) => p.span > 0)
  const total = drawable.reduce((a, b) => a + b.span, 0)

  return (
    <div className="mb-4">
      <div className="flex items-center justify-between mb-1">
        <span className="text-helper">Study intensity (FTE)</span>
        <span className="text-sm font-medium">{current == null ? '—' : `${current}% now`}</span>
      </div>

      {total > 0 ? (
        <>
          <div className="flex h-6 w-full overflow-hidden rounded-sm border border-border" title="Study intensity over time">
            {drawable.map((p, i) => (
              <div key={i}
                className="flex items-center justify-center text-[10px] font-medium text-white"
                style={{
                  width: `${(p.span / total) * 100}%`,
                  backgroundColor: `hsl(var(--primary) / ${0.35 + 0.55 * (p.pct / 100)})`,
                }}
                title={`${p.from} → ${p.to}: ${p.pct}%`}>
                {(p.span / total) > 0.08 ? `${p.pct}%` : ''}
              </div>
            ))}
          </div>
          <div className="flex justify-between text-[10px] text-muted-foreground mt-0.5 num">
            <span>{drawable[0].from}</span>
            <span>{drawable[drawable.length - 1].to}</span>
          </div>
        </>
      ) : (
        // No real span to plot (e.g. no expected end date) — list the changes instead of a bar.
        <div className="text-xs text-muted-foreground">
          {data.periods.map((p, i) => (
            <span key={i} className="num">
              {i > 0 && ' → '}{p.pct}%{i < data.periods.length - 1 ? ` (from ${p.from})` : ''}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

export function LifecyclePanel({ studentId, student }: { studentId: string; student?: Student }) {
  const { toast } = useToast()
  const { hasPermission } = useAuth()
  const events = useLifecycleEvents(studentId)
  const approve = useApproveLifecycleEvent(studentId)
  const reject = useRejectLifecycleEvent(studentId)
  // Hiding the buttons is convenience only — the API enforces the permission.
  const canDecide = hasPermission('student.lifecycle.approve')
  const canRequest = hasPermission('student.write')

  const status = student?.status
  const original = student?.originalExpectedEndDate ?? null
  const current = student?.expectedEndDate ?? null
  const shifted = !!original && !!current && original !== current
  const delta = shifted ? dayDelta(original, current) : 0

  const statusVariant = status && PAUSED.includes(status)
    ? 'warning'
    : status && HEALTHY.includes(status) ? 'success' : 'secondary'

  const err = (e: unknown) =>
    toast({ title: 'Action failed', description: (e as ApiError).message, variant: 'destructive' })

  return (
    <PageSection
      icon={CalendarRange}
      title="Lifecycle changes"
      accent={shifted ? 'warning' : 'primary'}
      description="Suspensions, extensions and mode changes — and what they did to the timeline."
      headerRight={
        canRequest ? (
          <div className="flex items-center gap-2">
            {status && PAUSED.includes(status) && <ReturnDialog studentId={studentId} />}
            <RequestDialog studentId={studentId} />
          </div>
        ) : undefined
      }
    >
      {/* Header strip — the original-vs-now contrast is the point of this feature. */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 mb-4">
        {status ? <Badge variant={statusVariant}>{status.replace(/_/g, ' ')}</Badge> : <Skeleton className="h-5 w-20" />}
        {shifted ? (
          <div className="flex flex-wrap items-baseline gap-2 text-sm">
            <span className="text-muted-foreground">Originally</span>
            <span className="num line-through text-muted-foreground">{original}</span>
            <span className="text-muted-foreground">→ now</span>
            <span className="num font-semibold text-[hsl(var(--warning))]">{current}</span>
            <Badge variant="warning">
              {delta >= 0 ? '+' : ''}{delta} day{Math.abs(delta) === 1 ? '' : 's'}
            </Badge>
          </div>
        ) : (
          <span className="text-helper">
            Expected end {current ?? '—'} — unchanged from the date agreed at registration.
          </span>
        )}
      </div>

      <IntensityStrip studentId={studentId} />

      {events.isLoading ? <Skeleton className="h-24 w-full" /> : (
        events.data && events.data.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Type</TableHead>
                <TableHead>Dates</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Days applied</TableHead>
                <TableHead className="text-right">Decision</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.data.map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="font-medium whitespace-nowrap">
                    {EVENT_LABELS[e.eventType]}
                    {e.eventType === 'mode_change' && e.newMode && (
                      <span className="text-muted-foreground font-normal">
                        {' '}({(e.previousMode ?? '?').replace(/_/g, ' ')} → {e.newMode.replace(/_/g, ' ')})
                      </span>
                    )}
                    {e.eventType === 'intensity_change' && e.intensityPct != null && (
                      <span className="text-muted-foreground font-normal">
                        {' '}({e.previousIntensityPct ?? '?'}% → {e.intensityPct}%)
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="num whitespace-nowrap text-sm">{eventDates(e)}</TableCell>
                  <TableCell className="text-sm" title={e.reason ?? undefined}>
                    {e.reason && e.reason.length > 60 ? `${e.reason.slice(0, 60)}…` : e.reason || '—'}
                  </TableCell>
                  <TableCell><Badge variant={STATUS_VARIANT[e.status]}>{e.status}</Badge></TableCell>
                  <TableCell className="num">
                    {e.daysApplied !== null && e.daysApplied !== undefined
                      ? `${e.daysApplied > 0 ? '+' : ''}${e.daysApplied}`
                      : e.impact
                        ? (
                          <span className="text-muted-foreground" title={e.impact.summary}>
                            {e.impact.daysDelta > 0 ? '+' : ''}{e.impact.daysDelta}
                            <span className="text-[10px]"> (if approved)</span>
                          </span>
                        )
                        : '—'}
                  </TableCell>
                  <TableCell className="text-right">
                    {e.status === 'requested' && !canDecide && (
                      <span className="text-sm text-muted-foreground">Awaiting approval</span>
                    )}
                    {e.status === 'requested' && canDecide ? (
                      <div className="flex justify-end gap-2">
                        <DecisionDialog
                          label="Approve" variant="default" title="Approve this request"
                          pending={approve.isPending}
                          impactNote={e.impact?.summary}
                          intensityEventId={e.eventType === 'intensity_change' ? e.id : undefined}
                          onConfirm={async (note) => {
                            try {
                              const res = await approve.mutateAsync({ eventId: e.id, note })
                              toast({ title: 'Approved', description: res.recalculation?.note })
                              return true
                            } catch (err2) { err(err2); return false }
                          }}
                        />
                        <DecisionDialog
                          label="Reject" variant="outline" title="Reject this request"
                          pending={reject.isPending}
                          onConfirm={async (note) => {
                            try {
                              await reject.mutateAsync({ eventId: e.id, note })
                              toast({ title: 'Request rejected', description: 'No dates were changed.' })
                              return true
                            } catch (err2) { err(err2); return false }
                          }}
                        />
                      </div>
                    ) : e.status !== 'requested' ? (
                      <span className="text-sm text-muted-foreground" title={e.decisionNote ?? undefined}>
                        {e.decidedAt ? e.decidedAt.slice(0, 10) : '—'}
                      </span>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <p className="text-helper">
            No suspensions, extensions or mode changes have been requested for this student.
          </p>
        )
      )}
    </PageSection>
  )
}
