'use client'

/**
 * Structural graphics — tree, roadmap, heatmap, gauge, pie.
 *
 * Each is hand-rolled SVG or plain layout rather than a charting library call. Trees and
 * heatmaps do not have a well-fitting recharts primitive, and recharts adds no value for
 * roadmaps or single-value gauges. The cost of a library dependency here would be higher
 * than the code it replaces.
 */

import { PieChart, Pie as RPie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import { seriesColour, TONE_HEX, formatValue } from '../chartTheme'
import type {
  Gauge as GaugeBlock, Heatmap as HeatmapBlock, Pie as PieBlock,
  Roadmap, Tree, TreeEdge, TreeNode,
} from '../types'

/* ------------------------------------------------------------------- Tree */

interface Positioned extends TreeNode { x: number; y: number }

// Node box size. `NODE_W` sits either side of the pivot, so the actual rectangle is 2 ×
// this wide; edge start/end coordinates are adjusted for it so arrowheads reach the border
// rather than piling into the centre.
const NODE_W = 64
const NODE_H = 18
const MARGIN = 20

/**
 * Longest-path layering — the algorithm dagre and Graphviz use.
 *
 * Every node's layer is `1 + max(parent layer)`, iterated to a fixed point. A node with no
 * incoming edges sits at layer 0. This handles the shapes the composer actually produces:
 * multiple roots pointing at the same target (funding lineage), diamond dependencies, and
 * disconnected subgraphs. My previous BFS-once approach put nodes at the first depth it
 * saw them, which stranded siblings at layer 0 and caused the pileup you saw on screen.
 */
function layoutHierarchical(
  nodes: TreeNode[], edges: TreeEdge[], direction: 'down' | 'right',
): { positioned: Positioned[]; width: number; height: number } {
  const layer = new Map<string, number>()
  const parents = new Map<string, string[]>()
  for (const node of nodes) {
    layer.set(node.id, 0)
    parents.set(node.id, [])
  }
  for (const edge of edges) {
    const p = parents.get(edge.target)
    if (p && !p.includes(edge.source)) p.push(edge.source)
  }

  // Fixed-point relaxation. Cap iterations at nodes+2 — enough for the longest chain, and
  // a hard bound in case an accidental cycle sneaks through.
  for (let iter = 0; iter < nodes.length + 2; iter++) {
    let changed = false
    for (const node of nodes) {
      const parentLayers = (parents.get(node.id) ?? [])
        .map((p) => (layer.get(p) ?? 0) + 1)
      const desired = parentLayers.length === 0 ? 0 : Math.max(...parentLayers)
      if (desired !== layer.get(node.id)) {
        layer.set(node.id, desired)
        changed = true
      }
    }
    if (!changed) break
  }

  const byLayer = new Map<number, string[]>()
  for (const [id, l] of layer.entries()) {
    if (!byLayer.has(l)) byLayer.set(l, [])
    byLayer.get(l)!.push(id)
  }
  // Group nodes on the same layer by their group tag, so like nodes cluster together and
  // an aisle forms between differently-coloured columns.
  for (const [, ids] of byLayer.entries()) {
    ids.sort((a, b) => {
      const nodeA = nodes.find((n) => n.id === a)
      const nodeB = nodes.find((n) => n.id === b)
      return (nodeA?.group ?? '').localeCompare(nodeB?.group ?? '')
    })
  }

  const along = direction === 'down' ? 180 : 220    // one layer to the next
  const across = direction === 'down' ? 44 : 44     // sibling to sibling
  const depth = Math.max(...byLayer.keys()) + 1
  const widest = Math.max(...[...byLayer.values()].map((row) => row.length))

  const width = direction === 'down'
    ? Math.max(320, widest * (NODE_W * 2 + across) + MARGIN * 2)
    : depth * along + MARGIN * 2
  const height = direction === 'down'
    ? depth * along + MARGIN * 2
    : Math.max(200, widest * (NODE_H * 2 + across) + MARGIN * 2)

  const positioned: Positioned[] = []
  for (const [l, ids] of byLayer.entries()) {
    const laneCount = ids.length
    ids.forEach((id, index) => {
      const node = nodes.find((n) => n.id === id)!
      // Even distribution along the "across" axis, so a single node sits centred and
      // many nodes fill the available run.
      const laneCentre = ((index + 0.5) / laneCount)
      positioned.push(
        direction === 'down'
          ? { ...node,
              x: MARGIN + laneCentre * (width - MARGIN * 2),
              y: MARGIN + NODE_H + l * along }
          : { ...node,
              x: MARGIN + NODE_W + l * along,
              y: MARGIN + laneCentre * (height - MARGIN * 2) },
      )
    })
  }
  return { positioned, width, height }
}

/** Node-border intersection so arrowheads land on the box, not its centre. */
function trimToBox(
  from: { x: number; y: number }, to: { x: number; y: number },
): { x: number; y: number } {
  const dx = to.x - from.x
  const dy = to.y - from.y
  if (dx === 0 && dy === 0) return to
  const tX = dx !== 0 ? (NODE_W + 4) / Math.abs(dx) : Infinity
  const tY = dy !== 0 ? (NODE_H + 4) / Math.abs(dy) : Infinity
  const t = Math.min(tX, tY, 1)
  return { x: to.x - dx * t, y: to.y - dy * t }
}

/** Even circular layout for peer relationships. */
function layoutNetwork(
  nodes: TreeNode[],
): { positioned: Positioned[]; width: number; height: number } {
  const radius = 40 + nodes.length * 12
  const size = radius * 2 + 120
  return {
    width: size,
    height: size,
    positioned: nodes.map((node, i) => {
      const angle = (i / nodes.length) * Math.PI * 2 - Math.PI / 2
      return {
        ...node,
        x: size / 2 + radius * Math.cos(angle),
        y: size / 2 + radius * Math.sin(angle),
      }
    }),
  }
}

export function TreeBlockView({ block }: { block: Tree }) {
  const layout = block.layout ?? 'hierarchical'
  const direction = block.direction ?? 'down'
  const { positioned, width, height } =
    layout === 'network' ? layoutNetwork(block.nodes)
      : layoutHierarchical(block.nodes, block.edges, direction)
  const byId = new Map(positioned.map((n) => [n.id, n]))

  const groupColour = (group?: string | null): string => {
    if (!group) return '#888780'
    // Same colour for the same group across the diagram — the model chooses the
    // grouping, we assign the palette slot deterministically.
    let hash = 0
    for (const ch of group) hash = (hash * 31 + ch.charCodeAt(0)) & 0xffffffff
    return seriesColour(Math.abs(hash))
  }

  return (
    <div className="overflow-x-auto">
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}
           className="max-w-full h-auto">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5"
                  markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#888780" />
          </marker>
        </defs>
        {/* Edges draw first, so the structure is visible before the nodes populate it.
            Each edge gets its own delay — cascade left-to-right. */}
        {block.edges.map((edge, i) => {
          const from = byId.get(edge.source)
          const to = byId.get(edge.target)
          if (!from || !to) return null
          // Trim start and end back to the node borders so the arrowheads point
          // at the box, not the invisible centre.
          const start = trimToBox(to, from)
          const end = trimToBox(from, to)
          return (
            <g key={`edge-${i}`}>
              <line
                x1={start.x} y1={start.y} x2={end.x} y2={end.y}
                stroke={edge.tone ? TONE_HEX[edge.tone] : '#c3c2b7'}
                strokeWidth={1.5} markerEnd="url(#arrow)"
                className="composer-edge"
                style={{ animationDelay: `${120 + i * 80}ms` }}
              />
              {edge.label && (
                <text x={(from.x + to.x) / 2} y={(from.y + to.y) / 2 - 4}
                      textAnchor="middle" fontSize={10} fill="#898781"
                      className="composer-reveal"
                      style={{ animationDelay: `${350 + i * 80}ms`, animationDuration: '260ms' }}>
                  {edge.label}
                </text>
              )}
            </g>
          )
        })}
        {positioned.map((node, i) => {
          const fill = node.tone && node.tone !== 'neutral'
            ? TONE_HEX[node.tone]
            : groupColour(node.group)
          // Outer <g> owns the SVG position; inner <g> owns the CSS drop-in animation.
          // A CSS transform on the outer group would override the position attribute
          // and pile every node up at the origin — the bug in the last screenshot.
          return (
            <g key={node.id} transform={`translate(${node.x}, ${node.y})`}>
              <g className="composer-node" style={{ animationDelay: `${i * 90}ms` }}>
                <rect x={-NODE_W} y={-NODE_H} width={NODE_W * 2} height={NODE_H * 2} rx={6}
                      fill="hsl(var(--surface-1))" stroke={fill} strokeWidth={1.5} />
                <text textAnchor="middle" y={3} fontSize={10.5}
                      fill="hsl(var(--foreground))">
                  {node.label.length > 16 ? `${node.label.slice(0, 15)}…` : node.label}
                </text>
                {node.detail && (
                  <text textAnchor="middle" y={NODE_H + 12} fontSize={9.5} fill="#898781">
                    {node.detail.length > 20 ? `${node.detail.slice(0, 19)}…` : node.detail}
                  </text>
                )}
              </g>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

/* ------------------------------------------------------------------- Roadmap */

const ROADMAP_TONE: Record<Roadmap['steps'][number]['status'], {
  bg: string; ring: string; label: string
}> = {
  done:     { bg: 'bg-[hsl(var(--success))]',    ring: 'ring-[hsl(var(--success))]',    label: 'Done' },
  current:  { bg: 'bg-primary',                  ring: 'ring-primary',                  label: 'Now' },
  upcoming: { bg: 'bg-surface-3',                ring: 'ring-border',                   label: 'Upcoming' },
  at_risk:  { bg: 'bg-[hsl(var(--warning))]',    ring: 'ring-[hsl(var(--warning))]',    label: 'At risk' },
  missed:   { bg: 'bg-destructive',              ring: 'ring-destructive',              label: 'Missed' },
}

export function RoadmapBlockView({ block }: { block: Roadmap }) {
  return (
    <ol className="flex flex-wrap items-stretch gap-y-4">
      {block.steps.map((step, i) => {
        const tone = ROADMAP_TONE[step.status]
        const last = i === block.steps.length - 1
        return (
          <li key={i} className="flex items-center min-w-0 flex-1">
            <div className="flex flex-col items-center text-center min-w-0 flex-1">
              <span
                className={`composer-step h-8 w-8 rounded-full ${tone.bg} text-white flex items-center justify-center text-xs font-semibold ring-4 ring-offset-2 ring-offset-background ${tone.ring} ${tone.ring.replace('ring-', 'ring-opacity-20 ring-')}`}
                style={{ animationDelay: `${i * 120}ms` }}
              >
                {i + 1}
              </span>
              <div className="mt-2 min-w-0 px-1.5">
                <p className="text-sm font-medium truncate">{step.label}</p>
                {step.at && (
                  <p className="text-[11px] text-muted-foreground num">{step.at}</p>
                )}
                {step.detail && (
                  <p className="text-[11px] text-muted-foreground truncate">{step.detail}</p>
                )}
              </div>
            </div>
            {!last && (
              <div className="h-px flex-1 bg-border -mt-6 shrink-0 min-w-6" />
            )}
          </li>
        )
      })}
    </ol>
  )
}

/* ------------------------------------------------------------------- Heatmap */

/**
 * Interpolate between two hex colours in oklch-ish sRGB space. Good enough here — the
 * ramp is between the app's surface and its primary, so the sequential progression reads
 * naturally in both themes.
 */
function interpolate(hex1: string, hex2: string, t: number): string {
  const parse = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16))
  const [r1, g1, b1] = parse(hex1)
  const [r2, g2, b2] = parse(hex2)
  const r = Math.round(r1 + (r2 - r1) * t)
  const g = Math.round(g1 + (g2 - g1) * t)
  const b = Math.round(b1 + (b2 - b1) * t)
  return `rgb(${r}, ${g}, ${b})`
}

export function HeatmapBlockView({ block }: { block: HeatmapBlock }) {
  const map = new Map<string, number>()
  for (const cell of block.cells) map.set(`${cell.row}||${cell.column}`, cell.value)
  const values = block.cells.map((c) => c.value)
  const min = Math.min(...values, 0)
  const max = Math.max(...values, 1)
  const span = max - min || 1

  // Each cell reveals after a delay proportional to its (row, column) — the top-left
  // cell arrives first, the bottom-right last. Reads as a wash across the grid.
  const cell = (row: string, col: string, rIndex: number, cIndex: number) => {
    const key = `${row}||${col}`
    const value = map.get(key)
    const delay = 60 + rIndex * 40 + cIndex * 30
    if (value === undefined) {
      return (
        <div key={key} className="composer-cell h-9 border-r border-b border-border/40 bg-surface-2/40"
             style={{ animationDelay: `${delay}ms` }} />
      )
    }
    const t = (value - min) / span
    return (
      <div
        key={key}
        className="composer-cell h-9 border-r border-b border-border/40 flex items-center justify-center text-[11px] font-medium"
        style={{
          background: interpolate('#f5f0e7', '#c74634', t),
          color: t > 0.55 ? 'white' : 'hsl(var(--foreground))',
          animationDelay: `${delay}ms`,
        }}
        title={`${row} · ${col} · ${value}`}
      >
        {formatValue(value, block.unit)}
      </div>
    )
  }

  const columnCount = block.columns.length
  return (
    <div className="overflow-x-auto">
      <div className="inline-block min-w-full">
        <div
          className="grid"
          style={{
            gridTemplateColumns: `minmax(120px, auto) repeat(${columnCount}, minmax(52px, 1fr))`,
          }}
        >
          <div className="border-r border-b border-border/40 px-2 py-1.5" />
          {block.columns.map((col) => (
            <div
              key={col}
              className="border-r border-b border-border/40 px-1 py-1.5 text-center text-[11px] font-medium text-muted-foreground"
            >
              {col}
            </div>
          ))}
          {block.rows.map((row, rIndex) => (
            <div key={row} className="contents">
              <div className="border-r border-b border-border/40 px-2 py-1.5 text-xs font-medium truncate">
                {row}
              </div>
              {block.columns.map((col, cIndex) => cell(row, col, rIndex, cIndex))}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------- Gauge */

function unitSuffix(unit: GaugeBlock['unit']): string {
  switch (unit) {
    case 'percent': return '%'
    case 'months':  return ' months'
    case 'days':    return ' days'
    default:        return ''
  }
}

/**
 * Half-doughnut gauge.
 *
 * A single arc from `minimum` to `maximum` with the current `value` marked. If the model
 * supplied `thresholds`, the arc is banded (danger → warning → success) so the reader
 * sees which zone the value falls in without reading the number.
 */
export function GaugeBlockView({ block }: { block: GaugeBlock }) {
  const min = block.minimum ?? 0
  const max = block.maximum
  const clamped = Math.max(min, Math.min(max, block.value))
  const span = max - min || 1

  const zoneColours = ['#e24b4a', '#eda100', '#1baf7a']
  const stops = [min, ...(block.thresholds ?? []), max]
  const bands = []
  for (let i = 0; i < stops.length - 1; i++) {
    bands.push({
      name: `band-${i}`,
      value: Math.max(0, stops[i + 1] - stops[i]),
      fill: block.thresholds && block.thresholds.length > 0
        ? zoneColours[i] ?? '#c3c2b7'
        : '#c3c2b7',
    })
  }

  return (
    <div className="flex flex-wrap items-center gap-6">
      <div className="relative" style={{ width: 220, height: 130 }}>
        <ResponsiveContainer>
          <PieChart>
            <RPie
              data={bands} dataKey="value" cx="50%" cy="90%" innerRadius={68}
              outerRadius={98} startAngle={180} endAngle={0} paddingAngle={1} stroke="none"
            >
              {bands.map((b) => <Cell key={b.name} fill={b.fill} />)}
            </RPie>
            <RPie
              data={[{ value: clamped - min }, { value: max - clamped }]}
              dataKey="value" cx="50%" cy="90%" innerRadius={54} outerRadius={64}
              startAngle={180} endAngle={0} stroke="none"
            >
              <Cell fill="hsl(var(--foreground))" fillOpacity={0.9} />
              <Cell fill="transparent" />
            </RPie>
          </PieChart>
        </ResponsiveContainer>
        <div className="absolute inset-x-0 bottom-2 text-center pointer-events-none">
          <div className="text-2xl font-semibold num tracking-tight">
            {Math.round(clamped * 10) / 10}{unitSuffix(block.unit)}
          </div>
          {block.target !== null && block.target !== undefined && (
            <div className="text-[11px] text-muted-foreground num">
              target {block.target}{unitSuffix(block.unit)}
            </div>
          )}
        </div>
      </div>
      {block.label && (
        <p className="text-sm text-muted-foreground max-w-xs">{block.label}</p>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------- Pie */

export function PieBlockView({ block }: { block: PieBlock }) {
  const total = block.slices.reduce((sum, s) => sum + s.value, 0)
  return (
    <div className="flex flex-wrap items-center gap-6">
      <div style={{ width: 200, height: 200 }}>
        <ResponsiveContainer>
          <PieChart>
            <RPie data={block.slices} dataKey="value" nameKey="label"
                  outerRadius={90} stroke="hsl(var(--surface-1))" strokeWidth={2}>
              {block.slices.map((_, i) => <Cell key={i} fill={seriesColour(i)} />)}
            </RPie>
            <Tooltip
              contentStyle={{
                fontSize: 12, borderRadius: 8,
                border: '1px solid hsl(var(--border))',
                background: 'hsl(var(--popover))',
              }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <ul className="space-y-1.5 text-sm">
        {block.slices.map((s, i) => (
          <li key={s.label} className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-sm shrink-0"
                  style={{ background: seriesColour(i) }} />
            <span>{s.label}</span>
            <span className="num text-muted-foreground">
              {s.value.toLocaleString()}
              {total > 0 && ` · ${Math.round((s.value / total) * 100)}%`}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
