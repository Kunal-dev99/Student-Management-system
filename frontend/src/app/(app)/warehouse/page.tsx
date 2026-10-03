'use client'

/**
 * Data warehouse — how this institution's data reaches its warehouse or BI tools.
 *
 *   1. Publications: scheduled Parquet/CSV files (full, then incremental), with run history.
 *   2. API consumers: systems that pull through the API with OAuth client credentials.
 *   3. Catalogue: exactly what is published, column by column, personal data marked.
 *
 * Reading needs reporting.read; changing anything needs admin.configure (the API enforces both).
 */

import { Fragment, useEffect, useState } from 'react'
import { Database, KeyRound, Library, Play, Plus, RotateCw, ShieldOff, Trash2 } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { useConfirm } from '@/components/common/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useToast } from '@/components/ui/use-toast'
import { useCan } from '@/shared/auth/Can'
import {
  useCatalogue, useConsumerAction, useConsumers, useCreateConsumer, useDeletePublication, usePublications,
  useRunPublication, useRuns, useSavePublication,
  type CatalogueObject, type Consumer, type Publication, type PublicationInput,
} from '@/features/warehouse/api'

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : '—')
const errText = (e: unknown) => (e as Error).message

// ------------------------------------------------------------------ object picker

function ObjectPicker({ value, onChange }: { value: string[] | null; onChange: (v: string[] | null) => void }) {
  const { data } = useCatalogue()
  const all = value === null
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Checkbox id="all-objects" checked={all} onCheckedChange={(v) => onChange(v === true ? null : [])} />
        <Label htmlFor="all-objects" className="font-normal cursor-pointer">Every object (new ones included automatically)</Label>
      </div>
      {!all && (
        <div className="grid grid-cols-2 gap-1 max-h-48 overflow-y-auto rounded-md border border-border p-2">
          {data?.map((o) => (
            <label key={o.name} className="flex items-center gap-2 text-xs cursor-pointer">
              <Checkbox
                checked={value?.includes(o.name) ?? false}
                onCheckedChange={(v) => onChange(v === true ? [...(value ?? []), o.name] : (value ?? []).filter((n) => n !== o.name))}
              />
              <span className="font-mono">{o.name}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  )
}

function PersonalDataToggle({ checked, onChange, id }: { checked: boolean; onChange: (v: boolean) => void; id: string }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <Checkbox id={id} checked={checked} onCheckedChange={(v) => onChange(v === true)} />
        <Label htmlFor={id} className="font-normal cursor-pointer">Include personal data (names, emails, dates of birth, notes)</Label>
      </div>
      <p className="text-xs text-muted-foreground">
        Off: names and emails are left out and date of birth becomes year of birth. Turn on only when
        the receiving system is covered by your data-sharing agreement.
      </p>
    </div>
  )
}

// ------------------------------------------------------------------ publications

const BLANK: PublicationInput = {
  name: '', objects: null, fileFormat: 'parquet', frequency: 'daily', runAtHour: 2,
  personalData: false, fullEveryDays: 7, enabled: true,
}

function PublicationDialog({ open, onOpenChange, editing }: {
  open: boolean; onOpenChange: (o: boolean) => void; editing: Publication | null
}) {
  const { toast } = useToast()
  const save = useSavePublication()
  const [f, setF] = useState<PublicationInput>(BLANK)
  useEffect(() => { if (open) setF(editing ? { ...editing } : BLANK) }, [open, editing])
  const set = <K extends keyof PublicationInput>(k: K, v: PublicationInput[K]) => setF((p) => ({ ...p, [k]: v }))
  const invalid = !f.name.trim() || (f.objects !== null && f.objects.length === 0)

  const submit = async () => {
    try {
      await save.mutateAsync({ ...f, id: editing?.id })
      toast({ title: editing ? 'Publication saved' : 'Publication created',
              description: editing ? undefined : 'Its first run publishes everything; later runs only what changed.' })
      onOpenChange(false)
    } catch (e) { toast({ title: 'Could not save', description: errText(e), variant: 'destructive' }) }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>{editing ? `Edit ${editing.name}` : 'New publication'}</DialogTitle></DialogHeader>
        <div className="space-y-4 text-sm">
          <div className="space-y-1.5">
            <Label htmlFor="pub-name">Name</Label>
            <Input id="pub-name" value={f.name} onChange={(e) => set('name', e.target.value)} placeholder="Nightly warehouse feed" />
          </div>
          <div className="space-y-1.5"><Label>Objects</Label><ObjectPicker value={f.objects} onChange={(v) => set('objects', v)} /></div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1.5">
              <Label>Format</Label>
              <Select value={f.fileFormat} onValueChange={(v) => set('fileFormat', v as PublicationInput['fileFormat'])}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="parquet">Parquet</SelectItem><SelectItem value="csv">CSV</SelectItem></SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Frequency</Label>
              <Select value={f.frequency} onValueChange={(v) => set('frequency', v as PublicationInput['frequency'])}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="daily">Daily</SelectItem><SelectItem value="hourly">Hourly</SelectItem></SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pub-hour">Hour (UTC)</Label>
              <Input id="pub-hour" type="number" min={0} max={23} disabled={f.frequency !== 'daily'}
                     value={f.runAtHour} onChange={(e) => set('runAtHour', Number(e.target.value))} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="pub-full">Full extract every (days)</Label>
            <Input id="pub-full" type="number" min={0} value={f.fullEveryDays}
                   onChange={(e) => set('fullEveryDays', Number(e.target.value))} className="w-28" />
            <p className="text-xs text-muted-foreground">Other runs publish only what changed. 0 = only the first run is full.</p>
          </div>
          <PersonalDataToggle id="pub-personal" checked={f.personalData} onChange={(v) => set('personalData', v)} />
          <div className="flex items-center gap-2">
            <Checkbox id="pub-enabled" checked={f.enabled} onCheckedChange={(v) => set('enabled', v === true)} />
            <Label htmlFor="pub-enabled" className="font-normal cursor-pointer">Enabled — run on schedule</Label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} disabled={invalid || save.isPending}>{save.isPending ? 'Saving…' : 'Save'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function RunsTable({ publicationId }: { publicationId: string }) {
  const { data, isLoading } = useRuns(publicationId)
  if (isLoading) return <Skeleton className="h-16 w-full" />
  if (!data?.length) return <p className="text-xs text-muted-foreground px-2 py-3">No runs yet.</p>
  return (
    <Table>
      <TableHeader><TableRow>
        <TableHead>Started</TableHead><TableHead>Mode</TableHead><TableHead>Status</TableHead>
        <TableHead className="text-right">Rows</TableHead><TableHead className="text-right">Deleted</TableHead><TableHead>Location</TableHead>
      </TableRow></TableHeader>
      <TableBody>
        {data.map((r) => (
          <TableRow key={r.id}>
            <TableCell className="text-xs">{when(r.startedAt)} <span className="text-muted-foreground">({r.triggeredBy})</span></TableCell>
            <TableCell><Badge variant={r.mode === 'full' ? 'info' : 'secondary'}>{r.mode}</Badge></TableCell>
            <TableCell>
              <Badge variant={r.status === 'succeeded' ? 'success' : r.status === 'failed' ? 'destructive' : 'warning'}>{r.status}</Badge>
              {r.error && <p className="text-[11px] text-danger mt-1 max-w-xs break-words">{r.error}</p>}
            </TableCell>
            <TableCell className="text-right tabular-nums">{r.rows ?? '—'}</TableCell>
            <TableCell className="text-right tabular-nums">{r.deletedRows ?? '—'}</TableCell>
            <TableCell className="text-[11px] font-mono break-all max-w-xs">{r.location ?? '—'}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function Publications({ canManage }: { canManage: boolean }) {
  const { toast } = useToast()
  const confirm = useConfirm()
  const { data, isLoading } = usePublications()
  const run = useRunPublication()
  const del = useDeletePublication()
  const [dialog, setDialog] = useState<{ open: boolean; editing: Publication | null }>({ open: false, editing: null })
  const [expanded, setExpanded] = useState<string | null>(null)

  const runNow = async (p: Publication) => {
    try {
      const r = await run.mutateAsync(p.id)
      setExpanded(p.id)
      toast(r.status === 'succeeded'
        ? { title: `Published ${r.rows ?? 0} rows (${r.mode})`, description: r.location ?? undefined }
        : { title: 'Run failed', description: r.error ?? undefined, variant: 'destructive' })
    } catch (e) { toast({ title: 'Could not run', description: errText(e), variant: 'destructive' }) }
  }
  const remove = async (p: Publication) => {
    if (!(await confirm({ title: `Delete ${p.name}?`, description: 'Files already published stay where they are.',
                          confirmLabel: 'Delete publication' }))) return
    try { await del.mutateAsync(p.id) } catch (e) { toast({ title: 'Could not delete', description: errText(e), variant: 'destructive' }) }
  }

  return (
    <PageSection icon={Database} title="Publications" accent="primary"
      description="Scheduled files for your warehouse: the first run publishes everything, later runs only what changed (plus deletions), with a manifest listing every file."
      actions={canManage ? <Button size="sm" onClick={() => setDialog({ open: true, editing: null })}><Plus className="h-4 w-4 mr-1" /> New publication</Button> : undefined}>
      {isLoading && <Skeleton className="h-24 w-full" />}
      {data && data.length === 0 && <p className="text-helper">No publications yet.</p>}
      {data && data.length > 0 && (
        <Table>
          <TableHeader><TableRow>
            <TableHead>Name</TableHead><TableHead>Objects</TableHead><TableHead>Schedule</TableHead>
            <TableHead>Edition</TableHead><TableHead>Next run</TableHead><TableHead className="text-right"></TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {data.map((p) => (
              <Fragment key={p.id}>
                <TableRow className="cursor-pointer" onClick={() => setExpanded(expanded === p.id ? null : p.id)}>
                  <TableCell className="font-medium">{p.name} {!p.enabled && <Badge variant="secondary">paused</Badge>}</TableCell>
                  <TableCell className="text-xs">{p.objects === null ? 'All' : p.objects.length} · {p.fileFormat}</TableCell>
                  <TableCell className="text-xs">{p.frequency === 'daily' ? `Daily ${String(p.runAtHour).padStart(2, '0')}:00 UTC` : 'Hourly'}</TableCell>
                  <TableCell>{p.personalData ? <Badge variant="warning">personal data</Badge> : <Badge variant="secondary">standard</Badge>}</TableCell>
                  <TableCell className="text-xs">{p.enabled ? when(p.nextRunAt) : '—'}</TableCell>
                  <TableCell className="text-right whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                    {canManage && (
                      <>
                        <Button size="sm" variant="secondary" disabled={run.isPending} onClick={() => runNow(p)}>
                          <Play className="h-3.5 w-3.5 mr-1" /> Run now
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setDialog({ open: true, editing: p })}>Edit</Button>
                        <Button size="sm" variant="ghost" aria-label={`Delete ${p.name}`} onClick={() => remove(p)}><Trash2 className="h-3.5 w-3.5" /></Button>
                      </>
                    )}
                  </TableCell>
                </TableRow>
                {expanded === p.id && (
                  <TableRow><TableCell colSpan={6} className="bg-surface-2"><RunsTable publicationId={p.id} /></TableCell></TableRow>
                )}
              </Fragment>
            ))}
          </TableBody>
        </Table>
      )}
      <PublicationDialog open={dialog.open} editing={dialog.editing} onOpenChange={(o) => setDialog((d) => ({ ...d, open: o }))} />
    </PageSection>
  )
}

// ------------------------------------------------------------------ consumers

function SecretDialog({ consumer, onClose }: { consumer: Consumer | null; onClose: () => void }) {
  const { toast } = useToast()
  const copy = async (text: string) => {
    try { await navigator.clipboard.writeText(text); toast({ title: 'Copied' }) } catch { /* clipboard blocked */ }
  }
  return (
    <Dialog open={!!consumer} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>Credentials for {consumer?.name}</DialogTitle></DialogHeader>
        <div className="space-y-3 text-sm">
          <p className="text-helper">
            The secret is shown <b>once</b>. Put it straight into the receiving system&apos;s secret store; it can&apos;t be
            shown again (rotate it if it&apos;s lost).
          </p>
          {consumer && [['Client ID', consumer.clientId], ['Client secret', consumer.clientSecret ?? '']].map(([label, value]) => (
            <div key={label} className="space-y-1">
              <Label>{label}</Label>
              <div className="flex gap-2">
                <Input readOnly value={value} className="font-mono text-xs" />
                <Button size="sm" variant="secondary" onClick={() => copy(value)}>Copy</Button>
              </div>
            </div>
          ))}
          <p className="text-xs text-muted-foreground">
            Token: <span className="font-mono">POST /api/v1/warehouse/oauth/token</span> with
            grant_type=client_credentials. Data: <span className="font-mono">GET /api/v1/warehouse/data/objects</span>.
          </p>
        </div>
        <DialogFooter><Button onClick={onClose}>I&apos;ve stored it</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function NewConsumerDialog({ open, onOpenChange, onCreated }: {
  open: boolean; onOpenChange: (o: boolean) => void; onCreated: (c: Consumer) => void
}) {
  const { toast } = useToast()
  const create = useCreateConsumer()
  const [name, setName] = useState('')
  const [objects, setObjects] = useState<string[] | null>(null)
  const [personal, setPersonal] = useState(false)
  useEffect(() => { if (open) { setName(''); setObjects(null); setPersonal(false) } }, [open])
  const submit = async () => {
    try {
      const c = await create.mutateAsync({ name: name.trim(), objects, personalData: personal })
      onOpenChange(false)
      onCreated(c)
    } catch (e) { toast({ title: 'Could not create', description: errText(e), variant: 'destructive' }) }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>New API consumer</DialogTitle></DialogHeader>
        <div className="space-y-4 text-sm">
          <div className="space-y-1.5">
            <Label htmlFor="c-name">Name</Label>
            <Input id="c-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Snowflake loader" />
          </div>
          <div className="space-y-1.5"><Label>Objects it may read</Label><ObjectPicker value={objects} onChange={setObjects} /></div>
          <PersonalDataToggle id="c-personal" checked={personal} onChange={setPersonal} />
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} disabled={!name.trim() || (objects !== null && !objects.length) || create.isPending}>Create</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Consumers() {
  const { toast } = useToast()
  const confirm = useConfirm()
  const { data, isLoading } = useConsumers(true)
  const act = useConsumerAction()
  const [creating, setCreating] = useState(false)
  const [shown, setShown] = useState<Consumer | null>(null)

  const run = async (c: Consumer, action: 'rotate' | 'revoke' | 'delete') => {
    const copy = {
      rotate: { title: `Issue a new secret for ${c.name}?`, description: 'The current secret stops working immediately.', confirmLabel: 'Rotate secret' },
      revoke: { title: `Revoke ${c.name}?`, description: 'Its tokens stop working immediately. It can be deleted afterwards.', confirmLabel: 'Revoke' },
      delete: { title: `Delete ${c.name}?`, description: 'This removes the consumer for good.', confirmLabel: 'Delete' },
    }[action]
    if (!(await confirm(copy))) return
    try {
      const res = await act.mutateAsync({ id: c.id, action })
      if (action === 'rotate' && res) setShown(res)
    } catch (e) { toast({ title: 'Failed', description: errText(e), variant: 'destructive' }) }
  }

  return (
    <PageSection icon={KeyRound} title="API consumers"
      description="Systems that pull through the API with OAuth client credentials. Each reads only this institution's data, and only the objects you allow."
      actions={<Button size="sm" onClick={() => setCreating(true)}><Plus className="h-4 w-4 mr-1" /> New consumer</Button>}>
      {isLoading && <Skeleton className="h-16 w-full" />}
      {data && data.length === 0 && <p className="text-helper">No consumers yet.</p>}
      {data && data.length > 0 && (
        <Table>
          <TableHeader><TableRow>
            <TableHead>Name</TableHead><TableHead>Client ID</TableHead><TableHead>Objects</TableHead>
            <TableHead>Edition</TableHead><TableHead>Last used</TableHead><TableHead className="text-right"></TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {data.map((c) => (
              <TableRow key={c.id}>
                <TableCell className="font-medium">{c.name} {!c.active && <Badge variant="destructive">revoked</Badge>}</TableCell>
                <TableCell className="font-mono text-xs">{c.clientId}</TableCell>
                <TableCell className="text-xs">{c.objects === null ? 'All' : c.objects.length}</TableCell>
                <TableCell>{c.personalData ? <Badge variant="warning">personal data</Badge> : <Badge variant="secondary">standard</Badge>}</TableCell>
                <TableCell className="text-xs">{when(c.lastUsedAt)}</TableCell>
                <TableCell className="text-right whitespace-nowrap">
                  {c.active && <Button size="sm" variant="ghost" onClick={() => run(c, 'rotate')}><RotateCw className="h-3.5 w-3.5 mr-1" /> Rotate</Button>}
                  {c.active && <Button size="sm" variant="ghost" onClick={() => run(c, 'revoke')}><ShieldOff className="h-3.5 w-3.5 mr-1" /> Revoke</Button>}
                  {!c.active && <Button size="sm" variant="ghost" aria-label={`Delete ${c.name}`} onClick={() => run(c, 'delete')}><Trash2 className="h-3.5 w-3.5" /></Button>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <NewConsumerDialog open={creating} onOpenChange={setCreating} onCreated={setShown} />
      <SecretDialog consumer={shown} onClose={() => setShown(null)} />
    </PageSection>
  )
}

// ------------------------------------------------------------------ catalogue

function Catalogue() {
  const { data, isLoading } = useCatalogue()
  const [open, setOpen] = useState<string | null>(null)
  return (
    <PageSection icon={Library} title="What is published"
      description="The same objects and columns feed the files, the API and the reporting views. Personal columns appear only where personal data is switched on.">
      {isLoading && <Skeleton className="h-24 w-full" />}
      <div className="grid gap-2 md:grid-cols-2">
        {data?.map((o: CatalogueObject) => (
          <div key={o.name} className="rounded-md border border-border p-3">
            <button type="button" className="w-full text-left" onClick={() => setOpen(open === o.name ? null : o.name)}>
              <span className="font-mono text-sm">{o.name}</span>
              <span className="text-xs text-muted-foreground"> · {o.columns.length} columns{o.personalColumns.length ? ` · ${o.personalColumns.length} personal` : ''}</span>
              <p className="text-xs text-muted-foreground mt-0.5">{o.description}</p>
            </button>
            {open === o.name && (
              <div className="mt-2 flex flex-wrap gap-1">
                {o.columns.map((c) => <Badge key={c.name} variant="outline" className="font-mono text-[10px]" title={c.type}>{c.name}</Badge>)}
                {o.personalColumns.map((c) => <Badge key={c} variant="warning" className="font-mono text-[10px]" title="personal data">{c}</Badge>)}
              </div>
            )}
          </div>
        ))}
      </div>
    </PageSection>
  )
}

export default function WarehousePage() {
  const canManage = useCan('admin.configure')
  return (
    <>
      <PageHeader title="Data warehouse"
        description="Publish this institution's data to its warehouse on a schedule, or let approved systems pull it through the API. Only this institution's data is ever included." />
      <div className="px-6 pb-6 space-y-4">
        <Publications canManage={canManage} />
        {canManage && <Consumers />}
        <Catalogue />
      </div>
    </>
  )
}
