'use client'

/**
 * Relationship graph (Phase 7 R5) — Person ↔ Research ↔ Supervisor ↔ Award ↔ Funding.
 *
 * Layout is a **deterministic layered assignment**, not a force simulation: each
 * `kind` owns a fixed column (funder → award → funding → project → student →
 * supervisor) and nodes are spread evenly down their column in a stable sort
 * order. That means no new dependency, no animation cost, and — the point —
 * the same data always draws the same picture, so a screenshot of this graph
 * is evidence rather than a snapshot of a random seed.
 */

import { useCallback, useId, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { AlertTriangle, ArrowUpRight, ChevronDown, ChevronRight, Network, X } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ApiError } from '@/shared/api/client'
import { useCan } from '@/shared/auth/Can'
import {
  useRelationshipGraph,
  type GraphEdge, type GraphNode, type GraphNodeKind, type GraphParams,
} from './api'

/* ------------------------------------------------------------------ *
 * Layout constants — the whole geometry is derived from these.
 * ------------------------------------------------------------------ */

/** Column order, left to right. Money flows in, people come out. */
const COLUMN_ORDER: GraphNodeKind[] = [
  'funder', 'award', 'opportunity', 'funding', 'project', 'student', 'supervisor',
]

const KIND_LABEL: Record<GraphNodeKind, string> = {
  funder: 'Funder',
  award: 'Award',
  opportunity: 'Opportunity',
  funding: 'Funding',
  project: 'Project',
  student: 'Student',
  supervisor: 'Supervisor',
}

/** One semantic token per kind, so the legend and the nodes cannot drift apart. */
const KIND_VAR: Record<GraphNodeKind, string> = {
  funder: '--warning',
  award: '--accent',
  opportunity: '--info',
  funding: '--success',
  project: '--primary',
  student: '--primary',
  supervisor: '--muted-foreground',
}

const NODE_W = 176
const NODE_H = 46
const COL_GAP = 104
const ROW_GAP = 24
const PAD = 20

interface Placed extends GraphNode {
  x: number
  y: number
}

interface Layout {
  placed: Placed[]
  byId: Map<string, Placed>
  columns: GraphNodeKind[]
  width: number
  height: number
}

/**
 * Pure function of the node list — no state, no randomness, no measurement.
 * Empty columns are skipped so the drawing stays compact, and nodes are sorted
 * by (label, id) so the vertical order is stable across refetches even if the
 * backend's insertion order changes.
 */
function layout(nodes: GraphNode[]): Layout {
  const columns = COLUMN_ORDER.filter((k) => nodes.some((n) => n.kind === k))
  const rowPitch = NODE_H + ROW_GAP

  const buckets = columns.map((kind) =>
    nodes
      .filter((n) => n.kind === kind)
      .sort((a, b) => a.label.localeCompare(b.label) || a.id.localeCompare(b.id)),
  )

  const tallest = buckets.reduce((m, b) => Math.max(m, b.length), 0)
  const contentH = Math.max(rowPitch * tallest - ROW_GAP, NODE_H)

  const placed: Placed[] = []
  buckets.forEach((bucket, col) => {
    const colH = rowPitch * bucket.length - ROW_GAP
    const top = PAD + (contentH - colH) / 2
    bucket.forEach((n, row) => {
      placed.push({ ...n, x: PAD + col * (NODE_W + COL_GAP), y: top + row * rowPitch })
    })
  })

  return {
    placed,
    byId: new Map(placed.map((p) => [p.id, p])),
    columns,
    width: PAD * 2 + Math.max(columns.length, 1) * NODE_W + Math.max(columns.length - 1, 0) * COL_GAP,
    height: PAD * 2 + contentH,
  }
}

/**
 * A horizontal S-curve between the facing edges of two boxes. Control points sit
 * at the horizontal midpoint, which makes the curve's own midpoint the plain
 * average of the endpoints — that is where the edge label goes.
 */
function edgeGeometry(from: Placed, to: Placed) {
  const rightwards = to.x >= from.x
  const sx = rightwards ? from.x + NODE_W : from.x
  const tx = rightwards ? to.x : to.x + NODE_W
  const sy = from.y + NODE_H / 2
  const ty = to.y + NODE_H / 2
  const mx = (sx + tx) / 2
  return {
    d: `M ${sx} ${sy} C ${mx} ${sy}, ${mx} ${ty}, ${tx} ${ty}`,
    labelX: mx,
    labelY: (sy + ty) / 2,
  }
}

