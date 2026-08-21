'use client'

import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { usePersons } from '@/features/persons/api'
import {
  useApproveNomination, useExaminers, useNominateExaminer, type ExaminerType,
} from './api'

export function ExaminersSection({ studentId, thesisId }: { studentId: string; thesisId: string }) {
  const { toast } = useToast()
  const examiners = useExaminers(thesisId)
  const people = usePersons('')
  const nominate = useNominateExaminer(studentId, thesisId)
  const approve = useApproveNomination(thesisId)
  const [personId, setPersonId] = useState('')
  const [type, setType] = useState<ExaminerType>('internal')

  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as Error).message, variant: 'destructive' })

  return (
    <div className="pt-3 border-t border-border">
      <div className="text-sm font-medium mb-2">Examiners</div>
      {examiners.isLoading ? <Skeleton className="h-12 w-full" /> : (
        <div className="space-y-2 mb-3">
          {examiners.data && examiners.data.length > 0 ? examiners.data.map((n) => (
            <div key={n.id} className="flex items-center justify-between border-b border-border/60 last:border-0 pb-2 last:pb-0">
              <div className="flex items-center gap-2">
                <span className="text-sm">{n.examinerName}</span>
                <Badge variant="secondary">{n.examinerType}</Badge>
                {n.approved
                  ? <Badge variant="success">approved</Badge>
                  : <Badge variant="warning">pending</Badge>}
              </div>
              {!n.approved && (
                <Button size="sm" variant="ghost" disabled={approve.isPending}
                  onClick={async () => { try { await approve.mutateAsync(n.id); toast({ title: 'Examiner approved' }) } catch (e) { err(e) } }}>
                  Approve
                </Button>
              )}
            </div>
          )) : <p className="text-helper">No examiners nominated yet.</p>}
        </div>
      )}
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-[180px]">
          <Select value={personId} onValueChange={setPersonId}>
            <SelectTrigger className="h-8"><SelectValue placeholder="Choose examiner…" /></SelectTrigger>
            <SelectContent>
              {people.data?.data.map((p) => <SelectItem key={p.id} value={p.id}>{p.givenName} {p.familyName}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <Select value={type} onValueChange={(v) => setType(v as ExaminerType)}>
          <SelectTrigger className="w-32 h-8"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="internal">internal</SelectItem>
            <SelectItem value="external">external</SelectItem>
          </SelectContent>
        </Select>
        <Button size="sm" disabled={!personId || nominate.isPending}
          onClick={async () => { try { await nominate.mutateAsync({ examinerPersonId: personId, examinerType: type }); toast({ title: 'Examiner nominated' }); setPersonId('') } catch (e) { err(e) } }}>
          Nominate
        </Button>
      </div>
    </div>
  )
}
