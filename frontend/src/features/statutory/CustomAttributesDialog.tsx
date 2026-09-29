'use client'

/**
 * Custom student attributes — create an attribute HESA needs but the core model doesn't hold, and
 * enter its value per student. Two steps in one place:
 *   1) "Add attribute" (label + type + mandatory reason) — one click, no code release.
 *   2) "Enter data" — a modal listing every student with a value box.
 * Once created it is mappable in a field as `custom.<key>`, so a required field can be re-pointed
 * at it instead of being deleted.
 */
import { useEffect, useState } from 'react'
import { Plus, Table2, Trash2, Copy, Check } from 'lucide-react'
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/components/ui/use-toast'
import { useConfirm } from '@/components/common/ConfirmDialog'
import {
  useCustomFields, useCreateCustomField, useDeleteCustomField,
  useCustomFieldValues, useSetCustomFieldValues,
  type CustomField, type CustomFieldType,
} from '@/features/statutory/customFields'

const TYPES: { v: CustomFieldType; l: string }[] = [
  { v: 'code', l: 'Code (e.g. 01, 02)' },
  { v: 'string', l: 'Text' },
  { v: 'number', l: 'Number' },
  { v: 'date', l: 'Date' },
]

function CopyPath({ path }: { path: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button type="button" title="Copy the mapping path"
      className="inline-flex items-center gap-1 font-mono text-xs text-muted-foreground hover:text-foreground"
      onClick={() => { navigator.clipboard?.writeText(path).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1200) }) }}>
      {path}{copied ? <Check className="h-3 w-3 text-[hsl(var(--success))]" /> : <Copy className="h-3 w-3" />}
    </button>
  )
}

/** The per-field data-entry modal: every student in a scrollable grid with a value box. */
function ValuesDialog({ field, onClose }: { field: CustomField; onClose: () => void }) {
  const { toast } = useToast()
  const { data, isLoading } = useCustomFieldValues(field.id)
  const save = useSetCustomFieldValues(field.id)
  const [draft, setDraft] = useState<Record<string, string>>({})

  useEffect(() => {
    if (data) {
      const seed: Record<string, string> = {}
      for (const r of data.rows) seed[r.studentId] = r.value ?? ''
      setDraft(seed)
    }
  }, [data])

  const onSave = async () => {
    const values = Object.entries(draft).map(([studentId, value]) => ({ studentId, value: value || null }))
    try {
      const res = await save.mutateAsync(values)
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
          <DialogTitle>Enter data — {field.label}</DialogTitle>
        </DialogHeader>
        <p className="flex-none text-helper">
          Maps to <span className="font-mono text-xs">{field.sourcePath}</span>. Leave a row blank to
          clear it. HESA is strict — enter the exact coded value the specification expects.
        </p>
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
                      <Input
                        className="h-8"
                        type={field.dataType === 'date' ? 'date' : field.dataType === 'number' ? 'number' : 'text'}
                        value={draft[r.studentId] ?? ''}
                        onChange={(e) => setDraft((d) => ({ ...d, [r.studentId]: e.target.value }))}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
        <DialogFooter className="flex-none">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={onSave} disabled={save.isPending}>
            {save.isPending ? 'Saving…' : 'Save values'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function CustomAttributesDialog() {
  const { toast } = useToast()
  const confirm = useConfirm()
  const { data: fields, isLoading } = useCustomFields()
  const create = useCreateCustomField()
  const del = useDeleteCustomField()
  const [open, setOpen] = useState(false)
  const [entering, setEntering] = useState<CustomField | null>(null)

  const [label, setLabel] = useState('')
  const [dataType, setDataType] = useState<CustomFieldType>('code')
  const [reason, setReason] = useState('')

  const reset = () => { setLabel(''); setDataType('code'); setReason('') }

  const onCreate = async () => {
    try {
      const f = await create.mutateAsync({ label: label.trim(), dataType, reason: reason.trim() })
      toast({ title: `Created "${f.label}"`, description: `Map a field to ${f.sourcePath}, then enter data.` })
      reset()
    } catch (e) {
      toast({ title: 'Could not create attribute', description: (e as Error).message, variant: 'destructive' })
    }
  }

  return (
    <>
      <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) reset() }}>
        <DialogTrigger asChild>
          <Button size="sm" variant="outline"><Plus className="h-4 w-4 mr-1" /> Custom attributes</Button>
        </DialogTrigger>
        <DialogContent className="flex max-h-[88vh] max-w-2xl flex-col overflow-hidden">
          <DialogHeader className="flex-none"><DialogTitle>Custom student attributes</DialogTitle></DialogHeader>
          <p className="flex-none text-helper">
            Capture an attribute a return needs but the system doesn&apos;t hold yet — no code release.
            Create it here, enter each student&apos;s value, then map the field to its{' '}
            <span className="font-mono text-xs">custom.…</span> path.
          </p>

          <div className="-mr-2 mt-2 flex-1 space-y-5 overflow-y-auto pr-2">
            {/* Create form */}
            <div className="rounded-md border border-border bg-muted/30 p-3 space-y-3">
              <p className="text-label">New attribute</p>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="cf-label">Label</Label>
                  <Input id="cf-label" value={label} onChange={(e) => setLabel(e.target.value)}
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
                <Label htmlFor="cf-reason">Reason (why this is being captured)</Label>
                <Textarea id="cf-reason" className="min-h-[60px]" value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="e.g. HESA CARELEAVER — mandatory, not held in the core model." />
              </div>
              <Button size="sm" onClick={onCreate}
                disabled={!label.trim() || !reason.trim() || create.isPending}>
                {create.isPending ? 'Creating…' : 'Create attribute'}
              </Button>
            </div>

            {/* Existing attributes */}
            <div className="space-y-2">
              <p className="text-label">Existing attributes</p>
              {isLoading ? <Skeleton className="h-16 w-full" /> : (fields ?? []).length === 0 ? (
                <p className="text-helper">None yet.</p>
              ) : (
                <div className="rounded-md border border-border divide-y divide-border">
                  {(fields ?? []).map((f) => (
                    <div key={f.id} className="flex items-start justify-between gap-3 p-3">
                      <div className="min-w-0 space-y-0.5">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{f.label}</span>
                          <Badge variant="secondary">{f.dataType}</Badge>
                        </div>
                        <CopyPath path={f.sourcePath} />
                        <p className="text-xs text-muted-foreground">{f.reason}</p>
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        <Button size="sm" variant="secondary" onClick={() => setEntering(f)}>
                          <Table2 className="h-3.5 w-3.5 mr-1" /> Enter data
                        </Button>
                        <Button size="icon" variant="ghost" className="h-8 w-8 text-danger"
                          title={`Delete ${f.label}`}
                          onClick={async () => {
                            if (!(await confirm({
                              title: `Delete "${f.label}"?`,
                              description: 'This removes the attribute and every value entered for it. Any mapping pointing at it will read blank.',
                              confirmLabel: 'Delete attribute',
                            }))) return
                            try {
                              await del.mutateAsync(f.id)
                              toast({ title: `Deleted "${f.label}"` })
                            } catch (e) {
                              toast({ title: 'Could not delete', description: (e as Error).message, variant: 'destructive' })
                            }
                          }}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <DialogFooter className="flex-none">
            <Button variant="outline" onClick={() => setOpen(false)}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {entering && <ValuesDialog field={entering} onClose={() => setEntering(null)} />}
    </>
  )
}
