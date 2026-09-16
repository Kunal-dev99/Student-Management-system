'use client'

/**
 * Statutory returns (Phase 6.6).
 *
 * The whole point of this screen: a statutory return is **configuration, not code**.
 */

import { useEffect, useMemo, useState } from 'react'
import {
  CheckCircle2, CopyPlus, Download, FileSpreadsheet, FileUp, ListChecks, Lock, Unlock, Play, Plus, Pencil, Trash2, ShieldAlert, ShieldCheck, Sparkles,
} from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useToast } from '@/components/ui/use-toast'
import { ApiError } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import { downloadExport } from '@/features/exports/api'
import { AdvisoriesPanel } from '@/features/statutory/AdvisoriesPanel'
import {
  useAddField, useCloneProfile, useCompileProfile, useCreateFromSpec, useCreateProfile,
  useGenerateProfile, useProfile, useProfiles, useSignOffProfile, useSpecs, useTransforms,
  useUnsignProfile, useValidateProfile, useFixSuggestions, useApplyFix,
  useUpdateField, useDeleteField,
  type GenerateResult, type ReportProfile, type ValidationResult, type FieldMapping,
} from '@/features/statutory/api'

function err(toast: ReturnType<typeof useToast>['toast'], title: string) {
  return (e: unknown) =>
    toast({ title, description: (e as ApiError).message, variant: 'destructive' })
}

// ---------------------------------------------------------------- dialogs

