'use client'

import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { usePersons } from '@/features/persons/api'
import { useAuth } from '@/shared/auth/AuthContext'
import {
  useAddPanelMember, useAppeals, useDecideAppeal, usePanel, useReviewDetail,
  useSignOffConditions, useSubmitAppeal,
  type AppealDecision, type AppealStatus, type PanelRole,
} from './api'

const PANEL_ROLES: PanelRole[] = ['chair', 'internal_assessor', 'independent_assessor', 'supervisor_observer']
const APPEAL_DECISIONS: AppealDecision[] = ['under_review', 'upheld', 'rejected', 'withdrawn']

const APPEAL_VARIANT: Record<AppealStatus, 'secondary' | 'info' | 'success' | 'destructive' | 'outline'> = {
  submitted: 'info', under_review: 'info', upheld: 'success', rejected: 'destructive', withdrawn: 'outline',
}

export function MilestoneReviewSection({ studentId, milestoneId }: { studentId: string; milestoneId: string }) {
  const { toast } = useToast()
  const { hasPermission } = useAuth()
  const review = useReviewDetail(milestoneId)
  const panel = usePanel(milestoneId)
  const appeals = useAppeals(milestoneId)
  const people = usePersons('')
  const addMember = useAddPanelMember(milestoneId)
  const signOff = useSignOffConditions(studentId, milestoneId)
  const submitAppeal = useSubmitAppeal(milestoneId)
  const decideAppeal = useDecideAppeal(milestoneId)

  const [personId, setPersonId] = useState('')
  const [role, setRole] = useState<PanelRole>('chair')
  const [grounds, setGrounds] = useState('')
  const [appealStatus, setAppealStatus] = useState<Record<string, AppealDecision>>({})
  const [appealNote, setAppealNote] = useState<Record<string, string>>({})

  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as Error).message, variant: 'destructive' })
  const r = review.data
  const canDecide = hasPermission('progression.decide')

  return (
    <div className="mt-3 pt-3 border-t border-border/60 space-y-4 bg-surface-2 rounded-md p-3">
      {/* Panel */}
      <div>
        <div className="text-sm font-medium mb-2">Review panel</div>
        {panel.isLoading ? <Skeleton className="h-10 w-full" /> : (
          <div className="space-y-1 mb-2">
            {panel.data && panel.data.length > 0 ? panel.data.map((p) => (
              <div key={p.id} className="flex items-center gap-2 text-sm">
                <span>{p.personName}</span>
                <Badge variant="secondary">{p.role.replace(/_/g, ' ')}</Badge>
                {p.isIndependent && <Badge variant="info">independent</Badge>}
              </div>
            )) : <p className="text-helper">No panel members appointed yet.</p>}
          </div>
        )}
        {canDecide && (
          <div className="flex flex-wrap items-end gap-2">
            <div className="min-w-[180px]">
              <Select value={personId} onValueChange={setPersonId}>
                <SelectTrigger className="h-8"><SelectValue placeholder="Choose a person…" /></SelectTrigger>
                <SelectContent>
                  {people.data?.data.map((p) => (
                    <SelectItem key={p.id} value={p.id}>{p.givenName} {p.familyName}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Select value={role} onValueChange={(v) => setRole(v as PanelRole)}>
              <SelectTrigger className="w-52 h-8"><SelectValue /></SelectTrigger>
              <SelectContent>
                {PANEL_ROLES.map((pr) => <SelectItem key={pr} value={pr}>{pr.replace(/_/g, ' ')}</SelectItem>)}
              </SelectContent>
            </Select>
            <Button size="sm" disabled={!personId || addMember.isPending}
              onClick={async () => {
                try {
                  await addMember.mutateAsync({ personId, role, isIndependent: role === 'independent_assessor' })
                  toast({ title: 'Panel member added' }); setPersonId('')
                } catch (e) { err(e) }
              }}>
              Add panel member
            </Button>
          </div>
        )}
      </div>

      {/* Conditions + outcome letter + appeal window */}
      {review.isLoading ? <Skeleton className="h-10 w-full" /> : r?.decided && (
        <div className="space-y-2">
          {r.conditions && (
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm font-medium">Conditions</span>
                {r.conditionsMet
                  ? <Badge variant="success">met</Badge>
                  : <Badge variant="warning">outstanding</Badge>}
                {r.reReviewDue && <span className="text-helper num">re-review due {r.reReviewDue}</span>}
              </div>
              <p className="text-sm whitespace-pre-wrap">{r.conditions}</p>
              {!r.conditionsMet && canDecide && (
                <Button size="sm" className="mt-2" variant="secondary" disabled={signOff.isPending}
                  onClick={async () => { try { await signOff.mutateAsync(); toast({ title: 'Conditions signed off' }) } catch (e) { err(e) } }}>
                  Sign off conditions
                </Button>
              )}
            </div>
          )}
          {r.outcomeLetter && (
            <div>
              <p className="text-label">Outcome letter</p>
              <p className="text-sm whitespace-pre-wrap mt-0.5">{r.outcomeLetter}</p>
            </div>
          )}
          <p className="text-helper">
            {r.appealDeadline ? `Appeal deadline ${r.appealDeadline}.` : 'No appeal window recorded.'}
          </p>
        </div>
      )}

      {/* Appeals */}
      {r?.decided && (
        <div>
          <div className="text-sm font-medium mb-2">Appeals</div>
          {appeals.isLoading ? <Skeleton className="h-10 w-full" /> : (
            <div className="space-y-2 mb-2">
              {appeals.data && appeals.data.length > 0 ? appeals.data.map((a) => (
                <div key={a.id} className="border-b border-border/60 last:border-0 pb-2 last:pb-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge variant={APPEAL_VARIANT[a.status]}>{a.status.replace(/_/g, ' ')}</Badge>
                    <span className="text-helper num">{a.submittedAt ? a.submittedAt.slice(0, 10) : '—'}</span>
                  </div>
                  <p className="text-sm mt-1 whitespace-pre-wrap">{a.grounds}</p>
                  {a.decisionNote && <p className="text-helper mt-0.5">Decision note: {a.decisionNote}</p>}
                  {canDecide && (a.status === 'submitted' || a.status === 'under_review') && (
                    <div className="flex flex-wrap items-end gap-2 mt-2">
                      <Select value={appealStatus[a.id] ?? ''}
                        onValueChange={(v) => setAppealStatus((s) => ({ ...s, [a.id]: v as AppealDecision }))}>
                        <SelectTrigger className="w-44 h-8"><SelectValue placeholder="Appeal outcome…" /></SelectTrigger>
                        <SelectContent>
                          {APPEAL_DECISIONS.map((d) => <SelectItem key={d} value={d}>{d.replace(/_/g, ' ')}</SelectItem>)}
                        </SelectContent>
                      </Select>
                      <Textarea className="min-h-[36px] w-64" placeholder="Decision note"
                        value={appealNote[a.id] ?? ''}
                        onChange={(e) => setAppealNote((s) => ({ ...s, [a.id]: e.target.value }))} />
                      <Button size="sm" disabled={!appealStatus[a.id] || decideAppeal.isPending}
                        onClick={async () => {
                          try {
                            await decideAppeal.mutateAsync({
                              appealId: a.id, status: appealStatus[a.id], decisionNote: appealNote[a.id] || undefined,
                            })
                            toast({ title: 'Appeal decided' })
                          } catch (e) { err(e) }
                        }}>
                        Decide appeal
                      </Button>
                    </div>
                  )}
                </div>
              )) : <p className="text-helper">No appeals against this decision.</p>}
            </div>
          )}
          <div className="flex flex-wrap items-end gap-2">
            <Textarea className="min-h-[36px] w-72" placeholder="Grounds for appeal" value={grounds}
              onChange={(e) => setGrounds(e.target.value)} />
            <Button size="sm" variant="secondary" disabled={!grounds.trim() || submitAppeal.isPending}
              onClick={async () => {
                try { await submitAppeal.mutateAsync(grounds); toast({ title: 'Appeal submitted' }); setGrounds('') }
                catch (e) { err(e) }
              }}>
              Submit appeal
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
