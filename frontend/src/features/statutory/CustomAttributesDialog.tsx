'use client'

/**
 * Custom student attributes — capture an attribute HESA needs but the core model doesn't hold.
 *
 * Governed (maker-checker): someone *requests* an attribute (label + type + mandatory reason); a
 * different person approves it — or rejects it with a reason — and activates it. Only an active
 * attribute takes values ("Enter data") and is mappable in a field as `custom.<key>`.
 *
 * Tabs: Attributes (live ones) · Requests (the queue) · New request · History (decision trail).
 * Each tab and action only shows for someone who holds the permission it needs.
 */
import { useEffect, useState } from 'react'
import { Plus, Table2, X, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/components/ui/use-toast'
import { useConfirm } from '@/components/common/ConfirmDialog'
import { useAuth } from '@/shared/auth/AuthContext'
import {
  useCustomFields, useCustomFieldRequests, useCustomFieldEvents,
  useRequestCustomField, useApproveCustomField, useRejectCustomField, useActivateCustomField,
  useWithdrawCustomField, useEnableCustomFieldHistory, useCheckCustomField, useReassessCustomField,
  useCustomFieldValues, useSetCustomFieldValues,
  type CustomField, type CustomFieldStatus, type CustomFieldType,
} from '@/features/statutory/customFields'
import { AssessmentPanel, VerdictBadge } from '@/features/statutory/AssessmentPanel'
import { ACTION_LABEL, CopyPath, StatusBadge, fmt } from '@/features/statutory/customAttrUi'
import { CatalogueTab } from '@/features/statutory/CustomAttributeCatalogue'
import { UsageReviewTab } from '@/features/statutory/CustomAttributeUsage'

const TYPES: { v: CustomFieldType; l: string }[] = [
  { v: 'code', l: 'Code (e.g. 01, 02)' },
  { v: 'string', l: 'Text' },
  { v: 'number', l: 'Number' },
  { v: 'date', l: 'Date' },
]

/** The per-field data-entry modal: every student in a scrollable grid with a value box.
 *  A retired attribute opens read-only — its values are kept and can be looked at. */
export function ValuesDialog({ field, onClose }: { field: CustomField; onClose: () => void }) {
  const readOnly = field.status === 'retired'
  const { toast } = useToast()
  const { data, isLoading } = useCustomFieldValues(field.id)
  const save = useSetCustomFieldValues(field.id)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [original, setOriginal] = useState<Record<string, string>>({})
  // Effective dating, Phase 6 — the date new values take effect (attributes that keep history).
  const [effectiveDate, setEffectiveDate] = useState('')

  useEffect(() => {
    if (data) {
      const seed: Record<string, string> = {}
      for (const r of data.rows) seed[r.studentId] = r.value ?? ''
      setDraft(seed)
      setOriginal(seed)
    }
  }, [data])

  const onSave = async () => {
    // A dated attribute records a change only for the rows that actually changed.
    const values = Object.entries(draft)
      .filter(([studentId, value]) => !field.trackHistory || value !== (original[studentId] ?? ''))
      .map(([studentId, value]) => ({ studentId, value: value || null }))
    try {
      const res = await save.mutateAsync({ values, effectiveDate: field.trackHistory ? effectiveDate || undefined : undefined })
      toast({ title: 'Values saved', description: `${res.filled} student(s) now have a value.` })
      onClose()
    } catch (e) {
      toast({ title: 'Could not save', description: (e as Error).message, variant: 'destructive' })
    }
  }

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="flex max-h-[88vh] max-w-2xl flex-col overflow-hidden">
        <DialogHeader className="flex-none">
          <DialogTitle>{readOnly ? 'Values' : 'Enter data'} — {field.label}</DialogTitle>
        </DialogHeader>
        {readOnly ? (
          <p className="flex-none text-helper">
            This attribute is retired: its values are kept for the record but can&apos;t be changed,
            and no return reads them. Restore it to use it again.
          </p>
        ) : <p className="flex-none text-helper">
          Maps to <span className="font-mono text-xs">{field.sourcePath}</span>.{' '}
          {field.trackHistory
            ? 'This attribute keeps dated history: changed values are recorded from the date below, and the return reads the value in force at the end of each period.'
            : 'Leave a row blank to clear it.'}{' '}
          HESA is strict — enter the exact coded value the specification expects.
        </p>}
        {field.trackHistory && !readOnly && (
          <div className="flex-none flex items-end gap-2">
            <div className="space-y-1">
              <Label htmlFor="cf-eff">Changed values take effect from</Label>
              <Input id="cf-eff" type="date" className="h-8 w-40" value={effectiveDate}
                onChange={(e) => setEffectiveDate(e.target.value)} />
            </div>
            <span className="text-helper pb-1.5">Blank = today. Dates inside a signed-off return need returns-amendment rights.</span>
          </div>
        )}
        <div className="-mr-2 mt-2 flex-1 overflow-y-auto pr-2">
          {isLoading ? <Skeleton className="h-40 w-full" /> : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="min-w-[120px]">Student ref</TableHead>
                  <TableHead className="min-w-[160px]">Name</TableHead>
                  <TableHead className="min-w-[160px]">Value</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(data?.rows ?? []).map((r) => (
                  <TableRow key={r.studentId}>
                    <TableCell className="font-mono text-xs">{r.studentRef}</TableCell>
                    <TableCell>{r.studentName}</TableCell>
                    <TableCell>
                      {readOnly ? (
                        <span className="font-mono text-xs">{r.value ?? '—'}</span>
                      ) : (
                        <Input
                          className="h-8"
                          type={field.dataType === 'date' ? 'date' : field.dataType === 'number' ? 'number' : 'text'}
                          value={draft[r.studentId] ?? ''}
                          onChange={(e) => setDraft((d) => ({ ...d, [r.studentId]: e.target.value }))}
                        />
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
        <DialogFooter className="flex-none">
          <Button variant="outline" onClick={onClose}>{readOnly ? 'Close' : 'Cancel'}</Button>
          {!readOnly && (
            <Button onClick={onSave} disabled={save.isPending}>
              {save.isPending ? 'Saving…' : 'Save values'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Approve / reject a request. Reject needs a reason; approve can activate in the same step. */
function DecisionDialog({ field, mode, onClose }: { field: CustomField; mode: 'approve' | 'reject'; onClose: () => void }) {
  const { toast } = useToast()
  const approve = useApproveCustomField()
  const reject = useRejectCustomField()
  const reassess = useReassessCustomField()
  const [reason, setReason] = useState('')
  const [activate, setActivate] = useState(true)
  const [assessment, setAssessment] = useState(field.assessment ?? null)
  const busy = approve.isPending || reject.isPending
  // Approving something the check calls a duplicate needs a stated reason (the backend enforces it).
  const needsOverride = mode === 'approve' && assessment?.verdict === 'duplicate'

  const onSubmit = async () => {
    try {
      if (mode === 'approve') {
        const f = await approve.mutateAsync({ id: field.id, reason: reason.trim() || undefined, activate })
        toast({
          title: `Approved "${f.label}"`,
          description: f.status === 'active' ? `Active — map a field to ${f.sourcePath}, then enter data.` : 'Activate it when it should go live.',
        })
      } else {
        await reject.mutateAsync({ id: field.id, reason: reason.trim() })
        toast({ title: `Rejected "${field.label}"` })
      }
      onClose()
    } catch (e) {
      toast({ title: mode === 'approve' ? 'Could not approve' : 'Could not reject', description: (e as Error).message, variant: 'destructive' })
    }
  }

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="flex max-h-[88vh] max-w-xl flex-col overflow-y-auto">
        <DialogHeader><DialogTitle>{mode === 'approve' ? 'Approve' : 'Reject'} “{field.label}”</DialogTitle></DialogHeader>
        <div className="space-y-3 text-sm">
          <div className="rounded-md border border-border bg-muted/30 p-3 space-y-1">
            <div className="flex items-center gap-2">
              <Badge variant="secondary">{field.dataType}</Badge>
              {field.trackHistory && <Badge variant="info">dated history</Badge>}
              <span className="font-mono text-xs text-muted-foreground">{field.sourcePath}</span>
            </div>
            <p><span className="text-muted-foreground">Requested by</span> {field.requestedByEmail ?? 'unknown'} · {fmt(field.createdAt)}</p>
            <p><span className="text-muted-foreground">Reason:</span> {field.reason}</p>
          </div>
          {assessment ? <AssessmentPanel a={assessment} /> : (
            <p className="text-helper">This request hasn&apos;t been checked yet.</p>
          )}
          <Button size="sm" variant="ghost" className="h-7 px-2" disabled={reassess.isPending}
            onClick={async () => {
              try { setAssessment(await reassess.mutateAsync(field.id)) } catch (e) {
                toast({ title: 'Could not run the check', description: (e as Error).message, variant: 'destructive' })
              }
            }}>
            <RefreshCw className="h-3.5 w-3.5 mr-1" /> {reassess.isPending ? 'Checking…' : 'Re-run the check'}
          </Button>
          <div className="space-y-1.5">
            <Label htmlFor="cf-decision">
              {mode === 'reject' ? 'Reason for rejecting (required)'
                : needsOverride ? 'Why approve it anyway? (required — it looks like a duplicate)' : 'Note (optional)'}
            </Label>
            <Textarea id="cf-decision" className="min-h-[70px]" value={reason} onChange={(e) => setReason(e.target.value)}
              placeholder={mode === 'approve' ? 'e.g. Confirmed against the 2026/27 spec.' : 'e.g. Already held in the core record as …'} />
          </div>
          {mode === 'approve' && (
            <label className="flex items-start gap-2">
              <input type="checkbox" className="mt-0.5" checked={activate} onChange={(e) => setActivate(e.target.checked)} />
              <span>
                Activate now
                <span className="block text-helper">Makes it mappable and open for data entry straight away. Leave unticked to activate later.</span>
              </span>
            </label>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button variant={mode === 'reject' ? 'destructive' : 'default'} onClick={onSubmit}
            disabled={busy || ((mode === 'reject' || needsOverride) && !reason.trim())}>
            {busy ? 'Saving…' : mode === 'approve' ? (activate ? 'Approve & activate' : 'Approve') : 'Reject request'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function AttributesTab({ canEnterData, canConfigure, onEnter }: {
  canEnterData: boolean; canConfigure: boolean; onEnter: (f: CustomField) => void
}) {
  const { toast } = useToast()
  const confirm = useConfirm()
  const { data: fields, isLoading } = useCustomFields()
  const enableHistory = useEnableCustomFieldHistory()

  if (isLoading) return <Skeleton className="h-16 w-full" />
  if ((fields ?? []).length === 0) {
    return <p className="text-helper">No active attributes yet. Request one, and once someone else approves it, it appears here.</p>
  }
  return (
    <div className="rounded-md border border-border divide-y divide-border">
      {(fields ?? []).map((f) => (
        <div key={f.id} className="flex items-start justify-between gap-3 p-3">
          <div className="min-w-0 space-y-0.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{f.label}</span>
              <Badge variant="secondary">{f.dataType}</Badge>
              {f.trackHistory && <Badge variant="info">dated history</Badge>}
              {f.status !== 'active' && <StatusBadge status={f.status} />}
            </div>
            <CopyPath path={f.sourcePath} />
            <p className="text-xs text-muted-foreground">{f.reason}</p>
            {f.decidedByEmail && (
              <p className="text-xs text-muted-foreground">Approved by {f.decidedByEmail} · {fmt(f.decidedAt)}</p>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {canConfigure && !f.trackHistory && (
              <Button size="sm" variant="ghost" disabled={enableHistory.isPending}
                title="Record values with the date they took effect from now on"
                onClick={async () => {
                  if (!(await confirm({
                    title: `Keep dated history for "${f.label}"?`,
                    description: 'Values already entered are kept from each student\'s start date. From now on a change is recorded with the date it took effect, and values can no longer be cleared. This can\'t be switched off.',
                    confirmLabel: 'Keep dated history',
                  }))) return
                  try {
                    await enableHistory.mutateAsync(f.id)
                    toast({ title: `"${f.label}" now keeps dated history` })
                  } catch (e) {
                    toast({ title: 'Could not switch on history', description: (e as Error).message, variant: 'destructive' })
                  }
                }}>
                Keep history
              </Button>
            )}
            {canEnterData && (
              <Button size="sm" variant="secondary" onClick={() => onEnter(f)}>
                <Table2 className="h-3.5 w-3.5 mr-1" /> Enter data
              </Button>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

function RequestsTab({ canApprove, myUserId }: { canApprove: boolean; myUserId: string | null }) {
  const { toast } = useToast()
  const confirm = useConfirm()
  const { data, isLoading, isError, error } = useCustomFieldRequests(true)
  const activate = useActivateCustomField()
  const withdraw = useWithdrawCustomField()
  const [deciding, setDeciding] = useState<{ field: CustomField; mode: 'approve' | 'reject' } | null>(null)

  if (isLoading) return <Skeleton className="h-16 w-full" />
  if (isError) return <p className="text-sm text-danger">{(error as Error).message}</p>
  const order: CustomFieldStatus[] = ['pending', 'approved', 'rejected']
  const rows = [...(data ?? [])].sort((a, b) => order.indexOf(a.status) - order.indexOf(b.status))
  if (rows.length === 0) return <p className="text-helper">No requests.</p>

  return (
    <>
      <div className="rounded-md border border-border divide-y divide-border">
        {rows.map((f) => {
          const mine = !!myUserId && f.requestedBy === myUserId
          return (
            <div key={f.id} className="flex items-start justify-between gap-3 p-3">
              <div className="min-w-0 space-y-0.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{f.label}</span>
                  <StatusBadge status={f.status} />
                  <Badge variant="secondary">{f.dataType}</Badge>
                  {f.trackHistory && <Badge variant="info">dated history</Badge>}
                  {f.status === 'pending' && f.assessment && <VerdictBadge verdict={f.assessment.verdict} />}
                </div>
                <p className="text-xs text-muted-foreground">{f.reason}</p>
                {f.status === 'pending' && f.assessment?.hesa.match && (
                  <p className="text-xs text-muted-foreground">
                    HESA <span className="font-mono">{f.assessment.hesa.match.field}</span> · {f.assessment.hesa.specification}
                  </p>
                )}
                <p className="text-xs text-muted-foreground">
                  Requested by {mine ? 'you' : (f.requestedByEmail ?? 'unknown')} · {fmt(f.createdAt)}
                </p>
                {f.decidedByEmail && (
                  <p className="text-xs text-muted-foreground">
                    {f.status === 'rejected' ? 'Rejected' : 'Approved'} by {f.decidedByEmail} · {fmt(f.decidedAt)}
                    {f.decisionReason ? ` — “${f.decisionReason}”` : ''}
                  </p>
                )}
                {f.status === 'pending' && mine && canApprove && (
                  <p className="text-xs text-muted-foreground">You raised this, so someone else has to decide it.</p>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                {f.status === 'pending' && canApprove && !mine && (
                  <>
                    <Button size="sm" onClick={() => setDeciding({ field: f, mode: 'approve' })}>Approve</Button>
                    <Button size="sm" variant="outline" onClick={() => setDeciding({ field: f, mode: 'reject' })}>Reject</Button>
                  </>
                )}
                {f.status === 'approved' && canApprove && (
                  <Button size="sm" disabled={activate.isPending} onClick={async () => {
                    try {
                      await activate.mutateAsync(f.id)
                      toast({ title: `"${f.label}" is active`, description: `Map a field to ${f.sourcePath}, then enter data.` })
                    } catch (e) {
                      toast({ title: 'Could not activate', description: (e as Error).message, variant: 'destructive' })
                    }
                  }}>Activate</Button>
                )}
                {f.status === 'pending' && (mine || canApprove) && (
                  <Button size="icon" variant="ghost" className="h-8 w-8" title="Withdraw this request"
                    aria-label={`Withdraw the request for ${f.label}`}
                    disabled={withdraw.isPending}
                    onClick={async () => {
                      if (!(await confirm({
                        title: `Withdraw the request for "${f.label}"?`,
                        description: 'The request is removed. The withdrawal stays in the history.',
                        confirmLabel: 'Withdraw request',
                      }))) return
                      try {
                        await withdraw.mutateAsync(f.id)
                        toast({ title: `Withdrew "${f.label}"` })
                      } catch (e) {
                        toast({ title: 'Could not withdraw', description: (e as Error).message, variant: 'destructive' })
                      }
                    }}>
                    <X className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </div>
          )
        })}
      </div>
      {deciding && <DecisionDialog field={deciding.field} mode={deciding.mode} onClose={() => setDeciding(null)} />}
    </>
  )
}

function NewRequestTab({ onRequested }: { onRequested: () => void }) {
  const { toast } = useToast()
  const create = useRequestCustomField()
  const [label, setLabel] = useState('')
  const [dataType, setDataType] = useState<CustomFieldType>('code')
  const [reason, setReason] = useState('')
  const [trackHistory, setTrackHistory] = useState(false)
  // Check as they type (debounced) — duplicates, HESA match, suggested type.
  const [probe, setProbe] = useState({ label: '', reason: '' })
  useEffect(() => {
    const t = setTimeout(() => setProbe({ label: label.trim(), reason: reason.trim() }), 600)
    return () => clearTimeout(t)
  }, [label, reason])
  const check = useCheckCustomField({ ...probe, dataType }, probe.label.length >= 3)

  const onCreate = async () => {
    try {
      const f = await create.mutateAsync({ label: label.trim(), dataType, reason: reason.trim(), trackHistory })
      toast({ title: `Requested "${f.label}"`, description: 'Someone else needs to approve it before it can be used.' })
      setLabel(''); setDataType('code'); setReason(''); setTrackHistory(false)
      onRequested()
    } catch (e) {
      toast({ title: 'Could not raise the request', description: (e as Error).message, variant: 'destructive' })
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-helper">
        Ask for an attribute the return needs but the system doesn&apos;t hold. A different person reviews
        and approves it; only then can it be mapped and filled in.
      </p>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="cf-label">Label</Label>
          <Input id="cf-label" value={label} maxLength={120} onChange={(e) => setLabel(e.target.value)}
            placeholder="e.g. Care leaver flag" />
        </div>
        <div className="space-y-1.5">
          <Label>Type</Label>
          <Select value={dataType} onValueChange={(v) => setDataType(v as CustomFieldType)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {TYPES.map((t) => <SelectItem key={t.v} value={t.v}>{t.l}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="cf-reason">Reason (why this is needed — which HESA field, which return)</Label>
        <Textarea id="cf-reason" className="min-h-[70px]" value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="e.g. HESA CARELEAVER — mandatory, not held in the core model." />
      </div>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" className="mt-0.5" checked={trackHistory}
          onChange={(e) => setTrackHistory(e.target.checked)} />
        <span>
          Keep dated history
          <span className="block text-helper">
            For attributes a return reads as at a date (e.g. a status that can change mid-year).
            Values are recorded with the date they took effect. Can&apos;t be switched off later.
          </span>
        </span>
      </label>
      {check.data && (
        <div className="space-y-1.5">
          <AssessmentPanel a={check.data} compact />
          {check.data.suggested.dataType !== dataType && (
            <Button size="sm" variant="ghost" className="h-7 px-2"
              onClick={() => setDataType(check.data!.suggested.dataType)}>
              Use the suggested type ({check.data.suggested.dataType})
            </Button>
          )}
        </div>
      )}
      <Button size="sm" onClick={onCreate} disabled={!label.trim() || !reason.trim() || create.isPending}>
        {create.isPending ? 'Sending…' : 'Submit request'}
      </Button>
    </div>
  )
}

function HistoryTab() {
  const { data, isLoading, isError, error } = useCustomFieldEvents(true)
  if (isLoading) return <Skeleton className="h-16 w-full" />
  if (isError) return <p className="text-sm text-danger">{(error as Error).message}</p>
  if ((data ?? []).length === 0) return <p className="text-helper">Nothing recorded yet.</p>
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="min-w-[140px]">When</TableHead>
          <TableHead>Attribute</TableHead>
          <TableHead>Action</TableHead>
          <TableHead>By</TableHead>
          <TableHead>Note</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {(data ?? []).map((e) => (
          <TableRow key={e.id}>
            <TableCell className="text-xs">{fmt(e.at)}</TableCell>
            <TableCell>{e.label}</TableCell>
            <TableCell>{ACTION_LABEL[e.action] ?? e.action}</TableCell>
            <TableCell className="text-xs">{e.actorEmail ?? '—'}</TableCell>
            <TableCell className="text-xs text-muted-foreground">{e.notes ?? ''}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

export function CustomAttributesDialog() {
  const { hasPermission, principal } = useAuth()
  const canRequest = hasPermission('custom_attribute.request')
  const canApprove = hasPermission('custom_attribute.approve')
  const canGovern = canRequest || canApprove
  const canEnterData = hasPermission('student.write')
  const canConfigure = hasPermission('admin.configure')
  const { data: queue } = useCustomFieldRequests(canGovern)
  const pending = (queue ?? []).filter((f) => f.status === 'pending' || f.status === 'approved').length

  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState('attributes')
  const [entering, setEntering] = useState<CustomField | null>(null)

  return (
    <>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger asChild>
          <Button size="sm" variant="outline">
            <Plus className="h-4 w-4 mr-1" /> Custom attributes
            {canApprove && pending > 0 && <Badge variant="warning" className="ml-1.5">{pending}</Badge>}
          </Button>
        </DialogTrigger>
        <DialogContent className="flex max-h-[88vh] max-w-3xl flex-col overflow-hidden">
          <DialogHeader className="flex-none"><DialogTitle>Custom student attributes</DialogTitle></DialogHeader>
          <p className="flex-none text-helper">
            Capture an attribute a return needs but the system doesn&apos;t hold yet — no code release.
            A request is approved by someone other than the requester; once active, enter each
            student&apos;s value and map the field to its <span className="font-mono text-xs">custom.…</span> path.
          </p>

          <Tabs value={tab} onValueChange={setTab} className="flex min-h-0 flex-1 flex-col">
            <TabsList className="flex-none self-start">
              <TabsTrigger value="attributes">Attributes</TabsTrigger>
              {canGovern && (
                <TabsTrigger value="requests">
                  Requests{pending > 0 && <Badge variant="warning" className="ml-1.5">{pending}</Badge>}
                </TabsTrigger>
              )}
              {canRequest && <TabsTrigger value="new">New request</TabsTrigger>}
              {canGovern && <TabsTrigger value="usage">Usage &amp; review</TabsTrigger>}
              {canGovern && <TabsTrigger value="history">History</TabsTrigger>}
            </TabsList>
            <div className="-mr-2 mt-3 min-h-0 flex-1 overflow-y-auto pr-2">
              <TabsContent value="attributes" className="mt-0">
                {canGovern ? (
                  <CatalogueTab canGovern={canGovern} canApprove={canApprove} canEnterData={canEnterData}
                    canConfigure={canConfigure} onValues={setEntering} />
                ) : (
                  <AttributesTab canEnterData={canEnterData} canConfigure={canConfigure} onEnter={setEntering} />
                )}
              </TabsContent>
              {canGovern && (
                <TabsContent value="requests" className="mt-0">
                  <RequestsTab canApprove={canApprove} myUserId={principal?.userId ?? null} />
                </TabsContent>
              )}
              {canRequest && (
                <TabsContent value="new" className="mt-0">
                  <NewRequestTab onRequested={() => setTab('requests')} />
                </TabsContent>
              )}
              {canGovern && (
                <TabsContent value="usage" className="mt-0"><UsageReviewTab canGovern={canGovern} /></TabsContent>
              )}
              {canGovern && (
                <TabsContent value="history" className="mt-0"><HistoryTab /></TabsContent>
              )}
            </div>
          </Tabs>

          <DialogFooter className="flex-none">
            <Button variant="outline" onClick={() => setOpen(false)}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {entering && <ValuesDialog field={entering} onClose={() => setEntering(null)} />}
    </>
  )
}
