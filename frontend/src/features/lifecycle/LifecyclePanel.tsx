'use client'

import { useEffect, useState } from 'react'
import { CalendarRange, Plus } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { EffectiveDateCheck, RetrospectiveWarnings } from '@/features/history/EffectiveDate'
import type { RetrospectiveWarning } from '@/features/history/api'
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
import { ProgrammeChangeImpactView } from './ProgrammeChangeImpactView'
import { useProgrammesAdmin, type ProgrammeDetail } from '@/features/programmes/api'
import { useInterruptModules, type ModuleProposal } from '@/features/taught/api'
import {
  useApproveLifecycleEvent, useIntensityImpact, useLifecycleEvents, useRecordReturn,
  useRejectLifecycleEvent, useRequestLifecycleEvent, useStudentIntensity, useIntensityImpactPreview,
  LEAVE_CATEGORIES,
  type LeaveCategory,
  type LifecycleEvent, type LifecycleEventStatus, type LifecycleEventType, type StudyMode,
} from './api'

const EVENT_LABELS: Record<LifecycleEventType, string> = {
  suspension: 'Suspension',
  extension: 'Extension',
  mode_change: 'Mode change',
  intensity_change: 'Intensity change',
  programme_change: 'Transfer to another programme',
  writing_up: 'Move to writing up',
  withdrawal: 'Withdrawal',
  termination: 'Termination',
}

/** Effective-dated status changes: the student's status changes from the effective date. */
const STATUS_EVENTS: LifecycleEventType[] = ['writing_up', 'withdrawal', 'termination']

const STATUS_EVENT_HELP: Partial<Record<LifecycleEventType, string>> = {
  writing_up: 'The research period is complete and the student is writing up the thesis. They stay a studying student.',
  withdrawal: 'The student leaves the programme. Use the last date of engagement.',
  termination: 'The institution ends the registration. Use the date it takes effect.',
}

const STATUS_VARIANT: Record<LifecycleEventStatus, 'success' | 'warning' | 'destructive' | 'secondary'> = {
  requested: 'warning',
  approved: 'success',
  rejected: 'destructive',
  cancelled: 'secondary',
}

/** Statuses where the student is off the clock and a return can be recorded. */
const PAUSED = ['suspended', 'on_leave']
const HEALTHY = ['active', 'registered', 'writing_up']

function dayDelta(from: string, to: string): number {
  return Math.round((Date.parse(to) - Date.parse(from)) / 86_400_000)
}

function eventDates(e: LifecycleEvent): string {
  if (e.eventType === 'extension') {
    return `${e.extensionDays ?? 0} day${e.extensionDays === 1 ? '' : 's'} from ${e.startDate}`
  }
  if (e.eventType === 'programme_change') {
    return `effective ${e.effectiveDate ?? e.startDate}`
  }
  if (STATUS_EVENTS.includes(e.eventType)) {
    return `effective ${e.startDate}`
  }
  const end = e.actualEndDate ?? e.endDate
  return end ? `${e.startDate} → ${end}${e.actualEndDate ? ' (actual)' : ''}` : e.startDate
}

