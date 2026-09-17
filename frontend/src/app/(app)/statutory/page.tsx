'use client'

/**
 * Statutory returns (Phase 6.6).
 *
 * The whole point of this screen: a statutory return is **configuration, not code**.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  CheckCircle2, CopyPlus, Download, FileSpreadsheet, FileUp, ListChecks, Lock, Unlock, Play, Plus, Pencil, Trash2, ShieldAlert, ShieldCheck, Sparkles,
  type LucideIcon,
} from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { JargonTip } from '@/features/statutory/JargonTip'
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
  Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue,
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
  useUpdateField, useDeleteField, useRecordSchema, usePreviewTransform,
  useSuggestDefaults, useApplyDefaults, useSuppressRule, useRemoveSuppression,
  type GenerateResult, type ReportProfile, type ValidationResult, type FieldMapping,
  type DefaultSuggestion, type ValidationIssue, type RuleAnalysis, type RuleSuppression,
  type ProfileDetail, type ValidationReport, type CompileReport, type CompileMissing,
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

/** Grouped dropdown for a source expression — the catalog comes from GET /report-profiles
 *  /record-schema. Falls back to a plain text input if the schema hasn't loaded (or the
 *  currently-picked value isn't in the catalog — respects hand-typed legacy values). */
function SourceExpressionPicker({
  value, onChange, inputId,
}: {
  value: string
  onChange: (v: string) => void
  inputId?: string
}) {
  const schema = useRecordSchema()
  const groups = schema.data?.groups
  const paths = schema.data?.paths ?? []
  const isCustom = !!value && !paths.includes(value)
  const [mode, setMode] = useState<'pick' | 'custom'>(isCustom ? 'custom' : 'pick')

  // If the value flips to something outside the catalog (e.g. legacy import), swap to custom
  // mode automatically so the value stays visible to the user.
  useEffect(() => {
    if (isCustom && mode !== 'custom') setMode('custom')
  }, [isCustom])   // eslint-disable-line react-hooks/exhaustive-deps

  if (!groups) {
    // Schema loading — fall back to the free-text input, don't block the user.
    return (
      <Input id={inputId} className="font-mono text-xs" value={value}
        onChange={(e) => onChange(e.target.value)} placeholder="student.ref" />
    )
  }

  return (
    <div className="space-y-1.5">
      {mode === 'pick' ? (
        <Select value={value || '__unset'} onValueChange={(v) => onChange(v === '__unset' ? '' : v)}>
          <SelectTrigger id={inputId} className="font-mono text-xs">
            <SelectValue placeholder="Pick a source column…" />
          </SelectTrigger>
          <SelectContent className="max-h-80">
            <SelectItem value="__unset">
              <span className="italic text-muted-foreground">(unmapped — the field ships empty)</span>
            </SelectItem>
            {groups.map((g) => (
              <SelectGroup key={g.root}>
                <SelectLabel className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  {g.label}
                </SelectLabel>
                {g.fields.map((f) => {
                  // Strip the group prefix from the label so we don't read "Student · start
                  // date" inside a "Student record" group — the group header already carries
                  // that context. e.g. "Student · start date" → "start date".
                  const shortLabel = f.label.replace(new RegExp(`^${g.label}·\\s*`), '').replace(/^[^·]+·\s*/, '')
                  return (
                    <SelectItem key={f.path} value={f.path}>
                      <div className="flex flex-col">
                        <span className="text-sm">{shortLabel}</span>
                        <span className="text-[10px] text-muted-foreground">
                          <span className="font-mono">{f.path}</span> · {f.type}
                        </span>
                      </div>
                    </SelectItem>
                  )
                })}
              </SelectGroup>
            ))}
          </SelectContent>
        </Select>
      ) : (
        <Input id={inputId} className="font-mono text-xs" value={value}
          onChange={(e) => onChange(e.target.value)} placeholder="custom.path" />
      )}
      <div className="flex items-center justify-between text-[11px]">
        <span className="text-muted-foreground">
          {mode === 'pick'
            ? 'Or type your own path if it isn\'t in the list.'
            : 'Or pick from the record catalog.'}
        </span>
        <button type="button"
          className="text-muted-foreground hover:text-foreground hover:underline"
          onClick={() => setMode((m) => m === 'pick' ? 'custom' : 'pick')}>
          {mode === 'pick' ? 'custom path' : 'back to picker'}
        </button>
      </div>
    </div>
  )
}

/** Transform CHAIN composer — chips left-to-right = execution order (matches the pipe).
 *  The composed value is stored as a `|`-joined string in the same `transform` field a single
 *  transform used to live in; empty chain → '' (no transform, matches the prior no-transform
 *  state). No drag-reorder in this pass — remove + re-add to reorder. */
