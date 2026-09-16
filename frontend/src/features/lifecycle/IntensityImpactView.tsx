'use client'

/**
 * ICR G6 — a visual "what this will do" for an intensity change, shown in the approve dialog.
 * The AI sentence on top, then a before→after timeline of the expected end date, then the exact
 * milestones that move with their current → projected due dates. Deterministic figures throughout.
 */
import { Sparkles } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import type { IntensityImpactNarrated } from './api'

const DAY = 86_400_000
const ymd = (s: string) => s // already ISO YYYY-MM-DD

/** Map a date (ms) into the [padL, W-padR] band of a 0..W viewBox. */
function scale(t: number, lo: number, hi: number, W: number, pad: number): number {
  if (hi <= lo) return pad
  return pad + ((t - lo) / (hi - lo)) * (W - 2 * pad)
}

export function IntensityImpactView({ impact }: { impact: IntensityImpactNarrated }) {
  const prev = impact.previousPct
  const next = impact.newPct
  const extends_ = impact.daysDelta > 0
  const noMove = impact.daysDelta === 0

  const start = impact.startDate ? Date.parse(impact.startDate) : null
  const curEnd = impact.currentEnd ? Date.parse(impact.currentEnd) : null
  const projEnd = impact.projectedEnd ? Date.parse(impact.projectedEnd) : null
  const milestones = impact.milestones ?? []

  const W = 1000, H = 74, pad = 70, axisY = 30
  // Timeline window: from the earliest of start/ends to the latest, with a little margin.
  const points = [start, curEnd, projEnd, ...milestones.flatMap((m) => [Date.parse(m.currentDue), Date.parse(m.projectedDue)])]
    .filter((x): x is number => x != null)
  const lo = points.length ? Math.min(...points) : 0
  const hi = points.length ? Math.max(...points) : 1
  const margin = (hi - lo) * 0.04 || DAY
  const LO = lo - margin, HI = hi + margin
  const x = (t: number) => scale(t, LO, HI, W, pad)

  return (
    <div className="space-y-3">
      {/* AI sentence */}
      <div>
        <div className="flex items-center gap-1.5 mb-0.5">
          <p className="text-sm font-medium">What this will do</p>
          <Badge variant={impact.narrationSource === 'model' ? 'info' : 'secondary'} className="gap-1">
            <Sparkles className="h-3 w-3" />
            {impact.narrationSource === 'model' ? 'AI summary' : 'computed'}
          </Badge>
        </div>
        <p className="text-sm text-muted-foreground">{impact.narration || impact.summary}</p>
      </div>

      {/* Headline chips */}
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {prev != null && next != null && (
          <Badge variant="outline" className="gap-1">
            intensity <span className="num">{prev}%</span> →
            <span className="num font-semibold">{next}%</span>
          </Badge>
        )}
        {!noMove && impact.currentEnd && impact.projectedEnd && (
          <Badge variant={extends_ ? 'warning' : 'success'} className="gap-1">
            end <span className="num line-through opacity-70">{ymd(impact.currentEnd)}</span> →
            <span className="num font-semibold">{ymd(impact.projectedEnd)}</span>
            <span className="ml-0.5">({impact.daysDelta > 0 ? '+' : ''}{impact.daysDelta}d)</span>
          </Badge>
        )}
      </div>

      {/* Timeline visualisation */}
      {curEnd != null && projEnd != null && (
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: 74 }} role="img"
             aria-label="Timeline showing the expected end date shift and milestone moves">
          {/* base axis */}
          <line x1={pad} y1={axisY} x2={W - pad} y2={axisY} stroke="hsl(var(--border))" strokeWidth={2} />
          {/* period up to current end */}
          {start != null && (
            <line x1={x(start)} y1={axisY} x2={x(curEnd)} y2={axisY} stroke="hsl(var(--primary))" strokeWidth={4} />
          )}
          {/* extension (or shortening) segment between current and projected end */}
          <line
            x1={x(Math.min(curEnd, projEnd))} y1={axisY} x2={x(Math.max(curEnd, projEnd))} y2={axisY}
            stroke={extends_ ? 'hsl(var(--warning))' : 'hsl(var(--success))'} strokeWidth={4}
            strokeDasharray="6 4"
          />
          {/* current end marker */}
          <g>
            <line x1={x(curEnd)} y1={axisY - 12} x2={x(curEnd)} y2={axisY + 12} stroke="hsl(var(--muted-foreground))" strokeWidth={2} />
            <text x={x(curEnd)} y={axisY - 16} textAnchor="middle" fontSize={20} fill="hsl(var(--muted-foreground))">now</text>
            <text x={x(curEnd)} y={axisY + 30} textAnchor="middle" fontSize={19} fill="hsl(var(--muted-foreground))">{impact.currentEnd}</text>
          </g>
          {/* projected end marker */}
          <g>
            <line x1={x(projEnd)} y1={axisY - 14} x2={x(projEnd)} y2={axisY + 14} stroke={extends_ ? 'hsl(var(--warning))' : 'hsl(var(--success))'} strokeWidth={3} />
            <text x={x(projEnd)} y={axisY - 16} textAnchor="middle" fontSize={20} fontWeight={600} fill="hsl(var(--foreground))">new end</text>
            <text x={x(projEnd)} y={axisY + 30} textAnchor="middle" fontSize={19} fontWeight={600} fill="hsl(var(--foreground))">{impact.projectedEnd}</text>
          </g>
          {/* milestone slides: hollow dot at current due, filled at projected, thin connector */}
          {milestones.map((m, i) => {
            const c = Date.parse(m.currentDue), p = Date.parse(m.projectedDue)
            return (
              <g key={i}>
                <line x1={x(c)} y1={axisY} x2={x(p)} y2={axisY} stroke="hsl(var(--primary) / 0.35)" strokeWidth={2} />
                <circle cx={x(c)} cy={axisY} r={4} fill="hsl(var(--background))" stroke="hsl(var(--muted-foreground))" strokeWidth={2} />
                <circle cx={x(p)} cy={axisY} r={4} fill="hsl(var(--primary))" />
              </g>
            )
          })}
        </svg>
      )}

      {/* Milestones that move */}
      {milestones.length > 0 && (
        <div>
          <p className="text-helper mb-1">{milestones.length} milestone{milestones.length === 1 ? '' : 's'} would shift</p>
          <div className="rounded-md border border-border divide-y divide-border">
            {milestones.map((m, i) => (
              <div key={i} className="flex items-center justify-between gap-3 px-2.5 py-1.5 text-sm">
                <span className="truncate">{m.name}</span>
                <span className="num whitespace-nowrap text-xs">
                  <span className="text-muted-foreground line-through">{m.currentDue}</span>
                  <span className="mx-1 text-muted-foreground">→</span>
                  <span className="font-medium">{m.projectedDue}</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
