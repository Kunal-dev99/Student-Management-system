'use client'

import { useState } from 'react'
import { UsersRound } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { useAuth } from '@/shared/auth/AuthContext'
import { EffectiveDateField } from '@/features/history/EffectiveDate'
import { todayIso } from '@/features/history/api'
import {
  useAssignSupervisor, useEndSupervisor, useReplaceSupervisor, useSupervisors, type SupervisorRole,
} from './api'
import { useSupervisorPool } from './w2_api'

export function SupervisorsPanel({ studentId }: { studentId: string }) {
  const { toast } = useToast()
  const { hasPermission } = useAuth()
  const { data, isLoading } = useSupervisors(studentId)
  // Assigning/ending supervision is student.write; supervisors see the team read-only.
  const canManage = hasPermission('student.write')
  // Effective dating (Phase 5): which row has its End / Change form open.
  const [open, setOpen] = useState<{ id: string; mode: 'end' | 'replace' } | null>(null)

  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as Error).message, variant: 'destructive' })
  const toggle = (id: string, mode: 'end' | 'replace') =>
    setOpen(open?.id === id && open.mode === mode ? null : { id, mode })

  return (
    <PageSection icon={UsersRound} title="Supervisors" accent="accent">
      {isLoading ? <Skeleton className="h-16 w-full" /> : (
        <div className="space-y-2 mb-4">
          {data && data.length > 0 ? data.map((s) => (
            <div key={s.id} className="border-b border-border/60 last:border-0 pb-2 last:pb-0">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium">{s.supervisorName}</span>
                  <Badge variant="secondary">{s.role.replace(/_/g, ' ')}</Badge>
                  {s.validTo === null
                    ? <Badge variant="success">current</Badge>
                    : <Badge variant="outline">ended {s.validTo}</Badge>}
                  <span className="text-helper num">from {s.validFrom}</span>
                </div>
                {s.validTo === null && canManage && (
                  <div className="flex items-center gap-1 shrink-0">
                    <Button size="sm" variant="ghost" onClick={() => toggle(s.id, 'replace')}>Change supervisor</Button>
                    <Button size="sm" variant="ghost" onClick={() => toggle(s.id, 'end')}>End</Button>
                  </div>
                )}
              </div>
              {open?.id === s.id && open.mode === 'end' && (
                <EndForm studentId={studentId} relId={s.id} onDone={() => setOpen(null)} onError={err} />
              )}
              {open?.id === s.id && open.mode === 'replace' && (
                <ReplaceForm studentId={studentId} relId={s.id} currentPersonId={s.supervisorPersonId}
                  onDone={() => setOpen(null)} onError={err} />
              )}
            </div>
          )) : <p className="text-helper">No supervisors assigned yet.</p>}
        </div>
      )}

      {canManage && <AssignForm studentId={studentId} onError={err} />}
    </PageSection>
  )
}

function EndForm({ studentId, relId, onDone, onError }: {
  studentId: string; relId: string; onDone: () => void; onError: (e: unknown) => void
}) {
  const { toast } = useToast()
  const end = useEndSupervisor(studentId)
  const [date, setDate] = useState(todayIso())
  const [reason, setReason] = useState('')
  return (
    <div className="flex flex-wrap items-end gap-2 mt-2 bg-surface-2 rounded-md p-2">
      <EffectiveDateField studentId={studentId} label="No longer supervising from" allowFuture={false}
        id={`sv-end-${relId}`} value={date} onChange={setDate} />
      <div className="flex flex-col gap-1">
        <label htmlFor={`sv-end-reason-${relId}`} className="text-label">Reason</label>
        <Input id={`sv-end-reason-${relId}`} className="h-8 w-56" placeholder="e.g. left the institution"
          value={reason} onChange={(e) => setReason(e.target.value)} />
      </div>
      <Button size="sm" disabled={end.isPending || !date}
        onClick={async () => {
          try {
            await end.mutateAsync({ id: relId, effectiveDate: date, reason: reason.trim() || undefined })
            toast({ title: 'Supervision ended' }); onDone()
          } catch (e) { onError(e) }
        }}>End supervision</Button>
      <Button size="sm" variant="ghost" onClick={onDone}>Cancel</Button>
    </div>
  )
}

