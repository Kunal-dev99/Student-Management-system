'use client'

/**
 * Payment Status — institution-wide visibility into every stipend/bursary instalment,
 * from the moment it's scheduled here through to Finance confirming it paid.
 *
 * This platform never moves money itself (Finance owns payment — see funding/models.py's
 * own docstring). What this page gives instead is the full paper trail: the instalment's
 * status (scheduled -> approved -> paid, or held/cancelled), plus — on drill-down — every
 * integration_log entry recorded against it, which is the actual evidence of when Finance
 * was told about it and when they confirmed or rejected it.
 *
 * Admins with funding.change can act from here too — approve a scheduled instalment, record
 * that Finance actually paid one, or put one on hold — the same mutations already used on a
 * student's own Funding panel, just reachable without navigating to that student first.
 */
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { ExternalLink } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { SearchInput } from '@/components/common/SearchInput'
import { FilterChips } from '@/components/common/FilterChips'
import { Pagination } from '@/components/common/Pagination'
import { Badge, type BadgeProps } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import { useToast } from '@/components/ui/use-toast'
import { useCan } from '@/shared/auth/Can'
import {
  usePaymentsList, usePayment, usePaymentTrail, useApprovePayment, useMarkPaymentPaid, useSetPaymentStatus,
  type PaymentStatus, type PaymentTrailEntry,
} from '@/features/funding/api'

const PAGE_SIZE = 50

const STATUS_FILTERS: { value: PaymentStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'scheduled', label: 'Scheduled' },
  { value: 'approved', label: 'Approved' },
  { value: 'paid', label: 'Paid' },
  { value: 'held', label: 'Held' },
  { value: 'cancelled', label: 'Cancelled' },
]

const STATUS_TONE: Record<PaymentStatus, BadgeProps['variant']> = {
  scheduled: 'secondary',
  approved: 'info',
  paid: 'success',
  held: 'warning',
  cancelled: 'destructive',
}

// The instalment's own status IS the lifecycle stage — this just spells out what each
// value means in plain English, since "held" and "cancelled" aren't self-explanatory.
const STATUS_STEP: Record<PaymentStatus, string> = {
  scheduled: '1. Scheduled here — not yet approved',
  approved: '2. Approved — ready for Finance to pay',
  paid: '4. Finance confirmed paid',
  held: 'Finance rejected — needs triage',
  cancelled: 'Cancelled — will not be paid',
}

const EVENT_LABEL: Record<string, string> = {
  'funding.changed': 'Sent to Finance',
  'payment.confirmed': 'Finance confirmed paid',
  'payment.rejected': 'Finance rejected',
}

// "funding.changed" covers both "approved, ready to pay" and "paid" outbound notices —
// the inner event on the emitted payload (approve_payment()/mark_paid() in funding/service.py)
// disambiguates which one this actually was.
function trailEventLabel(t: PaymentTrailEntry): string {
  if (t.eventType === 'funding.changed') {
    const inner = (t.detail?.reference as Record<string, unknown> | undefined)?.event
    if (inner === 'stipend_approved') return 'Approved — sent to Finance'
    if (inner === 'stipend_paid') return 'Paid — confirmation sent to Finance'
  }
  return EVENT_LABEL[t.eventType] ?? t.eventType
}

