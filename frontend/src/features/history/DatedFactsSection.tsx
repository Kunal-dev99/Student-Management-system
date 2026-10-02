'use client'

/** Effective dating — the student's dated facts and HESA Engagement fields on the Record tab.
 *
 *  Fee status, location of study (Phase 6), unit of assessment (Phase 9), fee eligibility and
 *  "primarily outside the UK" (Phase 10) are dated facts: "Change" records the new value from a
 *  date (default today) and the earlier value stays in the Dated history tab. Study intention and
 *  incoming exchange (Phase 10) are fixed for the engagement and edited in place. */

import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CalendarClock } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { api } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import { EffectiveDateField } from './EffectiveDate'
import { todayIso } from './api'
import { useUoas } from '@/features/uoa/api'

type FactKey = 'fee-status' | 'study-location' | 'uoa' | 'fee-eligibility' | 'outside-uk'

type Option = { value: string; label: string }

const FEE_STATUSES: Option[] = ['home', 'overseas', 'channel_islands', 'unknown']
  .map((v) => ({ value: v, label: v.replace(/_/g, ' ') }))
const FEE_ELIGIBILITIES: Option[] = [
  { value: 'eligible', label: 'Eligible' },
  { value: 'not_eligible', label: 'Not eligible' },
  { value: 'not_required', label: 'Not required' },
]
const YES_NO: Option[] = [{ value: 'true', label: 'Yes' }, { value: 'false', label: 'No' }]

function invalidateStudent(qc: ReturnType<typeof useQueryClient>, studentId: string) {
  qc.invalidateQueries({ queryKey: ['student', studentId] })
  qc.invalidateQueries({ queryKey: ['students'] })
}

function useRecordFact(studentId: string, fact: FactKey) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { value: string; effectiveDate?: string; reason?: string }) =>
      api.post<{ current: unknown }>(`/students/${studentId}/facts/${fact}`, body),
    onSuccess: () => invalidateStudent(qc, studentId),
  })
}

