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
 */
import { useState } from 'react'
import Link from 'next/link'
import { ExternalLink } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { SearchInput } from '@/components/common/SearchInput'
import { FilterChips } from '@/components/common/FilterChips'
import { Pagination } from '@/components/common/Pagination'
import { Badge, type BadgeProps } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import {
  usePaymentsList, usePaymentTrail, type PaymentStatus, type PaymentStatusRow,
  type PaymentTrailEntry,
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

function TrailDrawer({ payment, onOpenChange }: { payment: PaymentStatusRow | null; onOpenChange: (o: boolean) => void }) {
  const trail = usePaymentTrail(payment?.id ?? null)
  return (
    <Sheet open={payment !== null} onOpenChange={onOpenChange}>
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
  const [openPayment, setOpenPayment] = useState<PaymentStatusRow | null>(null)

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
                <TableRow key={p.id} className="cursor-pointer" onClick={() => setOpenPayment(p)}>
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

      <TrailDrawer payment={openPayment} onOpenChange={(o) => !o && setOpenPayment(null)} />
    </>
  )
}
