'use client'

/**
 * Statutory returns (Phase 6.6).
 *
 * The whole point of this screen: a statutory return is **configuration, not code**.
 */

import { useEffect, useState } from 'react'
import {
  CheckCircle2, CopyPlus, Download, FileSpreadsheet, ListChecks, Play, Plus,
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
import {
  useAddField, useCloneProfile, useCreateProfile, useGenerateProfile, useProfile, useProfiles,
  useTransforms, useValidateProfile,
  type GenerateResult, type ReportProfile, type ValidationResult,
} from '@/features/statutory/api'

function err(toast: ReturnType<typeof useToast>['toast'], title: string) {
  return (e: unknown) =>
    toast({ title, description: (e as ApiError).message, variant: 'destructive' })
}

// ---------------------------------------------------------------- dialogs

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

function ValidationReportView({ result, rowCount }: { result: ValidationResult; rowCount: number }) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={result.errors > 0 ? 'destructive' : 'success'}>
          {result.errors} error{result.errors === 1 ? '' : 's'}
        </Badge>
        <span className="text-helper num">{rowCount} row{rowCount === 1 ? '' : 's'} would be produced</span>
      </div>
      {result.issues.length === 0 ? (
        <p className="text-sm inline-flex items-center gap-2 text-[hsl(var(--success))]">
          <CheckCircle2 className="h-4 w-4" /> No validation errors.
        </p>
      ) : (
        <div className="card-elevated overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Student ref</TableHead>
                <TableHead>Field</TableHead>
                <TableHead>Message</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {result.issues.map((i, idx) => (
                <TableRow key={`${i.studentRef}-${i.field}-${idx}`}>
                  <TableCell className="font-mono text-xs whitespace-nowrap">{i.studentRef}</TableCell>
                  <TableCell className="font-mono text-xs whitespace-nowrap">{i.field}</TableCell>
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
      )}
    </div>
  )
}

// ---------------------------------------------------------------- page

export default function StatutoryPage() {
  const { toast } = useToast()
  const { hasPermission } = useAuth()
  const canConfigure = hasPermission('admin.configure')

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
        actions={canConfigure ? <NewProfileDialog /> : undefined}
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

        {selectedId && (
          <PageSection
            icon={ListChecks}
            title={detail.data ? `${detail.data.code} — ${detail.data.academicYear}` : 'Field mappings'}
            accent="accent"
            description="Target field ← source expression + transform + validation."
            actions={
              <div className="flex flex-wrap items-center gap-2">
                {canConfigure && <AddFieldDialog profileId={selectedId} />}
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
                {detail.data && <CloneDialog profile={detail.data} />}
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
                        <TableHead>Transform</TableHead>
                        <TableHead>Required</TableHead>
                        <TableHead>Allowed values</TableHead>
                        <TableHead>Default</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {detail.data.fields.map((f) => (
                        <TableRow key={f.id}>
                          <TableCell className="num text-muted-foreground">{f.position}</TableCell>
                          <TableCell className="font-mono text-xs font-medium">{f.targetField}</TableCell>
                          <TableCell className="font-mono text-xs text-muted-foreground">{f.sourceExpression}</TableCell>
                          <TableCell className="text-sm">{f.transform ?? '—'}</TableCell>
                          <TableCell>
                            {f.required ? <Badge variant="warning">required</Badge> : <span className="text-muted-foreground text-sm">—</span>}
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {f.allowedValues && f.allowedValues.length > 0 ? f.allowedValues.join(', ') : '—'}
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">{f.defaultValue ?? '—'}</TableCell>
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
