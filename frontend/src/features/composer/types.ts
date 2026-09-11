/**
 * Mirrors `backend/app/modules/composer/blocks.py`.
 *
 * The backend validates against its Pydantic models before anything reaches here, so a
 * renderer can trust the shape it receives. These types exist to keep the two sides
 * honest at compile time — when a block gains a field there, it must gain one here.
 */

export type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger'

export interface BlockBase {
  title?: string | null
  /** Data functions that produced this block — drives the provenance disclosure. */
  source?: string[]
}

export interface KpiItem {
  label: string
  value: string | number
  delta?: string | null
  tone?: Tone
  hint?: string | null
}
export interface KpiRow extends BlockBase {
  type: 'kpi_row'
  items: KpiItem[]
}

export interface Narrative extends BlockBase {
  type: 'narrative'
  body: string
  tone?: Tone
}

export interface AlertBanner extends BlockBase {
  type: 'alert_banner'
  body: string
  tone?: Tone
}

export interface ComposerAction {
  label: string
  /** Names a staged write. Pressing it opens a confirmation; nothing executes inline. */
  tool: string
  args?: Record<string, unknown>
  tone?: Tone
}
export interface ActionCard extends BlockBase {
  type: 'action_card'
  body?: string | null
  actions: ComposerAction[]
}

export type SeriesStyle = 'solid' | 'dashed' | 'reference'
export interface Series {
  name: string
  /** null breaks the line — "no data beyond here", never zero. */
  values: (number | null)[]
  style?: SeriesStyle
}
export type ValueFormat = 'number' | 'currency' | 'percent' | 'months'

export interface Marker {
  at: string
  label: string
  tone?: Tone
}
export interface Band {
  fromX: string
  toX: string
  label?: string | null
  tone?: Tone
}

export interface LineChart extends BlockBase {
  type: 'line_chart'
  x: string[]
  series: Series[]
  xLabel?: string | null
  yLabel?: string | null
  yFormat?: ValueFormat
  markers?: Marker[]
  bands?: Band[]
}

export interface BarChart extends BlockBase {
  type: 'bar_chart'
  x: string[]
  series: Series[]
  orientation?: 'vertical' | 'horizontal'
  xLabel?: string | null
  yLabel?: string | null
  yFormat?: ValueFormat
}

export interface StackedBar extends BlockBase {
  type: 'stacked_bar'
  x: string[]
  series: Series[]
  orientation?: 'vertical' | 'horizontal'
}

export interface Donut extends BlockBase {
  type: 'donut'
  slices: { label: string; value: number }[]
  centreLabel?: string | null
}

export interface Pie extends BlockBase {
  type: 'pie'
  slices: { label: string; value: number }[]
}

export interface Gauge extends BlockBase {
  type: 'gauge'
  value: number
  minimum?: number
  maximum: number
  target?: number | null
  unit?: 'number' | 'currency' | 'percent' | 'months' | 'days'
  label?: string | null
  /** Segment breakpoints in ascending order — e.g. [30, 70] gives three arc bands. */
  thresholds?: number[]
}

export interface RowAction {
  label: string
  tool: string
  /** Maps column name -> tool argument name, so one declaration wires the column. */
  argsFrom?: Record<string, string>
}
export interface TableBlock extends BlockBase {
  type: 'table'
  columns: string[]
  rows: (string | number | null)[][]
  rowTones?: Tone[] | null
  rowAction?: RowAction | null
  emptyMessage?: string | null
}

export interface TimelineEvent {
  at: string
  label: string
  kind: string
  detail?: string | null
  tone?: Tone
}
export interface Timeline extends BlockBase {
  type: 'timeline'
  events: TimelineEvent[]
}

export interface SparklineItem {
  label: string
  values: number[]
  baseline?: number | null
  caption?: string | null
  tone?: Tone
}
export interface SparklineGrid extends BlockBase {
  type: 'sparkline_grid'
  items: SparklineItem[]
}

export interface ComparisonColumn {
  label: string
  values: Record<string, string>
  highlight?: boolean
  note?: string | null
}
export interface Comparison extends BlockBase {
  type: 'comparison'
  attributes: string[]
  columns: ComparisonColumn[]
  actions?: ComposerAction[]
}

export interface TreeNode {
  id: string
  label: string
  group?: string | null
  detail?: string | null
  tone?: Tone
}
export interface TreeEdge {
  source: string
  target: string
  label?: string | null
  tone?: Tone
}
export interface Tree extends BlockBase {
  type: 'tree'
  nodes: TreeNode[]
  edges: TreeEdge[]
  layout?: 'hierarchical' | 'network'
  direction?: 'down' | 'right'
}

export type RoadmapStatus = 'done' | 'current' | 'upcoming' | 'at_risk' | 'missed'
export interface RoadmapStep {
  label: string
  status: RoadmapStatus
  at?: string | null
  detail?: string | null
}
export interface Roadmap extends BlockBase {
  type: 'roadmap'
  steps: RoadmapStep[]
}

export interface HeatmapCell {
  row: string
  column: string
  value: number
  label?: string | null
}
export interface Heatmap extends BlockBase {
  type: 'heatmap'
  rows: string[]
  columns: string[]
  cells: HeatmapCell[]
  unit?: 'number' | 'percent' | 'days' | 'months'
}

export type Block =
  | KpiRow | Narrative | AlertBanner | ActionCard
  | LineChart | BarChart | StackedBar | Donut | Pie | Gauge
  | TableBlock | Timeline | SparklineGrid | Comparison
  | Tree | Roadmap | Heatmap

export interface Composition {
  title: string
  subtitle?: string | null
  blocks: Block[]
  rationale?: string | null
}

export interface ComposeMeta {
  functionsCalled: string[]
  tokensIn: number
  tokensOut: number
  latencyMs: number
  provider: string
}

export interface ComposeResponse {
  composition: Composition
  meta: ComposeMeta
}

export interface ComposerStatus {
  enabled: boolean
  reason: string | null
  providerLive: boolean
  functions: { name: string; description: string }[]
}
