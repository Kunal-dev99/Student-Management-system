'use client'

import { useState } from 'react'
import { UsersRound } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { usePersons } from '@/features/persons/api'
import { useAuth } from '@/shared/auth/AuthContext'
import {
  useAssignSupervisor, useEndSupervisor, useSupervisors, type SupervisorRole,
} from './api'

export function SupervisorsPanel({ studentId }: { studentId: string }) {
  const { toast } = useToast()
  const { hasPermission } = useAuth()
  const { data, isLoading } = useSupervisors(studentId)
  const end = useEndSupervisor(studentId)
  // Assigning/ending supervision is student.write; supervisors see the team read-only.
  const canManage = hasPermission('student.write')

  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as Error).message, variant: 'destructive' })

  return (
    <PageSection icon={UsersRound} title="Supervisors" accent="accent">
      {isLoading ? <Skeleton className="h-16 w-full" /> : (
        <div className="space-y-2 mb-4">
          {data && data.length > 0 ? data.map((s) => (
            <div key={s.id} className="flex items-center justify-between border-b border-border/60 last:border-0 pb-2 last:pb-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{s.supervisorName}</span>
                <Badge variant="secondary">{s.role.replace(/_/g, ' ')}</Badge>
                {s.validTo === null
                  ? <Badge variant="success">current</Badge>
                  : <Badge variant="outline">ended {s.validTo}</Badge>}
              </div>
              {s.validTo === null && canManage && (
                <Button size="sm" variant="ghost" disabled={end.isPending}
                  onClick={async () => { try { await end.mutateAsync(s.id); toast({ title: 'Supervision ended' }) } catch (e) { err(e) } }}>
                  End
                </Button>
              )}
            </div>
          )) : <p className="text-helper">No supervisors assigned yet.</p>}
        </div>
      )}

      {canManage && <AssignForm studentId={studentId} onError={err} />}
    </PageSection>
  )
}

/** Separate component so the /persons query only fires for users who can assign. */
function AssignForm({ studentId, onError }: { studentId: string; onError: (e: unknown) => void }) {
  const { toast } = useToast()
  const people = usePersons('')
  const assign = useAssignSupervisor(studentId)
  const [personId, setPersonId] = useState('')
  const [role, setRole] = useState<SupervisorRole>('primary')

  return (
    <div className="flex flex-wrap items-end gap-2 pt-2 border-t border-border">
      <div className="min-w-[200px]">
        <Select value={personId} onValueChange={setPersonId}>
          <SelectTrigger><SelectValue placeholder="Choose a supervisor…" /></SelectTrigger>
          <SelectContent>
            {people.data?.data.map((p) => (
              <SelectItem key={p.id} value={p.id}>{p.givenName} {p.familyName}</SelectItem>
            ))}
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
      <Button size="sm" disabled={!personId || assign.isPending}
        onClick={async () => {
          try { await assign.mutateAsync({ supervisorPersonId: personId, role }); toast({ title: 'Supervisor assigned' }); setPersonId('') }
          catch (e) { onError(e) }
        }}>Assign</Button>
    </div>
  )
}
