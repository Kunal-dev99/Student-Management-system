'use client'

/**
 * Funding lineage and integrity (Phase 6.3).
 *
 * Shows the single trace finance and the CIO asked for —
 *
 *     Project → Award → Funder → Arrangements → Stipend
 *
 * — and then says whether it holds together. A missing hop is rendered as "not linked"
 * rather than omitted: the gap is the finding.
 */

import { AlertTriangle, CheckCircle2, GitBranch, Info, XCircle } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { ApiError } from '@/shared/api/client'
import {
  useFundingLineage,
  type FindingSeverity, type FundingFinding, type FundingLineage, type LineageAward,
} from './api'

/** Human labels for the evidence carried on a finding. Unlisted keys fall back to the key. */
const DETAIL_LABELS: Record<string, string> = {
  days: 'days',
  from_: 'from', // trailing underscore: `from` is reserved on the backend side
  to: 'to',
  shortfallDays: 'shortfall (days)',
  awardRef: 'award',
  awardValue: 'award value',
  committed: 'committed',
  projectCode: 'project code',
  funderReference: 'funder reference',
  studentStart: 'student started',
  firstFundingFrom: 'funding starts',
  fundingEnds: 'funding ends',
  expectedEnd: 'expected end',
  totalContributionPct: 'total contribution %',
}

/** Identifiers help nobody read a finding — the dates and amounts do. */
const DETAIL_HIDDEN = new Set(['arrangementId'])

function detailPairs(detail: Record<string, unknown>): Array<[string, string]> {
  return Object.entries(detail ?? {})
    .filter(([k, v]) => !DETAIL_HIDDEN.has(k) && v !== null && v !== undefined && v !== '')
    .map(([k, v]) => [DETAIL_LABELS[k] ?? k, String(v)] as [string, string])
}

const SEVERITY_ICON: Record<FindingSeverity, typeof XCircle> = {
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
}

const SEVERITY_CLASS: Record<FindingSeverity, string> = {
  error: 'bg-[hsl(var(--destructive)/0.1)] border-[hsl(var(--destructive)/0.3)] text-[hsl(var(--destructive))]',
  warning: 'bg-[hsl(var(--warning)/0.1)] border-[hsl(var(--warning)/0.3)] text-[hsl(var(--warning))]',
  info: 'bg-[hsl(var(--info)/0.1)] border-[hsl(var(--info)/0.3)] text-[hsl(var(--info))]',
}

const SEVERITY_LABEL: Record<FindingSeverity, string> = {
  error: 'Errors',
  warning: 'Warnings',
  info: 'For information',
}

const SEVERITY_ORDER: FindingSeverity[] = ['error', 'warning', 'info']

/** One finding — the message, then the evidence that produced it. */
export function FindingRow({ finding }: { finding: FundingFinding }) {
  const Icon = SEVERITY_ICON[finding.severity]
  const pairs = detailPairs(finding.detail)
  return (
    <div className={`rounded-md border px-3 py-2 ${SEVERITY_CLASS[finding.severity]}`}>
      <div className="flex items-start gap-2">
        <Icon className="h-4 w-4 mt-0.5 shrink-0" />
        <div className="min-w-0">
          <p className="text-sm font-medium">{finding.message}</p>
          {pairs.length > 0 && (
            <p className="text-xs mt-0.5 text-muted-foreground">
              {pairs.map(([label, value]) => `${label} ${value}`).join(' · ')}
            </p>
          )}
          <p className="text-xs mt-0.5 font-mono text-muted-foreground">{finding.code}</p>
        </div>
      </div>
    </div>
  )
}

/** Findings grouped by severity — errors first, because they are what must be fixed. */
export function FindingList({ findings }: { findings: FundingFinding[] }) {
  return (
    <div className="space-y-3">
      {SEVERITY_ORDER.map((sev) => {
        const group = findings.filter((f) => f.severity === sev)
        if (group.length === 0) return null
        return (
          <div key={sev} className="space-y-1.5">
            <p className="text-label">{SEVERITY_LABEL[sev]} ({group.length})</p>
            {group.map((f, i) => <FindingRow key={`${f.code}-${i}`} finding={f} />)}
          </div>
        )
      })}
    </div>
  )
}

function money(amount: string | null | undefined, currency: string | null | undefined) {
  if (amount === null || amount === undefined || amount === '') return '—'
  const n = Number(amount)
  if (Number.isNaN(n)) return amount
  return `${currency ?? ''} ${n.toLocaleString()}`.trim()
}

/** One hop in the chain. `linked` false renders the gap rather than hiding it. */
function Hop({
  label, linked, primary, secondary,
}: {
  label: string
  linked: boolean
  primary?: string
  secondary?: string
}) {
  return (
    <div className={`rounded-md border px-3 py-2 min-w-[9rem] flex-1 ${linked ? 'border-border bg-surface-2' : 'border-dashed border-border bg-transparent'}`}>
      <p className="text-label">{label}</p>
      {linked ? (
        <>
          <p className="text-sm font-medium mt-0.5 truncate" title={primary}>{primary}</p>
          {secondary && <p className="text-xs text-muted-foreground truncate" title={secondary}>{secondary}</p>}
        </>
      ) : (
        <p className="text-sm text-muted-foreground mt-0.5 italic">not linked</p>
      )}
    </div>
  )
}