function truncate(text: string, max: number) {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

function NodeBox({
  node, onSelect, selectedId, inLineage, dimmed,
}: {
  node: Placed
  onSelect: (id: string) => void
  selectedId: string | null
  inLineage: boolean
  dimmed: boolean
}) {
  const color = `hsl(var(${KIND_VAR[node.kind]}))`
  const sub = [node.sub, node.status?.replace(/_/g, ' ')].filter(Boolean).join(' · ')
  const isSelected = selectedId === node.id
  // While a selection exists, non-lineage nodes fade; the selected node itself gets a ring.
  const opacity = dimmed ? 0.18 : 1
  const strokeOpacity = isSelected ? 1 : inLineage ? 0.85 : 0.45
  const strokeWidth = isSelected ? 2.5 : inLineage ? 1.5 : 1
  return (
    <g
      transform={`translate(${node.x}, ${node.y})`}
      className="cursor-pointer transition-opacity"
      style={{ opacity }}
      role="button"
      tabIndex={0}
      onClick={(e) => { e.stopPropagation(); onSelect(node.id) }}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(node.id) }
      }}
    >
      <title>{`${KIND_LABEL[node.kind]}: ${node.label}${sub ? ` (${sub})` : ''}`}</title>
      {isSelected && (
        <rect
          x={-3} y={-3}
          width={NODE_W + 6} height={NODE_H + 6}
          rx={9}
          style={{ fill: 'none', stroke: color, strokeWidth: 2, strokeOpacity: 0.35 }}
        />
      )}
      <rect
        width={NODE_W}
        height={NODE_H}
        rx={6}
        style={{
          fill: 'hsl(var(--surface-1))',
          stroke: color,
          strokeOpacity,
          strokeWidth,
        }}
      />
      <path
        d={`M 6 0 H 3 A 3 3 0 0 0 0 3 V ${NODE_H - 3} A 3 3 0 0 0 3 ${NODE_H} H 6 Z`}
        style={{ fill: color }}
      />
      <text
        x={14}
        y={sub ? 20 : 27}
        style={{ fill: 'hsl(var(--foreground))', fontSize: 11.5, fontWeight: 500 }}
      >
        {truncate(node.label, 24)}
      </text>
      {sub && (
        <text x={14} y={34} style={{ fill: 'hsl(var(--muted-foreground))', fontSize: 9.5 }}>
          {truncate(sub, 28)}
        </text>
      )}
    </g>
  )
}

function EdgePath({
  edge, from, to, markerId, markerHighlightId, highlighted, dimmed,
}: {
  edge: GraphEdge
  from: Placed
  to: Placed
  markerId: string
  markerHighlightId: string
  highlighted: boolean
  dimmed: boolean
}) {
  const { d, labelX, labelY } = edgeGeometry(from, to)
  const label = edge.label.replace(/_/g, ' ')
  const w = label.length * 5.2 + 8
  const opacity = dimmed ? 0.15 : 1
  const strokeColor = highlighted ? 'hsl(var(--primary))' : 'hsl(var(--border))'
  const strokeWidth = highlighted ? 2 : 1.25
  return (
    <g style={{ opacity }} className="transition-opacity">
      <path
        d={d}
        fill="none"
        markerEnd={`url(#${highlighted ? markerHighlightId : markerId})`}
        style={{ stroke: strokeColor, strokeWidth }}
      />
      <rect
        x={labelX - w / 2}
        y={labelY - 7}
        width={w}
        height={14}
        rx={3}
        style={{ fill: 'hsl(var(--background))', fillOpacity: 0.92 }}
      />
      <text
        x={labelX}
        y={labelY + 3.5}
        textAnchor="middle"
        style={{
          fill: highlighted ? 'hsl(var(--primary))' : 'hsl(var(--muted-foreground))',
          fontSize: 9,
          fontWeight: highlighted ? 500 : 400,
        }}
      >
        {label}
      </text>
    </g>
  )
}

function Legend({ kinds }: { kinds: GraphNodeKind[] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
      {kinds.map((k) => (
        <span key={k} className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
          <span
            className="h-2.5 w-2.5 rounded-sm"
            style={{ backgroundColor: `hsl(var(${KIND_VAR[k]}))` }}
            aria-hidden
          />
          {KIND_LABEL[k]}
        </span>
      ))}
    </div>
  )
}

