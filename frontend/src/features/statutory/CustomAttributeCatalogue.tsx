'use client'

/**
 * Custom attribute catalogue (governance Phase 3): every attribute that has been live — active,
 * under review, retired — with how much it is used, and a detail view to review, keep, retire or
 * restore it. Retiring takes an attribute out of mapping, data entry and the return without
 * deleting anything; its values stay readable and come back on restore.
 */
import { useState } from 'react'
import { Table2, Eye, Info } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/components/ui/use-toast'
import { useConfirm } from '@/components/common/ConfirmDialog'
import {
  useCustomFieldCatalogue, useCustomFieldDetail, useCustomFieldLifecycle, useEnableCustomFieldHistory,
  type CustomField, type LifecycleAction,
} from '@/features/statutory/customFields'
import { ACTION_LABEL, CopyPath, StatusBadge, fmt } from '@/features/statutory/customAttrUi'

const FILTERS: { v: string | null; l: string }[] = [
  { v: 'active,review', l: 'Live' },
  { v: 'review', l: 'Under review' },
  { v: 'retired', l: 'Retired' },
  { v: null, l: 'All' },
]

const ACTIONS: Record<LifecycleAction, { label: string; needsReason: boolean; hint: string }> = {
  review: { label: 'Put under review', needsReason: true,
    hint: 'It keeps working while under review. An approver then keeps it or retires it.' },
  keep: { label: 'Keep it', needsReason: false, hint: 'Ends the review; the attribute stays active.' },
  retire: { label: 'Retire', needsReason: true,
    hint: 'Takes it out of mapping, data entry and the return. Values and history are kept and come back on restore.' },
  restore: { label: 'Restore', needsReason: true, hint: 'Makes it active again, with the values it had.' },
}

