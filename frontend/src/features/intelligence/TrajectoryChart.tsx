'use client'

/**
 * Trajectory chart (spec §11 §13) — deterministic sparkline over engagement or
 * prediction history. Accessible tabular fallback rendered off-screen for screen
 * readers per §26 (charts must have tabular values).
 */
import { cn } from '@/lib/utils'

export interface TrajectoryPoint {
  x: string       // ISO date or label
  y: number       // 0–100 or absolute
  label?: string  // optional secondary label under x
}

export interface TrajectoryChartProps {
  points: TrajectoryPoint[]
  height?: number
  /** Optional threshold line (e.g. model-review threshold). */
  threshold?: number
  /** Optional annotations rendered under the chart. */
  annotations?: Array<{ x: string; text: string }>
  yFormat?: (v: number) => string
  className?: string
  caption?: string
}

export function TrajectoryChart({
  points, height = 96, threshold, annotations, yFormat = (v) => `${v}`, className, caption,
}: TrajectoryChartProps) {
  if (points.length === 0) {
    return <p className="text-sm text-muted-foreground">No trajectory data.</p>
  }

  const w = 100
  const h = 100
  const ys = points.map((p) => p.y)
  const yMin = Math.min(...ys, threshold ?? Infinity)
  const yMax = Math.max(...ys, threshold ?? -Infinity)
  const yRange = yMax - yMin || 1
  const step = points.length > 1 ? w / (points.length - 1) : w / 2

  const path = points.map((p, i) => {
    const x = i * step
    const y = h - ((p.y - yMin) / yRange) * h
    return `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`
  }).join(' ')

  const thresholdY = threshold !== undefined ? h - ((threshold - yMin) / yRange) * h : null

  return (
    <figure className={cn('space-y-2', className)}>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full" style={{ height }} role="img" aria-label={caption ?? 'Trajectory chart'}>
        {thresholdY !== null ? (
          <line x1="0" x2={w} y1={thresholdY} y2={thresholdY}
                stroke="currentColor" strokeDasharray="2 2" className="text-muted-foreground/40" strokeWidth={0.4} />
        ) : null}
        <path d={path} fill="none" stroke="currentColor" strokeWidth={1.5} className="text-primary" strokeLinejoin="round" strokeLinecap="round" />
        {points.map((p, i) => {
          const x = i * step
          const y = h - ((p.y - yMin) / yRange) * h
          return <circle key={i} cx={x} cy={y} r={1.6} className="text-primary fill-current" />
        })}
      </svg>
      <div className="flex justify-between text-[10px] text-muted-foreground">
        {points.map((p, i) => (
          <span key={i} className="text-center">
            <div>{p.x}</div>
            <div className="font-medium text-foreground">{yFormat(p.y)}</div>
          </span>
        ))}
      </div>
      {annotations?.length ? (
        <ul className="text-xs text-muted-foreground space-y-0.5">
          {annotations.map((a, i) => <li key={i}>• {a.x} — {a.text}</li>)}
        </ul>
      ) : null}
      {/* Tabular fallback for accessibility (§26). */}
      <table className="sr-only">
        <caption>{caption ?? 'Trajectory data'}</caption>
        <thead><tr><th>Period</th><th>Value</th></tr></thead>
        <tbody>
          {points.map((p, i) => <tr key={i}><td>{p.x}</td><td>{yFormat(p.y)}</td></tr>)}
        </tbody>
      </table>
    </figure>
  )
}
