'use client'

/**
 * The necessity check for a custom attribute request (governance Phase 2): is it already in the
 * core record or another attribute, which HESA field needs it, and what type it should be. Shown
 * live in the request form and in full to the approver. Advisory — nothing here blocks a request.
 */
import { AlertTriangle, CheckCircle2, Info, Search } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import type { AssessmentVerdict, CustomFieldAssessment } from '@/features/statutory/customFields'

const VERDICT: Record<AssessmentVerdict, { label: string; variant: 'destructive' | 'warning' | 'success' | 'secondary' }> = {
  duplicate: { label: 'Possible duplicate', variant: 'destructive' },
  review: { label: 'Needs a look', variant: 'warning' },
  supported: { label: 'HESA-backed', variant: 'success' },
  no_hesa_basis: { label: 'No HESA field found', variant: 'secondary' },
}

const REQUIREMENT: Record<string, string> = {
  required: 'required by the return',
  optional: 'optional in the return',
  already_sourced: 'already sourced from the core record',
  not_found: 'not found',
}

export function VerdictBadge({ verdict }: { verdict: AssessmentVerdict }) {
  const v = VERDICT[verdict] ?? { label: verdict, variant: 'secondary' as const }
  return <Badge variant={v.variant}>{v.label}</Badge>
}

export function AssessmentPanel({ a, compact = false }: { a: CustomFieldAssessment; compact?: boolean }) {
  const hesa = a.hesa.match
  const Icon = a.verdict === 'supported' ? CheckCircle2 : a.verdict === 'duplicate' ? AlertTriangle : a.verdict === 'review' ? Search : Info
  return (
    <div className="rounded-md border border-border bg-muted/30 p-3 space-y-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Icon className="h-4 w-4 text-muted-foreground" />
        <VerdictBadge verdict={a.verdict} />
        {a.hesa.specification && <span className="text-xs text-muted-foreground">checked against {a.hesa.specification}</span>}
      </div>

      {hesa ? (
        <p>
          <span className="text-muted-foreground">HESA field:</span>{' '}
          <span className="font-mono text-xs">{hesa.field}</span> — {hesa.description}{' '}
          <span className="text-muted-foreground">({REQUIREMENT[a.hesa.requirement] ?? a.hesa.requirement}
            {hesa.how === 'named' ? ', named in the request' : ''})</span>
        </p>
      ) : (
        <p className="text-muted-foreground">No HESA field matched the label or reason.</p>
      )}

      {a.flags.length > 0 && (
        <ul className="list-disc pl-5 space-y-0.5 text-xs">
          {a.flags.map((f) => <li key={f}>{f}</li>)}
        </ul>
      )}

      {!compact && (a.coreMatches.length > 0 || a.customMatches.length > 0) && (
        <div className="space-y-1 text-xs">
          {a.coreMatches.length > 0 && (
            <p><span className="text-muted-foreground">Core record:</span>{' '}
              {a.coreMatches.map((m) => `${m.path} (${m.match})`).join(', ')}</p>
          )}
          {a.customMatches.length > 0 && (
            <p><span className="text-muted-foreground">Custom attributes:</span>{' '}
              {a.customMatches.map((m) => `${m.label} — ${m.status} (${m.match})`).join(', ')}</p>
          )}
        </div>
      )}

      <p className="text-xs">
        <span className="text-muted-foreground">Suggested type:</span> {a.suggested.dataType}
        {a.suggested.allowedValues.length > 0 && (
          <> · <span className="text-muted-foreground">allowed values:</span>{' '}
            <span className="font-mono">{a.suggested.allowedValues.slice(0, 12).join(', ')}
              {a.suggested.allowedValues.length > 12 ? ' …' : ''}</span></>
        )}
      </p>
    </div>
  )
}
