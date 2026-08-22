'use client'

/**
 * "List of values" tab — CRUD over the reference lists everything else points at
 * (departments, research areas, programmes, funding sources), plus a read-only
 * view of the platform-fixed value sets.
 *
 * Delete is deliberately always enabled: the backend refuses deletion of an
 * in-use value with a 409 that names exactly what references it, and we show
 * that message verbatim — the error teaches the rule better than a hidden button.
 */

import { useState } from 'react'
import { ChevronRight, Lock, Pencil, Plus, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { ApiError } from '@/shared/api/client'
import {
  useCreateLovRow, useDeleteLovRow, useLovKinds, useLovList, useUpdateLovRow, useValueSets,
  type LovKind, type LovRow,
} from '@/features/settings/api'

const FIELD_LABELS: Record<string, string> = {
  name: 'Name',
  code: 'Code',
  departmentId: 'Department',
  funderType: 'Funder type',
}

const NONE = '__none__'

/* ------------------------------------------------------------------ *
 * Add / edit dialog — generic over the kind's field list from the API.
 * ------------------------------------------------------------------ */

function LovFormDialog({ kind, row, departments }: {
  kind: LovKind
  row?: LovRow
  departments: LovRow[]
}) {
  const { toast } = useToast()
  const create = useCreateLovRow()
  const update = useUpdateLovRow()
  const [open, setOpen] = useState(false)
  const [values, setValues] = useState<Record<string, string>>({})

  const isEdit = !!row
  const initial = () => Object.fromEntries(
    kind.fields.map((f) => [f, row ? String(row[f] ?? '') : '']),
  )
  const set = (f: string, v: string) => setValues((prev) => ({ ...prev, [f]: v }))

  const textFields = kind.fields.filter((f) => f !== 'departmentId')
  const hasDepartment = kind.fields.includes('departmentId')
  const valid = textFields.every((f) => (values[f] ?? '').trim().length > 0)
  const pending = create.isPending || update.isPending

  const submit = async () => {
    const body: Record<string, string | null> = {}
    for (const f of textFields) body[f] = (values[f] ?? '').trim()
    if (hasDepartment) body.departmentId = values.departmentId && values.departmentId !== NONE ? values.departmentId : null
    try {
      if (isEdit && row) {
        await update.mutateAsync({ kind: kind.kind, id: row.id, body })
        toast({ title: `${kind.label} updated` })
      } else {
        await create.mutateAsync({ kind: kind.kind, body })
        toast({ title: `${kind.label} added` })
      }
      setOpen(false)
    } catch (e) {
      toast({
        title: isEdit ? `Could not update ${kind.label.toLowerCase()}` : `Could not add ${kind.label.toLowerCase()}`,
        description: (e as ApiError).message,
        variant: 'destructive',
      })
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (o) setValues(initial()) }}>
      <DialogTrigger asChild>
        {isEdit ? (
          <Button variant="ghost" size="sm" className="h-7 px-2" title={`Edit ${kind.label.toLowerCase()}`}>
            <Pencil className="h-3.5 w-3.5" />
          </Button>
        ) : (
          <Button size="sm"><Plus className="h-4 w-4 mr-1" /> Add {kind.label.toLowerCase()}</Button>
        )}
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? `Edit ${kind.label.toLowerCase()}` : `Add a ${kind.label.toLowerCase()}`}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          {textFields.map((f) => (
            <div key={f} className="space-y-1.5">
              <Label htmlFor={`lov-${f}`}>{FIELD_LABELS[f] ?? f}</Label>
              <Input
                id={`lov-${f}`}
                value={values[f] ?? ''}
                onChange={(e) => set(f, e.target.value)}
                placeholder={f === 'code' ? 'Short unique code' : undefined}
              />
            </div>
          ))}
          {hasDepartment && (
            <div className="space-y-1.5">
              <Label>Department</Label>
              <Select value={values.departmentId || NONE} onValueChange={(v) => set('departmentId', v)}>
                <SelectTrigger><SelectValue placeholder="No department" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>— No department —</SelectItem>
                  {departments.map((d) => (
                    <SelectItem key={d.id} value={d.id}>{String(d.name ?? '')}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button disabled={!valid || pending} onClick={submit}>
            {pending ? 'Saving…' : isEdit ? 'Save changes' : `Add ${kind.label.toLowerCase()}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/* ------------------------------------------------------------------ *
 * One kind's table.
 * ------------------------------------------------------------------ */

function LovTable({ kind }: { kind: LovKind }) {
  const { toast } = useToast()
  const rows = useLovList(kind.kind)
  const needsDepartments = kind.fields.includes('departmentId')
  // Departments double as the FK lookup for research areas / programmes.
  const departments = useLovList('departments', needsDepartments || kind.kind === 'departments')
  const del = useDeleteLovRow()

  const departmentName = (id: string | number | null | undefined) =>
    (id && departments.data?.find((d) => d.id === id)?.name) || '—'

  const remove = async (row: LovRow) => {
    try {
      await del.mutateAsync({ kind: kind.kind, id: row.id })
      toast({ title: `${kind.label} '${String(row.name ?? '')}' deleted` })
    } catch (e) {
      // The 409 names exactly what still references the value — show it verbatim.
      toast({ title: 'Delete refused', description: (e as ApiError).message, variant: 'destructive' })
    }
  }

  const colCount = kind.fields.length + 2

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-helper">
          Values still referenced by live records cannot be deleted — the platform will tell you
          exactly what is using them.
        </p>
        <LovFormDialog kind={kind} departments={departments.data ?? []} />
      </div>
      <div className="card-elevated overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              {kind.fields.map((f) => <TableHead key={f}>{FIELD_LABELS[f] ?? f}</TableHead>)}
              <TableHead>In use</TableHead>
              <TableHead className="w-24 text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.isLoading && (
              <TableRow><TableCell colSpan={colCount}><Skeleton className="h-5 w-full" /></TableCell></TableRow>
            )}
            {rows.data?.map((row) => (
              <TableRow key={row.id}>
                {kind.fields.map((f) => (
                  <TableCell
                    key={f}
                    className={cn(
                      f === 'name' && 'font-medium',
                      f === 'code' && 'font-mono text-xs',
                      f !== 'name' && f !== 'code' && 'text-muted-foreground',
                    )}
                  >
                    {f === 'departmentId' ? departmentName(row[f]) : String(row[f] ?? '—')}
                  </TableCell>
                ))}
                <TableCell>
                  {row.inUse > 0
                    ? <Badge variant="info">{row.inUse} record{row.inUse === 1 ? '' : 's'}</Badge>
                    : <Badge variant="secondary" className="text-muted-foreground">Not used</Badge>}
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex items-center justify-end gap-1">
                    <LovFormDialog kind={kind} row={row} departments={departments.data ?? []} />
                    {/* Enabled even when in use: the backend's 409 explains the rule. */}
                    <Button
                      variant="ghost" size="sm" className="h-7 px-2 text-danger hover:text-danger"
                      title={`Delete ${kind.label.toLowerCase()}`}
                      disabled={del.isPending}
                      onClick={() => remove(row)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {rows.data && rows.data.length === 0 && (
              <TableRow>
                <TableCell colSpan={colCount} className="text-muted-foreground text-center py-8">
                  No {kind.label.toLowerCase()}s defined yet.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ *
 * Platform-fixed value sets — read-only, collapsed by default.
 * ------------------------------------------------------------------ */

function ValueSetsSection() {
  const [open, setOpen] = useState(false)
  const valueSets = useValueSets(open) // fetch lazily on first expand

  const areas: string[] = []
  for (const vs of valueSets.data ?? []) {
    if (!areas.includes(vs.area)) areas.push(vs.area)
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="card-elevated px-4 py-3">
      <CollapsibleTrigger asChild>
        <button className="flex w-full items-center gap-2 text-left">
          <ChevronRight className={cn('h-4 w-4 text-muted-foreground transition-transform', open && 'rotate-90')} />
          <Lock className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-sm font-medium">Platform-fixed value sets</span>
          <span className="text-helper ml-1">read-only</span>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="pt-3 space-y-4">
          <p className="text-helper">
            These value sets carry code behind each value and are fixed by the platform; the
            editable lists live above.
          </p>
          {valueSets.isLoading && <Skeleton className="h-24 w-full" />}
          {areas.map((area) => (
            <div key={area} className="space-y-2">
              <p className="text-label">{area}</p>
              <div className="space-y-1.5">
                {valueSets.data?.filter((vs) => vs.area === area).map((vs) => (
                  <div key={vs.name} className="flex flex-wrap items-baseline gap-1.5">
                    <span className="text-xs font-mono text-muted-foreground w-56 shrink-0">{vs.name}</span>
                    {vs.values.map((v) => (
                      <Badge key={v} variant="secondary" className="font-normal text-muted-foreground">{v}</Badge>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

/* ------------------------------------------------------------------ *
 * The tab.
 * ------------------------------------------------------------------ */

export function LovTab() {
  const kinds = useLovKinds()
  const [active, setActive] = useState<string>('departments')
  const activeKind = kinds.data?.find((k) => k.kind === active)

  return (
    <div className="space-y-4">
      {kinds.isLoading && <Skeleton className="h-64 w-full" />}
      {kinds.data && (
        <>
          <div className="flex flex-wrap items-center gap-1.5">
            {kinds.data.map((k) => (
              <Button
                key={k.kind}
                size="sm"
                variant={active === k.kind ? 'default' : 'outline'}
                onClick={() => setActive(k.kind)}
              >
                {k.label}s
              </Button>
            ))}
          </div>
          {activeKind && <LovTable key={activeKind.kind} kind={activeKind} />}
        </>
      )}
      <ValueSetsSection />
    </div>
  )
}
