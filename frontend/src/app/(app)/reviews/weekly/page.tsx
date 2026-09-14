'use client'

/**
 * Weekly review — two views:
 *   • Intervention queue (default, spec §7): ranked table with owner + intervention
 *     type + one-click Prepare. Row expand carries the ranking explanation.
 *   • Reasoning trace: the original streaming AI-picks view — kept for anyone who
 *     wants to watch the model narrate its picks live.
 */
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { WeeklyInterventionQueue } from '@/features/intelligence'
import { WeeklyReviewQueue } from '@/features/reviews/WeeklyReviewQueue'

export default function WeeklyReviewsPage() {
  const [view, setView] = useState<'queue' | 'trace'>('queue')
  return (
    <div className="p-6 space-y-4">
      <div className="flex gap-2">
        <Button size="sm" variant={view === 'queue' ? 'default' : 'ghost'} onClick={() => setView('queue')}>
          Intervention queue
        </Button>
        <Button size="sm" variant={view === 'trace' ? 'default' : 'ghost'} onClick={() => setView('trace')}>
          Reasoning trace
        </Button>
      </div>
      {view === 'queue' ? <WeeklyInterventionQueue /> : <WeeklyReviewQueue />}
    </div>
  )
}