function TrailDrawer({ paymentId, onOpenChange }: { paymentId: string | null; onOpenChange: (o: boolean) => void }) {
  const { toast } = useToast()
  const canChange = useCan('funding.change')
  // Fetched by id, independent of whatever filter/search/page the list behind it is on —
  // so approving/marking-paid/holding refreshes this drawer even if the action just moved
  // the row out of the currently-active status filter.
  const { data: payment } = usePayment(paymentId)
  const trail = usePaymentTrail(paymentId)

  // Hooks must run unconditionally — studentId/arrangementId only matter for the query
  // keys these mutations invalidate on success, so an empty fallback is harmless while
  // the drawer is closed.
  const approve = useApprovePayment(payment?.studentId ?? '', payment?.arrangementId ?? '')
  const markPaid = useMarkPaymentPaid(payment?.studentId ?? '', payment?.arrangementId ?? '')
  const setStatus = useSetPaymentStatus(payment?.studentId ?? '', payment?.arrangementId ?? '')

  const [showPaidForm, setShowPaidForm] = useState(false)
  const [showHoldForm, setShowHoldForm] = useState(false)
  const [paidOn, setPaidOn] = useState('')
  const [financeReference, setFinanceReference] = useState('')
  const [holdNote, setHoldNote] = useState('')

  // Reset local UI state whenever the open payment changes — including switching straight
  // from one row to another without an explicit close in between, which the onOpenChange
  // cleanup alone doesn't catch and previously left a stale "mark paid" form showing for a
  // payment that was never approved.
  useEffect(() => {
    setShowPaidForm(false); setShowHoldForm(false)
    setPaidOn(''); setFinanceReference(''); setHoldNote('')
  }, [paymentId])

  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as Error).message, variant: 'destructive' })

  return (
    <Sheet open={paymentId !== null} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-lg overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{payment?.personName} — instalment {payment?.sequence}</SheetTitle>
          <SheetDescription>
            {payment?.studentRef} · {payment?.currency} {payment?.amount} · due {payment?.dueDate}
          </SheetDescription>
        </SheetHeader>

        {payment && (
          <div className="mt-4 space-y-4">
            <div className="rounded-md border bg-muted/30 px-3 py-2">
              <p className="text-xs text-muted-foreground mb-1">Current status</p>
              <div className="flex items-center gap-2">
                <Badge variant={STATUS_TONE[payment.status]}>{payment.status}</Badge>
                <span className="text-sm text-muted-foreground">{STATUS_STEP[payment.status]}</span>
              </div>
              {payment.paidOn && (
                <p className="text-xs text-muted-foreground mt-1">Paid on {payment.paidOn}</p>
              )}
              {payment.financeReference && (
                <p className="text-xs text-muted-foreground">Finance reference: {payment.financeReference}</p>
              )}
              {payment.note && (
                <p className="text-xs text-muted-foreground mt-1">Note: {payment.note}</p>
              )}
            </div>

            {canChange && payment.status !== 'paid' && payment.status !== 'cancelled' && (
              <div className="space-y-2">
                <p className="text-sm font-medium">Actions</p>
                <div className="flex flex-wrap gap-2">
                  {payment.status === 'scheduled' && (
                    <Button size="sm" disabled={approve.isPending}
                      onClick={() => approve.mutate(payment.id, {
                        onSuccess: () => toast({ title: 'Approved — sent to Finance' }), onError: err,
                      })}>
                      {approve.isPending ? 'Approving…' : 'Approve'}
                    </Button>
                  )}
                  {payment.status === 'approved' && !showPaidForm && (
                    <Button size="sm" onClick={() => { setShowPaidForm(true); setPaidOn(new Date().toISOString().slice(0, 10)) }}>
                      Mark paid
                    </Button>
                  )}
                  {!showHoldForm && (
                    <Button size="sm" variant="outline" onClick={() => setShowHoldForm(true)}>
                      Put on hold
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" className="text-destructive" disabled={setStatus.isPending}
                    onClick={() => setStatus.mutate({ paymentId: payment.id, status: 'cancelled' }, {
                      onSuccess: () => toast({ title: 'Instalment cancelled' }), onError: err,
                    })}>
                    Cancel instalment
                  </Button>
                </div>

                {showPaidForm && payment.status === 'approved' && (
                  <div className="rounded-md border p-3 space-y-2">
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <Label htmlFor="paid-on" className="text-xs">Paid on</Label>
                        <Input id="paid-on" type="date" className="h-8" value={paidOn}
                          onChange={(e) => setPaidOn(e.target.value)} />
                      </div>
                      <div>
                        <Label htmlFor="fin-ref" className="text-xs">Finance reference</Label>
                        <Input id="fin-ref" className="h-8" placeholder="FIN-123456" value={financeReference}
                          onChange={(e) => setFinanceReference(e.target.value)} />
                      </div>
                    </div>
                    <div className="flex justify-end gap-2">
                      <Button size="sm" variant="ghost" onClick={() => setShowPaidForm(false)}>Cancel</Button>
                      <Button size="sm" disabled={markPaid.isPending}
                        onClick={() => markPaid.mutate({ paymentId: payment.id, paidOn, financeReference: financeReference || undefined }, {
                          onSuccess: () => { setShowPaidForm(false); toast({ title: 'Marked paid' }) }, onError: err,
                        })}>
                        {markPaid.isPending ? 'Saving…' : 'Confirm paid'}
                      </Button>
                    </div>
                  </div>
                )}

                {showHoldForm && (
                  <div className="rounded-md border p-3 space-y-2">
                    <Label htmlFor="hold-note" className="text-xs">Reason (recorded on the instalment)</Label>
                    <Input id="hold-note" className="h-8" placeholder="e.g. Cost centre closed for this period"
                      value={holdNote} onChange={(e) => setHoldNote(e.target.value)} />
                    <div className="flex justify-end gap-2">
                      <Button size="sm" variant="ghost" onClick={() => setShowHoldForm(false)}>Cancel</Button>
                      <Button size="sm" variant="outline" disabled={setStatus.isPending}
                        onClick={() => setStatus.mutate({ paymentId: payment.id, status: 'held', note: holdNote || undefined }, {
                          onSuccess: () => { setShowHoldForm(false); toast({ title: 'Put on hold' }) }, onError: err,
                        })}>
                        {setStatus.isPending ? 'Saving…' : 'Confirm hold'}
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}

            <div>
              <p className="text-sm font-medium mb-2">Finance trail</p>
              {trail.isLoading ? (
                <Skeleton className="h-16 w-full" />
              ) : !trail.data || trail.data.length === 0 ? (
                <p className="text-sm text-muted-foreground rounded-md border border-dashed px-3 py-3">
                  Nothing sent to or received from Finance yet for this instalment. It stays
                  a local record — scheduled, and if approved, ready to be picked up — until
                  Finance actually confirms or rejects it here.
                </p>
              ) : (
                <ol className="space-y-2">
                  {trail.data.map((t) => (
                    <li key={t.id} className="flex items-start gap-3 rounded-md border p-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 text-sm">
                          <Badge variant={t.direction === 'inbound' ? 'info' : 'secondary'}>
                            {t.direction === 'inbound' ? 'From Finance' : 'To Finance'}
                          </Badge>
                          <span className="font-medium">{trailEventLabel(t)}</span>
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">
                          {new Date(t.createdAt).toLocaleString()} ·{' '}
                          <span className={t.status === 'failed' ? 'text-destructive' : ''}>{t.status}</span>
                        </p>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </div>

            <Link href={`/students/${payment.studentId}`}
                  className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
              Open student record <ExternalLink className="h-3.5 w-3.5" />
            </Link>
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}

export default function PaymentStatusPage() {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<PaymentStatus | 'all'>('all')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [offset, setOffset] = useState(0)
  const [openPaymentId, setOpenPaymentId] = useState<string | null>(null)

  const resetPage = () => setOffset(0)

  const { data, isLoading, isError, error } = usePaymentsList({
    search, status, fromDate: fromDate || undefined, toDate: toDate || undefined,
    limit: PAGE_SIZE, offset,
  })

  return (
    <>
      <PageHeader
        title="Payment Status"
        description="Every stipend and bursary instalment, from scheduling here through to Finance confirming it paid."
      />
      <div className="px-6 pb-6 space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <SearchInput
            value={search}
            onChange={(v) => { setSearch(v); resetPage() }}
            placeholder="Search by student name or ref…"
          />
          <div className="flex flex-wrap items-end gap-2">
            <Input type="date" aria-label="From date" className="w-40 h-9"
              value={fromDate} onChange={(e) => { setFromDate(e.target.value); resetPage() }} />
            <span className="text-helper mb-2">to</span>
            <Input type="date" aria-label="To date" className="w-40 h-9"
              value={toDate} onChange={(e) => { setToDate(e.target.value); resetPage() }} />
          </div>
        </div>

        <FilterChips
          label="Status:"
          options={STATUS_FILTERS}
          value={status}
          onChange={(v) => { setStatus(v); resetPage() }}
        />

        <div className="card-elevated overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Student</TableHead>
                <TableHead>Funding</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead>Due</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Paid on</TableHead>
                <TableHead>Finance ref</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && (
                <TableRow><TableCell colSpan={7}><Skeleton className="h-5 w-full" /></TableCell></TableRow>
              )}
              {isError && (
                <TableRow><TableCell colSpan={7} className="text-[hsl(var(--destructive))]">
                  {(error as Error)?.message}
                </TableCell></TableRow>
              )}
              {data?.data.map((p) => (
                <TableRow key={p.id} className="cursor-pointer" onClick={() => setOpenPaymentId(p.id)}>
                  <TableCell className="font-medium">
                    {p.personName}
                    <span className="block text-xs text-muted-foreground num">{p.studentRef}</span>
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">{p.fundingType.replace(/_/g, ' ')}</TableCell>
                  <TableCell className="text-right num">{p.currency} {p.amount}</TableCell>
                  <TableCell className="text-muted-foreground num">{p.dueDate}</TableCell>
                  <TableCell><Badge variant={STATUS_TONE[p.status]}>{p.status}</Badge></TableCell>
                  <TableCell className="text-muted-foreground num">{p.paidOn ?? '—'}</TableCell>
                  <TableCell className="text-muted-foreground font-mono text-xs">{p.financeReference ?? '—'}</TableCell>
                </TableRow>
              ))}
              {data && data.data.length === 0 && (
                <TableRow><TableCell colSpan={7} className="text-muted-foreground text-center py-8">
                  No instalments match this search/filter.
                </TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </div>

        <Pagination offset={offset} limit={PAGE_SIZE} total={data?.page.total} onOffsetChange={setOffset} />
      </div>

      <TrailDrawer paymentId={openPaymentId} onOpenChange={(o) => !o && setOpenPaymentId(null)} />
    </>
  )
}
