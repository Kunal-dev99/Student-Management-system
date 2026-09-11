'use client'

/** Chart blocks. Recharts renders; the block spec supplies every value. */

import {
  Bar, BarChart as RBarChart, CartesianGrid, Cell, Legend, Line, LineChart as RLineChart,
  Pie, PieChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import {
  AXIS_TICK, GRID_STROKE, TONE_HEX, formatValue, seriesColour, toRows,
} from '../chartTheme'
import type { BarChart, Donut, LineChart, StackedBar } from '../types'

const H = 260

/** Legends only earn their place with two or more series — one series is named by the title. */
function legend(count: number) {
  return count > 1
    ? <Legend wrapperStyle={{ fontSize: 12 }} iconType="plainline" iconSize={12} />
    : null
}

const tooltipStyle = {
  contentStyle: {
    fontSize: 12,
    borderRadius: 8,
    border: '1px solid hsl(var(--border))',
    background: 'hsl(var(--popover))',
    color: 'hsl(var(--popover-foreground))',
  },
} as const

export function LineChartBlock({ block }: { block: LineChart }) {
  const rows = toRows(block.x, block.series)
  return (
    <div style={{ width: '100%', height: H }}>
      <ResponsiveContainer>
        <RLineChart data={rows} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid stroke={GRID_STROKE} vertical={false} />
          <XAxis dataKey="x" tick={AXIS_TICK} tickLine={false} axisLine={false} />
          <YAxis
            tick={AXIS_TICK} tickLine={false} axisLine={false} width={52}
            tickFormatter={(v) => formatValue(v as number, block.yFormat)}
          />
          <Tooltip
            {...tooltipStyle}
            formatter={(v) => formatValue(v as number, block.yFormat)}
          />
          {legend(block.series.length)}

          {/* Bands render behind the data — a shaded range the reader should notice. */}
          {(block.bands ?? []).map((b, i) => (
            <ReferenceArea
              key={`band-${i}`} x1={b.fromX} x2={b.toX}
              fill={TONE_HEX[b.tone ?? 'danger']} fillOpacity={0.12}
              label={b.label ? { value: b.label, fontSize: 11, position: 'insideTop' } : undefined}
            />
          ))}
          {(block.markers ?? []).map((m, i) => (
            <ReferenceLine
              key={`marker-${i}`} x={m.at}
              stroke={TONE_HEX[m.tone ?? 'neutral']} strokeDasharray="4 4"
              label={{ value: m.label, fontSize: 11, position: 'top',
                       fill: TONE_HEX[m.tone ?? 'neutral'] }}
            />
          ))}

          {block.series.map((s, i) => (
            <Line
              key={s.name} type="monotone" dataKey={s.name}
              stroke={s.style === 'reference' ? '#898781' : seriesColour(i)}
              strokeWidth={s.style === 'reference' ? 1.5 : 2}
              strokeDasharray={s.style === 'solid' || !s.style ? undefined : '5 4'}
              dot={false} activeDot={{ r: 4 }} connectNulls={false}
            />
          ))}
        </RLineChart>
      </ResponsiveContainer>
    </div>
  )
}

export function BarChartBlock({ block }: { block: BarChart | StackedBar }) {
  const stacked = block.type === 'stacked_bar'
  const horizontal = block.orientation === 'horizontal'
  const rows = toRows(block.x, block.series)
  const format = 'yFormat' in block ? block.yFormat : undefined
  // Horizontal bars need vertical room per category or the labels collide.
  const height = horizontal ? Math.max(H, block.x.length * 34 + 60) : H

  return (
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer>
        <RBarChart
          data={rows}
          layout={horizontal ? 'vertical' : 'horizontal'}
          margin={{ top: 8, right: 16, bottom: 4, left: horizontal ? 8 : 0 }}
        >
          <CartesianGrid stroke={GRID_STROKE} vertical={horizontal} horizontal={!horizontal} />
          {horizontal ? (
            <>
              <XAxis type="number" tick={AXIS_TICK} tickLine={false} axisLine={false}
                     tickFormatter={(v) => formatValue(v as number, format)} />
              <YAxis type="category" dataKey="x" tick={AXIS_TICK} tickLine={false}
                     axisLine={false} width={132} />
            </>
          ) : (
            <>
              <XAxis dataKey="x" tick={AXIS_TICK} tickLine={false} axisLine={false} />
              <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} width={52}
                     tickFormatter={(v) => formatValue(v as number, format)} />
            </>
          )}
          <Tooltip {...tooltipStyle} cursor={{ fill: 'hsl(var(--muted)/0.4)' }}
                   formatter={(v) => formatValue(v as number, format)} />
          {legend(block.series.length)}

          {block.series.map((s, i) => (
            <Bar
              key={s.name} dataKey={s.name}
              stackId={stacked ? 'stack' : undefined}
              fill={s.style === 'reference' ? '#c3c2b7' : seriesColour(i)}
              radius={stacked ? 0 : horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]}
              maxBarSize={28}
            />
          ))}
        </RBarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function DonutBlock({ block }: { block: Donut }) {
  const total = block.slices.reduce((sum, s) => sum + s.value, 0)
  return (
    <div className="flex flex-wrap items-center gap-6">
      <div style={{ width: 200, height: 200 }}>
        <ResponsiveContainer>
          <PieChart>
            <Pie
              data={block.slices} dataKey="value" nameKey="label"
              innerRadius={58} outerRadius={88} paddingAngle={2} stroke="none"
            >
              {block.slices.map((_, i) => (
                <Cell key={i} fill={seriesColour(i)} />
              ))}
            </Pie>
            <Tooltip {...tooltipStyle} />
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
