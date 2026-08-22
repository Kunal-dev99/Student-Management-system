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
import { useApproveWaiver, useCreateWaiver, useFeeWaivers, type WaiverKind } from './api'

const KINDS: WaiverKind[] = ['full_fee', 'partial_fee', 'bench_fee']

export function FeeWaiversSection({ studentId }: { studentId: string }) {
  const { toast } = useToast()
  const waivers = useFeeWaivers(studentId)
  const create = useCreateWaiver(studentId)
  const approve = useApproveWaiver(studentId)

  const [kind, setKind] = useState<WaiverKind>('full_fee')
  const [amount, setAmount] = useState('')
  const [percentage, setPercentage] = useState('')
  const [academicYear, setAcademicYear] = useState('')
  const [note, setNote] = useState('')

  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as Error).message, variant: 'destructive' })

  return (
    <div className="pt-3 border-t border-border">
      <div className="text-sm font-medium mb-2">Fee waivers</div>
      {waivers.isLoading ? <Skeleton className="h-12 w-full" /> : (
        <div className="space-y-2 mb-3">
          {waivers.data && waivers.data.length > 0 ? waivers.data.map((w) => (
            <div key={w.id} className="flex items-center justify-between border-b border-border/60 last:border-0 pb-2 last:pb-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-medium">{w.kind.replace(/_/g, ' ')}</span>
                <span className="text-sm num">
                  {w.amount ? `${w.currency ?? ''} ${Number(w.amount).toLocaleString()}`.trim() : ''}
                  {w.percentage != null ? `${w.amount ? ' · ' : ''}${w.percentage}%` : ''}
                  {!w.amount && w.percentage == null ? '—' : ''}
                </span>
                {w.academicYear && <span className="text-helper num">{w.academicYear}</span>}
                {w.approved ? <Badge variant="success">approved</Badge> : <Badge variant="warning">pending</Badge>}
                {w.note && <span className="text-helper">{w.note}</span>}
              </div>
              {!w.approved && (
                <Button size="sm" variant="ghost" disabled={approve.isPending}
                  onClick={async () => { try { await approve.mutateAsync(w.id); toast({ title: 'Fee waiver approved' }) } catch (e) { err(e) } }}>
                  Approve
                </Button>
              )}
            </div>
          )) : <p className="text-helper">No fee waivers recorded.</p>}
        </div>
      )}
      <div className="flex flex-wrap items-end gap-2">
        <Select value={kind} onValueChange={(v) => setKind(v as WaiverKind)}>
          <SelectTrigger className="w-40 h-8"><SelectValue /></SelectTrigger>
          <SelectContent>
            {KINDS.map((k) => <SelectItem key={k} value={k}>{k.replace(/_/g, ' ')}</SelectItem>)}
          </SelectContent>
        </Select>
        <Input type="number" className="w-32 h-8" placeholder="Amount" value={amount}
          onChange={(e) => setAmount(e.target.value)} />
        <Input type="number" className="w-28 h-8" placeholder="%" value={percentage}
          onChange={(e) => setPercentage(e.target.value)} />
        <Input className="w-32 h-8" placeholder="2025/26" value={academicYear}
          onChange={(e) => setAcademicYear(e.target.value)} />
        <Input className="w-44 h-8" placeholder="Note" value={note} onChange={(e) => setNote(e.target.value)} />
        <Button size="sm" disabled={create.isPending}
          onClick={async () => {
            try {
              await create.mutateAsync({
                kind,
                amount: amount || undefined,
                percentage: percentage ? Number(percentage) : undefined,
                currency: amount ? 'GBP' : undefined,
                academicYear: academicYear || undefined,
                note: note || undefined,
              })
              toast({ title: 'Fee waiver recorded' })
              setAmount(''); setPercentage(''); setAcademicYear(''); setNote('')
            } catch (e) { err(e) }
          }}>
          Add waiver
        </Button>
      </div>
    </div>
  )
}
