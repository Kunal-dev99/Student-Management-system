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

import { useEffect, useState } from 'react'
import { Pencil, Plus, RotateCcw, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { ApiError } from '@/shared/api/client'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import {
  useCreateLovRow, useDeleteLovRow, useLovKinds, useLovList, useResetValueSet,
  useUpdateLovRow, useUpsertValueSet, useValueSets,
  type LovKind, type LovRow, type ValueSet, type ValueSetValue,
} from '@/features/settings/api'

const FIELD_LABELS: Record<string, string> = {
  name: 'Name',
  code: 'Code',
  departmentId: 'Department',
  funderType: 'Funder type',
}

const NONE = '__none__'

// Canonical funder types (mirrors backend FundingType enum). Kept here as a
// static list so the dropdown renders instantly without an extra fetch — if a
// new type is added to the enum server-side, add it here too.
const FUNDER_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: 'research_council',      label: 'Research council' },
  { value: 'university_scholarship', label: 'University scholarship' },
  { value: 'scholarship',           label: 'Scholarship (charity / trust)' },
  { value: 'employer',              label: 'Employer-sponsored' },
  { value: 'external',              label: 'External' },
  { value: 'self_funded',           label: 'Self-funded' },
  { value: 'mixed',                 label: 'Mixed' },
]

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

  // Seed the form immediately for the Edit case so the first render already
  // shows the row's current values (not the defaults from an empty state).
  useEffect(() => {
    if (isEdit) setValues(initial())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [row?.id])

  const hasDepartment = kind.fields.includes('departmentId')
  const hasFunderType = kind.fields.includes('funderType')
  const textFields = kind.fields.filter((f) => f !== 'departmentId' && f !== 'funderType')
  const valid = textFields.every((f) => (values[f] ?? '').trim().length > 0)
  const pending = create.isPending || update.isPending

  const submit = async () => {
    const body: Record<string, string | null> = {}
    for (const f of textFields) body[f] = (values[f] ?? '').trim()
    if (hasDepartment) body.departmentId = values.departmentId && values.departmentId !== NONE ? values.departmentId : null
    if (hasFunderType) body.funderType = values.funderType && values.funderType !== NONE ? values.funderType : null
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
          {hasFunderType && (() => {
            const current = values.funderType
            const known = FUNDER_TYPE_OPTIONS.some((o) => o.value === current)
            // Preserve legacy values (older seed rows) so the current selection
            // is visible even if the enum has since been renamed.
            const options = current && !known
              ? [...FUNDER_TYPE_OPTIONS, { value: current, label: `${current} (legacy)` }]
              : FUNDER_TYPE_OPTIONS
            return (
              <div className="space-y-1.5">
                <Label>Funder type</Label>
                <Select value={current || NONE} onValueChange={(v) => set('funderType', v)}>
                  <SelectTrigger><SelectValue placeholder="Select a funder type" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>— Unspecified —</SelectItem>
                    {options.map((o) => (
                      <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )
          })()}
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
                      'capitalize',
                      f === 'name' && 'font-medium',
                      f === 'code' && 'font-mono text-xs',
                      f !== 'name' && f !== 'code' && 'text-muted-foreground',
                    )}
                  >
                    {f === 'departmentId'
                      ? departmentName(row[f])
                      : f === 'funderType'
                        ? (FUNDER_TYPE_OPTIONS.find((o) => o.value === row[f])?.label ?? String(row[f] ?? '—'))
                        : String(row[f] ?? '—')}
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
 * Platform value sets — every enum is configurable per institution.
 * The value CODE is stable (used by FKs / business logic), the LABEL,
 * DESCRIPTION and HIDDEN flag can be overridden.
 * ------------------------------------------------------------------ */

function ValueEditorDialog({
  enumName, value, open, onClose,
}: { enumName: string; value: ValueSetValue | null; open: boolean; onClose: () => void }) {
  const { toast } = useToast()
  const upsert = useUpsertValueSet()
  const reset = useResetValueSet()
  const [label, setLabel] = useState('')
  const [description, setDescription] = useState('')
  const [hidden, setHidden] = useState(false)

  useEffect(() => {
    if (value) {
      setLabel(value.label ?? '')
      setDescription(value.description ?? '')
      setHidden(value.hidden)
    }
  }, [value])

  if (!value) return null

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Configure &ldquo;{value.code}&rdquo;</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="rounded-md border border-border bg-surface-1 p-3 space-y-1">
            <p className="text-label">Value code (fixed)</p>
            <code className="text-xs font-mono">{enumName} / {value.code}</code>
            <p className="text-helper text-xs">
              The code is what the database and business logic use. It cannot be changed
              without a migration. The label, description and availability below are yours
              to configure.
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="vs-label">Display label</Label>
            <Input id="vs-label" value={label} onChange={(e) => setLabel(e.target.value)}
              placeholder={value.code} />
            <p className="text-helper text-xs">Shown to users wherever this value appears. Leave blank to use the shipped default.</p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="vs-desc">Description</Label>
            <Textarea id="vs-desc" value={description} rows={3}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What this value means in this institution's process." />
          </div>
          <label className="flex items-start gap-2 rounded-md border border-border p-3 cursor-pointer">
            <Checkbox checked={hidden} onCheckedChange={(v) => setHidden(!!v)} />
            <div>
              <p className="text-sm font-medium">Hide from new selectors</p>
              <p className="text-helper text-xs">
                Existing records keep this value; new pickers won&rsquo;t offer it. Use this to
                retire an option without breaking historical data.
              </p>
            </div>
          </label>
        </div>
        <DialogFooter className="justify-between">
          <Button
            variant="ghost"
            size="sm"
            disabled={!value.overridden || reset.isPending}
            onClick={async () => {
              try {
                await reset.mutateAsync({ enumName, code: value.code })
                toast({ title: 'Reset to the shipped default' })
                onClose()
              } catch (e) {
                toast({ title: 'Reset failed', description: (e as ApiError).message, variant: 'destructive' })
              }
            }}
          >
            <RotateCcw className="h-3.5 w-3.5 mr-1" /> Reset to default
          </Button>
          <Button
            disabled={upsert.isPending}
            onClick={async () => {
              try {
                await upsert.mutateAsync({
                  enumName, code: value.code,
                  body: {
                    label: label.trim() || null,
                    description: description.trim() || null,
                    hidden,
                  },
                })
                toast({ title: 'Saved' })
                onClose()
              } catch (e) {
                toast({ title: 'Save failed', description: (e as ApiError).message, variant: 'destructive' })
              }
            }}
          >
            {upsert.isPending ? 'Saving…' : 'Save changes'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** "StudentStatus" -> "Student status"; "funding_type" -> "Funding type". */
function humanizeEnum(name: string): string {
  const s = name.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/[_-]+/g, ' ').trim()
  return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase()
}

/** Right pane for one value set — its values as a table, each editable (label/description/hide). */
function ValueSetEditor({ vs }: { vs: ValueSet }) {
  const [editing, setEditing] = useState<ValueSetValue | null>(null)
  return (
    <div className="space-y-3">
      <p className="text-helper">
        Rename, describe or hide any value for your institution. The underlying code stays
        stable, so data and business logic keep working.
      </p>
      <div className="card-elevated overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Label</TableHead>
              <TableHead>Code</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="w-16 text-right">Edit</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {vs.values.map((v) => (
              <TableRow key={v.code} className={cn(v.hidden && 'opacity-60')}>
                <TableCell className={cn('font-medium', v.hidden && 'line-through')}>{v.label}</TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">{v.code}</TableCell>
                <TableCell className="space-x-1">
                  {v.overridden && <Badge variant="info">Customised</Badge>}
                  {v.hidden && <Badge variant="warning">Hidden</Badge>}
                  {!v.overridden && !v.hidden && <span className="text-helper text-xs">Default</span>}
                </TableCell>
                <TableCell className="text-right">
                  <Button variant="ghost" size="sm" className="h-7 px-2" title={`Configure ${v.code}`}
                    onClick={() => setEditing(v)}>
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {editing && (
        <ValueEditorDialog enumName={vs.name} value={editing} open onClose={() => setEditing(null)} />
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ *
 * The tab.
 * ------------------------------------------------------------------ */

export function LovTab() {
  const kinds = useLovKinds()
  const valueSets = useValueSets(true)
  const [sel, setSel] = useState<{ type: 'kind' | 'vs'; id: string }>({ type: 'kind', id: 'departments' })

  const activeKind = kinds.data?.find((k) => k.kind === sel.id)
  const activeVs = valueSets.data?.find((v) => v.name === sel.id)

  const NavItem = ({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) => (
    <button type="button" onClick={onClick}
      className={cn('w-full truncate rounded-md px-3 py-1.5 text-left text-sm transition-colors',
        active ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-surface-2 hover:text-foreground')}>
      {label}
    </button>
  )

  return (
    <div className="grid gap-5 md:grid-cols-[210px_minmax(0,1fr)]">
      {/* Single switcher: reference lists + value-set overrides, one click to any of them. */}
      <nav className="space-y-4 self-start">
        <div className="space-y-0.5">
          <p className="px-1 pb-1 text-label">Reference lists</p>
          {kinds.isLoading && <Skeleton className="h-40 w-full" />}
          {kinds.data?.map((k) => (
            <NavItem key={k.kind} active={sel.type === 'kind' && sel.id === k.kind}
              label={`${k.label}s`} onClick={() => setSel({ type: 'kind', id: k.kind })} />
          ))}
        </div>
        <div className="space-y-0.5">
          <p className="px-1 pb-1 text-label">Value-set overrides</p>
          {valueSets.isLoading && <Skeleton className="h-40 w-full" />}
          {valueSets.data?.map((v) => (
            <NavItem key={v.name} active={sel.type === 'vs' && sel.id === v.name}
              label={humanizeEnum(v.name)} onClick={() => setSel({ type: 'vs', id: v.name })} />
          ))}
        </div>
      </nav>

      <div className="min-w-0">
        {sel.type === 'kind' && activeKind && <LovTable key={activeKind.kind} kind={activeKind} />}
        {sel.type === 'vs' && activeVs && <ValueSetEditor key={activeVs.name} vs={activeVs} />}
      </div>
    </div>
  )
}
