/**
 * Chart theming.
 *
 * Recharts draws into SVG, so it can read CSS custom properties at render time — but only
 * for values it passes straight through to `fill`/`stroke`. Anything recharts computes
 * with (tick colours it interpolates, for instance) needs a resolved value, so the series
 * palette is literal hex.
 *
 * The palette deliberately does not cycle a rainbow: series 1 carries the answer, and
 * everything after it is context. Reference series render dashed and recessive, which is
 * how a target line or a cohort median should read.
 */

import type { Tone, ValueFormat } from './types'

/** Fixed order, never shuffled — colour follows the entity, not its rank. */
export const SERIES_COLOURS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100'] as const

export const TONE_HEX: Record<Tone, string> = {
  neutral: '#888780',
  info: '#2a78d6',
  success: '#1baf7a',
  warning: '#eda100',
  danger: '#e24b4a',
}

/** Tailwind classes for tone-coloured text/borders, resolved through the app's tokens. */
export const TONE_CLASS: Record<Tone, string> = {
  neutral: 'text-muted-foreground',
  info: 'text-[hsl(var(--info))]',
  success: 'text-[hsl(var(--success))]',
  warning: 'text-[hsl(var(--warning))]',
  danger: 'text-destructive',
}

export const TONE_SURFACE: Record<Tone, string> = {
  neutral: 'border-border bg-surface-2',
  info: 'border-[hsl(var(--info)/0.3)] bg-[hsl(var(--info)/0.08)]',
  success: 'border-[hsl(var(--success)/0.3)] bg-[hsl(var(--success)/0.08)]',
  warning: 'border-[hsl(var(--warning)/0.35)] bg-[hsl(var(--warning)/0.08)]',
  danger: 'border-destructive/35 bg-destructive/8',
}

export function seriesColour(index: number): string {
  return SERIES_COLOURS[index % SERIES_COLOURS.length]
}

/**
 * Axis and tooltip values. `currency` has no symbol because the composer does not
 * guarantee one currency per chart — the block title carries it when it matters.
 */
export function formatValue(
  value: number | null | undefined,
  // Heatmap and gauge speak in days too; accepting a superset keeps one number formatter.
  format?: ValueFormat | 'days',
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  switch (format) {
    case 'currency':
      return Math.abs(value) >= 1000
        ? `${(value / 1000).toFixed(value % 1000 === 0 ? 0 : 1)}k`
        : value.toLocaleString(undefined, { maximumFractionDigits: 0 })
    case 'percent':
      return `${Math.round(value)}%`
    case 'months':
      return `${Math.round(value)}m`
    case 'days':
      return `${Math.round(value)}d`
    default:
      return value.toLocaleString(undefined, { maximumFractionDigits: 2 })
  }
}

/** Recharts wants row-oriented data; blocks arrive column-oriented. */
export function toRows(
  x: string[],
  series: { name: string; values: (number | null)[] }[],
): Record<string, string | number | null>[] {
  return x.map((label, i) => {
    const row: Record<string, string | number | null> = { x: label }
    for (const s of series) row[s.name] = s.values[i] ?? null
    return row
  })
}

export const AXIS_TICK = { fontSize: 11, fill: '#898781' } as const
export const GRID_STROKE = 'hsl(var(--border))'
