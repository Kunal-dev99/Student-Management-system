'use client'

/** Effective dating, Phase 8b — a programme's dated versions (Demo 2 item 1.3, the CMA rule).
 *
 *  A version is what the programme promised a cohort: total credits, duration, grading policy and
 *  its module structure. Students are pinned to the version in force when they started, and keep
 *  it to completion. A version with students on it only gains modules; any other change is a new
 *  version from a date, for the next cohort. */

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { GitBranch, Lock } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useToast } from '@/components/ui/use-toast'
import { api, type ApiError } from '@/shared/api/client'

export interface ProgrammeVersion {
  id: string
  versionNo: number
  label: string
  validFrom: string
  /** Exclusive; null = open-ended. */
  validTo: string | null
  taughtTotalCredits: number | null
  durationMonths: number | null
  gradingPolicy: Record<string, unknown> | null
  structure: { moduleId: string; code: string; isCore: boolean }[]
  changeNote: string | null
  students: number
  locked: boolean
  current: boolean
}

export const useProgrammeVersions = (programmeId: string) =>
  useQuery({
    queryKey: ['programme-versions', programmeId],
    queryFn: () => api.get<{ programmeId: string; code: string; versions: ProgrammeVersion[] }>(
      `/programmes/${programmeId}/versions`),
    enabled: !!programmeId,
  })

export function useNewProgrammeVersion(programmeId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { effectiveFrom: string; taughtTotalCredits?: number; durationMonths?: number; note: string }) =>
      api.post(`/programmes/${programmeId}/versions`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['programme-versions', programmeId] })
      qc.invalidateQueries({ queryKey: ['programmes'] })
    },
  })
}

function dayBefore(iso: string | null): string | null {
  if (!iso) return null
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() - 1)
  return d.toISOString().slice(0, 10)
}

export function ProgrammeVersionsPanel({ programmeId, taught }: { programmeId: string; taught: boolean }) {
  const { toast } = useToast()
  const q = useProgrammeVersions(programmeId)
  const create = useNewProgrammeVersion(programmeId)
  const [form, setForm] = useState({ effectiveFrom: '', credits: '', duration: '', note: '' })

  return (
    <div className="card-elevated p-4 space-y-3">
      <p className="flex items-center gap-1.5 text-sm font-medium">
        <GitBranch className="h-4 w-4" /> Versions — what each cohort was promised
      </p>
      <p className="text-helper">
        Students stay on the version in force when they started (the CMA rule). A locked version has
        students on it: it can gain modules, but removing one, making a core module optional, or
        changing credits, duration or grading needs a new version from a date.
      </p>
      {q.isLoading ? <Skeleton className="h-20 w-full" /> : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Version</TableHead>
              <TableHead>In force</TableHead>
              {taught && <TableHead className="text-right">Credits</TableHead>}
              <TableHead className="text-right">Months</TableHead>
              {taught && <TableHead>Modules</TableHead>}
              <TableHead className="text-right">Students</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(q.data?.versions ?? []).map((v) => (
              <TableRow key={v.id}>
                <TableCell className="whitespace-nowrap">
                  <span className="font-medium">{v.label}</span>
                  {v.current && <Badge variant="success" className="ml-1.5">current</Badge>}
                  {v.locked && <Lock className="inline h-3 w-3 ml-1.5 text-muted-foreground" aria-label="locked" />}
                  {v.changeNote && <span className="block text-xs text-muted-foreground">{v.changeNote}</span>}
                </TableCell>
                <TableCell className="num whitespace-nowrap text-xs">{v.validFrom} → {dayBefore(v.validTo) ?? 'open'}</TableCell>
                {taught && <TableCell className="num text-right">{v.taughtTotalCredits ?? '—'}</TableCell>}
                <TableCell className="num text-right">{v.durationMonths ?? '—'}</TableCell>
                {taught && (
                  <TableCell className="text-xs">
                    {v.structure.length
                      ? v.structure.map((m) => `${m.code}${m.isCore ? '' : ' (opt.)'}`).join(', ')
                      : '—'}
                  </TableCell>
                )}
                <TableCell className="num text-right">{v.students}</TableCell>
              </TableRow>
            ))}
            {q.data && q.data.versions.length === 0 && (
              <TableRow><TableCell colSpan={6} className="text-helper">
                No versions yet — version 1 is created when the first student enrols.
              </TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      )}
      <div className="flex flex-wrap items-end gap-2 pt-2 border-t border-border">
        <div className="flex flex-col gap-1">
          <label htmlFor={`pv-from-${programmeId}`} className="text-label">New version from</label>
          <Input id={`pv-from-${programmeId}`} type="date" className="h-8 w-40" value={form.effectiveFrom}
            onChange={(e) => setForm((s) => ({ ...s, effectiveFrom: e.target.value }))} />
        </div>
        {taught && (
          <Input className="h-8 w-32" type="number" placeholder="Total credits" value={form.credits}
            onChange={(e) => setForm((s) => ({ ...s, credits: e.target.value }))} />
        )}
        <Input className="h-8 w-28" type="number" placeholder="Months" value={form.duration}
          onChange={(e) => setForm((s) => ({ ...s, duration: e.target.value }))} />
        <Input className="h-8 w-64" placeholder="What changes and why (required)" value={form.note}
          onChange={(e) => setForm((s) => ({ ...s, note: e.target.value }))} />
        <Button size="sm" disabled={create.isPending || !form.effectiveFrom || !form.note.trim()}
          onClick={async () => {
            try {
              await create.mutateAsync({
                effectiveFrom: form.effectiveFrom, note: form.note.trim(),
                taughtTotalCredits: form.credits ? Number(form.credits) : undefined,
                durationMonths: form.duration ? Number(form.duration) : undefined,
              })
              toast({ title: 'New version created', description: `For students starting from ${form.effectiveFrom}; current students keep theirs.` })
              setForm({ effectiveFrom: '', credits: '', duration: '', note: '' })
            } catch (e) {
              toast({ title: 'Could not create the version', description: (e as ApiError).message, variant: 'destructive' })
            }
          }}>Create version</Button>
      </div>
      {taught && (
        <p className="text-helper">
          After creating a version, change its modules on the Modules tab: changes go to the newest
          version while nobody has started on it.
        </p>
      )}
    </div>
  )
}
