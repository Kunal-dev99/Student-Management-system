'use client'

/**
 * W4 — Finance lens on the funding-integrity page.
 * Cashflow-first cut of stipend payments: totals in window, plus three actionable lists
 * (Finance-held, approved-but-overdue, paid without a Finance reference).
 */

import Link from 'next/link'
import { AlertOctagon, ArrowUpRight, Banknote, Clock, FileWarning } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { PageSection } from '@/components/common/PageSection'
import { ErrorState } from '@/components/common/ErrorState'
import { useFundingCashflow, type FinancePaymentRow } from '@/features/funding/api'

function money(v: string, currency: string | null | undefined) {
  const n = Number(v)
  if (Number.isNaN(n)) return v
  return `${(currency ?? 'GBP')} ${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function Tile({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: 'error' | 'warning' | 'success' }) {
  const toneClass =
    tone === 'error' ? 'text-[hsl(var(--destructive))]'
      : tone === 'warning' ? 'text-[hsl(var(--warning))]'
        : tone === 'success' ? 'text-[hsl(var(--success))]'
          : 'text-foreground'
  return (
    <div className="card-elevated rounded-md border border-border bg-surface-2 px-4 py-3">
      <p className="text-label">{label}</p>
      <p className={`text-lg num font-semibold mt-1 ${toneClass}`}>{value}</p>
      {sub ? <p className="text-helper mt-0.5">{sub}</p> : null}
    </div>
  )
}

function PersonCell({ row }: { row: FinancePaymentRow }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Link href={row.link} className="text-sm font-medium text-primary hover:underline inline-flex items-center gap-1">
        {row.personName}
        <ArrowUpRight className="h-3.5 w-3.5" />
      </Link>
      <span className="font-mono text-xs text-muted-foreground">{row.studentRef}</span>
    </div>
  )
}

export function FinanceLensPanel() {
  const { data, isLoading, isError, error } = useFundingCashflow()

  if (isLoading) return <Skeleton className="h-40 w-full" />
  if (isError) return <ErrorState error={error} />
  if (!data) return null

  const currency = data.byFundingType[0]?.paid ? 'GBP' : 'GBP'
  const window = `${data.window.from} → ${data.window.to}`

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Tile label="Paid (window)" value={money(data.totals.paid, currency)} sub={window} tone="success" />
        <Tile label="Approved (window)" value={money(data.totals.approved, currency)} />
        <Tile label="Scheduled (window)" value={money(data.totals.scheduled, currency)} />
        <Tile label="Held" value={money(data.totals.held, currency)} tone="error" />
        <Tile label="Payments in window" value={String(data.paymentsInWindow)} />
      </div>

      <PageSection
        icon={AlertOctagon}
        title={`Finance held ${data.counts.held ? `(${data.counts.held})` : ''}`}
        accent={data.counts.held ? 'danger' : 'primary'}
        attention={data.counts.held > 0}
        description="Payments Finance rejected. The note carries the reason so someone can triage."
      >
        {data.held.length === 0 ? <p className="text-helper">Nothing held.</p> : (
          <ul className="space-y-2">
            {data.held.map((r) => (
              <li key={r.paymentId} className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 last:border-0 pb-2 last:pb-0">
                <div className="space-y-0.5">
                  <PersonCell row={r} />
                  {r.note ? <p className="text-helper">{r.note}</p> : null}
                </div>
                <div className="text-right">
                  <p className="text-sm num font-medium">{money(r.amount, r.currency)}</p>
                  <p className="text-helper num">due {r.dueDate ?? '—'}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </PageSection>

      <PageSection
        icon={Clock}
        title={`Approved but overdue ${data.counts.overdueApproved ? `(${data.counts.overdueApproved})` : ''}`}
        accent={data.counts.overdueApproved ? 'warning' : 'primary'}
        attention={data.counts.overdueApproved > 0}
        description="Approved by us, not yet paid by Finance — chase up with the finance reference or expedite."
      >
        {data.overdueApproved.length === 0 ? <p className="text-helper">Nothing overdue.</p> : (
          <ul className="space-y-2">
            {data.overdueApproved.map((r) => (
              <li key={r.paymentId} className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 last:border-0 pb-2 last:pb-0">
                <div className="space-y-0.5">
                  <PersonCell row={r} />
                  <Badge variant="warning">{r.daysOverdue} days overdue</Badge>
                </div>
                <div className="text-right">
                  <p className="text-sm num font-medium">{money(r.amount, r.currency)}</p>
                  <p className="text-helper num">due {r.dueDate}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </PageSection>

      <PageSection
        icon={FileWarning}
        title={`Paid without a Finance reference ${data.counts.paidWithoutFinanceReference ? `(${data.counts.paidWithoutFinanceReference})` : ''}`}
        accent={data.counts.paidWithoutFinanceReference ? 'warning' : 'primary'}
        description="Reconciliation drift — the row is paid on our side but nothing ties it back to a Finance transaction."
      >
        {data.paidWithoutFinanceReference.length === 0 ? <p className="text-helper">Nothing drifting.</p> : (
          <ul className="space-y-2">
            {data.paidWithoutFinanceReference.map((r) => (
              <li key={r.paymentId} className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 last:border-0 pb-2 last:pb-0">
                <div className="space-y-0.5">
                  <PersonCell row={r} />
                  <p className="text-helper num">paid {r.paidOn ?? '—'}</p>
                </div>
                <div className="text-right">
                  <p className="text-sm num font-medium">{money(r.amount, r.currency)}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </PageSection>

      <PageSection icon={Banknote} title="By funding type" accent="primary">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {data.byFundingType.map((row) => (
            <div key={row.fundingType} className="flex items-center justify-between border border-border rounded-md px-3 py-2">
              <span className="text-sm font-medium">{row.fundingType.replace(/_/g, ' ')}</span>
              <div className="text-right">
                <p className="text-sm num">Paid {money(row.paid, 'GBP')} · Outstanding {money(row.outstanding, 'GBP')}</p>
                <p className="text-helper num">{row.count} payment{row.count === 1 ? '' : 's'}</p>
              </div>
            </div>
          ))}
          {data.byFundingType.length === 0 ? <p className="text-helper">No payments in window.</p> : null}
        </div>
      </PageSection>
    </div>
  )
}
