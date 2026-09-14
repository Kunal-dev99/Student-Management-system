'use client'

/**
 * Read-only workflow flowchart — states as boxes, transitions as labelled arrows.
 *
 * Layout follows the same convention as RelationshipGraph.tsx (research module):
 * a deterministic layered assignment, not a force simulation or external graph
 * library. Column = longest-path distance from the initial state (a simple,
 * stable topological layering); nodes within a column are stacked and sorted by
 * name so the same definition always draws the same picture. Self-loops and
 * back-edges (common in approval workflows — "rejected" looping back to
 * "draft") are drawn as curved connectors below their row rather than straight
 * lines crossing the whole diagram.
 */
import { useMemo } from 'react'
import { cn } from '@/lib/utils'

export interface DiagramTransition {
  from: string
  on: string
  to: string
}

export interface WorkflowDiagramProps {
  states: string[]
  transitions: DiagramTransition[]
  initialState?: string
  /** Highlights one node — e.g. a running instance's current state. */
  currentState?: string | null
  className?: string
}

const NODE_W = 148
const NODE_H = 40
const COL_GAP = 96
const ROW_GAP = 20
const PAD = 24

interface Placed { name: string; x: number; y: number; col: number }

function layout(states: string[], transitions: DiagramTransition[], initialState?: string) {
  const adjacency = new Map<string, string[]>()
  for (const s of states) adjacency.set(s, [])
  for (const t of transitions) {
    if (!adjacency.has(t.from)) adjacency.set(t.from, [])
    adjacency.get(t.from)!.push(t.to)
  }

  // Longest-path layering from the initial state via BFS — cycles are safe because a
  // state's column only ever increases, and a visited-at-this-depth guard stops re-queuing.
  const col = new Map<string, number>()
  const start = initialState && states.includes(initialState) ? initialState : states[0]
  if (start) {
    col.set(start, 0)
    const queue: string[] = [start]
    while (queue.length) {
      const cur = queue.shift()!
      const curCol = col.get(cur)!
      for (const next of adjacency.get(cur) ?? []) {
        const existing = col.get(next)
        if (existing === undefined || existing < curCol + 1) {
          // Avoid runaway growth on a tight cycle (e.g. a<->b) — cap relative to state count.
          if (curCol + 1 <= states.length) {
            col.set(next, curCol + 1)
            queue.push(next)
          }
        }
      }
    }
  }
  // Anything never reached from the initial state (orphaned/typo'd state) still needs a
  // column so it's visible rather than silently dropped.
  let maxCol = Math.max(0, ...Array.from(col.values()))
  for (const s of states) {
    if (!col.has(s)) { maxCol += 1; col.set(s, maxCol) }
  }

  const byCol = new Map<number, string[]>()
  for (const s of states) {
    const c = col.get(s)!
    if (!byCol.has(c)) byCol.set(c, [])
    byCol.get(c)!.push(s)
  }
  for (const arr of byCol.values()) arr.sort((a, b) => a.localeCompare(b))

  const placed: Placed[] = []
  const columns = Array.from(byCol.keys()).sort((a, b) => a - b)
  for (const c of columns) {
    const names = byCol.get(c)!
    names.forEach((name, i) => {
      placed.push({
        name, col: c,
        x: PAD + c * (NODE_W + COL_GAP),
        y: PAD + i * (NODE_H + ROW_GAP),
      })
    })
  }
  const byName = new Map(placed.map((p) => [p.name, p]))
  const width = PAD * 2 + (columns.length) * NODE_W + Math.max(0, columns.length - 1) * COL_GAP
  const height = PAD * 2 + Math.max(...Array.from(byCol.values()).map((a) => a.length)) * (NODE_H + ROW_GAP) - ROW_GAP
  return { placed, byName, width: Math.max(width, NODE_W + PAD * 2), height: Math.max(height, NODE_H + PAD * 2) }
}

