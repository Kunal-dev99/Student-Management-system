'use client'

/**
 * Engagement Trajectory panel (spec §11) — "Supervision engagement" over time.
 *
 * The label is deterministic (rules score); the LLM path enriches it via
 * `?engine=llm` on the compute endpoint. We render the observed contact pattern
 * plus why-it-changed reasons; we never describe relationship quality.
 */
import { useEffect, useMemo, useState } from 'react'
import { Users } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { TrajectoryChart, type TrajectoryPoint } from './TrajectoryChart'
import { AIStateBanner } from './AIStateBanner'
import { intelligenceApi, type EngagementTrajectory } from './api'

const LABEL_TONE: Record<string, 'success' | 'warning' | 'secondary' | 'destructive'> = {
  thriving: 'success', steady: 'secondary', drifting: 'warning', strained: 'destructive',
}

export interface EngagementPanelProps {
  studentId: string
}

export function EngagementPanel({ studentId }: EngagementPanelProps) {
  const [data, setData] = useState<EngagementTrajectory | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [computing, setComputing] = useState(false)
  // User-controlled, not a hardcoded prop nobody ever set to true — this is the
  // actual "engine=llm" path the backend supports; without a real toggle it was
  // unreachable from the UI.
  const [useLlm, setUseLlm] = useState(false)

  async function refresh() {
    setLoading(true); setError(null)
    try { setData(await intelligenceApi.engagement(studentId)) }
    catch (e) { setError((e as Error).message) }
    finally { setLoading(false) }
  }

  useEffect(() => { void refresh() }, [studentId])  // eslint-disable-line react-hooks/exhaustive-deps

  async function computeNow() {
    setComputing(true)
    try {
      await intelligenceApi.computeEngagement(studentId, { engine: useLlm ? 'llm' : 'rules' })
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setComputing(false)
    }
  }

  const latest = data?.points[data.points.length - 1]
  const points: TrajectoryPoint[] = useMemo(() => (
    data?.points.map((p) => ({
      x: new Date(p.computedAt).toLocaleDateString(undefined, { month: 'short' }),
      y: p.score,
      label: p.label,
    })) ?? []
  ), [data])

  const reasons: string[] = useMemo(() => {
    if (!data) return []
    const bucket: Record<string, number> = {}
    data.recentEvents.slice(0, 12).forEach((e) => { bucket[e.kind] = (bucket[e.kind] ?? 0) + 1 })
    return Object.entries(bucket).map(([kind, n]) => `${n} × ${kind.replace(/_/g, ' ')}`)
  }, [data])

  // No snapshots AND no underlying events: there is nothing to show and nothing
  // useful for "Recompute" to do (it would just write a manufactured score-0
  // row). An always-visible empty card here is exactly the kind of chrome that
  // makes the page look busier than it is without adding value — skip it.
  const hasNothing = !loading && !error && (!data || (data.points.length === 0 && data.recentEvents.length === 0))
  if (hasNothing) return null

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Users className="h-4 w-4" />
          Supervision engagement
        </CardTitle>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Checkbox checked={useLlm} onCheckedChange={(v) => setUseLlm(!!v)} />
            LLM label
          </label>
          <Button size="sm" variant="ghost" onClick={computeNow} disabled={computing}>
            {computing ? 'Computing…' : 'Recompute'}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {loading ? (
          <div className="space-y-2"><Skeleton className="h-4 w-40" /><Skeleton className="h-20 w-full" /></div>
        ) : error ? (
          <AIStateBanner state="error" detail={error} action={{ label: 'Retry', onClick: () => void refresh() }} />
        ) : !data || data.points.length === 0 ? (
          <p className="text-sm text-muted-foreground">No engagement snapshots yet — click Recompute.</p>
        ) : (
          <>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">Latest label:</span>
              <Badge variant={LABEL_TONE[latest?.label ?? 'steady']}>{latest?.label}</Badge>
              <span className="text-xs text-muted-foreground">
                score {latest?.score} · engine {latest?.engine}
              </span>
            </div>
            <TrajectoryChart
              points={points}
              caption="Engagement score over time"
            />
            {reasons.length > 0 ? (
              <div>
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">Why it changed</p>
                <ul className="text-xs text-muted-foreground space-y-0.5">
                  {reasons.map((r) => <li key={r}>· {r}</li>)}
                </ul>
              </div>
            ) : null}
            <p className="text-[11px] text-muted-foreground">
              Explains observed contact patterns — not relationship quality.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  )
}
