'use client'

/**
 * ICR G3 — Programmes admin (Settings tab).
 *
 * Create and edit programmes and their milestone templates. The template is per programme and
 * auto-instantiates for every student on it; editing an offset here re-dates non-overridden
 * milestones on the next "Regenerate schedule" for a student.
 */
import { useEffect, useState } from 'react'
import { GraduationCap, Plus, Trash2 } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useToast } from '@/components/ui/use-toast'
import {
  useProgrammesAdmin, useCreateProgramme, useUpdateProgramme,
  useDefinitions, useCreateDefinition, useUpdateDefinition, useDeleteDefinition,
  type ProgrammeDetail, type ProgrammeType, type GradingPolicy,
} from '@/features/programmes/api'
import { ProgrammeModulesEditor } from '@/features/taught/ProgrammeModulesEditor'

/** Labels, range and default for each grading-policy field (mirrors DEFAULT_GRADING_POLICY). */
const POLICY_FIELDS: { key: keyof GradingPolicy; label: string; fallback: number; min: number; max: number; unit: string }[] = [
  { key: 'passMark', label: 'Module pass mark', fallback: 50, min: 0, max: 100, unit: '%' },
  { key: 'resitCap', label: 'Resit cap', fallback: 50, min: 0, max: 100, unit: '%' },
  { key: 'condonementCredits', label: 'Max condonement credits', fallback: 30, min: 0, max: 180, unit: ' cr' },
  { key: 'distinctionMark', label: 'Distinction from', fallback: 70, min: 0, max: 100, unit: '%' },
  { key: 'meritMark', label: 'Merit from', fallback: 60, min: 0, max: 100, unit: '%' },
  { key: 'passMarkAward', label: 'Award pass from', fallback: 50, min: 0, max: 100, unit: '%' },
]

/**
 * A labelled range slider that commits on release. Shows the live value; when the value equals the
 * platform default it is marked "default" and (when `resettable`) offers a reset that clears the
 * per-programme override. No dependency — a styled native range input.
 */
function RangeField({ label, value, fallback, min, max, unit = '', resettable = true, onCommit }: {
  label: string
  value: number | null | undefined
  fallback: number
  min: number
  max: number
  unit?: string
  resettable?: boolean
  onCommit: (v: number | null) => void
}) {
  const isSet = value != null
  const initial = isSet ? (value as number) : fallback
  // Uncontrolled: the browser owns the slider during a drag; we mirror its live value into
  // `display` on every `input` event (fires continuously while dragging). `key={initial}` remounts
  // the input when the committed value changes (after save/refresh) so the thumb re-seats.
  const [display, setDisplay] = useState<number>(initial)
  useEffect(() => { setDisplay(initial) }, [initial])

  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <Label className="text-xs">{label}</Label>
        <span className="num text-sm font-semibold tabular-nums">
          {display}{unit}
          {!isSet && display === fallback && <span className="text-helper text-[10px] font-normal ml-1">default</span>}
        </span>
      </div>
      <input
        key={initial}
        type="range" min={min} max={max} defaultValue={initial}
        onInput={(e) => setDisplay(Number((e.target as HTMLInputElement).value))}
        onChange={(e) => setDisplay(Number(e.target.value))}
        onPointerUp={(e) => onCommit(Number((e.target as HTMLInputElement).value))}
        onKeyUp={(e) => onCommit(Number((e.target as HTMLInputElement).value))}
        className="w-full cursor-pointer accent-[hsl(var(--primary))]"
      />
      {resettable && isSet && (
        <button type="button" className="text-[10px] text-muted-foreground hover:text-foreground underline"
          onClick={() => onCommit(null)}>reset to default</button>
      )}
    </div>
  )
}

function num(v: string): number | null {
  const n = parseInt(v, 10)
  return Number.isFinite(n) ? n : null
}