function FactRow({
  studentId, fact, label, current, currentValue, options, placeholder, canEdit,
}: {
  studentId: string; fact: FactKey; label: string
  /** What is shown for today's value. */
  current: string | null | undefined
  /** The stored value when it differs from what is shown (e.g. the UOA id behind its name). */
  currentValue?: string | null
  /** A fixed list to choose from; free text when omitted. */
  options?: Option[]
  placeholder?: string
  canEdit: boolean
}) {
  const { toast } = useToast()
  const record = useRecordFact(studentId, fact)
  const stored = currentValue !== undefined ? currentValue : current
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState('')
  const [date, setDate] = useState(todayIso())
  const [reason, setReason] = useState('')

  return (
    <div className="border-b border-border/60 last:border-0 pb-2 last:pb-0">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-label">{label}</p>
          <p className="text-sm mt-0.5">
            {current ? current.replace(/_/g, ' ') : <span className="text-muted-foreground">Not recorded</span>}
          </p>
        </div>
        {canEdit && (
          <Button size="sm" variant="ghost" onClick={() => {
            setOpen(!open); setValue(stored ?? ''); setDate(todayIso()); setReason('')
          }}>{current ? 'Change' : 'Record'}</Button>
        )}
      </div>
      {open && (
        <div className="flex flex-wrap items-end gap-2 mt-2 bg-surface-2 rounded-md p-2">
          <div className="flex flex-col gap-1">
            <span className="text-label">New value</span>
            {options ? (
              <Select value={value} onValueChange={setValue}>
                <SelectTrigger className="h-8 w-60"><SelectValue placeholder="Choose…" /></SelectTrigger>
                <SelectContent>
                  {options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                </SelectContent>
              </Select>
            ) : (
              <Input className="h-8 w-44" placeholder={placeholder} maxLength={60}
                value={value} onChange={(e) => setValue(e.target.value)} />
            )}
          </div>
          <EffectiveDateField studentId={studentId} label="From" id={`${fact}-from`} value={date} onChange={setDate} />
          <div className="flex flex-col gap-1">
            <label htmlFor={`${fact}-reason`} className="text-label">Reason</label>
            <Input id={`${fact}-reason`} className="h-8 w-56" placeholder="Optional"
              value={reason} onChange={(e) => setReason(e.target.value)} />
          </div>
          <Button size="sm" disabled={record.isPending || !value.trim() || value === stored}
            onClick={async () => {
              try {
                await record.mutateAsync({ value: value.trim(), effectiveDate: date || undefined, reason: reason.trim() || undefined })
                toast({ title: `${label} recorded`, description: `From ${date || 'today'}.` })
                setOpen(false)
              } catch (e) {
                toast({ title: 'Could not record', description: (e as Error).message, variant: 'destructive' })
              }
            }}>Save</Button>
          <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
        </div>
      )}
    </div>
  )
}

/** Phase 10 — Engagement fields fixed for the engagement (not dated). */
function EngagementFields({
  studentId, studyIntention, incomingExchange, canEdit,
}: { studentId: string; studyIntention?: string | null; incomingExchange?: boolean | null; canEdit: boolean }) {
  const { toast } = useToast()
  const qc = useQueryClient()
  const save = useMutation({
    mutationFn: (body: { studyIntention?: string | null; incomingExchange?: boolean | null }) =>
      api.patch(`/students/${studentId}`, body),
    onSuccess: () => invalidateStudent(qc, studentId),
  })
  const [intention, setIntention] = useState(studyIntention ?? '')
  useEffect(() => { setIntention(studyIntention ?? '') }, [studyIntention])
  const err = (e: unknown) => toast({ title: 'Could not save', description: (e as Error).message, variant: 'destructive' })

  return (
    <div className="flex flex-wrap items-end gap-4 pt-1">
      <div className="flex flex-col gap-1">
        <label htmlFor={`si-${studentId}`} className="text-label">Study intention</label>
        <Input id={`si-${studentId}`} className="h-8 w-48" maxLength={40} disabled={!canEdit}
          placeholder="e.g. doctorate" value={intention} onChange={(e) => setIntention(e.target.value)}
          onBlur={async () => {
            const v = intention.trim()
            if (v === (studyIntention ?? '')) return
            try { await save.mutateAsync({ studyIntention: v || null }) } catch (e) { err(e) }
          }} />
      </div>
      <label className="flex items-center gap-1.5 text-sm pb-1.5">
        <input type="checkbox" disabled={!canEdit || save.isPending} checked={!!incomingExchange}
          onChange={async (e) => {
            try { await save.mutateAsync({ incomingExchange: e.target.checked }) } catch (er) { err(er) }
          }} />
        Incoming exchange student
      </label>
    </div>
  )
}

export function DatedFactsSection({
  studentId, feeStatus, studyLocation, uoa, uoaId,
  feeEligibility, primarilyOutsideUk, studyIntention, incomingExchange,
}: {
  studentId: string; feeStatus?: string | null; studyLocation?: string | null
  uoa?: string | null; uoaId?: string | null
  feeEligibility?: string | null; primarilyOutsideUk?: boolean | null
  studyIntention?: string | null; incomingExchange?: boolean | null
}) {
  const { hasPermission } = useAuth()
  const canEdit = hasPermission('student.write')
  const uoas = useUoas()
  const uoaOptions = (uoas.data ?? []).filter((u) => u.isActive).map((u) => ({ value: u.id, label: `${u.code} ${u.name}` }))
  const outsideUk = primarilyOutsideUk == null ? null : primarilyOutsideUk ? 'yes' : 'no'

  return (
    <PageSection icon={CalendarClock} title="Engagement and dated facts"
      description="Dated: a change is recorded from the day it took effect; earlier values stay in Dated history.">
      <div className="space-y-2">
        <FactRow studentId={studentId} fact="fee-status" label="Fee status" current={feeStatus}
          options={FEE_STATUSES} canEdit={canEdit} />
        <FactRow studentId={studentId} fact="fee-eligibility" label="Fee eligibility" current={feeEligibility}
          options={FEE_ELIGIBILITIES} canEdit={canEdit} />
        <FactRow studentId={studentId} fact="study-location" label="Location of study" current={studyLocation}
          placeholder="Location code" canEdit={canEdit} />
        <FactRow studentId={studentId} fact="outside-uk" label="Studying primarily outside the UK" current={outsideUk}
          currentValue={primarilyOutsideUk == null ? null : String(primarilyOutsideUk)} options={YES_NO} canEdit={canEdit} />
        <FactRow studentId={studentId} fact="uoa" label="Unit of assessment" current={uoa}
          currentValue={uoaId ?? null} options={uoaOptions} canEdit={canEdit} />
        <EngagementFields studentId={studentId} studyIntention={studyIntention}
          incomingExchange={incomingExchange} canEdit={canEdit} />
      </div>
    </PageSection>
  )
}
