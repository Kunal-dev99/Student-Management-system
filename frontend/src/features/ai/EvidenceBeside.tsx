'use client'

/**
 * Two-column shell: AI-produced content on the left, the deterministic evidence table on
 * the right. This is the layout that makes the AI cite-able — every figure or pick in the
 * prose has a row on the right the reader can point at.
 *
 * On narrow viewports the evidence stacks below the prose. That's deliberate — the AI's
 * reading is still the primary thing on the page; the evidence is what makes it trusted.
 */

import { type ReactNode } from 'react'
import { cn } from '@/lib/utils'

export function EvidenceBeside({
  prose, evidence, className,
}: { prose: ReactNode; evidence: ReactNode; className?: string }) {
  return (
    <div className={cn('grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]', className)}>
      <div className="min-w-0">{prose}</div>
      <aside className="min-w-0 border-l lg:pl-4 lg:border-l lg:border-border pt-4 lg:pt-0 border-t lg:border-t-0">
        <p className="text-label mb-2">Evidence</p>
        {evidence}
      </aside>
    </div>
  )
}