export function ProgrammesTab() {
  const { toast } = useToast()
  const { data: programmes, isLoading } = useProgrammesAdmin()
  const create = useCreateProgramme()
  const update = useUpdateProgramme()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [draft, setDraft] = useState({ name: '', code: '', programmeType: 'research' as ProgrammeType, durationMonths: '', supervisionMeetingIntervalDays: '' })

  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as Error).message, variant: 'destructive' })
  const selected = programmes?.find((p) => p.id === selectedId) ?? null

  const saveNew = async () => {
    if (!draft.name.trim() || !draft.code.trim()) return
    try {
      const p = await create.mutateAsync({
        name: draft.name.trim(), code: draft.code.trim().toUpperCase(),
        programmeType: draft.programmeType,
        durationMonths: num(draft.durationMonths),
        supervisionMeetingIntervalDays: num(draft.supervisionMeetingIntervalDays),
      })
      toast({ title: 'Programme created', description: `${p.name} (${p.code})` })
      setDraft({ name: '', code: '', programmeType: 'research', durationMonths: '', supervisionMeetingIntervalDays: '' })
      setCreating(false)
      setSelectedId(p.id)
    } catch (e) { err(e) }
  }

  const patch = async (id: string, patch: Record<string, unknown>) => {
    try { await update.mutateAsync({ id, patch }); toast({ title: 'Programme updated' }) } catch (e) { err(e) }
  }

  return (
    <PageSection icon={GraduationCap} title="Programmes & milestone templates" accent="primary">
      <div className="mb-3">
        <Button size="sm" variant="outline" onClick={() => setCreating((v) => !v)}>
          <Plus className="mr-1.5 h-3.5 w-3.5" />New programme
        </Button>
      </div>

      {creating && (
        <Card className="card-elevated mb-4">
          <CardContent className="grid gap-3 py-4 md:grid-cols-5">
            <div className="space-y-1.5 md:col-span-2">
              <Label>Name</Label>
              <Input value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label>Code</Label>
              <Input value={draft.code} onChange={(e) => setDraft((d) => ({ ...d, code: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label>Type</Label>
              <Select value={draft.programmeType} onValueChange={(v) => setDraft((d) => ({ ...d, programmeType: v as ProgrammeType }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="research">Research</SelectItem>
                  <SelectItem value="taught">Taught</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Duration (months)</Label>
              <Input type="number" value={draft.durationMonths} onChange={(e) => setDraft((d) => ({ ...d, durationMonths: e.target.value }))} />
            </div>
            <div className="md:col-span-5">
              <Button size="sm" disabled={!draft.name.trim() || !draft.code.trim() || create.isPending} onClick={saveNew}>
                Create programme
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {isLoading ? <Skeleton className="h-24 w-full" /> : (
        <div className="grid gap-4 lg:grid-cols-[minmax(260px,1fr)_2fr]">
          <div className="card-elevated overflow-hidden self-start">
            <Table>
              <TableHeader>
                <TableRow><TableHead>Name</TableHead><TableHead>Code</TableHead><TableHead>Type</TableHead></TableRow>
              </TableHeader>
              <TableBody>
                {programmes?.map((p) => (
                  <TableRow key={p.id} className={`cursor-pointer ${p.id === selectedId ? 'bg-surface-2' : ''}`}
                    onClick={() => setSelectedId(p.id)}>
                    <TableCell className="font-medium">{p.name}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{p.code}</TableCell>
                    <TableCell><Badge variant={p.programmeType === 'taught' ? 'info' : 'secondary'}>{p.programmeType}</Badge></TableCell>
                  </TableRow>
                ))}
                {programmes && programmes.length === 0 && (
                  <TableRow><TableCell colSpan={3} className="text-helper text-center py-6">No programmes yet.</TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </div>

          {selected ? (
            <ProgrammeEditor key={selected.id} programme={selected} onPatch={patch} />
          ) : (
            <div className="text-helper self-center px-4">Select a programme to edit its details and milestone template.</div>
          )}
        </div>
      )}
    </PageSection>
  )
}

function ProgrammeEditor({ programme, onPatch }: {
  programme: ProgrammeDetail
  onPatch: (id: string, patch: Record<string, unknown>) => Promise<void>
}) {
  const { toast } = useToast()
  const { data: defs, isLoading } = useDefinitions(programme.id)
  const createDef = useCreateDefinition(programme.id)
  const updateDef = useUpdateDefinition(programme.id)
  const deleteDef = useDeleteDefinition(programme.id)
  const [newDef, setNewDef] = useState({ name: '', dueOffsetDays: '' })
  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as Error).message, variant: 'destructive' })

  const addDef = async () => {
    const off = parseInt(newDef.dueOffsetDays, 10)
    if (!newDef.name.trim() || !Number.isFinite(off)) return
    try {
      await createDef.mutateAsync({ name: newDef.name.trim(), dueOffsetDays: off })
      setNewDef({ name: '', dueOffsetDays: '' })
      toast({ title: 'Milestone added to template' })
    } catch (e) { err(e) }
  }

  return (
    <div className="space-y-5">
      <div className="card-elevated p-4 space-y-4">
        <div className="space-y-1.5">
          <Label>Name</Label>
          <Input defaultValue={programme.name}
            onBlur={(e) => { if (e.target.value.trim() && e.target.value !== programme.name) onPatch(programme.id, { name: e.target.value.trim() }) }} />
        </div>
        <div className="grid gap-6 sm:grid-cols-2">
          <RangeField label="Expected duration (months)"
            value={programme.durationMonths} fallback={36} min={6} max={72} unit=" mo" resettable={false}
            onCommit={(v) => onPatch(programme.id, { durationMonths: v })} />
          <RangeField label="Supervision meeting interval (days)"
            value={programme.supervisionMeetingIntervalDays} fallback={90} min={7} max={365} unit=" d"
            onCommit={(v) => onPatch(programme.id, { supervisionMeetingIntervalDays: v })} />
        </div>
      </div>

      {programme.programmeType === 'taught' && (
        <>
          <ProgrammeModulesEditor programmeId={programme.id} />
          <GradingPolicyEditor programme={programme} onPatch={onPatch} />
        </>
      )}

      <div>
        <h4 className="text-sm font-medium mb-2">Milestone template</h4>
        <div className="card-elevated overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow><TableHead>Milestone</TableHead><TableHead className="w-40">Due (days from start)</TableHead><TableHead className="w-12" /></TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && <TableRow><TableCell colSpan={3}><Skeleton className="h-5 w-full" /></TableCell></TableRow>}
              {defs?.map((d) => (
                <TableRow key={d.id}>
                  <TableCell>
                    <Input className="h-8" defaultValue={d.name}
                      onBlur={(e) => { if (e.target.value.trim() && e.target.value !== d.name) updateDef.mutate({ id: d.id, patch: { name: e.target.value.trim() } }) }} />
                  </TableCell>
                  <TableCell>
                    <Input className="h-8 w-32" type="number" defaultValue={d.dueOffsetDays}
                      onBlur={(e) => { const v = parseInt(e.target.value, 10); if (Number.isFinite(v) && v !== d.dueOffsetDays) updateDef.mutate({ id: d.id, patch: { dueOffsetDays: v } }) }} />
                  </TableCell>
                  <TableCell>
                    <Button size="icon" variant="ghost" className="h-7 w-7"
                      aria-label={`Delete ${d.name}`}
                      onClick={async () => { try { await deleteDef.mutateAsync(d.id); toast({ title: 'Milestone removed' }) } catch (e) { err(e) } }}>
                      <Trash2 className="h-3.5 w-3.5 text-[hsl(var(--destructive))]" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {defs && defs.length === 0 && !isLoading && (
                <TableRow><TableCell colSpan={3} className="text-helper text-center py-4">No milestones in this template yet.</TableCell></TableRow>
              )}
              <TableRow>
                <TableCell>
                  <Input className="h-8" placeholder="New milestone name" value={newDef.name}
                    onChange={(e) => setNewDef((s) => ({ ...s, name: e.target.value }))} />
                </TableCell>
                <TableCell>
                  <Input className="h-8 w-32" type="number" placeholder="e.g. 270" value={newDef.dueOffsetDays}
                    onChange={(e) => setNewDef((s) => ({ ...s, dueOffsetDays: e.target.value }))} />
                </TableCell>
                <TableCell>
                  <Button size="icon" variant="ghost" className="h-7 w-7" aria-label="Add milestone" disabled={createDef.isPending} onClick={addDef}>
                    <Plus className="h-4 w-4" />
                  </Button>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
        <p className="text-helper mt-2">
          Milestones are ordered by their day offset from the student&apos;s start date. Editing an
          offset re-dates non-overridden milestones the next time a student&apos;s schedule is regenerated.
        </p>
      </div>
    </div>
  )
}

/**
 * Per-programme grading policy — the classification bands, pass mark, resit cap and condonement
 * limit that the exam board applies. Blank fields fall back to the platform default (shown as the
 * placeholder). Saved as a partial JSON override on the programme; only the fields set here differ.
 */
function GradingPolicyEditor({ programme, onPatch }: {
  programme: ProgrammeDetail
  onPatch: (id: string, patch: Record<string, unknown>) => Promise<void>
}) {
  const policy = programme.gradingPolicy ?? {}

  const save = (key: keyof GradingPolicy, val: number | null) => {
    const next: GradingPolicy = { ...policy }
    if (val === null) delete next[key]
    else next[key] = val
    if ((policy[key] ?? null) === (val ?? null)) return   // no change → skip the round-trip
    onPatch(programme.id, { gradingPolicy: next })
  }

  return (
    <div>
      <h4 className="text-sm font-medium mb-2">Grading policy</h4>
      <div className="card-elevated grid gap-x-6 gap-y-5 p-4 sm:grid-cols-2 lg:grid-cols-3">
        {POLICY_FIELDS.map((f) => (
          <RangeField key={f.key} label={f.label}
            value={policy[f.key]} fallback={f.fallback} min={f.min} max={f.max} unit={f.unit}
            onCommit={(v) => save(f.key, v)} />
        ))}
      </div>
      <p className="text-helper mt-2">
        Each value defaults to the platform standard until you move its slider; reset returns it to
        the default. These drive module pass/fail, capped resits, board condonement and the final
        classification bands for this programme.
      </p>
    </div>
  )
}
