'use client'

import { Activity, LayoutDashboard, ListChecks } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { useHealth } from '@/shared/hooks/useHealth'
import { useAuth } from '@/shared/auth/AuthContext'
import { useAdministratorDashboard, useExecutiveDashboard } from '@/features/reporting/api'

function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="card-elevated p-4">
      <p className="text-label">{label}</p>
      <p className="mt-1 text-2xl font-semibold tracking-tight num">{value}</p>
      {hint && <p className="text-helper mt-0.5">{hint}</p>}
    </div>
  )
}

export default function DashboardPage() {
  const health = useHealth()
  const { principal } = useAuth()
  const exec = useExecutiveDashboard()
  const admin = useAdministratorDashboard()

  const dbOk = health.data?.checks?.database === 'ok'
  const apiReachable = !health.isError && !!health.data
  const n = (v: number | undefined) => (v == null ? '—' : String(v))
  const e = exec.data

  return (
    <>
      <PageHeader title="Executive dashboard" description="PGR lifecycle at a glance." />
      <div className="px-6 pb-6 space-y-4">
        <PageSection icon={Activity} title="Platform connectivity" accent="primary">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span className="flex items-center gap-2">API
              <Badge variant={apiReachable ? 'success' : 'destructive'}>
                {health.isLoading ? 'checking…' : apiReachable ? 'reachable' : 'unreachable'}
              </Badge>
            </span>
            <span className="flex items-center gap-2">Database
              <Badge variant={dbOk ? 'success' : 'warning'}>{health.isLoading ? 'checking…' : dbOk ? 'ok' : (health.data?.status ?? 'unknown')}</Badge>
            </span>
            <span className="flex items-center gap-2">Signed in as
              <Badge variant={principal?.authenticated ? 'success' : 'secondary'}>{principal?.email ?? 'anonymous'}</Badge>
            </span>
            {principal?.roles?.length ? (
              <span className="flex items-center gap-2">Role <Badge variant="info">{principal.roles.join(', ')}</Badge></span>
            ) : null}
          </div>
        </PageSection>

        <PageSection icon={LayoutDashboard} title="Lifecycle metrics" accent="accent">
          {exec.isLoading ? <Skeleton className="h-20 w-full" /> : (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
              <StatTile label="Active researchers" value={n(e?.activeResearchers)} hint="registered / active" />
              <StatTile label="Applications" value={n(e?.applicationsInPipeline)} hint="in pipeline" />
              <StatTile label="Conversion rate" value={e ? `${e.conversionRatePct}%` : '—'} hint="applicant → student" />
              <StatTile label="Funded students" value={n(e?.fundedStudents)} hint="active arrangement" />
              <StatTile label="Theses submitted" value={n(e?.thesesSubmitted)} hint="awaiting/under exam" />
              <StatTile label="Completions" value={n(e?.completions)} hint="graduated" />
            </div>
          )}
        </PageSection>

        <PageSection icon={ListChecks} title="Administrator queues" accent="primary">
          {admin.isLoading ? <Skeleton className="h-20 w-full" /> : (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatTile label="Awaiting assessment" value={n(admin.data?.applicationsAwaitingAssessment)} hint="applications" />
              <StatTile label="Offers to accept" value={n(admin.data?.offersAwaitingAcceptance)} hint="issued" />
              <StatTile label="Reviews due" value={n(admin.data?.progressionReviewsDue)} hint="progression" />
              <StatTile label="Theses submitted" value={n(admin.data?.thesesSubmitted)} hint="to examine" />
            </div>
          )}
        </PageSection>
      </div>
    </>
  )
}
