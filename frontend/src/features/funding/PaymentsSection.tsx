'use client'

import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useToast } from '@/components/ui/use-toast'
import {
  useApprovePayment, useGenerateSchedule, useMarkPaymentPaid, usePayments, useSetPaymentStatus,
  type PaymentFrequency, type PaymentStatus,
} from './api'

const FREQUENCIES: PaymentFrequency[] = ['monthly', 'quarterly', 'termly', 'annual', 'one_off']

const PAYMENT_VARIANT: Record<PaymentStatus, 'secondary' | 'info' | 'success' | 'warning' | 'outline'> = {
  scheduled: 'secondary', approved: 'info', paid: 'success', held: 'warning', cancelled: 'outline',
}

export function PaymentsSection({ studentId, arrangementId }: { studentId: string; arrangementId: string }) {
  const { toast } = useToast()
  const payments = usePayments(arrangementId)
  const generate = useGenerateSchedule(studentId, arrangementId)
  const approve = useApprovePayment(studentId, arrangementId)
  const markPaid = useMarkPaymentPaid(studentId, arrangementId)
  const setStatus = useSetPaymentStatus(studentId, arrangementId)

  const [frequency, setFrequency] = useState<PaymentFrequency>('monthly')
  const [instalments, setInstalments] = useState('')
  const [firstDue, setFirstDue] = useState('')
  const [payingId, setPayingId] = useState<string | null>(null)
  const [financeRef, setFinanceRef] = useState('')

  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as Error).message, variant: 'destructive' })

  return (
    <div className="mt-2 bg-surface-2 rounded-md p-3 space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <span className="text-sm font-medium mr-1">Payment schedule</span>
        <Select value={frequency} onValueChange={(v) => setFrequency(v as PaymentFrequency)}>
          <SelectTrigger className="w-36 h-8"><SelectValue /></SelectTrigger>
          <SelectContent>
            {FREQUENCIES.map((f) => <SelectItem key={f} value={f}>{f.replace(/_/g, ' ')}</SelectItem>)}
          </SelectContent>
        </Select>
        <Input type="number" className="w-32 h-8" placeholder="Instalments" value={instalments}
          onChange={(e) => setInstalments(e.target.value)} />
        <Input type="date" className="w-40 h-8" value={firstDue} onChange={(e) => setFirstDue(e.target.value)}
          title="First due date" />
        <Button size="sm" disabled={generate.isPending}
          onClick={async () => {
            try {
              await generate.mutateAsync({
                frequency,
                instalments: instalments ? Number(instalments) : undefined,
                firstDue: firstDue || undefined,
              })
              toast({ title: 'Payment schedule generated' })
            } catch (e) { err(e) }
          }}>
          Generate schedule
        </Button>
      </div>

      {payments.isLoading ? <Skeleton className="h-16 w-full" /> : (
        payments.data && payments.data.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>#</TableHead>
                <TableHead>Due</TableHead>
                <TableHead>Amount</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Paid on</TableHead>
                <TableHead>Finance ref</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {payments.data.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="num">{p.sequence}</TableCell>
                  <TableCell className="num whitespace-nowrap">{p.dueDate}</TableCell>
                  <TableCell className="num">{`${p.currency ?? ''} ${Number(p.amount).toLocaleString()}`.trim()}</TableCell>
                  <TableCell><Badge variant={PAYMENT_VARIANT[p.status]}>{p.status}</Badge></TableCell>
                  <TableCell className="num whitespace-nowrap">{p.paidOn ?? '—'}</TableCell>
                  <TableCell className="text-sm font-mono">{p.financeReference ?? '—'}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1 flex-wrap">
                      {p.status === 'scheduled' && (
                        <Button size="sm" variant="ghost" disabled={approve.isPending}
                          onClick={async () => { try { await approve.mutateAsync(p.id); toast({ title: 'Instalment approved' }) } catch (e) { err(e) } }}>
                          Approve
                        </Button>
                      )}
                      {(p.status === 'scheduled' || p.status === 'approved') && (
                        payingId === p.id ? (
                          <>
                            <Input className="w-36 h-8" placeholder="Finance reference" value={financeRef}
                              onChange={(e) => setFinanceRef(e.target.value)} />
                            <Button size="sm" disabled={markPaid.isPending}
                              onClick={async () => {
                                try {
                                  await markPaid.mutateAsync({ paymentId: p.id, financeReference: financeRef || undefined })
                                  toast({ title: 'Instalment marked paid' }); setPayingId(null); setFinanceRef('')
                                } catch (e) { err(e) }
                              }}>Confirm</Button>
                            <Button size="sm" variant="ghost" onClick={() => { setPayingId(null); setFinanceRef('') }}>Cancel</Button>
                          </>
                        ) : (
                          <Button size="sm" variant="ghost" onClick={() => { setPayingId(p.id); setFinanceRef('') }}>
                            Mark paid
                          </Button>
                        )
                      )}
                      {(p.status === 'scheduled' || p.status === 'approved') && payingId !== p.id && (
                        <Button size="sm" variant="ghost" disabled={setStatus.isPending}
                          onClick={async () => { try { await setStatus.mutateAsync({ paymentId: p.id, status: 'held' }); toast({ title: 'Instalment held' }) } catch (e) { err(e) } }}>
                          Hold
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : <p className="text-helper">No instalments scheduled for this arrangement.</p>
      )}
    </div>
  )
}
