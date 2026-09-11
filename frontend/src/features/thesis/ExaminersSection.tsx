'use client'

import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { usePersons } from '@/features/persons/api'
import {
  useApproveNomination, useExaminers, useNominateExaminer, type ExaminerType,
} from './api'

const EXAMINER_TYPES: ExaminerType[] = ['internal', 'external', 'independent_chair']

export function ExaminersSection({ studentId, thesisId }: { studentId: string; thesisId: string }) {
  const { toast } = useToast()
  const examiners = useExaminers(thesisId)
  const people = usePersons('')
  const nominate = useNominateExaminer(studentId, thesisId)
  const approve = useApproveNomination(thesisId)
  const [personId, setPersonId] = useState('')
  const [type, setType] = useState<ExaminerType>('internal')
  const [affiliation, setAffiliation] = useState('')
  const [coi, setCoi] = useState(false)
  const [coiNote, setCoiNote] = useState('')

  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as Error).message, variant: 'destructive' })

  return (
    <div className="pt-3 border-t border-border">
      <div className="text-sm font-medium mb-2">Examiners</div>
      {examiners.isLoading ? <Skeleton className="h-12 w-full" /> : (
        <div className="space-y-2 mb-3">
          {examiners.data && examiners.data.length > 0 ? examiners.data.map((n) => (
            <div key={n.id} className="flex items-start justify-between border-b border-border/60 last:border-0 pb-2 last:pb-0">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm">{n.examinerName}</span>
                  <Badge variant="secondary">{n.examinerType.replace(/_/g, ' ')}</Badge>
                  {n.approved
                    ? <Badge variant="success">approved</Badge>
                    : <Badge variant="warning">pending</Badge>}
                  {n.conflictOfInterest && <Badge variant="destructive">Conflict declared</Badge>}
                </div>
                <p className="text-helper mt-0.5">
                  {n.affiliation || 'No affiliation recorded'}
                  {n.conflictOfInterest && n.conflictNote ? ` — ${n.conflictNote}` : ''}
                </p>
              </div>
              {!n.approved && (
                <Button size="sm" variant="secondary"
                  className="ml-3 shrink-0 border border-primary/40 text-primary hover:bg-primary hover:text-primary-foreground"
                  disabled={approve.isPending}
                  onClick={async () => { try { await approve.mutateAsync(n.id); toast({ title: 'Examiner approved' }) } catch (e) { err(e) } }}>
                  Approve nomination
                </Button>
              )}
            </div>
          )) : <p className="text-helper">No examiners nominated yet.</p>}
        </div>
      )}
      <div className="mt-4 pt-3 border-t border-border/60 space-y-2">
        <div className="text-sm font-medium">Nominate an examiner</div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1 min-w-[200px]">
            <label className="text-xs text-muted-foreground">Examiner</label>
            <Select value={personId} onValueChange={setPersonId}>
              <SelectTrigger className="h-8"><SelectValue placeholder="Choose examiner…" /></SelectTrigger>
              <SelectContent>
                {people.data?.data.map((p) => <SelectItem key={p.id} value={p.id}>{p.givenName} {p.familyName}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">Role</label>
            <Select value={type} onValueChange={(v) => setType(v as ExaminerType)}>
              <SelectTrigger className="w-44 h-8"><SelectValue /></SelectTrigger>
              <SelectContent>
                {EXAMINER_TYPES.map((t) => <SelectItem key={t} value={t}>{t.replace(/_/g, ' ')}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">Affiliation</label>
            <Input className="w-56 h-8" placeholder="e.g. Imperial College" value={affiliation}
              onChange={(e) => setAffiliation(e.target.value)} />
          </div>
          <label className="flex items-center gap-2 text-sm h-8 pb-0.5">
            <Checkbox checked={coi} onCheckedChange={(v) => setCoi(v === true)} />
            <span>Conflict of interest</span>
          </label>
          {coi && (
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Nature of conflict</label>
              <Input className="w-56 h-8" placeholder="e.g. co-authored a paper in 2024" value={coiNote}
                onChange={(e) => setCoiNote(e.target.value)} />
            </div>
          )}
        </div>
        <Button size="sm" disabled={!personId || nominate.isPending}
          onClick={async () => {
            try {
              await nominate.mutateAsync({
                examinerPersonId: personId,
                examinerType: type,
                affiliation: affiliation || undefined,
                conflictOfInterest: coi,
                conflictNote: coi ? (coiNote || undefined) : undefined,
              })
              toast({ title: 'Examiner nominated' })
              setPersonId(''); setAffiliation(''); setCoi(false); setCoiNote('')
            } catch (e) { err(e) }
          }}>
          Nominate
        </Button>
      </div>
    </div>
  )
}