/** Change supervisor: the old one ends and the new one starts on the same day, same role. */
function ReplaceForm({ studentId, relId, currentPersonId, onDone, onError }: {
  studentId: string; relId: string; currentPersonId: string; onDone: () => void; onError: (e: unknown) => void
}) {
  const { toast } = useToast()
  const pool = useSupervisorPool()
  const replace = useReplaceSupervisor(studentId)
  const [personId, setPersonId] = useState('')
  const [date, setDate] = useState(todayIso())
  const [reason, setReason] = useState('')
  return (
    <div className="flex flex-wrap items-end gap-2 mt-2 bg-surface-2 rounded-md p-2">
      <div className="flex flex-col gap-1 min-w-[220px]">
        <span className="text-label">New supervisor (same role)</span>
        <Select value={personId} onValueChange={setPersonId}>
          <SelectTrigger className="h-8"><SelectValue placeholder={pool.isLoading ? 'Loading…' : 'Choose…'} /></SelectTrigger>
          <SelectContent>
            {pool.data?.filter((p) => p.id !== currentPersonId).map((p) => (
              <SelectItem key={p.id} value={p.id}>{p.familyName}, {p.givenName}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <EffectiveDateField studentId={studentId} label="Hand over on" allowFuture={false}
        id={`sv-rep-${relId}`} value={date} onChange={setDate} />
      <div className="flex flex-col gap-1">
        <label htmlFor={`sv-rep-reason-${relId}`} className="text-label">Reason (required)</label>
        <Input id={`sv-rep-reason-${relId}`} className="h-8 w-56" placeholder="e.g. supervisor left"
          value={reason} onChange={(e) => setReason(e.target.value)} />
      </div>
      <Button size="sm" disabled={replace.isPending || !personId || !reason.trim() || !date}
        onClick={async () => {
          try {
            await replace.mutateAsync({ id: relId, newSupervisorPersonId: personId, reason: reason.trim(), effectiveDate: date })
            toast({ title: 'Supervisor changed', description: `Handover on ${date}.` }); onDone()
          } catch (e) { onError(e) }
        }}>Change supervisor</Button>
      <Button size="sm" variant="ghost" onClick={onDone}>Cancel</Button>
    </div>
  )
}

/** Separate component so the /persons query only fires for users who can assign. */
function AssignForm({ studentId, onError }: { studentId: string; onError: (e: unknown) => void }) {
  const { toast } = useToast()
  const pool = useSupervisorPool()
  const assign = useAssignSupervisor(studentId)
  const [personId, setPersonId] = useState('')
  const [role, setRole] = useState<SupervisorRole>('primary')
  const [validFrom, setValidFrom] = useState('')

  return (
    <div className="flex flex-wrap items-end gap-2 pt-2 border-t border-border">
      <div className="min-w-[240px]">
        <Select value={personId} onValueChange={setPersonId}>
          <SelectTrigger>
            <SelectValue placeholder={pool.isLoading ? 'Loading…' : 'Choose a supervisor…'} />
          </SelectTrigger>
          <SelectContent>
            {pool.data?.map((p) => (
              <SelectItem key={p.id} value={p.id}>
                {p.familyName}, {p.givenName}
                {!p.hasProfile && ' · no profile'}
              </SelectItem>
            ))}
            {pool.data && pool.data.length === 0 && (
              <div className="px-2 py-3 text-xs text-muted-foreground">
                No supervisor-capable persons yet. Provision an employee/researcher first.
              </div>
            )}
          </SelectContent>
        </Select>
      </div>
      <Select value={role} onValueChange={(v) => setRole(v as SupervisorRole)}>
        <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value="primary">primary</SelectItem>
          <SelectItem value="co_supervisor">co-supervisor</SelectItem>
          <SelectItem value="additional">additional</SelectItem>
        </SelectContent>
      </Select>
      <EffectiveDateField studentId={studentId} label="From" allowFuture={false}
        id="sv-assign-from" value={validFrom} onChange={setValidFrom} />
      <Button size="sm" disabled={!personId || assign.isPending}
        onClick={async () => {
          try {
            await assign.mutateAsync({ supervisorPersonId: personId, role, validFrom: validFrom || undefined })
            toast({ title: 'Supervisor assigned' }); setPersonId(''); setValidFrom('')
          } catch (e) { onError(e) }
        }}>Assign</Button>
    </div>
  )
}
