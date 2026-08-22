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

import { useId, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { AlertTriangle, ChevronDown, ChevronRight, Network } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ApiError } from '@/shared/api/client'
import {
  useRelationshipGraph,
  type GraphEdge, type GraphNode, type GraphNodeKind, type GraphParams,
} from './api'

/* ------------------------------------------------------------------ *
 * Layout constants — the whole geometry is derived from these.
 * ------------------------------------------------------------------ */

/** Column order, left to right. Money flows in, people come out. */
const COLUMN_ORDER: GraphNodeKind[] = [
  'funder', 'award', 'funding', 'project', 'student', 'supervisor',
]

const KIND_LABEL: Record<GraphNodeKind, string> = {
  funder: 'Funder',
  award: 'Award',
  funding: 'Funding',
  project: 'Project',
  student: 'Student',
  supervisor: 'Supervisor',
}

/** One semantic token per kind, so the legend and the nodes cannot drift apart. */
const KIND_VAR: Record<GraphNodeKind, string> = {
  funder: '--warning',
  award: '--accent',
  funding: '--success',
  project: '--info',
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

function NodeBox({ node, onOpen }: { node: Placed; onOpen: (link: string) => void }) {
  const color = `hsl(var(${KIND_VAR[node.kind]}))`
  const clickable = !!node.link
  const sub = [node.sub, node.status?.replace(/_/g, ' ')].filter(Boolean).join(' · ')
  return (
    <g
      transform={`translate(${node.x}, ${node.y})`}
      className={clickable ? 'cursor-pointer' : undefined}
      role={clickable ? 'link' : undefined}
      tabIndex={clickable ? 0 : undefined}
      onClick={clickable ? () => onOpen(node.link!) : undefined}
      onKeyDown={
        clickable
          ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen(node.link!) } }
          : undefined
      }
    >
      <title>{`${KIND_LABEL[node.kind]}: ${node.label}${sub ? ` (${sub})` : ''}`}</title>
      <rect
        width={NODE_W}
        height={NODE_H}
        rx={6}
        style={{ fill: 'hsl(var(--surface-1))', stroke: color, strokeOpacity: 0.45 }}
      />
      {/* Kind rail — the same colour as the legend swatch. */}
      <path
        d={`M 6 0 H 3 A 3 3 0 0 0 0 3 V ${NODE_H - 3} A 3 3 0 0 0 3 ${NODE_H} H 6 Z`}
        style={{ fill: color }}
      />
      <text
        x={14}
        y={sub ? 20 : 27}
        style={{ fill: 'hsl(var(--foreground))', fontSize: 11.5, fontWeight: 500 }}
        className={clickable ? 'underline-offset-2 group-hover:underline' : undefined}
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
  edge, from, to, markerId,
}: { edge: GraphEdge; from: Placed; to: Placed; markerId: string }) {
  const { d, labelX, labelY } = edgeGeometry(from, to)
  const label = edge.label.replace(/_/g, ' ')
  const w = label.length * 5.2 + 8
  return (
    <g>
      <path
        d={d}
        fill="none"
        markerEnd={`url(#${markerId})`}
        style={{ stroke: 'hsl(var(--border))', strokeWidth: 1.25 }}
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
        style={{ fill: 'hsl(var(--muted-foreground))', fontSize: 9 }}
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
  const markerId = `rg-arrow-${useId().replace(/:/g, '')}`
  const [open, setOpen] = useState(defaultOpen)
  // Nothing is fetched while the panel is folded away.
  const { data, isLoading, isError, error } = useRelationshipGraph({
    studentId, awardId, limit, enabled: open,
  })

  const nodes = useMemo(() => data?.nodes ?? [], [data])
  const view = useMemo(() => layout(nodes), [nodes])

  const forbidden = (error as ApiError | null)?.status === 403
  const edges = (data?.edges ?? []).filter(
    (e) => view.byId.has(e.source) && view.byId.has(e.target),
  )

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
          <Legend kinds={view.columns} />
          <div className="overflow-x-auto rounded-md border border-border bg-surface-2/40">
            <svg
              width={view.width}
              height={view.height}
              viewBox={`0 0 ${view.width} ${view.height}`}
              role="img"
              aria-label="Research relationship map"
              className="block"
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
              </defs>
              {/* Edges first so nodes always sit on top of them. */}
              {edges.map((e, i) => (
                <EdgePath
                  key={`${e.source}->${e.target}:${e.label}:${i}`}
                  edge={e}
                  from={view.byId.get(e.source)!}
                  to={view.byId.get(e.target)!}
                  markerId={markerId}
                />
              ))}
              {view.placed.map((n) => (
                <NodeBox key={n.id} node={n} onOpen={(link) => router.push(link)} />
              ))}
            </svg>
          </div>
          <p className="text-helper num">
            {data?.counts
              ? `${data.counts.nodes} node${data.counts.nodes === 1 ? '' : 's'} · ${data.counts.edges} connection${data.counts.edges === 1 ? '' : 's'} · ${data.counts.students} student${data.counts.students === 1 ? '' : 's'} in scope`
              : `${nodes.length} nodes · ${edges.length} connections`}
            . Layered layout — a node&apos;s position is fixed by its kind, so the picture does not
            move between refreshes. Nodes with a record open it when clicked.
          </p>
        </div>
      )}
    </PageSection>
  )
}
