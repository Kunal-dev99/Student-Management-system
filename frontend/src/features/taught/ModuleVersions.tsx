'use client'

/** Effective dating, Phase 8a — a module's dated versions and yearly runs (Demo 2 item 1.3).
 *
 *  What a module teaches (title, credits, level, term) belongs to a version in force over a
 *  period. A version students are enrolled on is locked (the CMA rule: you can't change what was
 *  sold); a change is a new version from a date, and students already enrolled stay on theirs. */

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

export interface ModuleVersion {
  id: string
  versionNo: number
  label: string
  title: string
  credits: number
  level: number
  term: string | null
  /** Phase 8c — module FTE % (share of a full-time year); derived from credits when not set. */
  ftePct: number | null
  fteDerived: boolean
  validFrom: string
  /** Exclusive; null = open-ended. */
  validTo: string | null
  changeNote: string | null
  enrolments: number | null
  locked: boolean
  current: boolean
}

export interface ModuleRunRow {
  id: string
  academicYear: string
  version: string
  versionId: string
  startDate: string | null
  endDate: string | null
  enrolments: number
}

export interface ModuleCatalogue {
  moduleId: string
  code: string
  versions: ModuleVersion[]
  runs: ModuleRunRow[]
}

export const useModuleCatalogue = (moduleId: string, enabled = true) =>
  useQuery({
    queryKey: ['taught-module-catalogue', moduleId],
    queryFn: () => api.get<ModuleCatalogue>(`/taught-modules/${moduleId}/catalogue`),
    enabled: !!moduleId && enabled,
  })

export function useNewModuleVersion(moduleId: string, programmeId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { effectiveFrom: string; title?: string; credits?: number; level?: number; term?: string; ftePct?: number; note: string }) =>
      api.post<ModuleVersion>(`/taught-modules/${moduleId}/versions`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['taught-module-catalogue', moduleId] })
      qc.invalidateQueries({ queryKey: ['taught-modules', programmeId] })
    },
  })
}

function dayBefore(iso: string | null): string | null {
  if (!iso) return null
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() - 1)
  return d.toISOString().slice(0, 10)
}

export function ModuleVersionsPanel({ moduleId, programmeId }: { moduleId: string; programmeId: string }) {
  const { toast } = useToast()
  const cat = useModuleCatalogue(moduleId)
  const create = useNewModuleVersion(moduleId, programmeId)
  const [form, setForm] = useState({ effectiveFrom: '', title: '', credits: '', level: '', fte: '', note: '' })

  if (cat.isLoading) return <Skeleton className="h-16 w-full" />
  const c = cat.data
  if (!c) return null

  return (
    <div className="mt-2 rounded-md border border-border bg-surface-2/40 p-2 space-y-2">
      <p className="flex items-center gap-1.5 text-xs font-medium">
        <GitBranch className="h-3.5 w-3.5" /> Versions — what the module teaches, by date
      </p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Version</TableHead>
            <TableHead>In force</TableHead>
            <TableHead>Title</TableHead>
            <TableHead className="text-right">Credits</TableHead>
            <TableHead>Level</TableHead>
            <TableHead className="text-right">FTE %</TableHead>
            <TableHead className="text-right">Students</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {c.versions.map((v) => (
            <TableRow key={v.id}>
              <TableCell className="whitespace-nowrap">
                <span className="font-medium">{v.label}</span>
                {v.current && <Badge variant="success" className="ml-1.5">current</Badge>}
                {v.locked && <Lock className="inline h-3 w-3 ml-1.5 text-muted-foreground" aria-label="locked" />}
                {v.changeNote && <span className="block text-xs text-muted-foreground">{v.changeNote}</span>}
              </TableCell>
              <TableCell className="num whitespace-nowrap text-xs">{v.validFrom} → {dayBefore(v.validTo) ?? 'open'}</TableCell>
              <TableCell className="text-xs">{v.title}</TableCell>
              <TableCell className="num text-right">{v.credits}</TableCell>
              <TableCell className="num">L{v.level}</TableCell>
              <TableCell className="num text-right"
                title={v.fteDerived ? 'Derived from credits ÷ the programme’s total credits' : 'Set on this version'}>
                {v.ftePct != null ? v.ftePct.toFixed(2) : '—'}
                {v.fteDerived && <span className="text-xs text-muted-foreground"> (from credits)</span>}
              </TableCell>
              <TableCell className="num text-right">{v.enrolments ?? 0}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {c.runs.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Runs: {c.runs.map((r) => `${r.academicYear} on ${r.version} (${r.enrolments} student${r.enrolments === 1 ? '' : 's'})`).join(' · ')}
        </p>
      )}
      <div className="flex flex-wrap items-end gap-2 pt-1 border-t border-border/60">
        <div className="flex flex-col gap-1">
          <label htmlFor={`mv-from-${moduleId}`} className="text-label">New version from</label>
          <Input id={`mv-from-${moduleId}`} type="date" className="h-7 w-36" value={form.effectiveFrom}
            onChange={(e) => setForm((s) => ({ ...s, effectiveFrom: e.target.value }))} />
        </div>
        <Input className="h-7 w-48" placeholder="New title (optional)" value={form.title}
          onChange={(e) => setForm((s) => ({ ...s, title: e.target.value }))} />
        <Input className="h-7 w-24" type="number" placeholder="Credits" value={form.credits}
          onChange={(e) => setForm((s) => ({ ...s, credits: e.target.value }))} />
        <Input className="h-7 w-20" type="number" placeholder="Level" value={form.level}
          onChange={(e) => setForm((s) => ({ ...s, level: e.target.value }))} />
        <Input className="h-7 w-24" type="number" min={0} max={100} step="0.01" placeholder="FTE %"
          title="Share of a full-time year. Blank = derived from credits." value={form.fte}
          onChange={(e) => setForm((s) => ({ ...s, fte: e.target.value }))} />
        <Input className="h-7 w-56" placeholder="What changed and why (required)" value={form.note}
          onChange={(e) => setForm((s) => ({ ...s, note: e.target.value }))} />
        <Button size="sm" className="h-7" disabled={create.isPending || !form.effectiveFrom || !form.note.trim()}
          onClick={async () => {
            try {
              const v = await create.mutateAsync({
                effectiveFrom: form.effectiveFrom, note: form.note.trim(),
                title: form.title.trim() || undefined,
                credits: form.credits ? Number(form.credits) : undefined,
                level: form.level ? Number(form.level) : undefined,
                ftePct: form.fte ? Number(form.fte) : undefined,
              })
              toast({ title: `${c.code} ${v.label} created`, description: `In force from ${v.validFrom}; enrolled students keep their version.` })
              setForm({ effectiveFrom: '', title: '', credits: '', level: '', fte: '', note: '' })
            } catch (e) {
              toast({ title: 'Could not create the version', description: (e as ApiError).message, variant: 'destructive' })
            }
          }}>Create version</Button>
      </div>
      <p className="text-xs text-muted-foreground">
        A locked version has students on it, so what it teaches can&apos;t change (CMA). The new version
        applies to runs from its date; students already enrolled stay on theirs.
      </p>
    </div>
  )
}
