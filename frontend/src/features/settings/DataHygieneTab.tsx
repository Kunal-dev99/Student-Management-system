'use client'

/**
 * Data hygiene — scan the domain for likely duplicate persons, opportunities,
 * awards and research projects. Nothing is deleted automatically; the admin
 * chooses per group. Persons open the existing merge dialog (person.gdpr);
 * the other kinds allow deletion only when nothing references the row.
 */

import { useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, GitMerge, Loader2, RefreshCw, Trash2, Users } from 'lucide-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/components/ui/use-toast'
import { api, ApiError } from '@/shared/api/client'
import { useMergePersons } from '@/features/persons/api'
import { useAuth } from '@/shared/auth/AuthContext'

interface DupItem {
  id: string
  label: string
  sub: string | null
  inUse: number
  createdAt: string | null
}
interface DupResult {
  groups: {
    persons: DupItem[][]
    opportunities: DupItem[][]
    awards: DupItem[][]
    projects: DupItem[][]
  }
  counts: {
    persons: number; opportunities: number; awards: number; projects: number
    groups: number
  }
}

function useDuplicates() {
  return useQuery({
    queryKey: ['admin', 'duplicates'],
    queryFn: () => api.get<DupResult>('/admin/duplicates'),
  })
}

function useDeleteDuplicate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ kind, id }: { kind: 'opportunity' | 'award' | 'project'; id: string }) =>
      api.del(`/admin/duplicates/${kind}/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'duplicates'] }),
  })
}

const KIND_LABEL = {
  persons: 'Persons',
  opportunities: 'Opportunities',
  awards: 'Awards',
  projects: 'Research projects',
} as const

/** One duplicate group — first item is the oldest ("keep") suggestion. */
function DuplicateGroup({
  kind, items, onMergePersons,
}: {
  kind: keyof DupResult['groups']
  items: DupItem[]
  onMergePersons: (surviving: string, losing: string) => void
}) {
  const { toast } = useToast()
  const del = useDeleteDuplicate()
  const [keepId, setKeepId] = useState(items[0]?.id)

  return (
    <div className="rounded-md border border-border p-3 space-y-2">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="text-sm font-medium">
          {items.length} rows share &ldquo;{items[0].label}&rdquo;
        </div>
        <Badge variant="outline" className="text-[10px]">
          suggested keep · oldest row
        </Badge>
      </div>
      <div className="space-y-1.5">
        {items.map((row) => {
          const isKeep = row.id === keepId
          const canDelete = kind !== 'persons' && !isKeep && row.inUse === 0
          const canMerge = kind === 'persons' && !isKeep
          return (
            <div
              key={row.id}
              className={`flex items-center justify-between gap-2 rounded-sm border px-2 py-1.5 ${
                isKeep ? 'border-primary/40 bg-primary/5' : 'border-border'
              }`}
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setKeepId(row.id)}
                    className={`h-3 w-3 shrink-0 rounded-full border ${
                      isKeep ? 'bg-primary border-primary' : 'border-muted-foreground/40 hover:border-primary'
                    }`}
                    aria-label={isKeep ? 'selected as keeper' : 'set as keeper'}
                  />
                  <span className="text-sm truncate">{row.label}</span>
                  {isKeep && <Badge variant="success" className="text-[10px]">keep</Badge>}
                </div>
                <div className="pl-5 text-xs text-muted-foreground flex flex-wrap items-baseline gap-3">
                  {row.sub && <span>{row.sub}</span>}
                  <span className="num">in use: {row.inUse}</span>
                  {row.createdAt && (
                    <span className="text-muted-foreground/70">
                      created {new Date(row.createdAt).toISOString().slice(0, 10)}
                    </span>
                  )}
                  {kind === 'persons' && (
                    <Link href={`/persons/${row.id}`}
                      className="text-primary hover:underline">open →</Link>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                {canMerge && (
                  <Button size="sm" variant="outline"
                    onClick={() => onMergePersons(keepId!, row.id)}>
                    <GitMerge className="h-3 w-3 mr-1" /> Merge into keeper
                  </Button>
                )}
                {canDelete && (
                  <Button
                    size="sm" variant="ghost"
                    disabled={del.isPending}
                    onClick={async () => {
                      try {
                        await del.mutateAsync({ kind: kind.slice(0, -1) as any, id: row.id })
                        toast({ title: 'Deleted' })
                      } catch (e) {
                        toast({ title: 'Cannot delete',
                          description: (e as ApiError).message, variant: 'destructive' })
                      }
                    }}
                  >
                    <Trash2 className="h-3 w-3 text-danger" />
                  </Button>
                )}
                {!isKeep && !canMerge && !canDelete && (
                  <span className="text-[11px] text-muted-foreground">
                    still in use · unlink first
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function DataHygieneTab() {
  const { hasPermission } = useAuth()
  const canMergePersons = hasPermission('person.gdpr')
  const { data, isLoading, refetch, isFetching } = useDuplicates()
  const merge = useMergePersons()
  const { toast } = useToast()

  const onMergePersons = async (surviving: string, losing: string) => {
    if (!canMergePersons) {
      toast({
        title: 'Merging persons needs the person.gdpr permission',
        variant: 'destructive',
      })
      return
    }
    try {
      const r = await merge.mutateAsync({
        survivingPersonId: surviving,
        losingPersonId: losing,
        reason: 'Data hygiene · duplicate cleanup',
      })
      toast({ title: `Merged — ${r.totalRowsRewritten} row(s) rewritten` })
      refetch()
    } catch (e) {
      toast({ title: 'Merge failed', description: (e as ApiError).message, variant: 'destructive' })
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-surface-1 p-3">
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-primary" />
          <div>
            <p className="text-sm font-medium">Data hygiene</p>
            <p className="text-helper text-xs">
              Scans persons, opportunities, awards and projects for likely duplicates by
              normalised name or reference. Pick a keeper; merge (persons) or delete unused
              rows. Nothing changes until you click.
            </p>
          </div>
        </div>
        <Button size="sm" variant="outline" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={`h-3.5 w-3.5 mr-1 ${isFetching ? 'animate-spin' : ''}`} /> Rescan
        </Button>
      </div>

      {isLoading && <Skeleton className="h-40 w-full" />}

      {data && data.counts.groups === 0 && (
        <div className="rounded-md border border-dashed border-border p-8 text-center">
          <p className="text-sm font-medium">No duplicates found.</p>
          <p className="text-helper text-xs mt-1">The data is tidy.</p>
        </div>
      )}

      {data && data.counts.groups > 0 && (
        <div className="rounded-md border border-warning/30 bg-warning/10 p-3 flex gap-2">
          <AlertTriangle className="h-4 w-4 text-warning shrink-0 mt-0.5" />
          <p className="text-sm">
            <span className="font-medium">{data.counts.groups} duplicate group(s) found</span>
            {' — '}
            {(['persons', 'opportunities', 'awards', 'projects'] as const)
              .filter((k) => data.groups[k].length > 0)
              .map((k) => `${data.groups[k].length} in ${KIND_LABEL[k].toLowerCase()}`)
              .join(', ')}.
          </p>
        </div>
      )}

      {data && (['persons', 'opportunities', 'awards', 'projects'] as const).map((kind) => {
        const groups = data.groups[kind]
        if (groups.length === 0) return null
        return (
          <section key={kind} className="space-y-2">
            <div className="flex items-baseline gap-2">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                {KIND_LABEL[kind]}
              </h3>
              <span className="text-xs text-muted-foreground num">{groups.length} group(s)</span>
            </div>
            <div className="space-y-2">
              {groups.map((items, i) => (
                <DuplicateGroup
                  key={`${kind}-${i}`}
                  kind={kind}
                  items={items}
                  onMergePersons={onMergePersons}
                />
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}
