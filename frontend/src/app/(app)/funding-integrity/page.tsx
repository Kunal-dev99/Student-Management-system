'use client'

/**
 * Funding integrity (Phase 6.3) — the cohort question that previously had no screen:
 * *which* students' funding chains do not hold together, and why.
 */

import { useState } from 'react'
import Link from 'next/link'
import { ArrowUpRight, ShieldAlert } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ApiError } from '@/shared/api/client'
import { FindingList } from '@/features/funding/FundingLineagePanel'
import { useFundingIntegrity } from '@/features/funding/api'

function Tile({ label, value, tone }: { label: string; value: number; tone?: 'error' | 'warning' }) {
  const toneClass =
    tone === 'error'
      ? 'text-[hsl(var(--destructive))]'
      : tone === 'warning'
        ? 'text-[hsl(var(--warning))]'
        : 'text-foreground'
  return (
    <div className="card-elevated rounded-md border border-border bg-surface-2 px-4 py-3">
      <p className="text-label">{label}</p>
      <p className={`text-2xl num font-semibold mt-1 ${toneClass}`}>{value}</p>
    </div>
  )
}

export default function FundingIntegrityPage() {
  const [errorsOnly, setErrorsOnly] = useState(false)
  const { data, isLoading, isError, error } = useFundingIntegrity(errorsOnly ? 'error' : undefined)

  return (
    <>
      <PageHeader
        title="Funding integrity"
        description="Every active student's funding chain, checked end to end: project → award → funder → arrangement → stipend."
      />
      <div className="px-6 pb-6 space-y-4">
        {isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : isError ? (
          <p className="text-sm text-[hsl(var(--destructive))]">{(error as ApiError)?.message}</p>
        ) : data ? (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Tile label="Students checked" value={data.checked} />
              <Tile label="With findings" value={data.withFindings} />
              <Tile label="Errors" value={data.errors} tone="error" />
              <Tile label="Warnings" value={data.warnings} tone="warning" />
            </div>

            <div className="flex items-center gap-2">
              <span className="text-label">Severity</span>
              <Button size="sm" variant={errorsOnly ? 'outline' : 'default'} onClick={() => setErrorsOnly(false)}>
                All
              </Button>
              <Button size="sm" variant={errorsOnly ? 'default' : 'outline'} onClick={() => setErrorsOnly(true)}>
                Errors only
              </Button>
            </div>

            <PageSection
              icon={ShieldAlert}
              title={errorsOnly ? 'Students with funding errors' : 'Students with funding findings'}
              accent={data.errors > 0 ? 'danger' : 'primary'}
              attention={data.errors > 0}
              description="Informational notes are excluded here — this list is only what somebody has to act on."
            >
              {data.students.length === 0 ? (
                <p className="text-helper">
                  No {errorsOnly ? 'errors' : 'findings'} across the {data.checked} student
                  {data.checked === 1 ? '' : 's'} in scope. Every funding chain holds together.
                </p>
              ) : (
                <div className="space-y-4">
                  {data.students.map((s) => (
                    <div key={s.id} className="border-b border-border/60 last:border-0 pb-4 last:pb-0 space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <Link
                          href={`/students/${s.id}`}
                          className="text-sm font-medium text-primary hover:underline inline-flex items-center gap-1"
                        >
                          {s.personName}
                          <ArrowUpRight className="h-3.5 w-3.5" />
                        </Link>
                        <span className="font-mono text-xs text-muted-foreground">{s.studentRef}</span>
                        <Badge variant="secondary">{s.status.replace(/_/g, ' ')}</Badge>
                        <Badge variant={s.worstSeverity === 'error' ? 'destructive' : 'warning'}>
                          {s.worstSeverity}
                        </Badge>
                        <span className="text-helper num">
                          {s.startDate ?? '—'} → {s.expectedEndDate ?? '—'}
                        </span>
                      </div>
                      <FindingList findings={s.findings} />
                    </div>
                  ))}
                </div>
              )}
            </PageSection>
          </>
        ) : null}
      </div>
    </>
  )
}