/** Small note dialog shared by Approve and Reject — the note is optional in both cases. */
function DecisionDialog({
  label, variant, title, pending, onConfirm, impactNote, intensityEventId, retrospective,
}: {
  label: string
  variant: 'default' | 'outline'
  title: string
  pending: boolean
  onConfirm: (note: string | undefined) => Promise<boolean>
  impactNote?: string
  intensityEventId?: string
  retrospective?: RetrospectiveWarning[]
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
      <DialogContent className="flex max-h-[88vh] flex-col overflow-hidden">
        <DialogHeader className="flex-none"><DialogTitle>{title}</DialogTitle></DialogHeader>
        <div className="-mr-2 flex-1 space-y-4 overflow-y-auto pr-2">
        {retrospective && retrospective.length > 0 && (
          <div className="rounded-md border border-[hsl(var(--warning)/0.3)] bg-[hsl(var(--warning)/0.08)] p-3">
            <p className="text-sm font-medium mb-1">Affects a signed-off return</p>
            <RetrospectiveWarnings warnings={retrospective} />
          </div>
        )}
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
        </div>
        <DialogFooter className="flex-none">
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

function RequestDialog({ studentId, student }: { studentId: string; student?: Student }) {
  const { toast } = useToast()
  const request = useRequestLifecycleEvent(studentId)
  const impactPreview = useIntensityImpactPreview(studentId)
  const today = new Date().toISOString().slice(0, 10)
  const [open, setOpen] = useState(false)
  const [eventType, setEventType] = useState<LifecycleEventType>('suspension')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [extensionDays, setExtensionDays] = useState('')
  const [newMode, setNewMode] = useState<StudyMode>('part_time')
  const [intensityPct, setIntensityPct] = useState('')
  const [newProgrammeId, setNewProgrammeId] = useState('')
  const [leaveCategory, setLeaveCategory] = useState<LeaveCategory | ''>('')
  const [reason, setReason] = useState('')

  // Programme picker for the transfer variant. Only fetched once the dialog opens so we
  // don't add a network call to every student page load.
  const programmesQ = useProgrammesAdmin()
  const currentProgramme: ProgrammeDetail | null =
    programmesQ.data?.find((p) => p.id === student?.programmeId) ?? null
  const newProgramme: ProgrammeDetail | null =
    programmesQ.data?.find((p) => p.id === newProgrammeId) ?? null

  const reset = () => {
    setEventType('suspension'); setStartDate(''); setEndDate('')
    setExtensionDays(''); setNewMode('part_time'); setIntensityPct('')
    setNewProgrammeId(''); setLeaveCategory(''); setReason('')
  }

  // Default an effective date to today the first time the user picks a dated type.
  const onTypeChange = (v: LifecycleEventType) => {
    setEventType(v)
    if ((v === 'programme_change' || STATUS_EVENTS.includes(v)) && !startDate) setStartDate(today)
  }

  const intensityValid = Number(intensityPct) >= 1 && Number(intensityPct) <= 100

  // Live, deterministic impact preview as the user enters an intensity change (debounced),
  // so they see the effect on the end date before submitting — not just the approver.
  useEffect(() => {
    if (eventType !== 'intensity_change' || !intensityValid || !startDate) {
      if (impactPreview.data || impactPreview.isError) impactPreview.reset()
      return
    }
    const t = setTimeout(
      () => impactPreview.mutate({ intensityPct: Number(intensityPct), effectiveDate: startDate }),
      350,
    )
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventType, intensityPct, startDate, intensityValid])

  const complete =
    !!reason.trim() && !!startDate &&
    (eventType !== 'suspension' || !!endDate) &&
    (eventType !== 'extension' || Number(extensionDays) > 0) &&
    (eventType !== 'intensity_change' || intensityValid) &&
    (eventType !== 'programme_change'
      || (!!newProgrammeId && newProgrammeId !== student?.programmeId))

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
        newProgrammeId: eventType === 'programme_change' ? newProgrammeId : undefined,
        leaveCategory: eventType === 'suspension' && leaveCategory ? leaveCategory : undefined,
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
      <DialogContent className="flex max-h-[88vh] flex-col overflow-hidden">
        <DialogHeader className="flex-none"><DialogTitle>Request a lifecycle change</DialogTitle></DialogHeader>
        <div className="-mr-2 flex-1 space-y-3 overflow-y-auto pr-2">
          <div className="space-y-1.5">
            <Label>Type</Label>
            <Select value={eventType} onValueChange={(v) => onTypeChange(v as LifecycleEventType)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {(Object.keys(EVENT_LABELS) as LifecycleEventType[]).map((t) => (
                  <SelectItem key={t} value={t}>{EVENT_LABELS[t]}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {eventType === 'suspension' && (
            <>
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
              <div className="space-y-1.5">
                <Label>Leave category (optional)</Label>
                <Select value={leaveCategory ?? '__none'}
                  onValueChange={(v) => setLeaveCategory(v === '__none' ? '' : v as LeaveCategory)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Not categorised" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none">Not categorised</SelectItem>
                    {LEAVE_CATEGORIES.map((c) => (
                      <SelectItem key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-helper">
                  Categorises the leave for statutory / wellbeing reporting. Optional at request
                  time — can be filled in later.
                </p>
              </div>
            </>
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
            <div className="space-y-3">
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
              <div className="flex gap-1.5">
                {[25, 50, 75, 100].map((p) => (
                  <Button key={p} type="button" size="sm"
                    variant={Number(intensityPct) === p ? 'default' : 'outline'}
                    onClick={() => setIntensityPct(String(p))}>{p}%</Button>
                ))}
              </div>
              {/* Live impact preview — deterministic, before submitting. */}
              {intensityValid && startDate && (
                <div className="rounded-md border border-border bg-muted/30 p-3 text-sm">
                  {impactPreview.isPending && <p className="text-muted-foreground">Working out the impact…</p>}
                  {impactPreview.data && (
                    <div className="space-y-1">
                      <p className="text-foreground">{impactPreview.data.summary}</p>
                      {impactPreview.data.projectedEnd && (
                        <p className="text-muted-foreground">
                          Expected end{' '}
                          <span className="num line-through">{impactPreview.data.currentEnd ?? '—'}</span>{' → '}
                          <span className="num font-medium text-foreground">{impactPreview.data.projectedEnd}</span>
                          {impactPreview.data.daysDelta !== 0 && (
                            <span> ({impactPreview.data.daysDelta > 0 ? '+' : ''}{impactPreview.data.daysDelta} days,{' '}
                              {impactPreview.data.milestonesAffected} milestone{impactPreview.data.milestonesAffected === 1 ? '' : 's'} shift)</span>
                          )}
                        </p>
                      )}
                    </div>
                  )}
                  {impactPreview.isError && <p className="text-muted-foreground">Preview unavailable — the change can still be requested.</p>}
                </div>
              )}
            </div>
          )}

          {eventType === 'programme_change' && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label>Target programme</Label>
                  <Select value={newProgrammeId} onValueChange={setNewProgrammeId}>
                    <SelectTrigger>
                      <SelectValue placeholder={
                        programmesQ.isLoading ? 'Loading…' : 'Pick a programme'
                      } />
                    </SelectTrigger>
                    <SelectContent>
                      {(programmesQ.data ?? [])
                        .filter((p) => p.id !== student?.programmeId)
                        .map((p) => (
                          <SelectItem key={p.id} value={p.id}>
                            {p.code} — {p.name} ({p.programmeType})
                          </SelectItem>
                        ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="lc-peff">Effective date</Label>
                  <Input id="lc-peff" type="date" value={startDate}
                    onChange={(e) => setStartDate(e.target.value)} />
                </div>
              </div>
              {newProgramme && startDate && (
                <ProgrammeChangeImpactView
                  studentId={studentId}
                  currentProgramme={currentProgramme}
                  newProgramme={newProgramme}
                  currentExpectedEnd={student?.expectedEndDate ?? null}
                  effectiveDate={startDate}
                />
              )}
            </>
          )}

          {STATUS_EVENTS.includes(eventType) && (
            <div className="space-y-1.5">
              <Label htmlFor="lc-seff">Effective date</Label>
              <Input id="lc-seff" type="date" value={startDate}
                onChange={(e) => setStartDate(e.target.value)} />
              <p className="text-helper">
                {STATUS_EVENT_HELP[eventType]} The status changes from this date once approved;
                a future date takes effect on the day.
              </p>
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="lc-reason">Reason</Label>
            <Textarea id="lc-reason" className="min-h-[72px]" value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why this change is needed — recorded permanently." />
          </div>

          {eventType !== 'extension' && (
            <EffectiveDateCheck studentId={studentId} from={startDate}
              to={eventType === 'suspension' ? endDate : null} />
          )}

          <p className="text-helper">
            Requesting changes nothing. The student&apos;s status, expected end date and milestone
            due dates move only when an approver signs this off.
          </p>
        </div>
        <DialogFooter className="flex-none">
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

/** After a suspension is approved: offer to interrupt the student's open modules on its start date
 * (HESA ends a module when the student suspends). Nothing changes until the registry confirms. */
function ModuleProposalDialog({
  studentId, proposal, onClose,
}: { studentId: string; proposal: ModuleProposal | null; onClose: () => void }) {
  const { toast } = useToast()
  const interrupt = useInterruptModules(studentId)
  const [unticked, setUnticked] = useState<Record<string, boolean>>({})
  const [reason, setReason] = useState('')
  if (!proposal) return null
  const chosen = proposal.modules.filter((m) => !unticked[m.enrolmentId]).map((m) => m.enrolmentId)
  const close = () => { setUnticked({}); setReason(''); onClose() }
  return (
    <Dialog open onOpenChange={(o) => { if (!o) close() }}>
      <DialogContent>
        <DialogHeader><DialogTitle>Interrupt open modules?</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            The student is suspended from {proposal.effectiveDate}. Interrupted modules end on that date
            and are re-taken as new enrolments when they return.
          </p>
          <div className="space-y-1.5">
            {proposal.modules.map((m) => (
              <label key={m.enrolmentId} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={!unticked[m.enrolmentId]}
                  onChange={(ev) => setUnticked((s) => ({ ...s, [m.enrolmentId]: !ev.target.checked }))} />
                <span className="font-medium">{m.moduleCode}</span>
                <span className="text-muted-foreground">{m.moduleTitle} · {m.academicYear}</span>
              </label>
            ))}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="mp-reason">Reason</Label>
            <Input id="mp-reason" value={reason} placeholder={`Suspended from ${proposal.effectiveDate}`}
              onChange={(ev) => setReason(ev.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={close}>Not now</Button>
          <Button disabled={!chosen.length || interrupt.isPending} onClick={async () => {
            try {
              await interrupt.mutateAsync({
                effectiveDate: proposal.effectiveDate, enrolmentIds: chosen,
                reason: reason.trim() || `Suspended from ${proposal.effectiveDate}`,
                sourceEventId: proposal.sourceEventId,
              })
              toast({ title: `${chosen.length} module${chosen.length === 1 ? '' : 's'} interrupted` })
              close()
            } catch (e) {
              toast({ title: 'Could not interrupt modules', description: (e as ApiError).message, variant: 'destructive' })
            }
          }}>
            {interrupt.isPending ? 'Saving…' : `Interrupt ${chosen.length} module${chosen.length === 1 ? '' : 's'}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function LifecyclePanel({ studentId, student }: { studentId: string; student?: Student }) {
  const { toast } = useToast()
  const { hasPermission } = useAuth()
  const events = useLifecycleEvents(studentId)
  const approve = useApproveLifecycleEvent(studentId)
  const reject = useRejectLifecycleEvent(studentId)
  const [moduleProposal, setModuleProposal] = useState<ModuleProposal | null>(null)
  // For the history-row label on programme_change events — resolve ids to codes if the
  // programmes list is already cached (it is once the request dialog has been opened).
  const programmesQ = useProgrammesAdmin()
  const progCode = (id: string | null) =>
    id ? programmesQ.data?.find((p) => p.id === id)?.code ?? id.slice(0, 6) : '?'
  // Hiding the buttons is convenience only — the API enforces the permission.
  const canDecide = hasPermission('student.lifecycle.approve')
  const canRequest = hasPermission('student.write')

  const status = student?.status
  const original = student?.originalExpectedEndDate ?? null
  const current = student?.expectedEndDate ?? null
  const shifted = !!original && !!current && original !== current
  const delta = shifted ? dayDelta(original, current) : 0

  // Additive summary: pending (requested-but-unapproved) changes don't move the dates yet, so
  // surface them explicitly with their projected effect — otherwise a requested mode change
  // looks ignored next to an already-approved extension.
  const pending = events.data?.filter((e) => e.status === 'requested') ?? []
  const projectedDelta = pending.reduce((sum, e) => sum + (e.impact?.daysDelta ?? 0), 0)
  const studyModeLabel = student?.studyMode === 'part_time' ? 'Part time'
    : student?.studyMode === 'full_time' ? 'Full time' : null

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
      description="Suspensions, extensions, mode and programme changes, writing up and withdrawals — and what they did to the timeline."
      headerRight={
        canRequest ? (
          <div className="flex items-center gap-2">
            {status && PAUSED.includes(status) && <ReturnDialog studentId={studentId} />}
            <RequestDialog studentId={studentId} student={student} />
          </div>
        ) : undefined
      }
    >
      {/* Header strip — the original-vs-now contrast is the point of this feature. */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 mb-2">
        {status ? <Badge variant={statusVariant}>{status.replace(/_/g, ' ')}</Badge> : <Skeleton className="h-5 w-20" />}
        {studyModeLabel && <Badge variant="secondary">{studyModeLabel}</Badge>}
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

      {/* Pending changes — requested but not yet approved. Called out so they never look ignored:
          the dates above stay put until an approver signs off, and this says what will move. */}
      {pending.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2 rounded-md border border-[hsl(var(--warning)/0.3)] bg-[hsl(var(--warning)/0.08)] px-3 py-2 text-sm">
          <Badge variant="warning">{pending.length} awaiting approval</Badge>
          <span className="text-muted-foreground">
            {pending.map((e) => EVENT_LABELS[e.eventType]).join(', ')} — the dates above move only once approved
            {projectedDelta !== 0 && (
              <> (projected <span className="font-medium text-foreground num">{projectedDelta > 0 ? '+' : ''}{projectedDelta} days</span>)</>
            )}.
          </span>
        </div>
      )}

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
                    {e.eventType === 'programme_change' && e.newProgrammeId && (
                      <span className="text-muted-foreground font-normal">
                        {' '}({progCode(e.previousProgrammeId)} → {progCode(e.newProgrammeId)})
                      </span>
                    )}
                    {e.eventType === 'suspension' && e.leaveCategory && (
                      <Badge variant="secondary" className="ml-1.5 text-[10px] py-0 px-1.5 capitalize">
                        {e.leaveCategory}
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="num whitespace-nowrap text-sm">{eventDates(e)}</TableCell>
                  <TableCell className="text-sm" title={e.reason ?? undefined}>
                    {e.reason && e.reason.length > 60 ? `${e.reason.slice(0, 60)}…` : e.reason || '—'}
                    {e.status === 'requested' && e.retrospective && e.retrospective.length > 0 && (
                      <span className="block text-xs text-[hsl(var(--warning))]"
                        title={e.retrospective.map((w) => w.message).join('\n')}>
                        Reaches the signed-off {e.retrospective.map((w) => w.academicYear).join(', ')} return
                      </span>
                    )}
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
                          retrospective={e.retrospective}
                          onConfirm={async (note) => {
                            try {
                              const res = await approve.mutateAsync({ eventId: e.id, note })
                              toast({ title: 'Approved', description: res.recalculation?.note })
                              if (res.moduleProposal?.modules.length) setModuleProposal(res.moduleProposal)
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
      <ModuleProposalDialog studentId={studentId} proposal={moduleProposal}
        onClose={() => setModuleProposal(null)} />
    </PageSection>
  )
}
