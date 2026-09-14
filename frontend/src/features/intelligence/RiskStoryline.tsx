'use client'

/**
 * Pattern Lab — student risk storyline (spec §12-13).
 *
 * Upgrade from "single score" to a trajectory + driver-change explanation. Rules:
 *
 *   - Trajectory of the last N predictions with a threshold line, model-version
 *     boundary markers, and the current point emphasised.
 *   - "What changed" surfaces the top driver deltas since the previous snapshot
 *     — clearly labelled as a *model explanation*, not a causal statement.
 *   - Model health is visible ENOUGH that a degraded model cannot look equally
 *     trustworthy. The banner sits above the numbers.
 *   - Non-causal banner is permanent — a governance rule spec §12.
 *   - Sensitivity: only bounded, side-effect-free scenario controls (delegated
 *     to the shared ScenarioDrawer).
 *
 * The endpoint is `/intelligence/predictions/{studentId}/history?target=X`. When no
 * history exists yet, the current prediction from `pattern-lab/students/{id}/predictions`
 * is rendered as a single point so the reader always sees the current number.
 */
import { useMemo, useState } from 'react'
import { AlertTriangle, ArrowDownRight, ArrowRight, ArrowUpRight, PlayCircle, ShieldAlert, TrendingUp } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useQuery } from '@tanstack/react-query'
import { cn } from '@/lib/utils'
import { intelligenceApi, type RiskStoryline as RiskStorylineData } from './api'
import { TrajectoryChart, type TrajectoryPoint } from './TrajectoryChart'
import { AIStateBanner } from './AIStateBanner'
import { ScenarioDrawer } from './ScenarioDrawer'
import { useStudentPredictions } from '@/features/pattern-lab/api'

// ---- Small helpers ---------------------------------------------------------

function ppDelta(current: number, prior: number): number {
  return Math.round((current - prior) * 100)  // percentage points
}

function directionIcon(d: 'up' | 'down' | 'flat') {
  return d === 'up' ? ArrowUpRight : d === 'down' ? ArrowDownRight : ArrowRight
}

function healthTone(h: string): 'success' | 'warning' | 'destructive' | 'secondary' {
  return h === 'healthy' || h === 'green' ? 'success'
       : h === 'review'  || h === 'amber' ? 'warning'
       : h === 'stale'   || h === 'red'   ? 'destructive'
       : 'secondary'
}

// ---- Component -------------------------------------------------------------

export interface RiskStorylineProps {
  studentId: string
  className?: string
}