function TransformChainComposer({
  value, onChange, id, profileId, sourceExpression,
}: {
  value: string
  onChange: (v: string) => void
  id?: string
  /** When both are passed the composer shows a "what your pipe produces" preview panel
   *  driven off the profile's own cohort. Omit either to fall back to the plain composer. */
  profileId?: string | null
  sourceExpression?: string
}) {
  const transforms = useTransforms()
  const cats = transforms.data?.categories
  // The chain is the source of truth for the UI; we keep the string field in sync via onChange.
  const chain = (value ?? '').split('|').map((s) => s.trim()).filter(Boolean)
  const [pickerOpen, setPickerOpen] = useState(false)

  // Flat lookup so a chip can render the human label even when we only stored the code name.
  const entryByName = useMemo(() => {
    const m = new Map<string, { name: string; label: string; category: string; description: string }>()
    for (const c of cats ?? []) for (const t of c.transforms) m.set(t.name, t)
    return m
  }, [cats])

  const emit = (next: string[]) => onChange(next.join('|'))
  const append = (name: string) => { emit([...chain, name]); setPickerOpen(false) }
  const removeAt = (idx: number) => emit(chain.filter((_, i) => i !== idx))

  // Backend still loading — fall back to plain free-text so the user isn't blocked.
  if (!cats) {
    return (
      <Input id={id} className="font-mono text-xs" value={value}
        onChange={(e) => onChange(e.target.value)} placeholder="No transform" />
    )
  }

  return (
    <div id={id} className="space-y-1.5">
      {chain.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {chain.map((name, idx) => {
            const entry = entryByName.get(name)
            return (
              <span
                key={`${name}-${idx}`}
                className="text-xs rounded-full border border-primary/40 bg-primary/10 inline-flex items-stretch overflow-hidden"
              >
                <span className="px-2.5 py-1 inline-flex items-center gap-1.5">
                  <span className="text-[10px] text-muted-foreground tabular-nums">{idx + 1}.</span>
                  <span className="font-medium">{entry?.label ?? name}</span>
                  <span className="font-mono text-[10px] text-muted-foreground">{name}</span>
                </span>
                <button
                  type="button"
                  onClick={() => removeAt(idx)}
                  title={`Remove ${entry?.label ?? name}`}
                  className="px-2 border-l border-primary/40 text-muted-foreground hover:bg-primary/10 hover:text-foreground"
                  aria-label={`Remove ${entry?.label ?? name}`}
                >
                  ×
                </button>
              </span>
            )
          })}
        </div>
      )}

      {pickerOpen ? (
        <Select
          open
          value=""
          onValueChange={(v) => { if (v) append(v) }}
          onOpenChange={(o) => { if (!o) setPickerOpen(false) }}
        >
          <SelectTrigger className="h-8">
            <SelectValue placeholder="Pick a transform to add…" />
          </SelectTrigger>
          <SelectContent className="max-h-96">
            {cats.map((c) => {
              const remaining = c.transforms.filter((t) => !chain.includes(t.name))
              if (remaining.length === 0) return null
              return (
                <SelectGroup key={c.category}>
                  <SelectLabel className="text-[10px] uppercase tracking-wider text-muted-foreground">
                    {c.category}
                  </SelectLabel>
                  {remaining.map((t) => (
                    <SelectItem key={t.name} value={t.name}>
                      <div className="flex flex-col">
                        <span className="text-sm">{t.label}</span>
                        <span className="text-[10px] text-muted-foreground">
                          <span className="font-mono">{t.name}</span> — {t.description}
                        </span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectGroup>
              )
            })}
          </SelectContent>
        </Select>
      ) : (
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-8"
          onClick={() => setPickerOpen(true)}
        >
          <Plus className="h-3.5 w-3.5 mr-1" />
          {chain.length === 0 ? 'Add transform' : 'Add step'}
        </Button>
      )}

      {chain.length > 0 && (
        <p className="text-[11px] text-muted-foreground">
          Pipeline: <span className="font-mono">{chain.join(' | ')}</span>
        </p>
      )}

      <TransformPreviewPanel
        profileId={profileId ?? null}
        sourceExpression={sourceExpression ?? ''}
        chain={value}
      />
    </div>
  )
}

/** Live "what will this pipe produce" panel driven off the backend's preview-transform endpoint.
 *  Debounced so a rapid chip-toggle spree doesn't fire N requests, and gated so it doesn't ask
 *  when there's nothing meaningful to preview (no profile / no source / catalog still loading). */
function TransformPreviewPanel({
  profileId, sourceExpression, chain,
}: { profileId: string | null; sourceExpression: string; chain: string }) {
  // Only fire when the user hasn't touched the chain for 300ms. Otherwise a "compose 4 chips
  // quickly" flow launches 4 requests against a 670-row cohort — wasteful and can flap the
  // panel between old and new results.
  const [debouncedChain, setDebouncedChain] = useState(chain)
  useEffect(() => {
    const h = window.setTimeout(() => setDebouncedChain(chain), 300)
    return () => window.clearTimeout(h)
  }, [chain])

  const preview = usePreviewTransform(profileId, sourceExpression, debouncedChain)

  if (!profileId || !sourceExpression.trim()) return null

  const errMsg = preview.error
    ? (preview.error as ApiError)?.message ?? 'Preview failed.'
    : null

  return (
    <div className="mt-2 rounded-md border border-border bg-surface-2/50 p-2 text-xs">
      <div className="flex items-center justify-between gap-2 mb-1">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
          Preview — first {preview.data?.sampled ?? 20} of {preview.data?.totalRecords ?? '…'} records
        </span>
        {preview.isFetching && (
          <span className="text-[10px] text-muted-foreground italic">refreshing…</span>
        )}
      </div>
      {errMsg ? (
        <p className="text-[hsl(var(--destructive))]">⚠ {errMsg}</p>
      ) : preview.data ? (
        <div className="max-h-40 overflow-y-auto">
          <table className="w-full text-[11px] tabular-nums">
            <thead className="text-muted-foreground">
              <tr>
                <th className="text-left font-normal pr-2">Ref</th>
                <th className="text-left font-normal pr-2">Input</th>
                <th className="text-left font-normal">Output</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {preview.data.rows.slice(0, 8).map((r) => {
                const isErr = r.output.startsWith('!!')
                return (
                  <tr key={r.studentRef} className="border-t border-border/50">
                    <td className="pr-2 whitespace-nowrap">{r.studentRef}</td>
                    <td className="pr-2 max-w-[140px] truncate" title={String(r.input ?? '')}>
                      {r.input === null || r.input === undefined
                        ? <span className="italic text-muted-foreground">null</span>
                        : String(r.input)}
                    </td>
                    <td className={`max-w-[140px] truncate ${isErr ? 'text-[hsl(var(--destructive))]' : ''}`}
                        title={r.output}>
                      {isErr ? r.output.slice(2) : (r.output || <span className="italic text-muted-foreground">empty</span>)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {preview.data.distinct.outputs.length > 0 && (
            <p className="mt-1.5 text-[10px] text-muted-foreground">
              Distinct outputs across sample: <span className="font-mono">
                {preview.data.distinct.outputs.slice(0, 6).map((o) => o || '""').join(', ')}
                {preview.data.distinct.outputs.length > 6 && ` +${preview.data.distinct.outputs.length - 6}`}
              </span>
            </p>
          )}
        </div>
      ) : (
        <p className="text-muted-foreground italic">Loading preview…</p>
      )}
    </div>
  )
}

interface AddFieldInitial {
  targetField?: string
  allowedValues?: string[]
  required?: boolean
  sourceExpression?: string
  transform?: string
  defaultValue?: string
}

function AddFieldDialog({
  profileId, initial, trigger, open: openProp, onOpenChange,
}: {
  profileId: string
  /** Prefill when opened from a "Map this field" affordance elsewhere. */
  initial?: AddFieldInitial
  /** Custom trigger. Omit for the default "+ Add field" button. */
  trigger?: React.ReactNode
  /** Controlled open state — pass this when the caller wants to drive the dialog. */
  open?: boolean
  onOpenChange?: (open: boolean) => void
}) {
  const { toast } = useToast()
  const add = useAddField(profileId)
  const [openUncontrolled, setOpenUncontrolled] = useState(false)
  const open = openProp ?? openUncontrolled
  const setOpen = (o: boolean) => { onOpenChange ? onOpenChange(o) : setOpenUncontrolled(o) }

  const [targetField, setTargetField] = useState(initial?.targetField ?? '')
  const [sourceExpression, setSourceExpression] = useState(initial?.sourceExpression ?? '')
  const [transform, setTransform] = useState(initial?.transform ?? '')
  const [defaultValue, setDefaultValue] = useState(initial?.defaultValue ?? '')
  const [position, setPosition] = useState('')
  const [required, setRequired] = useState(initial?.required ?? false)
  const [allowedValues, setAllowedValues] = useState((initial?.allowedValues ?? []).join(', '))

  // Re-seed from `initial` every time the dialog OPENS, so multiple "Map this" clicks in a row
  // each hydrate the form for their own missing field rather than showing stale data.
  useEffect(() => {
    if (open) {
      setTargetField(initial?.targetField ?? '')
      setSourceExpression(initial?.sourceExpression ?? '')
      setTransform(initial?.transform ?? '')
      setDefaultValue(initial?.defaultValue ?? '')
      setAllowedValues((initial?.allowedValues ?? []).join(', '))
      setRequired(initial?.required ?? false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initial?.targetField])

  const reset = () => {
    setTargetField(''); setSourceExpression(''); setTransform(''); setDefaultValue('')
    setPosition(''); setRequired(false); setAllowedValues('')
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) reset() }}>
      {trigger !== undefined ? (
        trigger
      ) : (
        <DialogTrigger asChild>
          <Button size="sm"><Plus className="h-4 w-4 mr-1" /> Add field</Button>
        </DialogTrigger>
      )}
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
            <Label htmlFor="f-src">Source column</Label>
            <SourceExpressionPicker
              inputId="f-src"
              value={sourceExpression}
              onChange={setSourceExpression}
            />
            <p className="text-helper">
              Which column on the flat student record this field reads from. Pick from the catalog or
              switch to a custom path (deliberately not an expression language).
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Transform (optional)</Label>
              <TransformChainComposer value={transform} onChange={setTransform}
                profileId={profileId} sourceExpression={sourceExpression} />
              <p className="text-helper">
                Steps run left-to-right. Chain e.g. <span className="font-mono text-xs">strip_special | upper</span>.
              </p>
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

function EditFieldDialog({
  profileId, field, trigger,
}: {
  profileId: string
  field: FieldMapping
  /** Custom trigger — passing one replaces the default Pencil icon button, so ANY element on the
   *  page (e.g. the source-expression cell) can behave like an "edit this mapping" hyperlink. */
  trigger?: React.ReactNode
}) {
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
        {trigger ?? (
          <Button size="icon" variant="ghost" className="h-8 w-8" title={`Edit ${field.targetField}`}>
            <Pencil className="h-4 w-4" />
          </Button>
        )}
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
            <Label htmlFor="e-src">Source column (what this field reads from)</Label>
            <SourceExpressionPicker
              inputId="e-src"
              value={sourceExpression}
              onChange={setSourceExpression}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="e-transform">Transform (optional)</Label>
              <TransformChainComposer id="e-transform" value={transform} onChange={setTransform}
                profileId={profileId} sourceExpression={sourceExpression} />
              <p className="text-helper">Steps run left-to-right. Remove and re-add to reorder.</p>
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

// ---------------------------------------------------------------- statutory field defaults
//
// ICR follow-on: most student records don't carry HESA-only demographics (SEXID, ETHNIC, BIRTHDTE
// etc.), so the return validates with thousands of "required but empty" errors. Rather than editing
// 8000 student records, an admin sets a **default per statutory field once**; on Generate the
// backend already substitutes the default when the record's source resolves to empty (see
// backend/app/modules/exports/statutory.py line 481–482). This section makes that setting inline
// per required field, with the empty-default rows surfaced first.

function DefaultRow({
  profileId, field, highlighted, rejectionCount, onGoToFields,
}: {
  profileId: string
  field: FieldMapping
  highlighted?: boolean
  rejectionCount?: number
  onGoToFields?: () => void
}) {
  const { toast } = useToast()
  const update = useUpdateField(profileId)
  const [value, setValue] = useState(field.defaultValue ?? '')
  const inputRef = useRef<HTMLInputElement | null>(null)
  const rowRef = useRef<HTMLTableRowElement | null>(null)
  // Re-seed when the underlying field changes (e.g. after a save elsewhere).
  useEffect(() => { setValue(field.defaultValue ?? '') }, [field.defaultValue])

  // When highlighted from the validation report, scroll into view and focus the input.
  useEffect(() => {
    if (!highlighted) return
    rowRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    inputRef.current?.focus()
  }, [highlighted])

  const dirty = (value || '') !== (field.defaultValue ?? '')
  const hasDefault = (field.defaultValue ?? '').length > 0
  const allowed = field.allowedValues ?? []
  const unmapped = !(field.sourceExpression ?? '').trim()
  // Recognise date-shape fields so we can render a real picker. Two signals: the transform chain
  // includes a date normaliser, OR the field code ends with DATE/DTE/DOB (HESA convention).
  const transformParts = new Set((field.transform ?? '').split('|').map((s) => s.trim()).filter(Boolean))
  const isDate = transformParts.has('date_compact') || transformParts.has('date_iso') || transformParts.has('year')
    || /^(?:.*)(DATE|DTE|DOB)$/i.test(field.targetField)
  // HESA usually stores dates as YYYYMMDD (date_compact). Convert to/from YYYY-MM-DD so the native
  // <input type="date"> is usable — we save back in the storage format.
  const isCompact = transformParts.has('date_compact') || /^\d{8}$/.test(value || '')
  const toPickerValue = (s: string) => {
    if (!s) return ''
    if (isCompact && /^\d{8}$/.test(s)) return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`
    return s   // date_iso already YYYY-MM-DD
  }
  const fromPickerValue = (s: string) => {
    if (!s) return ''
    if (isCompact) return s.replaceAll('-', '')   // YYYY-MM-DD → YYYYMMDD
    return s
  }

  const save = async () => {
    if (!dirty) return
    try {
      await update.mutateAsync({ id: field.id, body: { defaultValue: value || undefined } })
      toast({ title: value ? `Default set for ${field.targetField}` : `Default cleared for ${field.targetField}` })
    } catch (e) { err(toast, 'Could not save default')(e) }
  }

  return (
    <TableRow
      ref={rowRef}
      className={highlighted ? 'bg-primary/5 ring-2 ring-primary/40 transition-colors' : undefined}
    >
      <TableCell className="font-mono text-xs font-medium whitespace-nowrap">
        {field.targetField}
        {field.required && <Badge variant="warning" className="ml-1.5 text-[10px] py-0 px-1.5">req</Badge>}
      </TableCell>
      <TableCell className="text-xs text-muted-foreground max-w-[200px]">
        {unmapped ? (
          <span className="italic">unmapped</span>
        ) : (
          <span className="font-mono">{field.sourceExpression}</span>
        )}
        {field.keyedAt && <div className="text-[10px] mt-0.5">{field.keyedAt}</div>}
      </TableCell>
      <TableCell className="text-xs text-muted-foreground max-w-[220px]">
        {allowed.length > 0 ? (
          <span className="font-mono">{allowed.join(', ')}</span>
        ) : (
          <span className="italic">free text</span>
        )}
      </TableCell>
      <TableCell>
        {allowed.length > 0 ? (
          <Select value={value || '__none'} onValueChange={(v) => setValue(v === '__none' ? '' : v)}>
            <SelectTrigger className="h-8 w-[160px]"><SelectValue placeholder="(no default)" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__none"><span className="italic text-muted-foreground">(no default)</span></SelectItem>
              {allowed.map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}
            </SelectContent>
          </Select>
        ) : isDate ? (
          <Input
            ref={inputRef}
            type="date"
            className="h-8 w-[160px] font-mono text-xs"
            value={toPickerValue(value)}
            onChange={(e) => setValue(fromPickerValue(e.target.value))}
            onBlur={save}
          />
        ) : (
          <Input
            ref={inputRef}
            className="h-8 w-[160px] font-mono text-xs"
            value={value}
            placeholder="(no default)"
            onChange={(e) => setValue(e.target.value)}
            onBlur={save}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); (e.target as HTMLInputElement).blur() } }}
          />
        )}
      </TableCell>
      <TableCell>
        {hasDefault ? <Badge variant="success">set</Badge> : <Badge variant="warning">empty</Badge>}
        {hasDefault && (rejectionCount ?? 0) > 0 && (
          <div className="mt-1 text-[11px] leading-snug text-[hsl(var(--warning))] max-w-[220px]">
            ⚠ {rejectionCount} record{rejectionCount === 1 ? '' : 's'} produced a value that failed validation.
            Defaults only apply when the source column is empty.
            {onGoToFields && (
              <>
                {' '}
                <button
                  type="button"
                  onClick={onGoToFields}
                  className="underline underline-offset-2 hover:text-foreground"
                >
                  Edit mapping →
                </button>
              </>
            )}
          </div>
        )}
      </TableCell>
      <TableCell className="text-right">
        <Button
          size="sm" variant={dirty ? 'default' : 'outline'} className="h-7"
          disabled={!dirty || update.isPending}
          onClick={save}
        >
          {update.isPending ? 'Saving…' : dirty ? 'Save' : 'Saved'}
        </Button>
      </TableCell>
    </TableRow>
  )
}

function SuggestDefaultsDialog({ profileId }: { profileId: string }) {
  const { toast } = useToast()
  const suggest = useSuggestDefaults(profileId)
  const apply = useApplyDefaults(profileId)
  const [open, setOpen] = useState(false)
  const [picks, setPicks] = useState<Record<string, boolean>>({})   // field -> selected

  const openDialog = async () => {
    setOpen(true)
    const res = await suggest.refetch()
    if (res.data) {
      // Pre-check every applicable suggestion — user unchecks the ones they don't want.
      const pre: Record<string, boolean> = {}
      res.data.suggestions.forEach((s) => { if (s.applicable && s.suggested) pre[s.field] = true })
      setPicks(pre)
    }
  }

  const suggestions = suggest.data?.suggestions ?? []
  const applicable = suggestions.filter((s) => s.applicable)
  const skipped = suggestions.filter((s) => !s.applicable)
  const checkedCount = Object.values(picks).filter(Boolean).length

  const applySelected = async () => {
    const chosen = applicable
      .filter((s) => picks[s.field] && s.suggested)
      .map((s) => ({ field: s.field, value: s.suggested as string }))
    if (chosen.length === 0) { setOpen(false); return }
    try {
      const res = await apply.mutateAsync(chosen)
      toast({ title: `Applied ${res.count} default${res.count === 1 ? '' : 's'}` })
      setOpen(false); setPicks({})
    } catch (e) { err(toast, 'Could not apply defaults')(e) }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) setPicks({}) }}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline" onClick={openDialog}>
          <Sparkles className="h-4 w-4 mr-1" /> Suggest defaults
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Suggested defaults</DialogTitle>
        </DialogHeader>
        <p className="text-helper">
          Evidence-based, not opinion. For each field the system inspects every student record
          this return covers, computes the value distribution, and suggests the value the data
          already points to — with the counts visible so you can decide. When no value dominates
          the cohort but the spec publishes a "not known / other" code, that's the safe fallback.
          Dates and unrestricted free-text are never guessed.
        </p>
        {suggest.isFetching && !suggest.data ? (
          <Skeleton className="h-40 w-full" />
        ) : suggest.isError ? (
          <p className="text-sm text-[hsl(var(--destructive))]">
            {(suggest.error as ApiError)?.message ?? 'Could not fetch suggestions.'}
          </p>
        ) : (
          <div className="space-y-3 max-h-[420px] overflow-y-auto pr-2">
            {applicable.length > 0 ? (
              <div className="card-elevated overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[36px]"></TableHead>
                      <TableHead>Field</TableHead>
                      <TableHead>Suggested</TableHead>
                      <TableHead>Evidence in your cohort</TableHead>
                      <TableHead className="w-[90px]">Basis</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {applicable.map((s) => {
                      const ev = s.evidence
                      // "Basis" colour: data-driven picks are green (cohort said so), convention
                      // picks are amber (nothing in the cohort points anywhere — using the safe
                      // HESA fallback).
                      const basisLabel = s.source === 'data' ? 'cohort' : 'spec fallback'
                      const basisVariant: 'success' | 'warning' = s.source === 'data' ? 'success' : 'warning'
                      return (
                        <TableRow key={s.field}>
                          <TableCell>
                            <Checkbox
                              checked={!!picks[s.field]}
                              onCheckedChange={(c) => setPicks((p) => ({ ...p, [s.field]: c === true }))}
                            />
                          </TableCell>
                          <TableCell className="font-mono text-xs font-medium whitespace-nowrap">
                            {s.field}
                            {s.required && <Badge variant="warning" className="ml-1.5 text-[10px] py-0 px-1.5">req</Badge>}
                          </TableCell>
                          <TableCell className="font-mono text-xs">{s.suggested}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            <div className="tabular-nums">
                              {ev.populated} / {ev.total} populated
                              {ev.empty > 0 && <> · <span className="text-[hsl(var(--warning))]">{ev.empty} empty</span></>}
                              {ev.unique > 0 && <> · {ev.unique} unique value{ev.unique === 1 ? '' : 's'}</>}
                            </div>
                            {ev.topValues.length > 0 && (
                              <div className="mt-0.5 font-mono">
                                top: {ev.topValues.map((v) => `${v.value} (${v.count})`).join(', ')}
                              </div>
                            )}
                            <div className="mt-0.5 italic">{s.reason}</div>
                          </TableCell>
                          <TableCell>
                            <Badge variant={basisVariant} className="text-[10px] whitespace-nowrap">{basisLabel}</Badge>
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </div>
            ) : (
              <p className="text-helper italic">
                No safe defaults to suggest — all applicable fields already have one, or the remaining
                fields can't be safely defaulted (dates, unrestricted free text).
              </p>
            )}
            {skipped.length > 0 && (
              <details className="text-xs">
                <summary className="cursor-pointer text-muted-foreground">
                  {skipped.length} skipped (dates / free text / already set)
                </summary>
                <ul className="mt-2 space-y-1 pl-4">
                  {skipped.map((s) => (
                    <li key={s.field}>
                      <span className="font-mono">{s.field}</span>
                      {s.current && <span className="text-[hsl(var(--success))]"> · already set to {s.current}</span>}
                      <span className="text-muted-foreground"> — {s.reason}</span>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
          <Button
            disabled={checkedCount === 0 || apply.isPending}
            onClick={applySelected}
          >
            {apply.isPending ? 'Applying…' : `Apply ${checkedCount} default${checkedCount === 1 ? '' : 's'}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function FieldDefaultsSection({
  profileId, fields, onGoToFields, validationIssues,
}: {
  profileId: string
  fields: FieldMapping[]
  onGoToFields?: () => void
  validationIssues?: ValidationIssue[] | null
}) {
  // Per-field count of records where a value was produced but rejected. These are records where
  // the default does NOT help — the source column is populated, so the default never applies.
  // (Defaults only fill in for EMPTY source values; a wrong non-empty value needs a mapping edit.)
  const rejectionsByField = useMemo(() => {
    const m = new Map<string, number>()
    for (const i of validationIssues ?? []) {
      if (i.severity !== 'error') continue
      // "empty" errors ARE fixable by a default; skip those. Any other error means a value was
      // produced and rejected — a real mismatch the default can't fix.
      if (/\bempty\b/i.test(i.message)) continue
      m.set(i.field, (m.get(i.field) ?? 0) + 1)
    }
    return m
  }, [validationIssues])
  // Focus filter — required-only surfaces the sign-off blockers; "needs one" adds unmapped
  // fields (no source expression means the produced value is always empty); "all" is every field.
  const [focus, setFocus] = useState<'needs' | 'required' | 'all'>('needs')
  // Highlight target (set from the validation report's "Set default for FIELD" quick-jump).
  const highlight = useHighlightedField()

  // If the quick-jump target isn't in the current filter, widen to "all" so it can be scrolled to.
  useEffect(() => {
    if (!highlight) return
    const inView = fields.some((f) => f.targetField === highlight && (
      focus === 'all' || (focus === 'required' && f.required) ||
      (focus === 'needs' && (f.required || !(f.sourceExpression ?? '').trim()))
    ))
    if (!inView) setFocus('all')
  }, [highlight, fields, focus])

  const rows = useMemo(() => {
    const filtered = fields.filter((f) => {
      if (focus === 'all') return true
      if (focus === 'required') return f.required
      // "needs a default" — required OR unmapped (no source column). These are the fields that
      // ship an empty value today; setting a default plugs them.
      return f.required || !f.sourceExpression?.trim()
    })
    return [...filtered].sort((a, b) => {
      const aEmpty = !(a.defaultValue ?? '').length
      const bEmpty = !(b.defaultValue ?? '').length
      if (aEmpty !== bEmpty) return aEmpty ? -1 : 1
      // Prioritise required-and-empty, then by field code.
      if (a.required !== b.required) return a.required ? -1 : 1
      return a.targetField.localeCompare(b.targetField)
    })
  }, [fields, focus])

  const emptyCount = rows.filter((f) => !(f.defaultValue ?? '').length).length
  const totalRequired = fields.filter((f) => f.required).length
  const totalNeeds = fields.filter((f) => f.required || !f.sourceExpression?.trim()).length

  if (fields.length === 0) return null

  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-label inline-flex items-center gap-1.5">
            Statutory field defaults <JargonTip term="default when empty" />
          </p>
          <p className="text-helper max-w-2xl">
            Defaults apply <strong>only when the record's source column is empty</strong>. If a source
            column is populated but the produced value fails validation, the default won't help — fix
            the mapping's transform or allowed values on the <em>Fields</em> tab instead. Set once
            per year; the same default applies to every student the return covers.
          </p>
        </div>
        <div className="flex items-center gap-2 whitespace-nowrap">
          <SuggestDefaultsDialog profileId={profileId} />
          <Badge variant={emptyCount === 0 ? 'success' : 'warning'}>
            {emptyCount === 0
              ? `${rows.length} / ${rows.length} covered`
              : `${emptyCount} of ${rows.length} without a default`}
          </Badge>
        </div>
      </div>
      <div className="inline-flex rounded-md border border-border p-0.5 text-xs">
        {([
          ['needs', `Needs a default (${totalNeeds})`, 'Required fields plus every unmapped field — anywhere the return would ship an empty value.'],
          ['required', `Required only (${totalRequired})`, 'Only fields marked required by the specification.'],
          ['all', `All fields (${fields.length})`, 'Every field in the profile — including ones already populated from the record.'],
        ] as const).map(([k, label, tip]) => (
          <button key={k} type="button" title={tip} onClick={() => setFocus(k)}
            className={`px-2 py-0.5 rounded ${focus === k ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
            {label}
          </button>
        ))}
      </div>
      <div className="card-elevated overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Field</TableHead>
              <TableHead>Source</TableHead>
              <TableHead>Allowed values</TableHead>
              <TableHead>Default when empty</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right w-[90px]">Save</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((f) => (
              <DefaultRow
                key={f.id}
                profileId={profileId}
                field={f}
                highlighted={highlight === f.targetField}
                rejectionCount={rejectionsByField.get(f.targetField) ?? 0}
                onGoToFields={onGoToFields}
              />
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

// ---- cross-component quick-jump: validation report → defaults input ----
//
// A tiny module-scoped signal so the validation report can nudge the defaults section to scroll
// to a specific field and highlight its input, without threading refs through 3 components.
let _highlightTarget: string | null = null
const _highlightSubs = new Set<() => void>()
function setHighlightedField(field: string | null) {
  _highlightTarget = field
  _highlightSubs.forEach((fn) => fn())
  if (field) {
    // Auto-clear the highlight after a couple of seconds so it doesn't linger.
    window.setTimeout(() => { if (_highlightTarget === field) setHighlightedField(null) }, 2500)
  }
}
function useHighlightedField() {
  const [, force] = useState(0)
  useEffect(() => {
    const fn = () => force((n) => n + 1)
    _highlightSubs.add(fn)
    return () => { _highlightSubs.delete(fn) }
  }, [])
  return _highlightTarget
}

// ---------------------------------------------------------------- validation

const ISSUES_PER_PAGE = 25

function ValidationReportView({ result, rowCount, profileId }: { result: ValidationResult; rowCount: number; profileId: string }) {
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
          {/* Grouped by field ("error type") — click the label to filter, click "Fix all" to
             jump to the defaults input for that field (setting one default clears every "empty"
             or "not in allowed" error for that field in one shot — the group correction). */}
          <div className="flex flex-wrap gap-1.5">
            <button type="button" onClick={() => setField(null)}
              className={`text-xs rounded-full border px-2.5 py-1 ${!field ? 'bg-primary/10 border-primary/40 font-medium' : 'border-border hover:bg-surface-2'}`}>
              All fields ({result.issues.length})
            </button>
            {groups.map((g) => (
              <span key={g.field}
                className={`text-xs rounded-full border inline-flex items-stretch overflow-hidden ${field === g.field ? 'bg-primary/10 border-primary/40 font-medium' : 'border-border'}`}>
                <button type="button" onClick={() => setField(g.field)}
                  className="px-2.5 py-1 inline-flex items-center gap-1.5 hover:bg-surface-2">
                  <span className="font-mono">{g.field}</span>
                  <span className={g.errors ? 'text-[hsl(var(--destructive))]' : 'text-[hsl(var(--warning))]'}>{g.count}</span>
                </button>
                <button type="button"
                  title={`Fix all ${g.count} — set a default value for ${g.field}`}
                  onClick={() => setHighlightedField(g.field)}
                  className="px-2 py-1 border-l border-border hover:bg-primary/10 text-primary inline-flex items-center gap-1">
                  <Sparkles className="h-3 w-3" /> Fix all
                </button>
              </span>
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
                  <TableHead className="text-right w-[80px]">Fix</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pageItems.map((i, idx) => (
                  <ValidationRow key={`${i.studentRef}-${i.field}-${start + idx}`}
                    issue={i}
                    analysis={result.ruleAnalysis?.find((a) => a.ruleKey === i.ruleKey)}
                    profileId={profileId}
                  />
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

// ---- per-row smart Fix ----
//
// One "Fix" button per validation row that picks the right action for the error type:
//   * required-but-empty / not-in-allowed  →  quick-jump to the field's default input
//   * cross-field ordering (kind='order')  →  small dialog with EVIDENCE (X of Y records
//                                             violate this rule) and, when the rule is
//                                             clearly misconfigured (share > 50%), a
//                                             one-click "Mute this rule for this profile"
//   * date format issue                    →  jump to the field's default input (a valid
//                                             default at least stops the format explosion)

function ValidationRow({
  issue: i, analysis, profileId,
}: {
  issue: ValidationIssue
  analysis: RuleAnalysis | undefined
  profileId: string
}) {
  const canDefault = /is required.*but is empty|is not an accepted value/.test(i.message)
  const isOrder = i.fix?.kind === 'order'
  const isDate = i.fix?.kind === 'format_date'
  const [orderOpen, setOrderOpen] = useState(false)

  return (
    <TableRow>
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
        {analysis?.likelyMisconfigured && (
          <div className="mt-1">
            <Badge variant="warning" className="text-[10px]">
              rule violated on {analysis.violations} of {analysis.total} records ({Math.round(analysis.share * 100)}%)
            </Badge>
          </div>
        )}
      </TableCell>
      <TableCell className="text-right">
        {isOrder ? (
          <>
            <Button
              size="sm" variant={analysis?.likelyMisconfigured ? 'default' : 'ghost'} className="h-7 text-xs"
              onClick={() => setOrderOpen(true)}
            >
              Fix →
            </Button>
            <OrderFixDialog
              open={orderOpen} onClose={() => setOrderOpen(false)}
              issue={i} analysis={analysis} profileId={profileId}
            />
          </>
        ) : canDefault ? (
          <Button
            size="sm" variant="ghost" className="h-7 text-xs"
            title={`Jump to the default for ${i.field} (fixes this and every other row with the same error)`}
            onClick={() => setHighlightedField(i.field)}
          >
            Set default →
          </Button>
        ) : isDate ? (
          <Button
            size="sm" variant="ghost" className="h-7 text-xs"
            title={`Set a valid default for ${i.field}`}
            onClick={() => setHighlightedField(i.field)}
          >
            Set default →
          </Button>
        ) : (
          <span className="text-[10px] text-muted-foreground">per record</span>
        )}
      </TableCell>
    </TableRow>
  )
}

function OrderFixDialog({
  open, onClose, issue: i, analysis, profileId,
}: {
  open: boolean
  onClose: () => void
  issue: ValidationIssue
  analysis: RuleAnalysis | undefined
  profileId: string
}) {
  const { toast } = useToast()
  const suppress = useSuppressRule(profileId)
  const [reason, setReason] = useState('')
  const [scope, setScope] = useState<'profile' | 'pack'>('profile')
  useEffect(() => { if (open) { setReason(''); setScope('profile') } }, [open])
  if (i.fix?.kind !== 'order') return null

  const { thisField, thisValue, otherField, otherValue } = i.fix
  const misconfigured = analysis?.likelyMisconfigured
  const shareText = analysis
    ? `${analysis.violations} of ${analysis.total} records (${Math.round(analysis.share * 100)}%) violate this rule.`
    : ''

  const doSuppress = async () => {
    if (!i.ruleKey || !reason.trim()) return
    try {
      await suppress.mutateAsync({ ruleKey: i.ruleKey, reason: reason.trim(), scope })
      toast({
        title: `Rule suppressed (${scope === 'pack' ? 'spec-pack scope' : 'this profile only'}) — re-validate to see the drop.`,
      })
      onClose()
    } catch (e) { err(toast, 'Could not suppress the rule')(e) }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Suppress rule</DialogTitle>
          <p className="text-helper">
            Suppressing stops the rule firing — it doesn't fix the underlying issue. Only defensible
            when the rule itself is wrong (or doesn't apply to this pack).
          </p>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          <div className="rounded-md border border-border p-3 space-y-1 font-mono text-xs">
            <div><span className="text-muted-foreground">record</span> {i.studentRef}</div>
            <div><span className="text-muted-foreground">{otherField}</span> = {otherValue}</div>
            <div><span className="text-muted-foreground">{thisField}</span> = {thisValue}</div>
            <div className="pt-1 text-muted-foreground border-t border-border">
              rule expects {thisField} to be on or after {otherField}
            </div>
          </div>
          {misconfigured ? (
            <div className="rounded-md bg-[hsl(var(--warning)/0.08)] border border-[hsl(var(--warning)/0.4)] p-3 text-xs space-y-1">
              <p className="font-medium">This rule looks misconfigured.</p>
              <p className="text-muted-foreground">
                {shareText} A genuine cross-field rule catches outliers, not the majority — this
                one probably arrived via a bad advisory. Since this affects every profile using
                the same pack, consider suppressing at the spec-pack level below.
              </p>
            </div>
          ) : (
            <div className="rounded-md bg-surface-2 border border-border p-3 text-xs">
              <p>{shareText} A minority of records fails this rule — the data on the affected
                 records is the likely cause. Suppressing hides the errors without fixing them;
                 prefer editing the student records themselves.</p>
            </div>
          )}

          {i.ruleKey && (
            <>
              <div className="space-y-2">
                <Label>Scope</Label>
                <div className="rounded-md border border-border divide-y divide-border">
                  <label className="flex items-start gap-3 p-3 cursor-pointer hover:bg-surface-2">
                    <input type="radio" name="scope" className="mt-0.5"
                      checked={scope === 'profile'} onChange={() => setScope('profile')} />
                    <span className="text-xs">
                      <span className="font-medium block">Only this profile</span>
                      <span className="text-muted-foreground">Suppression applies to this return only. Other profiles on the same pack still enforce the rule.</span>
                    </span>
                  </label>
                  <label className="flex items-start gap-3 p-3 cursor-pointer hover:bg-surface-2">
                    <input type="radio" name="scope" className="mt-0.5"
                      checked={scope === 'pack'} onChange={() => setScope('pack')} />
                    <span className="text-xs">
                      <span className="font-medium block">For every profile on this spec pack</span>
                      <span className="text-muted-foreground">The right fix when the rule arrived via a bad advisory — one suppression covers every profile using the pack version.</span>
                    </span>
                  </label>
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="sup-reason">Why is this suppression justified? <span className="text-danger">*</span></Label>
                <textarea id="sup-reason" rows={2}
                  value={reason} onChange={(e) => setReason(e.target.value)}
                  placeholder="e.g. Rule's fields are inverted vs the HESA spec; raised with Registry."
                  className="w-full rounded-md border border-border bg-background p-2 text-sm" />
                <p className="text-helper">Recorded with your name and the time; shown on the sign-off card.</p>
              </div>
            </>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          {i.ruleKey && (
            <Button
              disabled={!reason.trim() || suppress.isPending}
              onClick={doSuppress}
            >
              {suppress.isPending ? 'Suppressing…'
                : `Suppress ${scope === 'pack' ? 'at spec-pack level' : 'for this profile'}`}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
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

function SuppressionsPanel({
  profileId, suppressions, canManage, signed,
}: {
  profileId: string
  suppressions: RuleSuppression[]
  canManage: boolean
  signed: boolean
}) {
  const { toast } = useToast()
  const remove = useRemoveSuppression(profileId)

  // UX fix (2026-09-17): the panel used to be amber-ringed with a prominent Undo button per
  // row, which read as "unresolved item, take action". That's misleading — a suppression is a
  // DECISION already made; sign-off is never blocked by one (only unmapped mandatory fields
  // block). Tone-down: neutral surface, small reassurance line, Undo demoted to a tiny link.
  return (
    <div className="rounded-md border border-border bg-surface-2 p-3 space-y-2">
      <div className="flex items-start gap-2 text-sm">
        <ShieldCheck className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="font-medium">
              {suppressions.length} suppression{suppressions.length === 1 ? '' : 's'} — attested at sign-off
            </span>
            <span className="text-helper">These don't block sign-off. Undo any row only if you want to re-enable the check.</span>
          </div>
        </div>
      </div>
      <div className="card-elevated overflow-hidden bg-background">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Rule</TableHead>
              <TableHead>Scope</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>By</TableHead>
              <TableHead>When</TableHead>
              {canManage && !signed && <TableHead className="text-right w-[80px]"></TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {suppressions.map((s) => (
              <TableRow key={`${s.scope}-${s.ruleKey}`}>
                <TableCell className="font-mono text-xs">{s.ruleKey}</TableCell>
                <TableCell>
                  <Badge
                    variant="secondary"
                    className="text-[10px] font-normal"
                    title={s.scope === 'pack'
                      ? "Suppressed at the spec-pack level — applies to every profile using this pack version. Stable admin decision."
                      : "Suppressed for this profile only. The shared spec pack is unaffected."}
                  >
                    {s.scope === 'pack' ? 'spec pack' : 'this profile'}
                  </Badge>
                </TableCell>
                <TableCell className="text-xs">
                  {s.reason ?? <span className="italic text-muted-foreground">no reason recorded (legacy)</span>}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">{s.byUserName ?? '—'}</TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {s.at ? new Date(s.at).toLocaleString() : '—'}
                </TableCell>
                {canManage && !signed && (
                  <TableCell className="text-right">
                    <button
                      type="button"
                      className="text-[11px] text-muted-foreground hover:text-foreground hover:underline"
                      disabled={remove.isPending}
                      onClick={async () => {
                        if (!window.confirm(
                          `Re-enable the ${s.ruleKey} rule for ${s.scope === 'pack' ? 'every profile on this spec pack' : 'this profile'}? The suppression will be removed.`,
                        )) return
                        try {
                          await remove.mutateAsync({ ruleKey: s.ruleKey, scope: s.scope })
                          toast({ title: `Suppression removed (${s.scope}) — re-validate to see the rule fire again.` })
                        } catch (e) { err(toast, 'Could not remove suppression')(e) }
                      }}
                    >
                      undo
                    </button>
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

/** The "Missing field" list on the Sign-off tab is the ONE place a user with sign-off
 *  responsibility lands when a profile is Not Ready. It has to answer the obvious question — "how
 *  do I map this?" — right there, not "go to another tab and find the right button".
 *
 *  UX v3: for fields the spec pack knows a default source for (the common case), the row shows a
 *  one-click "Map to <path>" — instant map, no dialog, no form. Fields with no spec-suggested
 *  source keep the "Map…" button that opens the full form. Progressive disclosure by row.
 */
function MissingFieldsTable({
  profileId, missing, canConfigure,
}: {
  profileId: string
  missing: CompileMissing[]
  canConfigure: boolean
}) {
  const { toast } = useToast()
  const add = useAddField(profileId)
  const [openField, setOpenField] = useState<string | null>(null)
  const [pendingField, setPendingField] = useState<string | null>(null)
  const target = missing.find((m) => m.field === openField) ?? null

  const oneClickMap = async (m: CompileMissing) => {
    if (!m.specDefaultSource) return
    setPendingField(m.field)
    try {
      await add.mutateAsync({
        targetField: m.field,
        sourceExpression: m.specDefaultSource,
        transform: m.specDefaultTransform ?? undefined,
        defaultValue: m.specDefaultValue ?? undefined,
        required: true,
        allowedValues: m.allowed ?? undefined,
      })
      toast({ title: `Mapped ${m.field} → ${m.specDefaultSource}` })
    } catch (e) { err(toast, `Could not map ${m.field}`)(e) }
    finally { setPendingField(null) }
  }

  // A "Map every suggested" pill lets the user resolve every missing field the spec has an answer
  // for in one action — the fastest path from "Not Ready" to a real conversation about the rest.
  const withSuggestion = missing.filter((m) => !!m.specDefaultSource)
  const mapAllSuggested = async () => {
    for (const m of withSuggestion) await oneClickMap(m)
  }

  return (
    <div className="card-elevated overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 px-3 py-2 border-b border-border bg-surface-2">
        <p className="text-xs text-muted-foreground max-w-xl">
          Required by the spec, not yet in your mapping. Rows the spec knows a source for get a one-click
          Map; the rest open a short form.
        </p>
        {canConfigure && withSuggestion.length > 0 && (
          <Button size="sm" onClick={mapAllSuggested}
            disabled={add.isPending || pendingField !== null}
            className="whitespace-nowrap">
            <Sparkles className="h-4 w-4 mr-1" />
            Map every suggested ({withSuggestion.length})
          </Button>
        )}
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Missing field</TableHead>
            <TableHead>Description</TableHead>
            <TableHead>Suggested source</TableHead>
            {canConfigure && <TableHead className="text-right w-[220px]">Map</TableHead>}
          </TableRow>
        </TableHeader>
        <TableBody>
          {missing.map((m) => {
            const suggestion = m.specDefaultSource
            const busy = pendingField === m.field
            return (
              <TableRow key={m.field}>
                <TableCell className="font-mono text-xs font-medium whitespace-nowrap">{m.field}</TableCell>
                <TableCell className="text-sm">
                  {m.description}
                  {m.allowed && m.allowed.length > 0 && (
                    <div className="text-[11px] text-muted-foreground font-mono mt-0.5">
                      allowed: {m.allowed.slice(0, 8).join(', ')}{m.allowed.length > 8 ? ', …' : ''}
                    </div>
                  )}
                </TableCell>
                <TableCell className="text-xs">
                  {suggestion
                    ? <span className="font-mono text-foreground">{suggestion}</span>
                    : <span className="italic text-muted-foreground">no default — needs the form</span>}
                </TableCell>
                {canConfigure && (
                  <TableCell className="text-right">
                    {suggestion ? (
                      <div className="inline-flex items-center gap-1">
                        <Button
                          size="sm" variant="default" className="h-7 text-xs whitespace-nowrap"
                          disabled={busy || add.isPending}
                          onClick={() => oneClickMap(m)}
                        >
                          {busy ? 'Mapping…' : `→ ${suggestion}`}
                        </Button>
                        <Button
                          size="sm" variant="ghost" className="h-7 text-xs"
                          disabled={busy}
                          title="Open the form to tweak the source, transform or default before saving"
                          onClick={() => setOpenField(m.field)}
                        >
                          edit…
                        </Button>
                      </div>
                    ) : (
                      <Button size="sm" variant="outline" className="h-7 text-xs"
                        onClick={() => setOpenField(m.field)}>
                        <Plus className="h-3.5 w-3.5 mr-1" /> Map…
                      </Button>
                    )}
                  </TableCell>
                )}
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
      {/* A single controlled AddFieldDialog for the "no suggestion" or "edit before save" paths.
         Same dialog the Fields tab uses — no divergent code path. */}
      {canConfigure && (
        <AddFieldDialog
          profileId={profileId}
          trigger={null}
          open={openField !== null}
          onOpenChange={(o) => { if (!o) setOpenField(null) }}
          initial={target ? {
            targetField: target.field,
            allowedValues: target.allowed ?? undefined,
            required: true,
            sourceExpression: target.specDefaultSource ?? undefined,
            transform: target.specDefaultTransform ?? undefined,
            defaultValue: target.specDefaultValue ?? undefined,
          } : undefined}
        />
      )}
    </div>
  )
}

function SignOffCard({ profileId, canSignOff }: { profileId: string; canSignOff: boolean }) {
  const { toast } = useToast()
  const { hasPermission } = useAuth()
  const canManageFields = hasPermission('admin.configure')
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

      {r.suppressions && r.suppressions.length > 0 && (
        <SuppressionsPanel profileId={profileId} suppressions={r.suppressions} canManage={canSignOff} signed={signed} />
      )}

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
            <MissingFieldsTable
              profileId={profileId}
              missing={r.missing}
              canConfigure={canManageFields}
            />
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
                  <br />Suppressions below don't block — they're attested to as part of sign-off.
                </span>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- guided flow (as tabs)
//
// UX v2: the "Get this return ready" guided flow now IS the tab bar. Each tab is a step —
// numbered, with a live status pill on the label so the user sees progress without scrolling.
// One tab visible at a time replaces the old nine-stacked-sections firehose. Advisories is a
// sibling tab (same UI grammar, direct jump).

type StatutoryTab = 'fields' | 'defaults' | 'validation' | 'signoff' | 'advisories'

interface TabStatuses {
  fields: { done: boolean; label: string; tone: 'ok' | 'warn' | 'idle' }
  defaults: { done: boolean; label: string; tone: 'ok' | 'warn' | 'idle' }
  validation: { done: boolean; label: string; tone: 'ok' | 'warn' | 'error' | 'idle' }
  signoff: { done: boolean; label: string; tone: 'ok' | 'warn' | 'idle' }
  advisories: { done: boolean; label: string; tone: 'ok' | 'warn' | 'idle' }
}

/** Compute the live status pill for every tab from the same queries the sections use. Kept as a
 *  pure function so the tab bar can render without owning any state itself. */
function computeTabStatuses(
  detail: ProfileDetail | undefined,
  compile: CompileReport | undefined,
  validate: ValidationReport | undefined,
  advisoryPendingCount: number,
): TabStatuses {
  // Bug fix: previously `missing === 0` was treated as "done" even before compile.data had
  // loaded (default `??0` on `missing` made a still-loading profile look complete). Now we
  // require both compile AND detail to have arrived; while loading, tabs render "loading…" idle.
  const compileLoaded = compile !== undefined
  const detailLoaded = detail !== undefined
  const missing = compile?.missing.length ?? 0
  const totalFields = detail?.fields.length ?? 0
  const emptyDefaults = detail?.fields.filter((f) =>
    (f.required || !f.sourceExpression?.trim()) && !(f.defaultValue ?? '').length,
  ).length ?? 0
  const errors = validate?.validation.errors ?? null
  // Only PROFILE-scope suppressions count on the Sign-off tab pill. Pack-scope suppressions are
  // an administrator-level decision that applies to every profile on the pack — they don't
  // represent unfinished work on THIS return, so they don't need to attract attention here.
  const profileSuppressions = compile?.suppressions?.filter((s) => s.scope === 'profile').length ?? 0
  const signed = compile?.profile.signedOff ?? false
  const ready = compile?.signOffReady ?? false

  return {
    fields: {
      done: compileLoaded && detailLoaded && missing === 0 && totalFields > 0,
      // Empty label ('') during load — with `placeholderData: keepPreviousData` this only shows
      // on the very first page load before ANY compile/detail landed, and the empty pill is far
      // less noisy than the previous amber "loading…" that flashed on every mutation.
      label: !compileLoaded || !detailLoaded
        ? ''
        : missing === 0 && totalFields > 0
          ? `${totalFields} mapped`
          : `${missing} unmapped`,
      tone: !compileLoaded || !detailLoaded
        ? 'idle'
        : missing === 0 && totalFields > 0 ? 'ok' : 'warn',
    },
    defaults: {
      done: detailLoaded && emptyDefaults === 0,
      label: !detailLoaded ? '' : emptyDefaults === 0 ? 'all covered' : `${emptyDefaults} empty`,
      tone: !detailLoaded ? 'idle' : emptyDefaults === 0 ? 'ok' : 'warn',
    },
    validation: {
      done: errors === 0,
      label: errors === null ? 'not run' : errors === 0 ? 'clean' : `${errors.toLocaleString()} errors`,
      tone: errors === null ? 'idle' : errors === 0 ? 'ok' : 'error',
    },
    signoff: {
      done: signed,
      label: signed
        ? 'signed'
        : profileSuppressions > 0
          ? `${profileSuppressions} to attest`
          : ready ? 'ready' : 'blocked',
      // Profile-scope suppressions are amber (they need attestation at sign-off).
      // Pack-scope suppressions no longer amber-flag the tab — they're stable admin decisions,
      // not per-return work items.
      tone: signed ? 'ok' : profileSuppressions > 0 ? 'warn' : ready ? 'ok' : 'idle',
    },
    advisories: {
      done: advisoryPendingCount === 0,
      label: advisoryPendingCount === 0 ? '—' : `${advisoryPendingCount} pending`,
      tone: advisoryPendingCount === 0 ? 'idle' : 'warn',
    },
  }
}

const TAB_DEFS: Array<{ id: StatutoryTab; n?: number; label: string; icon?: LucideIcon; group: 'flow' | 'aux' }> = [
  { id: 'fields',     n: 1, label: 'Fields',      icon: ListChecks,   group: 'flow' },
  { id: 'defaults',   n: 2, label: 'Defaults',    icon: Sparkles,     group: 'flow' },
  { id: 'validation', n: 3, label: 'Validate',    icon: ShieldAlert,  group: 'flow' },
  { id: 'signoff',    n: 4, label: 'Sign-off',    icon: ShieldCheck,  group: 'flow' },
  { id: 'advisories',       label: 'Advisories',  icon: FileUp,       group: 'aux' },
]

function StatutoryTabsBar({
  active, onSelect, statuses,
}: {
  active: StatutoryTab
  onSelect: (t: StatutoryTab) => void
  statuses: TabStatuses
}) {
  return (
    <div className="border-b border-border overflow-x-auto -mx-6 px-6">
      <div role="tablist" className="inline-flex gap-1 min-w-full">
        {TAB_DEFS.map((t, i) => {
          const st = statuses[t.id]
          const isActive = active === t.id
          const prevGroup = i > 0 ? TAB_DEFS[i - 1].group : t.group
          const isFirstAux = t.group === 'aux' && prevGroup === 'flow'
          const toneClass =
            st.tone === 'ok' ? 'bg-[hsl(var(--success)/0.15)] text-[hsl(var(--success))]' :
            st.tone === 'warn' ? 'bg-[hsl(var(--warning)/0.15)] text-[hsl(var(--warning))]' :
            st.tone === 'error' ? 'bg-[hsl(var(--destructive)/0.15)] text-[hsl(var(--destructive))]' :
            'bg-surface-2 text-muted-foreground'
          return (
            <div key={t.id} className={isFirstAux ? 'ml-4 pl-4 border-l border-border' : ''}>
              <button
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => onSelect(t.id)}
                className={`group inline-flex items-center gap-2 px-4 py-3 text-sm font-medium
                  border-b-2 transition-colors -mb-px whitespace-nowrap
                  ${isActive
                    ? 'border-primary text-foreground'
                    : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'}`}
              >
                {t.n !== undefined && (
                  <span className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold
                    ${st.done ? 'bg-[hsl(var(--success))] text-white' : isActive ? 'bg-primary text-primary-foreground' : 'bg-surface-2 text-muted-foreground'}`}>
                    {st.done ? '✓' : t.n}
                  </span>
                )}
                {t.icon && t.n === undefined && <t.icon className="h-4 w-4" />}
                <span>{t.label}</span>
                {st.label && (
                  <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${toneClass}`}>
                    {st.label}
                  </span>
                )}
                <span className="sr-only">
                  {st.label}
                </span>
              </button>
            </div>
          )
        })}
      </div>
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
  const compile = useCompileProfile(selectedId)
  const generate = useGenerateProfile()
  const [generated, setGenerated] = useState<GenerateResult | null>(null)
  const [tab, setTab] = useState<StatutoryTab>('fields')

  // Bug fix (2026-09-17): the "Fix all" chip and per-row "Set default →" in the validation report
  // used to fire setHighlightedField, but the FieldDefaultsSection subscribes to that signal —
  // and it now lives on a DIFFERENT tab. So the highlight fired against nothing. Watch the
  // signal at the page level and switch to Defaults when it fires; the section then mounts and
  // its own hook picks up the highlight, scrolls, and focuses in the same render.
  const highlight = useHighlightedField()
  useEffect(() => {
    if (highlight) setTab('defaults')
  }, [highlight])

  // Pick the first profile once the list arrives so the screen is never empty for no reason.
  useEffect(() => {
    if (!selectedId && profiles.data && profiles.data.length > 0) setSelectedId(profiles.data[0].id)
  }, [profiles.data, selectedId])

  const selectProfile = (id: string) => {
    setSelectedId(id)
    setGenerated(null)
    setTab('fields')
  }

  const showValidation = validate.data && validate.data.profile.id === selectedId
  const showGenerated = generated && generated.profile.id === selectedId

  const statuses = computeTabStatuses(
    detail.data ?? undefined,
    compile.data ?? undefined,
    validate.data ?? undefined,
    0,   // TODO: wire real pending-advisory count if useful; 0 keeps the pill idle
  )

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

        {/* Tabs replace the old nine-stacked-sections firehose. Each tab is a step in the flow
           (fields → defaults → validate → sign-off) plus Advisories as a sibling admin action.
           Tab labels carry live status pills so progress is visible without scrolling. */}
        {selectedId ? (
          <>
            <div className="pt-1">
              <div className="flex items-baseline justify-between gap-3 pb-2">
                <div>
                  <h2 className="text-section-title">
                    {(() => {
                      // Prefer the profile row from the list (loaded first), so switching or
                      // refetching never flashes the title to "Loading…". Fall back to detail
                      // when the list hasn't landed yet (very rare — same page load).
                      const fromList = profiles.data?.find((p) => p.id === selectedId)
                      const name = detail.data ?? fromList
                      return name ? `${name.code} — ${name.academicYear}` : ' '
                    })()}
                  </h2>
                  <p className="text-helper">
                    {tab === 'fields'     && <>Target field ← source expression + transform + validation.</>}
                    {tab === 'defaults'   && <>What the return should send when a record's source column is empty.</>}
                    {tab === 'validation' && <>Every problem the return would ship with today — with a fix path per row.</>}
                    {tab === 'signoff'    && <>Attest that the mappings are complete. Signed-off profiles are locked until unsigned.</>}
                    {tab === 'advisories' && <>Ingest a published HESA advisory, review the diff, and accept it to make the change the active spec version.</>}
                  </p>
                </div>
                {tab === 'validation' && (
                  <div className="flex items-center gap-2">
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
                  </div>
                )}
                {tab === 'fields' && (
                  <div className="flex items-center gap-2">
                    {canConfigure && !detail.data?.signedOff && <AddFieldDialog profileId={selectedId} />}
                    {canConfigure && detail.data && <CloneDialog profile={detail.data} />}
                  </div>
                )}
              </div>
              <StatutoryTabsBar active={tab} onSelect={setTab} statuses={statuses} />
            </div>

            <div className="pt-4">
              {tab === 'fields' && (
                detail.isLoading ? <Skeleton className="h-24 w-full" /> :
                detail.isError ? <p className="text-sm text-[hsl(var(--destructive))]">{(detail.error as ApiError)?.message}</p> :
                detail.data && detail.data.fields.length > 0 ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>#</TableHead>
                        <TableHead>Target field</TableHead>
                        <TableHead className="whitespace-nowrap">
                          Source expression <JargonTip term="source expression" />
                        </TableHead>
                        <TableHead className="whitespace-nowrap">
                          Keyed on record <JargonTip term="keyed on record" />
                        </TableHead>
                        <TableHead>
                          Transform <JargonTip term="transform" />
                        </TableHead>
                        <TableHead>Required</TableHead>
                        <TableHead className="whitespace-nowrap">
                          Allowed values <JargonTip term="allowed values" />
                        </TableHead>
                        <TableHead>Default</TableHead>
                        {canConfigure && !detail.data.signedOff && <TableHead className="text-right">Map</TableHead>}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {detail.data.fields.map((f) => (
                        <TableRow key={f.id}>
                          <TableCell className="num text-muted-foreground">{f.position}</TableCell>
                          <TableCell className="font-mono text-xs font-medium">{f.targetField}</TableCell>
                          <TableCell className="font-mono text-xs">
                            {/* The source expression IS the affordance to change the mapping — click it
                               to open the editor. When there's no admin permission or the profile is
                               signed off, render as static text (no dialog attached). */}
                            {canConfigure && !detail.data!.signedOff ? (
                              <EditFieldDialog
                                profileId={selectedId}
                                field={f}
                                trigger={
                                  <button
                                    type="button"
                                    className={`text-left text-primary hover:underline focus:underline focus:outline-none ${!f.sourceExpression ? 'italic text-muted-foreground' : ''}`}
                                    title="Edit this mapping"
                                  >
                                    {f.sourceExpression || 'unmapped — set source'}
                                  </button>
                                }
                              />
                            ) : (
                              <span className="text-muted-foreground">{f.sourceExpression || <span className="italic">unmapped</span>}</span>
                            )}
                          </TableCell>
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
                )
              )}

              {tab === 'defaults' && (
                detail.data && detail.data.fields.length > 0 ? (
                  detail.data.signedOff || !canConfigure ? (
                    <p className="text-helper">Defaults are read-only on a signed-off profile.</p>
                  ) : (
                    <FieldDefaultsSection
                      profileId={selectedId}
                      fields={detail.data.fields}
                      onGoToFields={() => setTab('fields')}
                      validationIssues={validate.data?.validation.issues ?? null}
                    />
                  )
                ) : (
                  <p className="text-helper">Map at least one field first — defaults are per field.</p>
                )
              )}

              {tab === 'validation' && (
                <div className="space-y-4">
                  {showValidation && validate.data ? (
                    <div>
                      <p className="text-label mb-2 inline-flex items-center gap-1.5">
                        Validation report <JargonTip term="validation report" />
                      </p>
                      <ValidationReportView
                        result={validate.data.validation}
                        rowCount={validate.data.rowCount}
                        profileId={selectedId}
                      />
                    </div>
                  ) : (
                    <p className="text-helper">Not yet checked. Click Validate above to see what would ship today.</p>
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
                        profileId={selectedId}
                      />
                    </div>
                  )}
                </div>
              )}

              {tab === 'signoff' && (
                <SignOffCard profileId={selectedId} canSignOff={canSignOff} />
              )}

              {tab === 'advisories' && (
                <AdvisoriesPanel canConfigure={canConfigure} canSignOff={canSignOff} />
              )}
            </div>
          </>
        ) : (
          <PageSection
            icon={FileUp}
            title="Statutory advisories"
            accent="accent"
            description="Ingest a published HESA advisory, review the diff against the current pack, and accept it to make the change the active spec version — ingest → recommend → accept, human-gated."
          >
            <AdvisoriesPanel canConfigure={canConfigure} canSignOff={canSignOff} />
          </PageSection>
        )}
      </div>
    </>
  )
}