function DetailDialog({ id, canGovern, canApprove, canEnterData, canConfigure, onValues, onClose }: {
  id: string; canGovern: boolean; canApprove: boolean; canEnterData: boolean; canConfigure: boolean
  onValues: (f: CustomField) => void; onClose: () => void
}) {
  const { toast } = useToast()
  const confirm = useConfirm()
  const { data: f, isLoading } = useCustomFieldDetail(id)
  const lifecycle = useCustomFieldLifecycle()
  const enableHistory = useEnableCustomFieldHistory()
  const [action, setAction] = useState<LifecycleAction | null>(null)
  const [reason, setReason] = useState('')

  const blockers = (f?.dependencies ?? []).filter((d) => d.blocksRetirement)
  const available: LifecycleAction[] = !f ? [] : [
    ...(f.status === 'active' && canGovern ? ['review' as const] : []),
    ...(f.status === 'review' && canApprove ? ['keep' as const, 'retire' as const] : []),
    ...(f.status === 'retired' && canApprove ? ['restore' as const] : []),
  ]

  const run = async () => {
    if (!f || !action) return
    try {
      const out = await lifecycle.mutateAsync({ id: f.id, action, reason: reason.trim() || undefined })
      toast({ title: `${ACTIONS[action].label}: "${out.label}"`, description: `Now ${out.status}.` })
      setAction(null); setReason('')
    } catch (e) {
      toast({ title: `Could not ${ACTIONS[action].label.toLowerCase()}`, description: (e as Error).message, variant: 'destructive' })
    }
  }

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="flex max-h-[88vh] max-w-2xl flex-col overflow-y-auto">
        <DialogHeader><DialogTitle>{f?.label ?? 'Attribute'}</DialogTitle></DialogHeader>
        {isLoading || !f ? <Skeleton className="h-40 w-full" /> : (
          <div className="space-y-4 text-sm">
            <div className="space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge status={f.status} />
                <Badge variant="secondary">{f.dataType}</Badge>
                {f.trackHistory && <Badge variant="info">dated history</Badge>}
                <CopyPath path={f.sourcePath} />
              </div>
              <p className="text-muted-foreground">{f.reason}</p>
              <p className="text-xs text-muted-foreground">
                Requested by {f.requestedByEmail ?? 'unknown'} · {fmt(f.createdAt)}
                {f.decidedByEmail && <> · approved by {f.decidedByEmail} · {fmt(f.decidedAt)}</>}
              </p>
            </div>

            <div className="grid grid-cols-3 gap-2">
              <div className="rounded-md border border-border p-2"><p className="text-label">Students with a value</p><p className="text-lg">{f.usage?.valueCount ?? 0}</p></div>
              <div className="rounded-md border border-border p-2"><p className="text-label">Mapped fields</p><p className="text-lg">{f.usage?.mappingCount ?? 0}</p></div>
              <div className="rounded-md border border-border p-2"><p className="text-label">Last value change</p><p className="text-xs pt-1">{fmt(f.usage?.lastValueUpdate) || '—'}</p></div>
            </div>

            <div className="space-y-1.5">
              <p className="text-label">Where it is mapped</p>
              {f.dependencies.length === 0 ? <p className="text-helper">Not mapped in any return.</p> : (
                <Table>
                  <TableHeader><TableRow>
                    <TableHead>Return</TableHead><TableHead>Year</TableHead><TableHead>Field</TableHead><TableHead>State</TableHead>
                  </TableRow></TableHeader>
                  <TableBody>
                    {f.dependencies.map((d) => (
                      <TableRow key={d.mappingId}>
                        <TableCell>{d.profileCode}</TableCell>
                        <TableCell>{d.academicYear}</TableCell>
                        <TableCell className="font-mono text-xs">{d.targetField}{d.required ? ' *' : ''}</TableCell>
                        <TableCell>
                          {d.signedOff ? <Badge variant="secondary">signed off</Badge>
                            : d.profileActive ? <Badge variant="warning">live</Badge> : <Badge variant="secondary">inactive</Badge>}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>

            {(available.length > 0 || canEnterData || (canConfigure && !f.trackHistory && f.status !== 'retired')) && (
              <div className="flex flex-wrap gap-2">
                {f.status !== 'retired' && canEnterData && (
                  <Button size="sm" variant="secondary" onClick={() => onValues(f)}><Table2 className="h-3.5 w-3.5 mr-1" /> Enter data</Button>
                )}
                {f.status === 'retired' && (
                  <Button size="sm" variant="secondary" onClick={() => onValues(f)}><Eye className="h-3.5 w-3.5 mr-1" /> View values</Button>
                )}
                {canConfigure && !f.trackHistory && f.status !== 'retired' && (
                  <Button size="sm" variant="ghost" disabled={enableHistory.isPending} onClick={async () => {
                    if (!(await confirm({
                      title: `Keep dated history for "${f.label}"?`,
                      description: 'Values already entered are kept from each student\'s start date. From now on a change is recorded with the date it took effect, and values can no longer be cleared. This can\'t be switched off.',
                      confirmLabel: 'Keep dated history',
                    }))) return
                    try { await enableHistory.mutateAsync(f.id); toast({ title: `"${f.label}" now keeps dated history` }) } catch (e) {
                      toast({ title: 'Could not switch on history', description: (e as Error).message, variant: 'destructive' })
                    }
                  }}>Keep history</Button>
                )}
                {available.map((a) => (
                  <Button key={a} size="sm" variant={a === 'retire' ? 'destructive' : a === 'keep' ? 'outline' : 'default'}
                    onClick={() => { setAction(a); setReason('') }}>{ACTIONS[a].label}</Button>
                ))}
              </div>
            )}

            {action && (
              <div className="rounded-md border border-border bg-muted/30 p-3 space-y-2">
                <p className="font-medium">{ACTIONS[action].label}</p>
                <p className="text-helper">{ACTIONS[action].hint}</p>
                {action === 'retire' && blockers.length > 0 && (
                  <p className="flex items-start gap-1.5 text-xs text-danger">
                    <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                    Still mapped in {blockers.map((d) => `${d.profileCode} ${d.academicYear} (${d.targetField})`).join(', ')}.
                    Re-map or remove those fields first.
                  </p>
                )}
                <div className="space-y-1">
                  <Label htmlFor="cf-lc-reason">Reason{ACTIONS[action].needsReason ? ' (required)' : ' (optional)'}</Label>
                  <Textarea id="cf-lc-reason" className="min-h-[60px]" value={reason} onChange={(e) => setReason(e.target.value)} />
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => setAction(null)}>Cancel</Button>
                  <Button size="sm" variant={action === 'retire' ? 'destructive' : 'default'} onClick={run}
                    disabled={lifecycle.isPending || (ACTIONS[action].needsReason && !reason.trim())
                      || (action === 'retire' && blockers.length > 0)}>
                    {lifecycle.isPending ? 'Saving…' : ACTIONS[action].label}
                  </Button>
                </div>
              </div>
            )}

            <div className="space-y-1.5">
              <p className="text-label">History</p>
              <ul className="space-y-1 text-xs">
                {f.events.map((e) => (
                  <li key={e.id}>
                    <span className="text-muted-foreground">{fmt(e.at)}</span> · {ACTION_LABEL[e.action] ?? e.action}
                    {e.actorEmail ? ` by ${e.actorEmail}` : ''}{e.notes ? ` — ${e.notes}` : ''}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
        <DialogFooter><Button variant="outline" onClick={onClose}>Close</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function CatalogueTab({ canGovern, canApprove, canEnterData, canConfigure, onValues }: {
  canGovern: boolean; canApprove: boolean; canEnterData: boolean; canConfigure: boolean
  onValues: (f: CustomField) => void
}) {
  const [filter, setFilter] = useState<string | null>('active,review')
  const [openId, setOpenId] = useState<string | null>(null)
  const { data, isLoading, isError, error } = useCustomFieldCatalogue(filter, true)

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1.5">
        {FILTERS.map((x) => (
          <Button key={x.l} size="sm" variant={filter === x.v ? 'default' : 'outline'} className="h-7"
            onClick={() => setFilter(x.v)}>{x.l}</Button>
        ))}
      </div>
      {isLoading ? <Skeleton className="h-16 w-full" /> : isError ? (
        <p className="text-sm text-danger">{(error as Error).message}</p>
      ) : (data ?? []).length === 0 ? (
        <p className="text-helper">Nothing here.</p>
      ) : (
        <div className="rounded-md border border-border divide-y divide-border">
          {(data ?? []).map((f) => (
            <div key={f.id} className="flex items-start justify-between gap-3 p-3">
              <div className="min-w-0 space-y-0.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{f.label}</span>
                  <StatusBadge status={f.status} />
                  <Badge variant="secondary">{f.dataType}</Badge>
                  {f.trackHistory && <Badge variant="info">dated history</Badge>}
                </div>
                <CopyPath path={f.sourcePath} />
                <p className="text-xs text-muted-foreground">
                  {f.usage?.valueCount ?? 0} student value(s) · mapped in {f.usage?.mappingCount ?? 0} field(s)
                  {f.usage?.lastValueUpdate ? ` · last change ${fmt(f.usage.lastValueUpdate)}` : ''}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                {f.status !== 'retired' && canEnterData && (
                  <Button size="sm" variant="secondary" onClick={() => onValues(f)}>
                    <Table2 className="h-3.5 w-3.5 mr-1" /> Enter data
                  </Button>
                )}
                <Button size="sm" variant="ghost" onClick={() => setOpenId(f.id)}>Details</Button>
              </div>
            </div>
          ))}
        </div>
      )}
      {openId && (
        <DetailDialog id={openId} canGovern={canGovern} canApprove={canApprove} canEnterData={canEnterData}
          canConfigure={canConfigure} onValues={onValues} onClose={() => setOpenId(null)} />
      )}
    </div>
  )
}
