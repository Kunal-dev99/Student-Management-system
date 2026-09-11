'use client'

/**
 * Renders a validated composition.
 *
 * The backend rejects any spec that fails its Pydantic models, so by the time a block
 * arrives here its shape is guaranteed. The one case worth handling is a block type this
 * build does not know about — a backend deployed ahead of the frontend. That renders as a
 * visible, honest placeholder rather than an empty gap or a crash.
 */

import { useState } from 'react'
import { ChevronRight, Database } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  ActionCardBlock, AlertBannerBlock, KpiRowBlock, NarrativeBlock,
} from './blocks/Structural'
import { BarChartBlock, DonutBlock, LineChartBlock } from './blocks/Charts'
import {
  ComparisonBlockView, SparklineGridView, TableBlockView, TimelineBlockView,
} from './blocks/DataDisplays'
import {
  GaugeBlockView, HeatmapBlockView, PieBlockView, RoadmapBlockView, TreeBlockView,
} from './blocks/Graphics'
import { Reveal } from './reveal'
import type { Block, ComposerAction, Composition } from './types'

function BlockBody({
  block, onAction,
}: { block: Block; onAction: (a: ComposerAction) => void }) {
  switch (block.type) {
    case 'kpi_row':       return <KpiRowBlock block={block} />
    case 'narrative':     return <NarrativeBlock block={block} />
    case 'alert_banner':  return <AlertBannerBlock block={block} />
    case 'action_card':   return <ActionCardBlock block={block} onAction={onAction} />
    case 'line_chart':    return <LineChartBlock block={block} />
    case 'bar_chart':     return <BarChartBlock block={block} />
    case 'stacked_bar':   return <BarChartBlock block={block} />
    case 'donut':         return <DonutBlock block={block} />
    case 'pie':           return <PieBlockView block={block} />
    case 'gauge':         return <GaugeBlockView block={block} />
    case 'table':         return <TableBlockView block={block} onAction={onAction} />
    case 'timeline':      return <TimelineBlockView block={block} />
    case 'sparkline_grid': return <SparklineGridView block={block} />
    case 'comparison':    return <ComparisonBlockView block={block} onAction={onAction} />
    case 'tree':          return <TreeBlockView block={block} />
    case 'roadmap':       return <RoadmapBlockView block={block} />
    case 'heatmap':       return <HeatmapBlockView block={block} />
    default:
      return (
        <p className="text-helper">
          This build cannot render a{' '}
          <span className="font-mono text-xs">{(block as { type: string }).type}</span> block.
        </p>
      )
  }
}

/** The alert and narrative blocks are their own container; everything else gets a heading. */
const BARE: ReadonlySet<string> = new Set(['alert_banner', 'narrative'])

function BlockShell({
  block, onAction,
}: { block: Block; onAction: (a: ComposerAction) => void }) {
  const bare = BARE.has(block.type) && !block.title
  if (bare) return <BlockBody block={block} onAction={onAction} />

  return (
    <section className="space-y-2">
      {block.title && (
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="text-sm font-medium">{block.title}</h3>
          {(block.source?.length ?? 0) > 0 && (
            <span
              className="text-[11px] text-muted-foreground font-mono shrink-0"
              title="Data functions that produced this block"
            >
              {/* The model tends to echo the full call including its arguments; the
                  function name is the useful part and a raw uuid is just noise. */}
              {[...new Set(block.source!.map((s) => s.split('(')[0]))].join(' · ')}
            </span>
          )}
        </div>
      )}
      <BlockBody block={block} onAction={onAction} />
    </section>
  )
}

export function CompositionView({
  composition, onAction, footer,
}: {
  composition: Composition
  onAction?: (a: ComposerAction) => void
  footer?: React.ReactNode
}) {
  const [showWhy, setShowWhy] = useState(false)
  const handle = onAction ?? (() => undefined)

  return (
    <article className="space-y-5">
      <header>
        <h2 className="text-lg font-semibold tracking-tight">{composition.title}</h2>
        {composition.subtitle && (
          <p className="text-helper mt-0.5">{composition.subtitle}</p>
        )}
      </header>

      {composition.blocks.map((block, i) => (
        <Reveal key={`${block.type}-${i}`} index={i}>
          <BlockShell block={block} onAction={handle} />
        </Reveal>
      ))}

      {composition.rationale && (
        <div className="pt-1">
          <button
            type="button"
            onClick={() => setShowWhy((v) => !v)}
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <ChevronRight className={cn('h-3 w-3 transition-transform', showWhy && 'rotate-90')} />
            <Database className="h-3 w-3" />
            Why this layout
          </button>
          {showWhy && (
            <p className="text-helper mt-1.5 pl-5">{composition.rationale}</p>
          )}
        </div>
      )}

      {footer}
    </article>
  )
}
