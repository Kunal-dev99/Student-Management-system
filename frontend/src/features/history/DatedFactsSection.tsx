'use client'

/** Effective dating, Phase 6 — fee status and study location on the student record. Each is a
 *  dated fact: "Change" records the new value from a date (default today), and the earlier value
 *  stays in the Dated history tab. Empty until first recorded. */

import { useState } from 'react'
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

type FactKey = 'fee-status' | 'study-location' | 'uoa'

const FEE_STATUSES = ['home', 'overseas', 'channel_islands', 'unknown'] as const

function useRecordFact(studentId: string, fact: FactKey) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { value: string; effectiveDate?: string; reason?: string }) =>
      api.post<{ current: string | null }>(`/students/${studentId}/facts/${fact}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['student', studentId] })
      qc.invalidateQueries({ queryKey: ['students'] })
    },
  })
}

function FactRow({
  studentId, fact, label, current, currentValue, canEdit,
}: {
  studentId: string; fact: FactKey; label: string; current: string | null | undefined
  /** The stored value when it differs from what is shown (the UOA id behind "1 Clinical Medicine"). */
  currentValue?: string | null
  canEdit: boolean
}) {
  const { toast } = useToast()
  const record = useRecordFact(studentId, fact)
  const uoas = useUoas()
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
            {fact === 'uoa' ? (
              <Select value={value} onValueChange={setValue}>
                <SelectTrigger className="h-8 w-60"><SelectValue placeholder="Choose…" /></SelectTrigger>
                <SelectContent>
                  {(uoas.data ?? []).filter((u) => u.isActive).map((u) => (
                    <SelectItem key={u.id} value={u.id}>{u.code} {u.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : fact === 'fee-status' ? (
              <Select value={value} onValueChange={setValue}>
                <SelectTrigger className="h-8 w-44"><SelectValue placeholder="Choose…" /></SelectTrigger>
                <SelectContent>
                  {FEE_STATUSES.map((f) => <SelectItem key={f} value={f}>{f.replace(/_/g, ' ')}</SelectItem>)}
                </SelectContent>
              </Select>
            ) : (
              <Input className="h-8 w-44" placeholder="Location code" maxLength={60}
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

export function DatedFactsSection({
  studentId, feeStatus, studyLocation, uoa, uoaId,
}: {
  studentId: string; feeStatus?: string | null; studyLocation?: string | null
  uoa?: string | null; uoaId?: string | null
}) {
  const { hasPermission } = useAuth()
  const canEdit = hasPermission('student.write')
  return (
    <PageSection icon={CalendarClock} title="Fee status, location and UOA"
      description="Dated: a change is recorded from the day it took effect; earlier values stay in Dated history.">
      <div className="space-y-2">
        <FactRow studentId={studentId} fact="fee-status" label="Fee status" current={feeStatus} canEdit={canEdit} />
        <FactRow studentId={studentId} fact="study-location" label="Location of study" current={studyLocation} canEdit={canEdit} />
        <FactRow studentId={studentId} fact="uoa" label="Unit of assessment" current={uoa}
          currentValue={uoaId ?? null} canEdit={canEdit} />
      </div>
    </PageSection>
  )
}