export function RiskStoryline({ studentId, className }: RiskStorylineProps) {
  const [scenarioOpen, setScenarioOpen] = useState(false)

  // Discover which models have scored this student — used to populate the target picker.
  const predictionsQ = useStudentPredictions(studentId)
  const availableTargets = useMemo(() => (
    (predictionsQ.data ?? []).map((p) => ({
      key: p.modelName.toLowerCase().replace(/\s+/g, '_'),
      // Backend history endpoint keys by target_key, but the pattern-lab StudentPrediction
      // doesn't expose that field. Try the outcome slug — the intelligence Twin uses
      // `target_key` from `MlModel`; if it doesn't match, we degrade to "current point only".
      probable: p.outcome.toLowerCase().replace(/[^a-z0-9]+/g, '_'),
      modelName: p.modelName,
      current: p,
    }))
  ), [predictionsQ.data])

  const [targetKey, setTargetKey] = useState<string | null>(null)
  const activeTargetKey = targetKey ?? availableTargets[0]?.key ?? null
  const activeTargetMeta = availableTargets.find((t) => t.key === activeTargetKey) ?? null

  // Historical trajectory from the intelligence layer. 404 is common (only the current
  // batch is stored for many models) — we still render the current-point fallback.
  const historyQ = useQuery({
    enabled: !!activeTargetKey,
    queryKey: ['intel', 'predictions', studentId, activeTargetKey],
    queryFn: () => intelligenceApi.predictionHistory(studentId, activeTargetKey!),
    retry: false,
  })

  const history: RiskStorylineData | null = historyQ.data ?? null
  const historyPoints = history?.points ?? []

  const chartPoints: TrajectoryPoint[] = useMemo(() => {
    if (historyPoints.length > 0) {
      return historyPoints.map((p) => ({
        x: new Date(p.predictedAt).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
        y: Math.round(p.probability * 100),
      }))
    }
    // Fall back to the single current prediction — one dot on the axis is still useful.
    if (activeTargetMeta?.current) {
      const at = activeTargetMeta.current.scoredAt
      return [{
        x: at ? new Date(at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : 'now',
        y: Math.round(activeTargetMeta.current.probability * 100),
      }]
    }
    return []
  }, [historyPoints, activeTargetMeta])

  const threshold = historyPoints[0]?.threshold ? Math.round(historyPoints[0].threshold * 100) : undefined

  // Driver deltas — from the last two snapshots' drivers. Falls back to the current
  // prediction's `factors` list (which already carries a signed contribution).
  const driverDeltas = useMemo(() => {
    if (historyPoints.length >= 2 && history) {
      const latest = historyPoints[historyPoints.length - 1]
      const drivers = history.driversByPrediction[latest.id] ?? []
      return drivers.slice(0, 4).map((d) => ({
        feature: d.feature,
        direction: d.direction,
        deltaPp: d.deltaPpOrSensitivity !== null ? Math.round(d.deltaPpOrSensitivity * 100) : null,
        method: d.method,
      }))
    }
    if (activeTargetMeta?.current) {
      return activeTargetMeta.current.factors.slice(0, 4).map((f) => ({
        feature: f.label ?? f.feature,
        direction: (f.deltaPp > 0 ? 'up' : f.deltaPp < 0 ? 'down' : 'flat') as 'up' | 'down' | 'flat',
        deltaPp: Math.round(f.deltaPp),
        method: 'shap-current',
      }))
    }
    return []
  }, [historyPoints, history, activeTargetMeta])

  const modelHealth = historyPoints[historyPoints.length - 1]?.modelHealth
  const healthLabel = typeof modelHealth?.status === 'string' ? String(modelHealth.status) : 'unknown'
  const modelVersion = historyPoints[historyPoints.length - 1]?.modelVersionId?.slice(0, 8)
                    ?? activeTargetMeta?.current.versionId?.slice(0, 8) ?? '—'

  const currentPct = chartPoints.length > 0 ? chartPoints[chartPoints.length - 1].y : null
  const priorPct = chartPoints.length > 1 ? chartPoints[chartPoints.length - 2].y : null
  const movement = currentPct !== null && priorPct !== null ? currentPct - priorPct : null

  if (predictionsQ.isLoading) {
    return (
      <Card className={className}>
        <CardHeader><CardTitle className="text-base">Risk storyline</CardTitle></CardHeader>
        <CardContent><Skeleton className="h-40 w-full" /></CardContent>
      </Card>
    )
  }
  if (availableTargets.length === 0) {
    return null  // No production model has scored this student — surface nothing.
  }

  return (
    <>
      <Card className={className}>
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <TrendingUp className="h-4 w-4 text-primary" />
              Risk score — how it has moved
            </CardTitle>
            <p className="text-xs text-muted-foreground mt-1">
              A trained model rates this student's chance of a specific outcome (e.g. funding
              running out). We show the number, how it changed, and how much to trust it —
              never as a decision, only as a lead.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Select value={activeTargetKey ?? undefined} onValueChange={setTargetKey}>
              <SelectTrigger className="h-8 w-56"><SelectValue placeholder="Target" /></SelectTrigger>
              <SelectContent>
                {availableTargets.map((t) => (
                  <SelectItem key={t.key} value={t.key}>{t.modelName}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button size="sm" variant="ghost" onClick={() => setScenarioOpen(true)}>
              <PlayCircle className="h-3.5 w-3.5 mr-1.5" /> Explore scenarios
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Permanent "not a decision" banner — spec §12 governance rule. */}
          <div className="flex items-start gap-2 rounded-md border border-purple-300/50 bg-purple-50 dark:border-purple-800 dark:bg-purple-950/20 px-3 py-2 text-xs text-purple-900 dark:text-purple-200">
            <ShieldAlert className="h-4 w-4 mt-0.5 shrink-0" aria-hidden />
            <span>
              This score is a pattern the model has seen before — it is <strong>not</strong> a
              prediction of what will happen to this student, and it is not a reason on its
              own to act. A human still decides.
            </span>
          </div>

          {/* Model health banner. */}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-muted-foreground uppercase tracking-wide">Model health</span>
            <Badge variant={healthTone(healthLabel)}>{healthLabel.toUpperCase()}</Badge>
            <span className="text-muted-foreground">·</span>
            <span className="font-mono">v{modelVersion}</span>
            {modelHealth?.psi ? (
              <>
                <span className="text-muted-foreground">·</span>
                <span>PSI {String(modelHealth.psi)}</span>
              </>
            ) : null}
            {healthLabel !== 'healthy' && healthLabel !== 'green' ? (
              <span className="ml-2 inline-flex items-center gap-1 text-amber-800 dark:text-amber-200">
                <AlertTriangle className="h-3 w-3" /> Treat this score as advisory.
              </span>
            ) : null}
          </div>

          {/* Headline current score + delta since prior. */}
          <div className="flex items-baseline gap-3">
            <span className="text-3xl font-semibold tabular-nums">
              {currentPct === null ? '—' : `${currentPct}%`}
            </span>
            {movement !== null ? (
              <Badge variant={movement > 0 ? 'destructive' : movement < 0 ? 'success' : 'secondary'} className="gap-1">
                {movement > 0 ? '+' : ''}{movement}pp vs previous
              </Badge>
            ) : (
              <span className="text-xs text-muted-foreground">Current snapshot</span>
            )}
          </div>

          {/* A chart with one dot isn't a trajectory — it just LOOKS broken. Show the
              plain fact instead and let the chart earn its place once there's
              actually a second point to draw a line to. */}
          {chartPoints.length >= 2 ? (
            <TrajectoryChart
              points={chartPoints}
              threshold={threshold}
              yFormat={(v) => `${v}%`}
              caption={`Trajectory of ${activeTargetMeta?.modelName ?? 'target'} probability`}
            />
          ) : (
            <p className="text-xs text-muted-foreground rounded-md border border-dashed px-3 py-2">
              {historyQ.error
                ? 'History unavailable — showing the current snapshot only.'
                : 'Only one score has been recorded for this student so far — a trend will appear once the model scores it again.'}
            </p>
          )}

          {/* "What changed" driver deltas. */}
          <section>
            <p className="text-sm font-medium mb-1">What the model noticed</p>
            <p className="text-xs text-muted-foreground mb-2">
              These are the features that moved the score most since the last snapshot.
              A feature moving <em>with</em> the score doesn't mean it <em>caused</em> the
              change — treat it as a lead to look at, not an explanation.
            </p>
            {driverDeltas.length === 0 ? (
              <p className="text-sm text-muted-foreground">No driver information for this snapshot.</p>
            ) : (
              <ul className="space-y-1">
                {driverDeltas.map((d) => {
                  const Icon = directionIcon(d.direction)
                  const tone = d.direction === 'up' ? 'text-destructive'
                             : d.direction === 'down' ? 'text-emerald-700 dark:text-emerald-300'
                             : 'text-muted-foreground'
                  return (
                    <li key={`${d.feature}-${d.method}`} className="flex items-center gap-2 text-sm">
                      <Icon className={cn('h-3.5 w-3.5 shrink-0', tone)} aria-hidden />
                      <span className="flex-1 min-w-0 truncate">{d.feature.replace(/_/g, ' ')}</span>
                      <span className={cn('tabular-nums font-mono text-xs', tone)}>
                        {d.deltaPp === null ? '—' : `${d.deltaPp > 0 ? '+' : ''}${d.deltaPp}pp`}
                      </span>
                    </li>
                  )
                })}
              </ul>
            )}
            <p className="text-[11px] text-muted-foreground mt-2">
              To flag incorrect input data, use the source record — do not edit model output directly.
            </p>
          </section>
        </CardContent>
      </Card>

      <ScenarioDrawer
        open={scenarioOpen}
        onOpenChange={setScenarioOpen}
        studentId={studentId}
      />
    </>
  )
}
