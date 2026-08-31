'use client'

/** ICR Overview — the cohort on the ICR pathways, read live from /icr/overview. */

import Link from 'next/link'
import { Landmark, GitFork, Wallet, TrendingUp } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/common/ErrorState'
import { useIcrOverview } from '@/features/icr/api'

function Tile({ label, value, hint, tone }: {
  label: string; value: string | number; hint?: string
  tone?: 'default' | 'warning' | 'danger' | 'success'
}) {
  const ring =
    tone === 'danger' ? 'border-[hsl(var(--destructive)/0.4)] bg-[hsl(var(--destructive)/0.05)]'
    : tone === 'warning' ? 'border-[hsl(var(--warning)/0.4)] bg-[hsl(var(--warning)/0.06)]'
    : tone === 'success' ? 'border-[hsl(var(--success)/0.4)] bg-[hsl(var(--success)/0.06)]'
    : 'border-border bg-surface-2'
  return (
    <div className={`rounded-md border px-3 py-2.5 ${ring}`}>
      <p className="text-label">{label}</p>
      <p className="text-2xl font-semibold num mt-0.5">{value}</p>
      {hint && <p className="text-xs text-muted-foreground mt-0.5">{hint}</p>}
    </div>
  )
}

export default function IcrOverviewPage() {
  const { data, isLoading, isError, error } = useIcrOverview()

  return (
    <>
      <PageHeader
        title="ICR — overview"
        description="The Institute of Cancer Research cohort: pathways, the upgrade gate, and the funding pillars."
      />
      <div className="px-6 pb-6 space-y-4">
        {isError && <ErrorState error={error} />}

        <PageSection icon={Landmark} title="The ICR cohort" accent="primary"
          description="Students registered on an ICR pathway right now.">
          {isLoading ? <Skeleton className="h-20 w-full" /> : (
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              <Tile label="Live cohort" value={data?.cohort ?? '—'} hint={`${data?.allTime ?? 0} all time`} />
              <Tile label="Upgraded to PhD" value={data?.transferViva.upgraded ?? '—'}
                hint="passed the transfer viva" tone="success" />
              <Tile label="Provisional MPhil" value={
                (data?.pathways.find((p) => !p.clinical)?.provisional) ?? '—'}
                hint="awaiting the upgrade gate" />
              <Tile label="Near submission limit" value={data?.nearSubmissionLimit ?? '—'}
                hint="within 6 months of the hard limit"
                tone={(data?.nearSubmissionLimit ?? 0) > 0 ? 'warning' : 'default'} />
            </div>
          )}
        </PageSection>

        <PageSection icon={TrendingUp} title="Transfer viva pipeline" accent="accent"
          description="The MPhil → PhD upgrade gate — the most crucial filter in the ICR model."
          actions={
            <Link href="/icr/transfer-viva" className="text-sm text-primary hover:underline">
              Open the tracker →
            </Link>
          }>
          {isLoading ? <Skeleton className="h-20 w-full" /> : (
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              <Tile label="Overdue" value={data?.transferViva.overdue ?? '—'}
                hint="past the 12–14 month window"
                tone={(data?.transferViva.overdue ?? 0) > 0 ? 'danger' : 'default'} />
              <Tile label="Due within 90 days" value={data?.transferViva.dueSoon ?? '—'}
                hint="upgrade report due"
                tone={(data?.transferViva.dueSoon ?? 0) > 0 ? 'warning' : 'default'} />
              <Tile label="Scheduled" value={data?.transferViva.awaiting ?? '—'} hint="still in year one" />
              <Tile label="Upgraded" value={data?.transferViva.upgraded ?? '—'}
                hint="registration now PhD" tone="success" />
            </div>
          )}
        </PageSection>

        <PageSection icon={GitFork} title="Dual pathways" accent="primary"
          description="Non-clinical PhD and clinical MD(Res) run on separate clocks."
          actions={
            <Link href="/icr/pathways" className="text-sm text-primary hover:underline">
              Open the cohort →
            </Link>
          }>
          {isLoading ? <Skeleton className="h-16 w-full" /> : (
            <div className="grid gap-3 md:grid-cols-2">
              {data?.pathways.map((p) => (
                <div key={p.code} className="card-elevated p-4">
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-medium text-sm">{p.label}</p>
                    <Badge variant={p.clinical ? 'info' : 'secondary'}>
                      {p.durationMonths}-month limit
                    </Badge>
                  </div>
                  <p className="text-helper mt-1">{p.detail}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
                    <span className="num font-semibold text-lg">{p.students}</span>
                    <span className="text-muted-foreground">students</span>
                    {!p.clinical && (
                      <>
                        <Badge variant="success">{p.upgraded} upgraded</Badge>
                        <Badge variant="secondary">{p.provisional} provisional MPhil</Badge>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </PageSection>

        <PageSection icon={Wallet} title="Funding pillars" accent="accent"
          description="Which funders pay for the ICR cohort."
          actions={
            <Link href="/icr/funding" className="text-sm text-primary hover:underline">
              Open funding →
            </Link>
          }>
          {isLoading ? <Skeleton className="h-16 w-full" /> : (
            data && data.funders.length > 0 ? (
              <div className="space-y-1.5">
                {data.funders.map((f) => (
                  <div key={f.name} className="flex items-center justify-between border-b border-border/60 last:border-0 py-1.5">
                    <span className="text-sm">{f.name}</span>
                    <div className="flex items-center gap-2">
                      {f.funderType && <Badge variant="outline">{f.funderType.replace(/_/g, ' ')}</Badge>}
                      <span className="text-sm num text-muted-foreground">{f.students} students</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : <p className="text-helper">No ICR funding arrangements yet.</p>
          )}
        </PageSection>
      </div>
    </>
  )
}
