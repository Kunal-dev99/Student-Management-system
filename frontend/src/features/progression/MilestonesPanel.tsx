'use client'

import { useState } from 'react'
import { Milestone as MilestoneIcon } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import {
  useDecideMilestone, useMilestones, useSubmitMilestone,
  type MilestoneStatus, type ProgressionOutcome,
} from './api'

const STATUS_VARIANT: Record<MilestoneStatus, 'secondary' | 'info' | 'warning' | 'success' | 'destructive'> = {
  not_started: 'secondary', due: 'warning', submitted: 'info',
  under_review: 'info', decided: 'success', overdue: 'destructive',
}
const OUTCOMES: ProgressionOutcome[] = [
  'progress', 'progress_with_conditions', 'further_review', 'transfer_award', 'withdraw', 'terminate',
]

export function MilestonesPanel({ studentId }: { studentId: string }) {
  const { toast } = useToast()
  const { data, isLoading } = useMilestones(studentId)
  const submit = useSubmitMilestone(studentId)
  const decide = useDecideMilestone(studentId)
  const [outcome, setOutcome] = useState<Record<string, ProgressionOutcome>>({})

  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as Error).message, variant: 'destructive' })

  return (
    <PageSection icon={MilestoneIcon} title="Progression milestones" accent="primary">
      {isLoading ? <Skeleton className="h-24 w-full" /> : (
        <div className="space-y-3">
          {data && data.length > 0 ? data.map((m) => (
            <div key={m.id} className="border border-border rounded-md p-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{m.name}</span>
                  <Badge variant={STATUS_VARIANT[m.status]}>{m.status.replace(/_/g, ' ')}</Badge>
                  {m.review?.panelDecision && (
                    <Badge variant="outline">{m.review.panelDecision.replace(/_/g, ' ')}</Badge>
                  )}
                </div>
                <span className="text-helper num">due {m.dueDate ?? '—'}</span>
              </div>

              {m.status !== 'decided' && (
                <div className="flex flex-wrap items-center gap-2 mt-3">
                  {m.status !== 'submitted' && (
                    <Button size="sm" variant="secondary" disabled={submit.isPending}
                      onClick={async () => { try { await submit.mutateAsync({ id: m.id, ref: 'submission.pdf' }); toast({ title: 'Milestone submitted' }) } catch (e) { err(e) } }}>
                      Submit
                    </Button>
                  )}
                  <Select value={outcome[m.id] ?? ''} onValueChange={(v) => setOutcome((o) => ({ ...o, [m.id]: v as ProgressionOutcome }))}>
                    <SelectTrigger className="w-56 h-8"><SelectValue placeholder="Panel outcome…" /></SelectTrigger>
                    <SelectContent>
                      {OUTCOMES.map((o) => <SelectItem key={o} value={o}>{o.replace(/_/g, ' ')}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  <Button size="sm" disabled={!outcome[m.id] || decide.isPending}
                    onClick={async () => {
                      try { await decide.mutateAsync({ id: m.id, outcome: outcome[m.id] }); toast({ title: 'Decision recorded' }) }
                      catch (e) { err(e) }
                    }}>Decide</Button>
                </div>
              )}
            </div>
          )) : <p className="text-helper">No milestones yet.</p>}
        </div>
      )}
    </PageSection>
  )
}
