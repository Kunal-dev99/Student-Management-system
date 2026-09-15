'use client'

import { useState } from 'react'
import { ChevronDown, ChevronRight, Milestone as MilestoneIcon, RefreshCw, Plus } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { useCan } from '@/shared/auth/Can'
import { MilestoneReviewSection } from './MilestoneReviewSection'
import {
  CONDITIONAL_OUTCOMES, useAddAdHocMilestone, useDecideMilestone, useMilestones,
  useOverrideMilestone, useRegenerateSchedule, useSubmitMilestone,
  type MilestoneOrigin, type MilestoneStatus, type ProgressionOutcome,
} from './api'

const ORIGIN_LABEL: Partial<Record<MilestoneOrigin, string>> = { override: 'override', ad_hoc: 'ad hoc' }

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
  // Schedule edits (regenerate, override due dates, ad-hoc) are student.write (ICR G3).
  const canWrite = useCan('student.write')
  const { data, isLoading } = useMilestones(studentId)
  const submit = useSubmitMilestone(studentId)
  const decide = useDecideMilestone(studentId)
  const regenerate = useRegenerateSchedule(studentId)
  const override = useOverrideMilestone(studentId)
  const addAdHoc = useAddAdHocMilestone(studentId)
  const [outcome, setOutcome] = useState<Record<string, ProgressionOutcome>>({})
  const [rationale, setRationale] = useState<Record<string, string>>({})
  const [conditions, setConditions] = useState<Record<string, string>>({})
  const [letter, setLetter] = useState<Record<string, string>>({})
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [adding, setAdding] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDate, setNewDate] = useState('')

  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as Error).message, variant: 'destructive' })

  const saveAdHoc = async () => {
    if (!newName.trim()) return
    try {
      await addAdHoc.mutateAsync({ name: newName.trim(), dueDate: newDate || undefined })
      toast({ title: 'Milestone added' })
      setNewName(''); setNewDate(''); setAdding(false)
    } catch (e) { err(e) }
  }

  return (
    <PageSection icon={MilestoneIcon} title="Progression milestones" accent="primary">
      {isLoading ? <Skeleton className="h-24 w-full" /> : (
        <div className="space-y-3">
          {canWrite && (
            <div className="flex flex-wrap items-center gap-2 pb-1">
              <Button size="sm" variant="outline" disabled={regenerate.isPending}
                onClick={async () => { try { await regenerate.mutateAsync(); toast({ title: 'Schedule regenerated from the programme template' }) } catch (e) { err(e) } }}>
                <RefreshCw className="mr-1.5 h-3.5 w-3.5" />Regenerate schedule
              </Button>
              <Button size="sm" variant="outline" onClick={() => setAdding((v) => !v)}>
                <Plus className="mr-1.5 h-3.5 w-3.5" />Add milestone
              </Button>
              {adding && (
                <div className="flex flex-wrap items-center gap-2">
                  <Input className="h-8 w-56" placeholder="Milestone name" value={newName}
                    onChange={(e) => setNewName(e.target.value)} />
                  <Input className="h-8 w-40" type="date" value={newDate}
                    onChange={(e) => setNewDate(e.target.value)} />
                  <Button size="sm" disabled={!newName.trim() || addAdHoc.isPending} onClick={saveAdHoc}>Save</Button>
                </div>
              )}
            </div>
          )}
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
                    {ORIGIN_LABEL[m.origin] && (
                      <Badge variant="secondary">{ORIGIN_LABEL[m.origin]}</Badge>
                    )}
                  </div>
                  {canWrite && m.status !== 'decided' ? (
                    <div className="flex items-center gap-1.5">
                      <span className="text-helper">due</span>
                      <Input
                        type="date"
                        className="h-7 w-36"
                        defaultValue={m.dueDate ?? ''}
                        aria-label={`Due date for ${m.name}`}
                        onBlur={async (e) => {
                          const v = e.target.value
                          if (!v || v === m.dueDate) return
                          try { await override.mutateAsync({ id: m.id, dueDate: v }); toast({ title: 'Due date updated' }) } catch (err2) { err(err2) }
                        }}
                      />
                    </div>
                  ) : (
                    <span className="text-helper num">due {m.dueDate ?? '—'}</span>
                  )}
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