export interface RelationshipGraphProps extends GraphParams {
  /** Panel heading — defaults differ for the centred and the overview views. */
  title?: string
  description?: string
  /** Start folded away (the student record is long enough already). */
  defaultOpen?: boolean
}

export function RelationshipGraph({
  studentId,
  awardId,
  limit,
  title,
  description,
  defaultOpen = true,
}: RelationshipGraphProps) {
  const router = useRouter()
  const idBase = useId().replace(/:/g, '')
  const markerId = `rg-arrow-${idBase}`
  const markerHighlightId = `rg-arrow-hl-${idBase}`
  const [open, setOpen] = useState(defaultOpen)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  // Nothing is fetched while the panel is folded away, and never without the
  // student.read the graph endpoint requires.
  const canRead = useCan('student.read')
  const { data, isLoading, isError, error } = useRelationshipGraph({
    studentId, awardId, limit, enabled: open && canRead,
  })

  const nodes = useMemo(() => data?.nodes ?? [], [data])
  const view = useMemo(() => layout(nodes), [nodes])

  const forbidden = (error as ApiError | null)?.status === 403
  const edges = useMemo(
    () => (data?.edges ?? []).filter(
      (e) => view.byId.has(e.source) && view.byId.has(e.target),
    ),
    [data, view.byId],
  )

  // Lineage = the DIRECTED chain the selected node sits on:
  //   • downstream = every node reachable by following edges source → target
  //   • upstream   = every node reachable by following edges target → source
  // The union is exactly the ancestry + descendants of the selection, NOT the whole
  // connected component. That's the difference between "here is Alice's specific funding
  // lineage" and "here is everyone in Alice's blob".
  const lineageIds = useMemo(() => {
    if (!selectedId) return new Set<string>()
    const forward = new Map<string, string[]>()
    const backward = new Map<string, string[]>()
    for (const e of edges) {
      if (!forward.has(e.source)) forward.set(e.source, [])
      if (!backward.has(e.target)) backward.set(e.target, [])
      forward.get(e.source)!.push(e.target)
      backward.get(e.target)!.push(e.source)
    }
    const walk = (adj: Map<string, string[]>) => {
      const seen = new Set<string>([selectedId])
      const queue = [selectedId]
      while (queue.length) {
        const id = queue.shift()!
        for (const n of adj.get(id) ?? []) {
          if (!seen.has(n)) { seen.add(n); queue.push(n) }
        }
      }
      return seen
    }
    const down = walk(forward)
    const up = walk(backward)
    return new Set<string>([...down, ...up])
  }, [selectedId, edges])

  // Edges are highlighted only if BOTH endpoints are in the lineage AND at least one
  // of them is on the actual path — i.e., the edge participates in the chain.
  const lineageEdgeKey = useMemo(() => {
    const s = new Set<string>()
    if (!selectedId) return s
    for (const e of edges) {
      if (lineageIds.has(e.source) && lineageIds.has(e.target)) {
        s.add(`${e.source}->${e.target}`)
      }
    }
    return s
  }, [edges, lineageIds, selectedId])

  const handleSelect = useCallback((id: string) => {
    setSelectedId((prev) => (prev === id ? null : id))
  }, [])

  const selectedNode = selectedId ? view.byId.get(selectedId) : undefined

  return (
    <PageSection
      icon={Network}
      title={title ?? (studentId ? 'Relationship map' : 'Research relationship map')}
      accent="accent"
      description={
        description ??
        'Funder, award, funding, project, student and supervisor drawn as one picture, so connections that live across six tables can be read at a glance.'
      }
      actions={
        <Button variant="ghost" size="sm" onClick={() => setOpen((o) => !o)}>
          {open ? <ChevronDown className="h-4 w-4 mr-1" /> : <ChevronRight className="h-4 w-4 mr-1" />}
          {open ? 'Hide' : 'Show'}
        </Button>
      }
    >
      {!open ? (
        <p className="text-helper">Map hidden.</p>
      ) : isLoading ? (
        <Skeleton className="h-56 w-full" />
      ) : forbidden ? (
        <div className="rounded-md border border-[hsl(var(--warning)/0.3)] bg-[hsl(var(--warning)/0.1)] px-3 py-2 flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0 text-[hsl(var(--warning))]" />
          <div>
            <p className="text-sm font-medium text-[hsl(var(--warning))]">
              You do not have permission to see this map
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">
              The map is built from student records, so it needs the{' '}
              <span className="font-mono">student.read</span> permission and only ever shows
              students already in your row scope. Ask an administrator to add it to your role.
            </p>
          </div>
        </div>
      ) : isError ? (
        <p className="text-sm text-[hsl(var(--destructive))]">
          {(error as ApiError)?.message}{' '}
          <span className="font-mono text-xs text-muted-foreground">
            ({(error as ApiError)?.requestId})
          </span>
        </p>
      ) : nodes.length === 0 ? (
        <div className="rounded-md border border-dashed border-border px-3 py-6 text-center">
          <Network className="h-5 w-5 mx-auto text-muted-foreground" aria-hidden />
          <p className="text-sm mt-2">{data?.note ?? 'Nothing in scope to draw.'}</p>
          <p className="text-helper mt-0.5">
            {studentId
              ? 'This student has no project, supervisor or active funding recorded yet.'
              : 'No students are visible in your scope, so there is nothing to connect.'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Legend kinds={view.columns} />
            {selectedNode ? (
              <div className="flex items-center gap-2 text-xs">
                <span className="text-muted-foreground">Lineage:</span>
                <span className="font-medium">{selectedNode.label}</span>
                <span className="text-muted-foreground">
                  · {lineageIds.size} connected node{lineageIds.size === 1 ? '' : 's'}
                </span>
                {selectedNode.link && (
                  <Button size="sm" variant="secondary"
                          onClick={() => router.push(selectedNode.link!)}>
                    Open record <ArrowUpRight className="ml-1 h-3 w-3" />
                  </Button>
                )}
                <Button size="sm" variant="ghost" onClick={() => setSelectedId(null)}>
                  <X className="h-3 w-3 mr-1" /> Clear
                </Button>
              </div>
            ) : (
              <span className="text-helper">Click a node to trace its full lineage.</span>
            )}
          </div>
          <div
            className="overflow-x-auto rounded-md border border-border bg-surface-2/40"
            onClick={() => setSelectedId(null)}
          >
            <svg
              width={view.width}
              height={view.height}
              viewBox={`0 0 ${view.width} ${view.height}`}
              role="img"
              aria-label="Research relationship map"
              className="block"
              onClick={(e) => e.stopPropagation()}
            >
              <defs>
                <marker
                  id={markerId}
                  viewBox="0 0 8 8"
                  refX={7}
                  refY={4}
                  markerWidth={6}
                  markerHeight={6}
                  orient="auto-start-reverse"
                >
                  <path d="M 0 1 L 7 4 L 0 7 z" style={{ fill: 'hsl(var(--border))' }} />
                </marker>
                <marker
                  id={markerHighlightId}
                  viewBox="0 0 8 8"
                  refX={7}
                  refY={4}
                  markerWidth={6}
                  markerHeight={6}
                  orient="auto-start-reverse"
                >
                  <path d="M 0 1 L 7 4 L 0 7 z" style={{ fill: 'hsl(var(--primary))' }} />
                </marker>
              </defs>
              {/* Edges first so nodes always sit on top of them. */}
              {edges.map((e, i) => {
                const inLineage = lineageEdgeKey.has(`${e.source}->${e.target}`)
                return (
                  <EdgePath
                    key={`${e.source}->${e.target}:${e.label}:${i}`}
                    edge={e}
                    from={view.byId.get(e.source)!}
                    to={view.byId.get(e.target)!}
                    markerId={markerId}
                    markerHighlightId={markerHighlightId}
                    highlighted={inLineage}
                    dimmed={!!selectedId && !inLineage}
                  />
                )
              })}
              {view.placed.map((n) => {
                const inLineage = lineageIds.has(n.id)
                return (
                  <NodeBox
                    key={n.id}
                    node={n}
                    onSelect={handleSelect}
                    selectedId={selectedId}
                    inLineage={inLineage}
                    dimmed={!!selectedId && !inLineage}
                  />
                )
              })}
            </svg>
          </div>
          <p className="text-helper num">
            {data?.counts
              ? `${data.counts.nodes} node${data.counts.nodes === 1 ? '' : 's'} · ${data.counts.edges} connection${data.counts.edges === 1 ? '' : 's'} · ${data.counts.students} student${data.counts.students === 1 ? '' : 's'} in scope`
              : `${nodes.length} nodes · ${edges.length} connections`}
            . Layered layout — a node&apos;s position is fixed by its kind, so the picture does
            not move between refreshes. Click any node to trace its lineage; click again or
            outside to clear.
          </p>
        </div>
      )}
    </PageSection>
  )
}
