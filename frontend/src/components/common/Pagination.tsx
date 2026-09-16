'use client'

/**
 * Prev/Next pager against the backend's standard list envelope
 * (`backend/app/core/pagination.py::list_envelope` — `{data, page: {limit, nextCursor, total}}`).
 * Every list endpoint already returns `total`, so page count is computed from
 * `offset`/`limit`/`total` rather than the unused cursor — simplest thing that works
 * for the offset-based lists this was built for (Students, Analytics, Workforce, ...).
 *
 * Renders nothing when there's only one page, so it's safe to drop in unconditionally.
 */
import { Button } from '@/components/ui/button'
import { ChevronLeft, ChevronRight } from 'lucide-react'

export interface PaginationProps {
  offset: number
  limit: number
  total: number | null | undefined
  /**
   * Same shape as a useState setter — accepts a value OR an updater function. Prev/Next call
   * this with an updater so rapid clicks always increment from the latest offset (a stale
   * `offset` prop from an earlier render would otherwise let clicks silently no-op).
   */
  onOffsetChange: (next: number | ((prev: number) => number)) => void
}

export function Pagination({ offset, limit, total, onOffsetChange }: PaginationProps) {
  if (total == null || total <= limit) return null

  const page = Math.floor(offset / limit) + 1
  const pageCount = Math.max(1, Math.ceil(total / limit))
  const from = total === 0 ? 0 : offset + 1
  const to = Math.min(offset + limit, total)

  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      {/* Keyed so React remounts these purely-numeric text spans on every change — text-node
         reconciliation could otherwise leave the numbers stale while the list updates. */}
      <p className="text-helper" key={`r-${from}-${to}-${total}`}>
        {from}–{to} of {total}
      </p>
      <div className="flex items-center gap-2">
        <Button
          size="sm" variant="outline"
          disabled={page <= 1}
          onClick={() => onOffsetChange((o) => Math.max(0, o - limit))}
        >
          <ChevronLeft className="h-4 w-4 mr-1" /> Prev
        </Button>
        <span className="text-helper tabular-nums" key={`p-${page}-${pageCount}`}>Page {page} of {pageCount}</span>
        <Button
          size="sm" variant="outline"
          disabled={page >= pageCount}
          onClick={() => onOffsetChange((o) => o + limit)}
        >
          Next <ChevronRight className="h-4 w-4 ml-1" />
        </Button>
      </div>
    </div>
  )
}