export function WorkflowDiagram({ states, transitions, initialState, currentState, className }: WorkflowDiagramProps) {
  const { placed, byName, width, height } = useMemo(
    () => layout(states, transitions, initialState),
    [states, transitions, initialState],
  )

  if (states.length === 0) return null

  return (
    <div className={cn('overflow-x-auto rounded-md border border-border/60 bg-surface-2/30 p-3', className)}>
      <svg width={width} height={height} className="block" role="img" aria-label="Workflow diagram">
        <defs>
          <marker id="wf-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="hsl(var(--muted-foreground))" />
          </marker>
        </defs>

        {transitions.map((t, i) => {
          const from = byName.get(t.from)
          const to = byName.get(t.to)
          if (!from || !to) return null

          if (from.name === to.name) {
            // Self-loop: a small arc above the node.
            const x = from.x + NODE_W / 2
            const y = from.y
            return (
              <g key={i}>
                <path
                  d={`M ${x - 18} ${y} C ${x - 18} ${y - 22}, ${x + 18} ${y - 22}, ${x + 18} ${y}`}
                  fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth={1.25}
                  markerEnd="url(#wf-arrow)"
                />
                <text x={x} y={y - 24} textAnchor="middle" className="fill-muted-foreground" fontSize={10}>
                  {t.on}
                </text>
              </g>
            )
          }

          const forward = to.col >= from.col
          const sx = forward ? from.x + NODE_W : from.x
          const sy = from.y + NODE_H / 2
          const ex = forward ? to.x : to.x + NODE_W
          const ey = to.y + NODE_H / 2
          const sameRow = from.y === to.y
          // Back-edges (to an earlier column, e.g. a rejection returning to draft) bow
          // downward below the row so they never overlap the forward-flow arrows.
          const bow = forward ? 0 : Math.max(28, Math.abs(ey - sy) === 0 ? 36 : 0)
          const midY = sameRow && !forward ? sy + bow : (sy + ey) / 2
          const path = sameRow
            ? `M ${sx} ${sy} C ${sx + (forward ? 40 : -40)} ${midY}, ${ex + (forward ? -40 : 40)} ${midY}, ${ex} ${ey}`
            : `M ${sx} ${sy} C ${(sx + ex) / 2} ${sy}, ${(sx + ex) / 2} ${ey}, ${ex} ${ey}`
          const labelX = sameRow ? (sx + ex) / 2 : (sx + ex) / 2
          const labelY = sameRow ? midY - 6 : (sy + ey) / 2 - 6

          return (
            <g key={i}>
              <path d={path} fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth={1.25} markerEnd="url(#wf-arrow)" />
              <rect x={labelX - t.on.length * 3 - 4} y={labelY - 10} width={t.on.length * 6 + 8} height={14} rx={3}
                    className="fill-surface-2" />
              <text x={labelX} y={labelY} textAnchor="middle" className="fill-muted-foreground" fontSize={10}>
                {t.on}
              </text>
            </g>
          )
        })}

        {placed.map((p) => {
          const isCurrent = currentState === p.name
          const isInitial = initialState === p.name
          return (
            <g key={p.name}>
              <rect
                x={p.x} y={p.y} width={NODE_W} height={NODE_H} rx={8}
                className={cn(
                  'stroke-border',
                  isCurrent ? 'fill-primary' : 'fill-background',
                )}
                strokeWidth={isInitial ? 2 : 1}
                stroke={isInitial ? 'hsl(var(--primary))' : undefined}
              />
              <text
                x={p.x + NODE_W / 2} y={p.y + NODE_H / 2 + 4} textAnchor="middle"
                fontSize={12} fontWeight={isCurrent ? 600 : 500}
                className={isCurrent ? 'fill-primary-foreground' : 'fill-foreground'}
              >
                {p.name.length > 18 ? `${p.name.slice(0, 17)}…` : p.name}
              </text>
            </g>
          )
        })}
      </svg>
      <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
        <span className="inline-flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded-sm border-2 border-primary" /> initial state
        </span>
        {currentState && (
          <span className="inline-flex items-center gap-1">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-primary" /> current state
          </span>
        )}
      </div>
    </div>
  )
}
