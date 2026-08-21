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
import {
  useAssignSupervisor, useEndSupervisor, useSupervisors, type SupervisorRole,
} from './api'

export function SupervisorsPanel({ studentId }: { studentId: string }) {
  const { toast } = useToast()
  const { data, isLoading } = useSupervisors(studentId)
  const people = usePersons('')
  const assign = useAssignSupervisor(studentId)
  const end = useEndSupervisor(studentId)
  const [personId, setPersonId] = useState('')
  const [role, setRole] = useState<SupervisorRole>('primary')

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
              {s.validTo === null && (
                <Button size="sm" variant="ghost" disabled={end.isPending}
                  onClick={async () => { try { await end.mutateAsync(s.id); toast({ title: 'Supervision ended' }) } catch (e) { err(e) } }}>
                  End
                </Button>
              )}
            </div>
          )) : <p className="text-helper">No supervisors assigned yet.</p>}
        </div>
      )}

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
            catch (e) { err(e) }
          }}>Assign</Button>
      </div>
    </PageSection>
  )
}