/** ICR G5 — create a profile pre-mapped from a published HESA spec pack. */
function FromSpecDialog({ onCreated }: { onCreated: (id: string) => void }) {
  const { toast } = useToast()
  const { data } = useSpecs()
  const fromSpec = useCreateFromSpec()
  const [open, setOpen] = useState(false)
  const [specKey, setSpecKey] = useState('')

  const specs = data?.specs ?? []

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) setSpecKey('') }}>
      <DialogTrigger asChild>
        <Button size="sm"><Sparkles className="h-4 w-4 mr-1" /> New from HESA spec</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>New profile from a published spec</DialogTitle></DialogHeader>
        <p className="text-helper -mt-1">
          Creates the profile with every spec field pre-mapped to its best-known source. Registry
          only fills the gaps (fields we can&apos;t source yet are left required-but-unmapped).
        </p>
        <div className="space-y-1.5 py-2">
          <Label>Spec pack</Label>
          <Select value={specKey} onValueChange={setSpecKey}>
            <SelectTrigger><SelectValue placeholder="Choose a published spec…" /></SelectTrigger>
            <SelectContent>
              {specs.map((s) => (
                <SelectItem key={s.key} value={s.key}>
                  {s.name} {s.academicYear} — {s.fieldCount} fields
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <DialogFooter>
          <Button
            disabled={!specKey || fromSpec.isPending}
            onClick={async () => {
              try {
                const p = await fromSpec.mutateAsync({ specKey })
                toast({ title: 'Profile created from spec', description: `${p.fields.length} fields pre-mapped.` })
                setOpen(false); setSpecKey('')
                onCreated(p.id)
              } catch (e) { err(toast, 'Could not create from spec')(e) }
            }}>
            {fromSpec.isPending ? 'Creating…' : 'Create from spec'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function NewProfileDialog() {
  const { toast } = useToast()
  const create = useCreateProfile()
  const [open, setOpen] = useState(false)
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [academicYear, setAcademicYear] = useState('')
  const [description, setDescription] = useState('')

  const reset = () => { setCode(''); setName(''); setAcademicYear(''); setDescription('') }

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) reset() }}>
      <DialogTrigger asChild>
        <Button size="sm"><Plus className="h-4 w-4 mr-1" /> New profile</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Create a report profile</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="p-code">Code</Label>
              <Input id="p-code" value={code} onChange={(e) => setCode(e.target.value)} placeholder="HESA_STUDENT" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="p-year">Academic year</Label>
              <Input id="p-year" value={academicYear} onChange={(e) => setAcademicYear(e.target.value)} placeholder="2026/27" />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="p-name">Name</Label>
            <Input id="p-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="HESA Student return" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="p-desc">Description (optional)</Label>
            <Textarea id="p-desc" className="min-h-[64px]" value={description}
              onChange={(e) => setDescription(e.target.value)} />
          </div>
          <p className="text-helper">
            A profile is versioned by academic year, so regenerating a prior year&apos;s return uses
            that year&apos;s mapping and reproduces the original file.
          </p>
        </div>
        <DialogFooter>
          <Button
            disabled={!code.trim() || !name.trim() || !academicYear.trim() || create.isPending}
            onClick={async () => {
              try {
                await create.mutateAsync({
                  code: code.trim(), name: name.trim(),
                  academicYear: academicYear.trim(),
                  description: description.trim() || undefined,
                })
                toast({ title: 'Profile created' })
                setOpen(false); reset()
              } catch (e) { err(toast, 'Could not create profile')(e) }
            }}
          >
            {create.isPending ? 'Saving…' : 'Create profile'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function AddFieldDialog({ profileId }: { profileId: string }) {
  const { toast } = useToast()
  const add = useAddField(profileId)
  const transforms = useTransforms()
  const [open, setOpen] = useState(false)
  const [targetField, setTargetField] = useState('')
  const [sourceExpression, setSourceExpression] = useState('')
  const [transform, setTransform] = useState('')
  const [defaultValue, setDefaultValue] = useState('')
  const [position, setPosition] = useState('')
  const [required, setRequired] = useState(false)
  const [allowedValues, setAllowedValues] = useState('')

  const reset = () => {
    setTargetField(''); setSourceExpression(''); setTransform(''); setDefaultValue('')
    setPosition(''); setRequired(false); setAllowedValues('')
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) reset() }}>
      <DialogTrigger asChild>
        <Button size="sm"><Plus className="h-4 w-4 mr-1" /> Add field</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Map a field</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="f-target">Target field</Label>
              <Input id="f-target" value={targetField} onChange={(e) => setTargetField(e.target.value)}
                placeholder="STUID" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="f-pos">Position (optional)</Label>
              <Input id="f-pos" type="number" min={1} value={position}
                onChange={(e) => setPosition(e.target.value)} placeholder="appended" />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="f-src">Source expression</Label>
            <Input id="f-src" className="font-mono text-xs" value={sourceExpression}
              onChange={(e) => setSourceExpression(e.target.value)} placeholder="student.ref" />
            <p className="text-helper">
              A dotted path over the flat student record — <span className="font-mono text-xs">student.*</span>,{' '}
              <span className="font-mono text-xs">person.*</span>, <span className="font-mono text-xs">programme.*</span>,{' '}
              <span className="font-mono text-xs">research.*</span>, <span className="font-mono text-xs">funding.*</span>,{' '}
              <span className="font-mono text-xs">award.*</span>. Deliberately not an expression language.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Transform (optional)</Label>
              <Select value={transform} onValueChange={setTransform}>
                <SelectTrigger><SelectValue placeholder="No transform" /></SelectTrigger>
                <SelectContent>
                  {transforms.data?.transforms.map((t) => (
                    <SelectItem key={t} value={t}>{t}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="f-default">Default value (optional)</Label>
              <Input id="f-default" value={defaultValue} onChange={(e) => setDefaultValue(e.target.value)} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="f-allowed">Allowed values (optional, comma separated)</Label>
            <Input id="f-allowed" value={allowedValues} onChange={(e) => setAllowedValues(e.target.value)}
              placeholder="01, 02, 03" />
          </div>
          <div className="flex items-center gap-2">
            <Checkbox id="f-required" checked={required}
              onCheckedChange={(c) => setRequired(c === true)} />
            <Label htmlFor="f-required">Required by the specification</Label>
          </div>
        </div>
        <DialogFooter>
          <Button
            disabled={!targetField.trim() || !sourceExpression.trim() || add.isPending}
            onClick={async () => {
              const allowed = allowedValues.split(',').map((v) => v.trim()).filter(Boolean)
              try {
                await add.mutateAsync({
                  targetField: targetField.trim(),
                  sourceExpression: sourceExpression.trim(),
                  position: position ? Number(position) : undefined,
                  transform: transform || undefined,
                  defaultValue: defaultValue || undefined,
                  required,
                  allowedValues: allowed.length > 0 ? allowed : undefined,
                })
                toast({ title: `Mapped ${targetField.trim()}` })
                setOpen(false); reset()
              } catch (e) { err(toast, 'Could not map field')(e) }
            }}
          >
            {add.isPending ? 'Saving…' : 'Add field'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function EditFieldDialog({ profileId, field }: { profileId: string; field: FieldMapping }) {
  const { toast } = useToast()
  const update = useUpdateField(profileId)
  const [open, setOpen] = useState(false)
  const [sourceExpression, setSourceExpression] = useState(field.sourceExpression ?? '')
  const [transform, setTransform] = useState(field.transform ?? '')
  const [defaultValue, setDefaultValue] = useState(field.defaultValue ?? '')
  const [position, setPosition] = useState(String(field.position ?? ''))
  const [required, setRequired] = useState(field.required)
  const [allowedValues, setAllowedValues] = useState((field.allowedValues ?? []).join(', '))

  // Re-seed from the field whenever the dialog is (re)opened, so it always reflects the saved state.
  const seed = () => {
    setSourceExpression(field.sourceExpression ?? ''); setTransform(field.transform ?? '')
    setDefaultValue(field.defaultValue ?? ''); setPosition(String(field.position ?? ''))
    setRequired(field.required); setAllowedValues((field.allowedValues ?? []).join(', '))
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (o) seed() }}>
      <DialogTrigger asChild>
        <Button size="icon" variant="ghost" className="h-8 w-8" title={`Edit ${field.targetField}`}>
          <Pencil className="h-4 w-4" />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Map {field.targetField}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Target field</Label>
              <Input value={field.targetField} disabled className="font-mono text-xs" />
              <p className="text-helper">The statutory field is fixed by the spec — map it to a source column below.</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="e-pos">Position</Label>
              <Input id="e-pos" type="number" min={1} value={position}
                onChange={(e) => setPosition(e.target.value)} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="e-src">Source expression (the column this field maps to)</Label>
            <Input id="e-src" className="font-mono text-xs" value={sourceExpression}
              onChange={(e) => setSourceExpression(e.target.value)} placeholder="student.ref" />
            <p className="text-helper">
              A dotted path over the flat student record — <span className="font-mono text-xs">student.*</span>,{' '}
              <span className="font-mono text-xs">person.*</span>, <span className="font-mono text-xs">programme.*</span>,{' '}
              <span className="font-mono text-xs">research.*</span>, <span className="font-mono text-xs">funding.*</span>,{' '}
              <span className="font-mono text-xs">award.*</span>.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="e-transform">Transform (optional)</Label>
              <Input id="e-transform" className="font-mono text-xs" value={transform}
                onChange={(e) => setTransform(e.target.value)} placeholder="e.g. upper|strip_name" />
              <p className="text-helper">One transform, or a <span className="font-mono text-xs">|</span>-separated chain applied in order.</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="e-default">Default value (optional)</Label>
              <Input id="e-default" value={defaultValue} onChange={(e) => setDefaultValue(e.target.value)} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="e-allowed">Allowed values (optional, comma separated)</Label>
            <Input id="e-allowed" value={allowedValues} onChange={(e) => setAllowedValues(e.target.value)}
              placeholder="01, 02, 03" />
          </div>
          <div className="flex items-center gap-2">
            <Checkbox id="e-required" checked={required}
              onCheckedChange={(c) => setRequired(c === true)} />
            <Label htmlFor="e-required">Required by the specification</Label>
          </div>
        </div>
        <DialogFooter>
          <Button
            disabled={!sourceExpression.trim() || update.isPending}
            onClick={async () => {
              const allowed = allowedValues.split(',').map((v) => v.trim()).filter(Boolean)
              try {
                await update.mutateAsync({
                  id: field.id,
                  body: {
                    sourceExpression: sourceExpression.trim(),
                    position: position ? Number(position) : undefined,
                    transform: transform.trim() || undefined,
                    defaultValue: defaultValue || undefined,
                    required,
                    allowedValues: allowed.length > 0 ? allowed : undefined,
                  },
                })
                toast({ title: `Updated ${field.targetField}` })
                setOpen(false)
              } catch (e) { err(toast, 'Could not update field')(e) }
            }}
          >
            {update.isPending ? 'Saving…' : 'Save mapping'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function DeleteFieldButton({ profileId, field }: { profileId: string; field: FieldMapping }) {
  const { toast } = useToast()
  const del = useDeleteField(profileId)
  return (
    <Button
      size="icon" variant="ghost" className="h-8 w-8 text-danger hover:text-danger"
      title={`Remove ${field.targetField}`}
      disabled={del.isPending}
      onClick={async () => {
        if (!window.confirm(`Remove the mapping for ${field.targetField}? This does not touch the master record.`)) return
        try {
          await del.mutateAsync(field.id)
          toast({ title: `Removed ${field.targetField}` })
        } catch (e) { err(toast, 'Could not remove field')(e) }
      }}
    >
      <Trash2 className="h-4 w-4" />
    </Button>
  )
}

function CloneDialog({ profile }: { profile: ReportProfile }) {
  const { toast } = useToast()
  const clone = useCloneProfile()
  const [open, setOpen] = useState(false)
  const [academicYear, setAcademicYear] = useState('')

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) setAcademicYear('') }}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline"><CopyPlus className="h-4 w-4 mr-1" /> Clone to new year</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Clone {profile.code} to a new year</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="c-year">New academic year</Label>
            <Input id="c-year" value={academicYear} onChange={(e) => setAcademicYear(e.target.value)}
              placeholder="2027/28" />
          </div>
          <p className="text-helper">
            Every field mapping is copied. {profile.academicYear} stays exactly as it was, so its
            return can still be reproduced byte for byte.
          </p>
        </div>
        <DialogFooter>
          <Button
            disabled={!academicYear.trim() || clone.isPending}
            onClick={async () => {
              try {
                const created = await clone.mutateAsync({ id: profile.id, academicYear: academicYear.trim() })
                toast({ title: `Cloned to ${created.academicYear}` })
                setOpen(false); setAcademicYear('')
              } catch (e) { err(toast, 'Could not clone profile')(e) }
            }}
          >
            {clone.isPending ? 'Cloning…' : 'Clone'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------- validation

const ISSUES_PER_PAGE = 25

function ValidationReportView({ result, rowCount }: { result: ValidationResult; rowCount: number }) {
  const [severity, setSeverity] = useState<'all' | 'error' | 'warning'>('all')
  const [field, setField] = useState<string | null>(null)   // filter to one field ("error type")
  const [page, setPage] = useState(0)

  // Group by field — the natural "error type" (same message repeats per student). Sorted by count.
  const groups = useMemo(() => {
    const m = new Map<string, { field: string; count: number; errors: number; warnings: number }>()
    for (const i of result.issues) {
      const g = m.get(i.field) ?? { field: i.field, count: 0, errors: 0, warnings: 0 }
      g.count++
      if (i.severity === 'warning') g.warnings++; else g.errors++
      m.set(i.field, g)
    }
    return [...m.values()].sort((a, b) => b.count - a.count)
  }, [result.issues])

  const filtered = useMemo(() => result.issues.filter((i) =>
    (severity === 'all' || i.severity === severity) && (!field || i.field === field),
  ), [result.issues, severity, field])

  // Reset to the first page whenever the filter changes.
  useEffect(() => { setPage(0) }, [severity, field])

  const pageCount = Math.max(1, Math.ceil(filtered.length / ISSUES_PER_PAGE))
  const clamped = Math.min(page, pageCount - 1)
  const start = clamped * ISSUES_PER_PAGE
  const pageItems = filtered.slice(start, start + ISSUES_PER_PAGE)
  // Use functional setState so a rapid click never captures a stale `clamped` from an earlier
  // render — otherwise clicks can no-op or the label lags behind the actual page state.
  const goPrev = () => setPage((p) => Math.max(0, Math.min(p, pageCount - 1) - 1))
  const goNext = () => setPage((p) => Math.min(pageCount - 1, Math.min(p, pageCount - 1) + 1))

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={result.errors > 0 ? 'destructive' : 'success'}>
          {result.errors} error{result.errors === 1 ? '' : 's'}
        </Badge>
        {(result.warnings ?? 0) > 0 && (
          <Badge variant="warning">{result.warnings} warning{result.warnings === 1 ? '' : 's'}</Badge>
        )}
        <span className="text-helper num">{rowCount} row{rowCount === 1 ? '' : 's'} would be produced</span>
        {/* Severity filter */}
        {result.issues.length > 0 && (
          <div className="ml-auto inline-flex rounded-md border border-border p-0.5 text-xs">
            {(['all', 'error', 'warning'] as const).map((s) => (
              <button key={s} type="button" onClick={() => setSeverity(s)}
                className={`px-2 py-0.5 rounded ${severity === s ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
                {s === 'all' ? 'All' : s === 'error' ? 'Errors' : 'Warnings'}
              </button>
            ))}
          </div>
        )}
      </div>

      {result.issues.length === 0 ? (
        <p className="text-sm inline-flex items-center gap-2 text-[hsl(var(--success))]">
          <CheckCircle2 className="h-4 w-4" /> No validation errors.
        </p>
      ) : (
        <>
          {/* Grouped by field ("error type") — click to filter to that field. */}
          <div className="flex flex-wrap gap-1.5">
            <button type="button" onClick={() => setField(null)}
              className={`text-xs rounded-full border px-2.5 py-1 ${!field ? 'bg-primary/10 border-primary/40 font-medium' : 'border-border hover:bg-surface-2'}`}>
              All fields ({result.issues.length})
            </button>
            {groups.map((g) => (
              <button key={g.field} type="button" onClick={() => setField(g.field)}
                className={`text-xs rounded-full border px-2.5 py-1 inline-flex items-center gap-1.5 ${field === g.field ? 'bg-primary/10 border-primary/40 font-medium' : 'border-border hover:bg-surface-2'}`}>
                <span className="font-mono">{g.field}</span>
                <span className={g.errors ? 'text-[hsl(var(--destructive))]' : 'text-[hsl(var(--warning))]'}>{g.count}</span>
              </button>
            ))}
          </div>

          <div className="card-elevated overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Student ref</TableHead>
                  <TableHead>Field</TableHead>
                  <TableHead>Severity</TableHead>
                  <TableHead>Message</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pageItems.map((i, idx) => (
                  <TableRow key={`${i.studentRef}-${i.field}-${start + idx}`}>
                    <TableCell className="font-mono text-xs whitespace-nowrap">{i.studentRef}</TableCell>
                    <TableCell className="font-mono text-xs whitespace-nowrap">{i.field}</TableCell>
                    <TableCell>
                      <Badge variant={i.severity === 'warning' ? 'warning' : 'destructive'}>{i.severity}</Badge>
                    </TableCell>
                    <TableCell className="text-sm">
                      {i.message}
                      {i.allowed && i.allowed.length > 0 && (
                        <span className="text-helper"> Allowed: {i.allowed.join(', ')}.</span>
                      )}
                      {i.sourceExpression && (
                        <span className="text-helper font-mono"> ({i.sourceExpression})</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span key={`s-${clamped}-${filtered.length}`}>
              {field ? <>Field <span className="font-mono">{field}</span> · </> : null}
              Showing {filtered.length === 0 ? 0 : start + 1}–{Math.min(start + ISSUES_PER_PAGE, filtered.length)} of {filtered.length}
            </span>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="outline" className="h-7" disabled={clamped <= 0}
                onClick={goPrev}>Prev</Button>
              {/* Keyed so React replaces the whole span (and its text nodes) on every page change —
                 avoids a rare text-node reconciliation gap where the number would stall while the
                 table rows below advanced correctly. */}
              <span key={`p-${clamped}-${pageCount}`}>Page {clamped + 1} / {pageCount}</span>
              <Button size="sm" variant="outline" className="h-7" disabled={clamped >= pageCount - 1}
                onClick={goNext}>Next</Button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- ICR G5 — fix assistant

function SuggestedFixes({ profileId, canApply }: { profileId: string; canApply: boolean }) {
  const { toast } = useToast()
  const fixes = useFixSuggestions(profileId)
  const apply = useApplyFix(profileId)
  const data = fixes.data?.suggestions

  return (
    <div className="pt-3 border-t border-border space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-label">Suggested fixes</p>
        <Button size="sm" variant="outline" disabled={fixes.isFetching}
          onClick={async () => {
            const r = await fixes.refetch()
            if (r.error) { err(toast, 'Could not scan')(r.error); return }
            toast({ title: `${r.data?.suggestions.length ?? 0} fix type(s) found` })
          }}>
          <Sparkles className="h-4 w-4 mr-1" />{fixes.isFetching ? 'Scanning…' : 'Scan for fixes'}
        </Button>
        <span className="text-helper">Rule-based cleaning — clean or massage, never remove; you approve each one.</span>
      </div>

      {data && data.length === 0 && (
        <p className="text-sm inline-flex items-center gap-2 text-[hsl(var(--success))]">
          <CheckCircle2 className="h-4 w-4" /> No data-quality issues found.
        </p>
      )}
      {data && data.length > 0 && (
        <div className="space-y-2">
          {data.map((f) => (
            <div key={f.field + f.type} className="card-elevated p-3 space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="warning" className="num">{f.count}</Badge>
                <span className="font-mono text-xs font-medium">{f.field}</span>
                <span className="text-sm font-medium">{f.label}</span>
                {canApply && f.applicable && (
                  <Button size="sm" className="ml-auto" disabled={apply.isPending}
                    onClick={async () => {
                      try {
                        await apply.mutateAsync({ field: f.field, transform: f.transform })
                        toast({ title: `Fix applied to ${f.field}`, description: `${f.count} value(s) will be cleaned in the return.` })
                        await fixes.refetch()
                      } catch (e) { err(toast, 'Could not apply fix')(e) }
                    }}>
                    Apply fix
                  </Button>
                )}
              </div>
              <p className="text-helper">{f.description}</p>
              {f.samples.length > 0 && (
                <div className="text-xs">
                  <span className="text-helper">Examples: </span>
                  {f.samples.slice(0, 3).map((s, i) => (
                    <span key={i} className="mr-3">&ldquo;{s.before}&rdquo; → <span className="font-medium">&ldquo;{s.after}&rdquo;</span></span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- F1 — sign-off + gap panel

function SignOffCard({ profileId, canSignOff }: { profileId: string; canSignOff: boolean }) {
  const { toast } = useToast()
  const compile = useCompileProfile(profileId)
  const signOff = useSignOffProfile(profileId)
  const unsign = useUnsignProfile(profileId)
  const [notesOpen, setNotesOpen] = useState(false)
  const [notes, setNotes] = useState('')

  if (compile.isLoading) return <Skeleton className="h-24 w-full" />
  if (compile.isError) return <p className="text-sm text-[hsl(var(--destructive))]">{(compile.error as ApiError)?.message}</p>
  if (!compile.data) return null
  const r = compile.data
  const signed = r.profile.signedOff

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {signed ? (
          <Badge variant="success" className="inline-flex items-center gap-1">
            <ShieldCheck className="h-3.5 w-3.5" /> Signed off
          </Badge>
        ) : r.signOffReady ? (
          <Badge variant="warning" className="inline-flex items-center gap-1">
            <ShieldAlert className="h-3.5 w-3.5" /> Ready to sign off
          </Badge>
        ) : (
          <Badge variant="destructive" className="inline-flex items-center gap-1">
            <ShieldAlert className="h-3.5 w-3.5" /> Not ready — {r.missing.length} mandatory field{r.missing.length === 1 ? '' : 's'} unmapped
          </Badge>
        )}
        <span className="text-helper num">
          {r.mappedFieldCount} / {r.specFieldCount} spec fields mapped
        </span>
        {signed && r.profile.signedOffAt && (
          <span className="text-helper">
            at {new Date(r.profile.signedOffAt).toLocaleString()}
            {r.profile.signedOffNotes ? ` — ${r.profile.signedOffNotes}` : ''}
          </span>
        )}
      </div>

      {signed ? (
        <div className="flex items-center gap-2 text-sm p-3 rounded-md bg-surface-2 border border-border">
          <Lock className="h-4 w-4 text-muted-foreground" />
          <span>This profile is locked. Edits to fields, deletes and further mappings are refused
            until it is unsigned. Cloning to a new year is still allowed — that is how a return
            carries forward.</span>
          {canSignOff && (
            <Button size="sm" variant="outline" className="ml-auto"
              disabled={unsign.isPending}
              onClick={async () => {
                try {
                  await unsign.mutateAsync()
                  toast({ title: 'Profile unsigned', description: 'Edits are re-enabled.' })
                } catch (e) { toast({ title: 'Could not unsign', description: (e as ApiError).message, variant: 'destructive' }) }
              }}>
              <Unlock className="h-4 w-4 mr-1" />
              {unsign.isPending ? 'Unsigning…' : 'Unsign'}
            </Button>
          )}
        </div>
      ) : (
        <>
          {r.missing.length > 0 && (
            <div className="card-elevated overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Missing field</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead>Coding frame</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {r.missing.map((m) => (
                    <TableRow key={m.field}>
                      <TableCell className="font-mono text-xs font-medium">{m.field}</TableCell>
                      <TableCell className="text-sm">{m.description}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {m.allowed && m.allowed.length > 0 ? m.allowed.join(', ') : 'free text'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
          {canSignOff && (
            <div className="flex items-center gap-2">
              <Dialog open={notesOpen} onOpenChange={(o) => { setNotesOpen(o); if (!o) setNotes('') }}>
                <DialogTrigger asChild>
                  <Button size="sm" disabled={!r.signOffReady}>
                    <ShieldCheck className="h-4 w-4 mr-1" /> Sign off
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader><DialogTitle>Sign off {r.profile.code} — {r.profile.academicYear}</DialogTitle></DialogHeader>
                  <div className="space-y-3">
                    <p className="text-sm text-muted-foreground">
                      By signing off you attest — as the responsible owner (Registry / HESA SME) —
                      that this profile is complete for the return. The profile will become
                      immutable until you unsign it.
                    </p>
                    <div className="space-y-1.5">
                      <Label htmlFor="s-notes">Notes (optional)</Label>
                      <Textarea id="s-notes" className="min-h-[64px]" value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                        placeholder="e.g. Confirmed against HESA Student 2026/27 v1.2 with Registry on 2026-08-24" />
                    </div>
                  </div>
                  <DialogFooter>
                    <Button
                      disabled={signOff.isPending}
                      onClick={async () => {
                        try {
                          await signOff.mutateAsync(notes.trim() || undefined)
                          toast({ title: 'Profile signed off' })
                          setNotesOpen(false); setNotes('')
                        } catch (e) { toast({ title: 'Could not sign off', description: (e as ApiError).message, variant: 'destructive' }) }
                      }}>
                      {signOff.isPending ? 'Signing…' : 'Sign off'}
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
              {!r.signOffReady && (
                <span className="text-helper">
                  Map the missing mandatory fields above, then sign-off will unlock.
                </span>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- page

export default function StatutoryPage() {
  const { toast } = useToast()
  const { hasPermission } = useAuth()
  const canConfigure = hasPermission('admin.configure')
  const canSignOff = hasPermission('reports.signoff')

  const profiles = useProfiles()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const detail = useProfile(selectedId)
  const validate = useValidateProfile(selectedId)
  const generate = useGenerateProfile()
  const [generated, setGenerated] = useState<GenerateResult | null>(null)

  // Pick the first profile once the list arrives so the screen is never empty for no reason.
  useEffect(() => {
    if (!selectedId && profiles.data && profiles.data.length > 0) setSelectedId(profiles.data[0].id)
  }, [profiles.data, selectedId])

  const selectProfile = (id: string) => {
    setSelectedId(id)
    setGenerated(null)
  }

  const showValidation = validate.data && validate.data.profile.id === selectedId
  const showGenerated = generated && generated.profile.id === selectedId

  return (
    <>
      <PageHeader
        title="Statutory returns"
        description="A statutory return is configuration, not code — HESA is an external specification, expressed as a versioned profile of field mappings."
        actions={canConfigure ? (
          <div className="flex items-center gap-2">
            <FromSpecDialog onCreated={setSelectedId} />
            <NewProfileDialog />
          </div>
        ) : undefined}
      />
      <div className="px-6 pb-6 space-y-4">
        <PageSection
          icon={FileSpreadsheet}
          title="Report profiles"
          accent="primary"
          description="Versioned by academic year. Next year's change is an edit here, not a code release."
        >
          {profiles.isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : profiles.isError ? (
            <p className="text-sm text-[hsl(var(--destructive))]">{(profiles.error as ApiError)?.message}</p>
          ) : profiles.data && profiles.data.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Code</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Academic year</TableHead>
                  <TableHead>Version</TableHead>
                  <TableHead>Fields</TableHead>
                  <TableHead>Sign-off</TableHead>
                  <TableHead className="text-right">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {profiles.data.map((p) => (
                  <TableRow
                    key={p.id}
                    onClick={() => selectProfile(p.id)}
                    className={`cursor-pointer ${p.id === selectedId ? 'bg-surface-2' : ''}`}
                  >
                    <TableCell className="font-mono text-xs">{p.code}</TableCell>
                    <TableCell className="font-medium" title={p.description ?? undefined}>{p.name}</TableCell>
                    <TableCell className="num">{p.academicYear}</TableCell>
                    <TableCell className="num">v{p.version}</TableCell>
                    <TableCell className="num">{p.fieldCount ?? '—'}</TableCell>
                    <TableCell>
                      {p.signedOff ? (
                        <Badge variant="success" className="inline-flex items-center gap-1">
                          <Lock className="h-3 w-3" /> signed
                        </Badge>
                      ) : (
                        <span className="text-helper">draft</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <Badge variant={p.isActive ? 'success' : 'secondary'}>
                        {p.isActive ? 'active' : 'inactive'}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-helper">
              No report profiles configured yet. Create one, map its fields, and the return exists —
              no code required.
            </p>
          )}
        </PageSection>

        <PageSection
          icon={FileUp}
          title="Statutory advisories"
          accent="accent"
          description="Ingest a published HESA advisory, review the diff against the current pack, and accept it to make the change the active spec version — ingest → recommend → accept, human-gated."
        >
          <AdvisoriesPanel canConfigure={canConfigure} canSignOff={canSignOff} />
        </PageSection>

        {selectedId && (
          <PageSection
            icon={ShieldCheck}
            title="Sign-off &amp; mandatory-field readiness"
            accent="primary"
            description="A profile can be signed off only when every mandatory field in the return's published spec is mapped and the current cohort validates. Signed-off profiles are immutable until unsigned."
          >
            <SignOffCard profileId={selectedId} canSignOff={canSignOff} />
          </PageSection>
        )}

        {selectedId && (
          <PageSection
            icon={ListChecks}
            title={detail.data ? `${detail.data.code} — ${detail.data.academicYear}` : 'Field mappings'}
            accent="accent"
            description="Target field ← source expression + transform + validation."
            actions={
              <div className="flex flex-wrap items-center gap-2">
                {canConfigure && !detail.data?.signedOff && <AddFieldDialog profileId={selectedId} />}
                <Button
                  size="sm" variant="outline"
                  disabled={validate.isFetching}
                  onClick={async () => {
                    const res = await validate.refetch()
                    if (res.error) { err(toast, 'Could not validate')(res.error); return }
                    const v = res.data?.validation
                    toast({
                      title: v?.valid ? 'No validation errors' : `${v?.errors ?? 0} validation error(s)`,
                      description: `${res.data?.rowCount ?? 0} rows checked.`,
                      variant: v?.valid ? undefined : 'destructive',
                    })
                  }}
                >
                  <ListChecks className="h-4 w-4 mr-1" />
                  {validate.isFetching ? 'Validating…' : 'Validate'}
                </Button>
                <Button
                  size="sm"
                  disabled={generate.isPending}
                  onClick={async () => {
                    try {
                      const res = await generate.mutateAsync(selectedId)
                      setGenerated(res)
                      toast({
                        title: `Generated ${res.job.rowCount ?? 0} row(s)`,
                        description: res.validation.valid
                          ? 'No validation errors — the file is ready to download.'
                          : `${res.validation.errors} validation error(s) travelled with the file.`,
                      })
                    } catch (e) { err(toast, 'Could not generate')(e) }
                  }}
                >
                  <Play className="h-4 w-4 mr-1" />
                  {generate.isPending ? 'Generating…' : 'Generate'}
                </Button>
                {/* Cloning creates a new profile — admin.configure, like New profile. */}
                {canConfigure && detail.data && <CloneDialog profile={detail.data} />}
              </div>
            }
          >
            {detail.isLoading ? (
              <Skeleton className="h-24 w-full" />
            ) : detail.isError ? (
              <p className="text-sm text-[hsl(var(--destructive))]">{(detail.error as ApiError)?.message}</p>
            ) : (
              <div className="space-y-4">
                {detail.data && detail.data.fields.length > 0 ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>#</TableHead>
                        <TableHead>Target field</TableHead>
                        <TableHead>Source expression</TableHead>
                        <TableHead>Keyed on record</TableHead>
                        <TableHead>Transform</TableHead>
                        <TableHead>Required</TableHead>
                        <TableHead>Allowed values</TableHead>
                        <TableHead>Default</TableHead>
                        {canConfigure && !detail.data.signedOff && <TableHead className="text-right">Map</TableHead>}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {detail.data.fields.map((f) => (
                        <TableRow key={f.id}>
                          <TableCell className="num text-muted-foreground">{f.position}</TableCell>
                          <TableCell className="font-mono text-xs font-medium">{f.targetField}</TableCell>
                          <TableCell className="font-mono text-xs text-muted-foreground">{f.sourceExpression || <span className="italic">unmapped</span>}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">{f.keyedAt ?? '—'}</TableCell>
                          <TableCell className="text-sm">{f.transform ?? '—'}</TableCell>
                          <TableCell>
                            {f.required ? <Badge variant="warning">required</Badge> : <span className="text-muted-foreground text-sm">—</span>}
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {f.allowedValues && f.allowedValues.length > 0 ? f.allowedValues.join(', ') : '—'}
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">{f.defaultValue ?? '—'}</TableCell>
                          {canConfigure && !detail.data!.signedOff && (
                            <TableCell className="text-right whitespace-nowrap">
                              <EditFieldDialog profileId={selectedId} field={f} />
                              <DeleteFieldButton profileId={selectedId} field={f} />
                            </TableCell>
                          )}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <p className="text-helper">
                    No fields mapped yet. This profile cannot produce a return until at least one
                    target field is mapped to a source expression.
                  </p>
                )}

                {showValidation && validate.data && (
                  <div className="pt-3 border-t border-border">
                    <p className="text-label mb-2">Validation report</p>
                    <ValidationReportView
                      result={validate.data.validation}
                      rowCount={validate.data.rowCount}
                    />
                  </div>
                )}

                {detail.data && detail.data.fields.length > 0 && !detail.data.signedOff && (
                  <SuggestedFixes profileId={selectedId} canApply={canConfigure} />
                )}

                {showGenerated && generated && (
                  <div className="pt-3 border-t border-border space-y-2">
                    <p className="text-label">Last generated</p>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-mono">{generated.job.filename ?? 'export.csv'}</span>
                      <Badge variant="secondary">{generated.job.status}</Badge>
                      <span className="text-helper num">{generated.job.rowCount ?? 0} rows</span>
                      <Badge variant={generated.validation.valid ? 'success' : 'destructive'}>
                        {generated.validation.errors} error{generated.validation.errors === 1 ? '' : 's'}
                      </Badge>
                      <Button size="sm" variant="outline" onClick={() => downloadExport(generated.job)}>
                        <Download className="h-4 w-4 mr-1" /> Download
                      </Button>
                    </div>
                    <ValidationReportView
                      result={generated.validation}
                      rowCount={generated.job.rowCount ?? 0}
                    />
                  </div>
                )}
              </div>
            )}
          </PageSection>
        )}
      </div>
    </>
  )
}
