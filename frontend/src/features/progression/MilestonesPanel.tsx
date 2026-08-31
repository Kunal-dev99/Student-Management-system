'use client'

import { useState } from 'react'
import { ChevronDown, ChevronRight, Milestone as MilestoneIcon } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { useCan } from '@/shared/auth/Can'
import { MilestoneReviewSection } from './MilestoneReviewSection'
import {
  CONDITIONAL_OUTCOMES, useDecideMilestone, useMilestones, useSubmitMilestone,
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
  // Panel decisions are progression.decide server-side; Submit is progression.read.
  const canDecide = useCan('progression.decide')
  const { data, isLoading } = useMilestones(studentId)
  const submit = useSubmitMilestone(studentId)
  const decide = useDecideMilestone(studentId)
  const [outcome, setOutcome] = useState<Record<string, ProgressionOutcome>>({})
  const [rationale, setRationale] = useState<Record<string, string>>({})
  const [conditions, setConditions] = useState<Record<string, string>>({})
  const [letter, setLetter] = useState<Record<string, string>>({})
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as Error).message, variant: 'destructive' })

  return (
    <PageSection icon={MilestoneIcon} title="Progression milestones" accent="primary">
      {isLoading ? <Skeleton className="h-24 w-full" /> : (
        <div className="space-y-3">
          {data && data.length > 0 ? data.map((m) => {
            const isOpen = !!expanded[m.id]
            const chosen = outcome[m.id]
            const needsConditions = !!chosen && CONDITIONAL_OUTCOMES.includes(chosen)
            return (
              <div key={m.id} className="border border-border rounded-md p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <button type="button" className="text-muted-foreground hover:text-foreground"
                      aria-label={isOpen ? 'Collapse review detail' : 'Expand review detail'}
                      onClick={() => setExpanded((s) => ({ ...s, [m.id]: !s[m.id] }))}>
                      {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                    </button>
                    <span className="text-sm font-medium">{m.name}</span>
                    <Badge variant={STATUS_VARIANT[m.status]}>{m.status.replace(/_/g, ' ')}</Badge>
                    {m.review?.panelDecision && (
                      <Badge variant="outline">{m.review.panelDecision.replace(/_/g, ' ')}</Badge>
                    )}
                  </div>
                  <span className="text-helper num">due {m.dueDate ?? '—'}</span>
                </div>

                {m.status !== 'decided' && (
                  <div className="mt-3 space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      {m.status !== 'submitted' && (
                        <Button size="sm" variant="secondary" disabled={submit.isPending}
                          onClick={async () => { try { await submit.mutateAsync({ id: m.id, ref: 'submission.pdf' }); toast({ title: 'Milestone submitted' }) } catch (e) { err(e) } }}>
                          Submit
                        </Button>
                      )}
                      {canDecide && <Select value={chosen ?? ''} onValueChange={(v) => setOutcome((o) => ({ ...o, [m.id]: v as ProgressionOutcome }))}>
                        <SelectTrigger className="w-56 h-8"><SelectValue placeholder="Panel outcome…" /></SelectTrigger>
                        <SelectContent>
                          {OUTCOMES.map((o) => <SelectItem key={o} value={o}>{o.replace(/_/g, ' ')}</SelectItem>)}
                        </SelectContent>
                      </Select>}
                      {canDecide && <Button size="sm" disabled={!chosen || decide.isPending}
                        onClick={async () => {
                          try {
                            await decide.mutateAsync({
                              id: m.id,
                              outcome: chosen,
                              rationale: rationale[m.id] || undefined,
                              conditions: conditions[m.id] || undefined,
                              outcomeLetter: letter[m.id] || undefined,
                            })
                            toast({ title: 'Decision recorded' })
                            setExpanded((s) => ({ ...s, [m.id]: true }))
                          } catch (e) { err(e) }
                        }}>Decide</Button>}
                    </div>
                    {canDecide && <div className="grid gap-2 md:grid-cols-3">
                      <Textarea className="min-h-[56px]" placeholder="Rationale" value={rationale[m.id] ?? ''}
                        onChange={(e) => setRationale((s) => ({ ...s, [m.id]: e.target.value }))} />
                      <Textarea className="min-h-[56px]"
                        placeholder={needsConditions ? 'Conditions (required for this outcome)' : 'Conditions'}
                        value={conditions[m.id] ?? ''}
                        onChange={(e) => setConditions((s) => ({ ...s, [m.id]: e.target.value }))} />
                      <Textarea className="min-h-[56px]" placeholder="Outcome letter" value={letter[m.id] ?? ''}
                        onChange={(e) => setLetter((s) => ({ ...s, [m.id]: e.target.value }))} />
                    </div>}
                    {needsConditions && (
                      <p className="text-helper">
                        “{chosen.replace(/_/g, ' ')}” requires written conditions and a complete panel.
                      </p>
                    )}
                  </div>
                )}

                {isOpen && <MilestoneReviewSection studentId={studentId} milestoneId={m.id} />}
              </div>
            )
          }) : <p className="text-helper">No milestones yet.</p>}
        </div>
      )}
    </PageSection>
  )
}
