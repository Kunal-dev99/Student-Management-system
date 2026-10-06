'use client'

/**
 * Usage & review (custom attribute governance, Phase 6): for every active attribute, which returns
 * map it, when a return last read it, how many current students have a value, when it last
 * changed, and whether its HESA field is still in the spec. Attributes the review rules flag are
 * listed first with the reasons; putting one under review is a person's decision — nothing here
 * changes an attribute on its own, and anything mapped in a live return is never flagged.
 */
import { useState } from 'react'
import { ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/components/ui/use-toast'
import { useCustomFieldDashboard, useCustomFieldLifecycle } from '@/features/statutory/customFields'
import { StatusBadge, fmt } from '@/features/statutory/customAttrUi'

const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString() : '—')

export function UsageReviewTab({ canGovern }: { canGovern: boolean }) {
  const { toast } = useToast()
  const { data, isLoading, isError, error } = useCustomFieldDashboard(true)
  const lifecycle = useCustomFieldLifecycle()
  const [busyId, setBusyId] = useState<string | null>(null)

  if (isLoading) return <Skeleton className="h-24 w-full" />
  if (isError) return <p className="text-sm text-danger">{(error as Error).message}</p>
  const rows = data ?? []
  if (rows.length === 0) return <p className="text-helper">No active attributes.</p>
  const candidates = rows.filter((r) => r.health.reviewCandidate).length

  return (
    <div className="space-y-3">
      <p className="text-helper">
        {candidates > 0
          ? `${candidates} attribute${candidates === 1 ? '' : 's'} may no longer be needed. `
          : 'Nothing is flagged for review. '}
        Flagged when not mapped and rarely filled, untouched for a reporting cycle, or its HESA field has
        left the specification. Attributes mapped in a live return are protected. Nothing changes on its own.
      </p>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Attribute</TableHead>
              <TableHead>Mapped in</TableHead>
              <TableHead>Last used</TableHead>
              <TableHead className="text-right">Fill rate</TableHead>
              <TableHead>Last change</TableHead>
              <TableHead>HESA</TableHead>
              <TableHead>Recommendation</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => {
              const h = r.health
              return (
                <TableRow key={r.id} className={h.reviewCandidate ? 'bg-[hsl(var(--warning)/0.07)]' : undefined}>
                  <TableCell>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-medium">{r.label}</span>
                      {r.status !== 'active' && <StatusBadge status={r.status} />}
                    </div>
                    <span className="font-mono text-[11px] text-muted-foreground">{r.sourcePath}</span>
                  </TableCell>
                  <TableCell className="text-xs">
                    {h.mappings.length === 0 ? <span className="text-muted-foreground">—</span> : h.mappings.map((m) => (
                      <div key={`${m.profileId}-${m.targetField}`}>
                        {m.profileCode} {m.academicYear} · <span className="font-mono">{m.targetField}</span>
                        {m.live ? '' : m.signedOff ? ' (signed off)' : ' (inactive)'}
                      </div>
                    ))}
                  </TableCell>
                  <TableCell className="text-xs" title={h.lastUsed ? fmt(h.lastUsed) : undefined}>
                    {day(h.lastUsed)}{h.useCount > 0 ? ` · ${h.useCount}×` : ''}
                  </TableCell>
                  <TableCell className="text-right text-xs num" title={`${h.filledCount} of ${h.currentStudents} current students`}>
                    {Math.round(h.fillRate * 100)}%
                  </TableCell>
                  <TableCell className="text-xs">{day(h.lastValueUpdate)}</TableCell>
                  <TableCell className="text-xs">
                    {h.hesa.field ? (
                      <span className={h.hesa.state === 'removed' ? 'text-danger' : undefined} title={h.hesa.specification ?? undefined}>
                        {h.hesa.field}{h.hesa.state === 'removed' ? ' — removed' : ''}
                      </span>
                    ) : <span className="text-muted-foreground">—</span>}
                  </TableCell>
                  <TableCell className="text-xs space-y-1 min-w-[220px]">
                    <div className="flex items-center gap-1.5">
                      {h.protected && <ShieldCheck className="h-3.5 w-3.5 text-[hsl(var(--success))]" />}
                      <Badge variant={h.reviewCandidate ? 'warning' : 'secondary'}>{h.recommendation}</Badge>
                    </div>
                    {h.reasons.length > 0 && (
                      <ul className="list-disc pl-4 text-muted-foreground">
                        {h.reasons.map((x) => <li key={x}>{x}</li>)}
                      </ul>
                    )}
                    {h.reviewCandidate && canGovern && (
                      <Button size="sm" variant="outline" className="h-7" disabled={busyId === r.id}
                        onClick={async () => {
                          setBusyId(r.id)
                          try {
                            await lifecycle.mutateAsync({ id: r.id, action: 'review', reason: h.reasons.join(' ') })
                            toast({ title: `"${r.label}" is under review`, description: 'An approver can now keep or retire it.' })
                          } catch (e) {
                            toast({ title: 'Could not start the review', description: (e as Error).message, variant: 'destructive' })
                          } finally { setBusyId(null) }
                        }}>
                        Put under review
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