function Arrow() {
  return <span aria-hidden className="text-muted-foreground select-none self-center px-0.5">→</span>
}

/** The award the chain runs through: the project's if there is one, otherwise an arrangement's. */
function chainAward(l: FundingLineage): LineageAward | null {
  return l.project?.award ?? l.arrangements.find((a) => a.award)?.award ?? null
}

export function FundingLineagePanel({ studentId }: { studentId: string }) {
  const { data, isLoading, isError, error } = useFundingLineage(studentId)

  const award = data ? chainAward(data) : null
  const funder = award?.funder ?? data?.arrangements.find((a) => a.fundingSource)?.fundingSource ?? null
  const active = data?.arrangements.filter((a) => a.validTo === null).length ?? 0
  const hasError = data?.findings.some((f) => f.severity === 'error') ?? false

  return (
    <PageSection
      icon={GitBranch}
      title="Funding lineage"
      accent={hasError ? 'danger' : data?.complete ? 'success' : 'primary'}
      attention={hasError}
      description="Where this student's money comes from, hop by hop — and whether the chain holds together."
      headerRight={data ? (
        <Badge variant={hasError ? 'destructive' : 'success'}>
          {hasError ? 'chain incomplete' : 'chain complete'}
        </Badge>
      ) : undefined}
    >
      {isLoading ? (
        <Skeleton className="h-28 w-full" />
      ) : isError ? (
        <p className="text-sm text-[hsl(var(--destructive))]">{(error as ApiError)?.message}</p>
      ) : data ? (
        <div className="space-y-4">
          {/* The chain itself. Every hop is shown, linked or not. */}
          <div className="flex flex-wrap items-stretch gap-1.5">
            <Hop
              label="Project"
              linked={!!data.project}
              primary={data.project?.researchTopic ?? 'Untitled project'}
              secondary={[data.project?.researchGroup, data.project?.startDate && `from ${data.project.startDate}`]
                .filter(Boolean).join(' · ') || undefined}
            />
            <Arrow />
            <Hop
              label="Award"
              linked={!!award}
              primary={award?.awardRef}
              secondary={[award?.title, award?.value ? money(award.value, award.currency) : null]
                .filter(Boolean).join(' · ') || undefined}
            />
            <Arrow />
            <Hop
              label="Funder"
              linked={!!funder}
              primary={funder?.name}
              secondary={award?.sourceSystem ? `via ${award.sourceSystem}` : undefined}
            />
            <Arrow />
            <Hop
              label="Arrangements"
              linked={data.arrangements.length > 0}
              primary={`${data.arrangements.length} recorded`}
              secondary={`${active} currently open`}
            />
            <Arrow />
            <Hop
              label="Stipend"
              linked={data.totals.committed !== '0' || data.totals.paid !== '0'}
              primary={`${money(data.totals.paid, data.totals.currency)} paid`}
              secondary={`${money(data.totals.committed, data.totals.currency)} committed`}
            />
          </div>

          {/* Per-arrangement detail — which award each slice of money is drawn from. */}
          {data.arrangements.length > 0 && (
            <div className="space-y-1.5">
              {data.arrangements.map((a) => (
                <div key={a.id} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 border-b border-border/60 last:border-0 pb-1.5 last:pb-0">
                  <span className="text-sm font-medium">{a.fundingType.replace(/_/g, ' ')}</span>
                  <span className="text-helper num">{a.validFrom} → {a.validTo ?? 'current'}</span>
                  <span className="text-sm num">{money(a.stipendAmount, a.currency)}</span>
                  {a.contributionPct != null && <Badge variant="secondary">{a.contributionPct}%</Badge>}
                  {a.award ? (
                    <Badge variant="info">{a.award.awardRef}</Badge>
                  ) : (
                    <span className="text-helper italic">no award link</span>
                  )}
                  {a.fundingSource && <span className="text-helper">{a.fundingSource.name}</span>}
                  <span className="text-helper num">
                    {a.instalments} instalment{a.instalments === 1 ? '' : 's'} ·{' '}
                    {money(a.paidTotal, a.currency)} paid
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Findings — or the reassurance that there are none. */}
          {data.findings.length === 0 || data.complete ? (
            <div className="rounded-md border border-[hsl(var(--success)/0.3)] bg-[hsl(var(--success)/0.1)] px-3 py-2 flex items-start gap-2">
              <CheckCircle2 className="h-4 w-4 mt-0.5 shrink-0 text-[hsl(var(--success))]" />
              <div>
                <p className="text-sm font-medium text-[hsl(var(--success))]">
                  Funding chain is complete and consistent
                </p>
                {data.findings.length > 0 && (
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {data.findings.length} non-blocking note{data.findings.length === 1 ? '' : 's'} below.
                  </p>
                )}
              </div>
            </div>
          ) : null}

          {data.findings.length > 0 && <FindingList findings={data.findings} />}
        </div>
      ) : null}
    </PageSection>
  )
}
