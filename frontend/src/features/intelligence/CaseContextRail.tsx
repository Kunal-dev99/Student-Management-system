'use client'

/**
 * Ask PGR / Case Copilot context rail (spec §15).
 *
 * Resolved student/cohort, time window, active filters and pending plan — shown as
 * chips so the reader can correct scope before an action plan is prepared.
 */
import { X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { CaseContext } from './api'

export interface CaseContextRailProps {
  context: CaseContext | null
  onClearFilter?: (key: string) => void
  className?: string
}

export function CaseContextRail({ context, onClearFilter, className }: CaseContextRailProps) {
  if (!context) return null
  const filters = Object.entries(context.activeFilters ?? {})
  return (
    <aside className={cn('rounded-md border bg-muted/30 p-3 space-y-2 text-xs', className)}>
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Case context</p>
      <div className="flex flex-wrap gap-1.5">
        {context.studentId ? (
          <Badge variant="secondary">Student · {String(context.studentId).slice(0, 8)}…</Badge>
        ) : null}
        {context.cohortFilter ? (
          <Badge variant="secondary">Cohort</Badge>
        ) : null}
        {context.timeWindow?.label ? (
          <Badge variant="secondary">Window · {context.timeWindow.label}</Badge>
        ) : null}
        {filters.map(([k, v]) => (
          <Badge key={k} variant="outline" className="gap-1">
            {k}: {String(v).slice(0, 24)}
            {onClearFilter ? (
              <button
                type="button"
                onClick={() => onClearFilter(k)}
                aria-label={`Clear ${k}`}
                className="ml-0.5 rounded hover:bg-muted p-0.5"
              >
                <X className="h-2.5 w-2.5" />
              </button>
            ) : null}
          </Badge>
        ))}
        {context.pendingActionPlanId ? (
          <Badge variant="warning">Pending plan</Badge>
        ) : (
          <Badge variant="outline">Pending: none</Badge>
        )}
      </div>
      {context.missingSources.length > 0 ? (
        <p className="text-muted-foreground">
          Missing: {context.missingSources.map((m) => m.source).join(', ')}
        </p>
      ) : null}
    </aside>
  )
}
