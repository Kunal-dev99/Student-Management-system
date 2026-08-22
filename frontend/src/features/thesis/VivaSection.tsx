'use client'

import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import {
  useApproveCorrections, useCorrections, useScheduleViva, useSubmitCorrections,
  type Examination, type VivaFormat,
} from './api'

const FORMATS: VivaFormat[] = ['in_person', 'online', 'hybrid']

export function VivaSection({
  studentId, thesisId, examination,
}: { studentId: string; thesisId: string; examination: Examination | null }) {
  const { toast } = useToast()
  const corrections = useCorrections(thesisId)
  const schedule = useScheduleViva(studentId, thesisId)
  const submitCorr = useSubmitCorrections(studentId, thesisId)
  const approveCorr = useApproveCorrections(studentId, thesisId)

  const [vivaDate, setVivaDate] = useState('')
  const [format, setFormat] = useState<VivaFormat>('in_person')
  const [location, setLocation] = useState('')

  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as Error).message, variant: 'destructive' })
  const scheduled = !!examination?.vivaDate

  return (
    <div className="pt-3 border-t border-border space-y-3">
      <div>
        <div className="flex items-center gap-2 mb-2">
          <span className="text-sm font-medium">Viva</span>
          {scheduled
            ? <Badge variant="info">scheduled {examination?.vivaDate}</Badge>
            : <Badge variant="secondary">not scheduled</Badge>}
          {examination?.vivaFormat && <Badge variant="outline">{examination.vivaFormat.replace(/_/g, ' ')}</Badge>}
        </div>
        {scheduled && (
          <p className="text-helper mb-2">
            {examination?.vivaLocation || 'No location recorded'}
            {examination?.vivaScheduledAt ? ` · booked ${examination.vivaScheduledAt.replace('T', ' ').slice(0, 16)}` : ''}
          </p>
        )}
        <div className="flex flex-wrap items-end gap-2">
          <Input type="date" className="w-40 h-8" value={vivaDate} onChange={(e) => setVivaDate(e.target.value)} />
          <Select value={format} onValueChange={(v) => setFormat(v as VivaFormat)}>
            <SelectTrigger className="w-36 h-8"><SelectValue /></SelectTrigger>
            <SelectContent>
              {FORMATS.map((f) => <SelectItem key={f} value={f}>{f.replace(/_/g, ' ')}</SelectItem>)}
            </SelectContent>
          </Select>
          <Input className="w-52 h-8" placeholder="Location / joining link" value={location}
            onChange={(e) => setLocation(e.target.value)} />
          <Button size="sm" disabled={!vivaDate || schedule.isPending}
            onClick={async () => {
              try {
                await schedule.mutateAsync({ vivaDate, vivaFormat: format, location: location || undefined })
                toast({ title: scheduled ? 'Viva rescheduled' : 'Viva scheduled' })
                setVivaDate(''); setLocation('')
              } catch (e) { err(e) }
            }}>
            {scheduled ? 'Reschedule viva' : 'Schedule viva'}
          </Button>
          <span className="text-helper">An approved examiner is required before a viva can be booked.</span>
        </div>
      </div>

      {corrections.isLoading ? <Skeleton className="h-10 w-full" /> : (
        corrections.data && corrections.data.length > 0 && (
          <div>
            <div className="text-sm font-medium mb-2">Corrections</div>
            <div className="space-y-2">
              {corrections.data.map((c) => (
                <div key={c.id} className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 last:border-0 pb-2 last:pb-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge variant={c.kind === 'major' ? 'warning' : 'info'}>{c.kind} corrections</Badge>
                    <span className="text-helper num">deadline {c.deadline ?? '—'}</span>
                    {c.submittedAt && <Badge variant="secondary">submitted {c.submittedAt.slice(0, 10)}</Badge>}
                    {c.approvedAt
                      ? <Badge variant="success">signed off {c.approvedAt.slice(0, 10)}</Badge>
                      : <Badge variant="warning">outstanding</Badge>}
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    {!c.submittedAt && (
                      <Button size="sm" variant="secondary" disabled={submitCorr.isPending}
                        onClick={async () => { try { await submitCorr.mutateAsync(); toast({ title: 'Corrections submitted' }) } catch (e) { err(e) } }}>
                        Submit corrections
                      </Button>
                    )}
                    {!c.approvedAt && (
                      <Button size="sm" disabled={approveCorr.isPending}
                        onClick={async () => { try { await approveCorr.mutateAsync(); toast({ title: 'Corrections signed off', description: 'The thesis is now approved.' }) } catch (e) { err(e) } }}>
                        Sign off
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )
      )}
    </div>
  )
}
