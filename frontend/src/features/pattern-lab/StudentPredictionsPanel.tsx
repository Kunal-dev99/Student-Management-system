'use client'

/**
 * Predicted risk (Pattern Lab) — the student-detail enrichment panel (PL-5).
 *
 * Silent absence by design: this renders nothing at all when the viewer lacks
 * `ml.read`, when the API refuses (403 or any other error), or when no
 * production model has scored this student — it is staff-facing enrichment,
 * not a fixture of the record, so there is no empty card and no error card.
 *
 * When predictions exist: one compact block per model — outcome, probability
 * as a plain-div bar + percent, the perturbation-derived contributing factors
 * as low-opacity chips, when it was scored, and the backend's advisory note
 * verbatim underneath.
 *
 * `ProbabilityBar` and `FactorChips` are exported for reuse by the Pattern Lab
 * page's Predictions tab (a page module must not export extra names itself).
 */

import { TrendingUp } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { cn } from '@/lib/utils'
import { useAuth } from '@/shared/auth/AuthContext'
import { useStudentPredictions, type PredictionFactor } from '@/features/pattern-lab/api'

const pct = (p: number) => `${Math.round(p * 100)}%`
const fmtDelta = (d: number) => `${d > 0 ? '+' : ''}${d.toFixed(1)} pp`

/** Probability as a plain-div bar + percent; the fill tone follows the risk. */
export function ProbabilityBar({
  probability, className,
}: { probability: number; className?: string }) {
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <div className="h-2 flex-1 min-w-[4rem] rounded-full bg-surface-3 overflow-hidden">
        <div
          className={cn(
            'h-full rounded-full',
            probability >= 0.7 ? 'bg-danger/70'
            : probability >= 0.4 ? 'bg-warning/70'
            : 'bg-success/60',
          )}
          style={{ width: `${Math.max(2, Math.round(probability * 100))}%` }}
        />
      </div>
      <span className="num text-sm font-medium w-10 text-right shrink-0">
        {pct(probability)}
      </span>
    </div>
  )
}

/**
 * Contributing factors as compact chips — "{label} {+x.x pp}". The sign
 * convention: a positive deltaPp means the student's value raises their
 * probability versus the population median (danger tone); a negative one
 * pulls it down (success tone).
 */
export function FactorChips({ factors }: { factors: PredictionFactor[] }) {
  if (factors.length === 0) {
    return <span className="text-xs text-muted-foreground">no dominant factors</span>
  }
  return (
    <div className="flex flex-wrap gap-1">
      {factors.map((f) => (
        <span
          key={f.feature}
          title={f.value == null ? f.label : `${f.label} = ${f.value}`}
          className={cn(
            'inline-flex items-center whitespace-nowrap rounded-sm border px-1.5 py-0.5 text-[11px]',
            f.deltaPp > 0
              ? 'border-[hsl(var(--danger)/0.3)] bg-[hsl(var(--danger)/0.1)] text-[hsl(var(--danger))]'
              : 'border-[hsl(var(--success)/0.3)] bg-[hsl(var(--success)/0.1)] text-[hsl(var(--success))]',
          )}
        >
          {f.label} <span className="num ml-1">{fmtDelta(f.deltaPp)}</span>
        </span>
      ))}
    </div>
  )
}

export function StudentPredictionsPanel({ studentId }: { studentId: string }) {
  const { hasPermission } = useAuth()
  const canRead = hasPermission('ml.read')
  const predictionsQ = useStudentPredictions(studentId, canRead)
  const predictions = predictionsQ.data ?? []

  // Silent absence: no permission, refused, still loading, or nothing scored.
  if (!canRead || predictionsQ.isError || predictions.length === 0) return null

  return (
    <PageSection
      icon={TrendingUp}
      title="Predicted risk (Pattern Lab)"
      description="Advisory model output — it sits beside the deterministic indicators, never replaces them."
      accent="primary"
    >
      <div className="space-y-3">
        {predictions.map((p) => (
          <div key={p.modelId} className="card-elevated p-3 space-y-2">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
              <p className="text-sm font-medium">{p.modelName}</p>
              {p.scoredAt && (
                <span className="text-xs text-muted-foreground">
                  scored {new Date(p.scoredAt).toLocaleString()}
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground">{p.outcome}</p>
            <ProbabilityBar probability={p.probability} className="max-w-xs" />
            <FactorChips factors={p.factors} />
            <p className="text-[11px] text-muted-foreground/80">{p.note}</p>
          </div>
        ))}
      </div>
    </PageSection>
  )
}
