'use client'

/** Blocks that lay data out rather than plot it: tables, histories, small multiples,
 *  and candidates judged side by side. */

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { TONE_CLASS, TONE_HEX, seriesColour } from '../chartTheme'
import type {
  Comparison, ComposerAction, SparklineGrid, TableBlock, Timeline, Tone,
} from '../types'

const ROW_TINT: Record<Tone, string> = {
  neutral: '',
  info: 'bg-[hsl(var(--info)/0.05)]',
  success: 'bg-[hsl(var(--success)/0.05)]',
  warning: 'bg-[hsl(var(--warning)/0.07)]',
  danger: 'bg-destructive/5',
}

export function TableBlockView({
  block, onAction,
}: { block: TableBlock; onAction: (action: ComposerAction) => void }) {
  if (block.rows.length === 0) {
    return (
      <p className="text-helper">
        {block.emptyMessage ?? 'Nothing matched.'}
      </p>
    )
  }
  return (
    <div className="card-elevated overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            {block.columns.map((c) => <TableHead key={c}>{c}</TableHead>)}
            {block.rowAction && <TableHead className="w-32 text-right">Action</TableHead>}
          </TableRow>
        </TableHeader>
        <TableBody>
          {block.rows.map((row, i) => (
            <TableRow key={i}
                      className={`composer-row ${ROW_TINT[block.rowTones?.[i] ?? 'neutral']}`}
                      style={{ animationDelay: `${i * 40}ms` }}>
              {row.map((cell, j) => (
                <TableCell key={j}
                           className={j === 0 ? 'font-medium' : 'text-muted-foreground'}>
                  {cell === null || cell === undefined ? '—' : String(cell)}
                </TableCell>
              ))}
              {block.rowAction && (
                <TableCell className="text-right">
                  <Button
                    size="sm" variant="ghost" className="h-7"
                    onClick={() => {
                      // argsFrom maps column name -> tool argument, so one declaration
                      // on the block wires every row in the column.
                      const args: Record<string, unknown> = {}
                      for (const [col, arg] of Object.entries(block.rowAction?.argsFrom ?? {})) {
                        const idx = block.columns.indexOf(col)
                        if (idx >= 0) args[arg] = row[idx]
                      }
                      onAction({ label: block.rowAction!.label, tool: block.rowAction!.tool, args })
                    }}
                  >
                    {block.rowAction.label}
                  </Button>
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

export function TimelineBlockView({ block }: { block: Timeline }) {
  return (
    <ol className="relative ml-2 space-y-3 border-l border-border">
      {block.events.map((e, i) => (
        <li key={`${e.at}-${i}`} className="ml-4">
          <span
            className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full"
            style={{ background: TONE_HEX[e.tone ?? 'neutral'] }}
          />
          <div className="flex flex-wrap items-center gap-2">
            <span className="num text-xs text-muted-foreground whitespace-nowrap">{e.at}</span>
            <span className="text-sm font-medium">{e.label}</span>
            <Badge variant="secondary">{e.kind}</Badge>
            {e.detail && <span className="text-helper">{e.detail}</span>}
          </div>
        </li>
      ))}
    </ol>
  )
}

/** Inline sparkline — an SVG polyline with an optional baseline. Small enough not to
 *  warrant a charting library instance per cell. */
function Sparkline({ values, baseline, tone }: {
  values: number[]; baseline?: number | null; tone?: Tone
}) {
  if (values.length < 2) return <div className="h-8" />
  const w = 120
  const h = 32
  const pad = 3
  const all = baseline != null ? [...values, baseline] : values
  const min = Math.min(...all)
  const max = Math.max(...all)
  const span = max - min || 1
  const yFor = (v: number) => pad + (1 - (v - min) / span) * (h - pad * 2)
  const points = values
    .map((v, i) => `${pad + (i / (values.length - 1)) * (w - pad * 2)},${yFor(v)}`)
    .join(' ')

  return (
    <svg width={w} height={h} role="img" aria-label={`Trend across ${values.length} points`}>
      {baseline != null && (
        <line x1={pad} x2={w - pad} y1={yFor(baseline)} y2={yFor(baseline)}
              stroke="#898781" strokeWidth={1} strokeDasharray="3 3" />
      )}
      <polyline points={points} fill="none" strokeWidth={1.75}
                stroke={TONE_HEX[tone ?? 'info']} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

export function SparklineGridView({ block }: { block: SparklineGrid }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {block.items.map((item) => (
        <div key={item.label} className="rounded-md border border-border/60 px-3 py-2">
          <p className="text-sm font-medium truncate">{item.label}</p>
          <Sparkline values={item.values} baseline={item.baseline} tone={item.tone} />
          {item.caption && (
            <p className={cn('text-xs', TONE_CLASS[item.tone ?? 'neutral'])}>{item.caption}</p>
          )}
        </div>
      ))}
    </div>
  )
}

export function ComparisonBlockView({
  block, onAction,
}: { block: Comparison; onAction: (action: ComposerAction) => void }) {
  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-40" />
              {block.columns.map((c) => (
                <TableHead key={c.label}
                           className={c.highlight ? 'text-primary font-medium' : undefined}>
                  {c.label}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {block.attributes.map((attr) => (
              <TableRow key={attr}>
                <TableCell className="text-label align-top">{attr}</TableCell>
                {block.columns.map((c) => (
                  <TableCell key={c.label}
                             className={cn('text-sm', c.highlight && 'bg-primary/5')}>
                    {c.values[attr] ?? '—'}
                  </TableCell>
                ))}
              </TableRow>
            ))}
            {block.columns.some((c) => c.note) && (
              <TableRow>
                <TableCell className="text-label align-top">Note</TableCell>
                {block.columns.map((c) => (
                  <TableCell key={c.label} className="text-helper">{c.note ?? '—'}</TableCell>
                ))}
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      {(block.actions ?? []).length > 0 && (
        <div className="flex flex-wrap gap-2">
          {block.actions!.map((a) => (
            <Button key={`${a.tool}-${a.label}`} size="sm" variant="secondary"
                    onClick={() => onAction(a)}>
              {a.label}
            </Button>
          ))}
        </div>
      )}
    </div>
  )
}
