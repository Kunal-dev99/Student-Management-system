'use client'

import { useMemo, useState } from 'react'
import { Award, BookOpen, ChevronDown, ChevronRight, GraduationCap, Plus, Settings2 } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { useCan } from '@/shared/auth/Can'
import {
  useAddAssessment, useComputeAward, useCreateModule, useEnrolModule, useProgrammeModules,
  useRecordResult, useSetEnrolmentStatus, useTaughtRecord, useUpsertDissertation,
  type AssessmentType, type ClassificationBand, type Enrolment,
} from './api'

const BAND_VARIANT: Record<ClassificationBand, 'success' | 'info' | 'secondary' | 'destructive'> = {
  distinction: 'success', merit: 'info', pass: 'secondary', fail: 'destructive',
}
const STATUS_VARIANT: Record<Enrolment['status'], 'secondary' | 'success' | 'warning' | 'destructive'> = {
  enrolled: 'secondary', completed: 'success', withdrawn: 'warning', failed: 'destructive',
}
const ASSESSMENT_TYPES: AssessmentType[] = ['essay', 'exam', 'coursework', 'presentation', 'dissertation']

function currentAcademicYear(): string {
  const now = new Date()
  // UK academic year starts in September.
  const startYear = now.getMonth() >= 8 ? now.getFullYear() : now.getFullYear() - 1
  return `${startYear}/${String((startYear + 1) % 100).padStart(2, '0')}`
}

export function TaughtRecordPanel({ studentId, programmeId }: { studentId: string; programmeId: string | null }) {
  const { toast } = useToast()
  const canChange = useCan('taught.change')
  const canConfigure = useCan('admin.configure')
  const { data, isLoading } = useTaughtRecord(studentId)
  const modules = useProgrammeModules(programmeId)

  const enrol = useEnrolModule(studentId)
  const recordResult = useRecordResult(studentId)
  const setStatus = useSetEnrolmentStatus(studentId)
  const upsertDiss = useUpsertDissertation(studentId)
  const computeAward = useComputeAward(studentId)

  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [enrolModuleId, setEnrolModuleId] = useState('')
  const [academicYear, setAcademicYear] = useState(currentAcademicYear())
  const [resultDraft, setResultDraft] = useState<Record<string, { assessmentId: string; mark: string; isResit: boolean }>>({})
  const [dissTitle, setDissTitle] = useState('')
  const [dissMark, setDissMark] = useState('')
  const [manageOpen, setManageOpen] = useState(false)

  const moduleById = useMemo(
    () => new Map((modules.data ?? []).map((m) => [m.id, m])),
    [modules.data],
  )

  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as Error).message, variant: 'destructive' })
  const num = (v: string | null) => (v == null ? '—' : Number(v).toFixed(1))

  return (
    <PageSection icon={GraduationCap} title="Taught record — modules, assessments & award" accent="primary">
      {isLoading ? <Skeleton className="h-28 w-full" /> : (
        <div className="space-y-5">
          {/* Award summary */}
          <div className="flex flex-wrap items-center gap-4 rounded-md border border-border/60 bg-surface-2/30 p-3">
            <div className="flex items-center gap-2">
              <Award className="h-4 w-4 text-primary" />
              <span className="text-label">Classification</span>
              {data?.award?.classification
                ? <Badge variant={BAND_VARIANT[data.award.classification]}>{data.award.classification}</Badge>
                : <span className="text-helper">not yet computed</span>}
            </div>
            {data?.award?.finalMark && <span className="text-sm">Final mark <span className="num font-medium">{num(data.award.finalMark)}</span></span>}
            <span className="text-helper">
              Credits {data?.creditsEnrolled ?? 0}{data?.totalCreditsTarget ? ` / ${data.totalCreditsTarget}` : ''} enrolled
              {data?.award?.creditsAchieved != null && ` · ${data.award.creditsAchieved} achieved`}
            </span>
            {canChange && (
              <Button size="sm" variant="secondary" className="ml-auto" disabled={computeAward.isPending}
                onClick={async () => { try { const a = await computeAward.mutateAsync(); toast({ title: `Classification: ${a.classification ?? '—'} (${num(a.finalMark)})` }) } catch (e) { err(e) } }}>
                Compute classification
              </Button>
            )}
          </div>

          {/* Enrolments */}
          <div className="space-y-2">
            <p className="text-label flex items-center gap-1.5"><BookOpen className="h-3.5 w-3.5" /> Module enrolments</p>
            {data && data.enrolments.length > 0 ? data.enrolments.map((e) => {
              const isOpen = !!expanded[e.id]
              const mod = moduleById.get(e.moduleId)
              const draft = resultDraft[e.id] ?? { assessmentId: '', mark: '', isResit: false }
              return (
                <div key={e.id} className="border border-border rounded-md p-3">
                  <div className="flex items-center justify-between">
                    <button type="button" className="flex items-center gap-2 hover:text-primary"
                      onClick={() => setExpanded((s) => ({ ...s, [e.id]: !s[e.id] }))}>
                      {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                      <span className="text-sm font-medium">{e.moduleCode} — {e.moduleTitle}</span>
                      <Badge variant={STATUS_VARIANT[e.status]}>{e.status}</Badge>
                      <span className="text-helper num">{e.credits ?? 0} cr · {e.academicYear}</span>
                    </button>
                    <span className="text-sm">Module mark <span className="num font-medium">{num(e.moduleMark)}</span></span>
                  </div>

                  {isOpen && (
                    <div className="mt-3 space-y-2 pl-6">
                      {/* Results table */}
                      {e.results.length > 0 ? (
                        <div className="space-y-1">
                          {e.results.map((r) => {
                            const a = mod?.assessments.find((x) => x.id === r.assessmentId)
                            return (
                              <div key={r.id} className="flex items-center gap-2 text-sm">
                                <span className="min-w-[160px]">{a ? a.title : 'assessment'}</span>
                                {a && <span className="text-helper">{a.assessmentType} · {Number(a.weightPct).toFixed(0)}%</span>}
                                <span className="num font-medium">{num(r.mark)}</span>
                                {r.isResit && <Badge variant="outline">resit</Badge>}
                              </div>
                            )
                          })}
                        </div>
                      ) : <p className="text-helper">No results recorded yet.</p>}

                      {/* Record result */}
                      {canChange && mod && mod.assessments.length > 0 && (
                        <div className="flex flex-wrap items-center gap-2 pt-1">
                          <Select value={draft.assessmentId}
                            onValueChange={(v) => setResultDraft((s) => ({ ...s, [e.id]: { ...draft, assessmentId: v } }))}>
                            <SelectTrigger className="h-8 w-56"><SelectValue placeholder="Assessment…" /></SelectTrigger>
                            <SelectContent>
                              {mod.assessments.map((a) => <SelectItem key={a.id} value={a.id}>{a.title}</SelectItem>)}
                            </SelectContent>
                          </Select>
                          <Input className="h-8 w-24" type="number" placeholder="Mark" value={draft.mark}
                            onChange={(ev) => setResultDraft((s) => ({ ...s, [e.id]: { ...draft, mark: ev.target.value } }))} />
                          <label className="flex items-center gap-1 text-helper">
                            <input type="checkbox" checked={draft.isResit}
                              onChange={(ev) => setResultDraft((s) => ({ ...s, [e.id]: { ...draft, isResit: ev.target.checked } }))} />
                            resit
                          </label>
                          <Button size="sm" disabled={!draft.assessmentId || !draft.mark || recordResult.isPending}
                            onClick={async () => {
                              try {
                                await recordResult.mutateAsync({ enrolmentId: e.id, body: { assessmentId: draft.assessmentId, mark: draft.mark, isResit: draft.isResit } })
                                setResultDraft((s) => ({ ...s, [e.id]: { assessmentId: '', mark: '', isResit: false } }))
                                toast({ title: 'Result recorded' })
                              } catch (er) { err(er) }
                            }}>Record</Button>
                        </div>
                      )}

                      {canChange && (
                        <div className="flex items-center gap-2 pt-1">
                          <span className="text-helper">Set status:</span>
                          {(['enrolled', 'completed', 'withdrawn', 'failed'] as const).map((st) => (
                            <Button key={st} size="sm" variant={e.status === st ? 'secondary' : 'ghost'} className="h-7"
                              disabled={setStatus.isPending}
                              onClick={async () => { try { await setStatus.mutateAsync({ enrolmentId: e.id, status: st }); toast({ title: `Marked ${st}` }) } catch (er) { err(er) } }}>
                              {st}
                            </Button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            }) : <p className="text-helper">No module enrolments yet.</p>}

            {/* Enrol on a module */}
            {canChange && (
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <Select value={enrolModuleId} onValueChange={setEnrolModuleId}>
                  <SelectTrigger className="h-8 w-64"><SelectValue placeholder="Enrol on module…" /></SelectTrigger>
                  <SelectContent>
                    {(modules.data ?? []).map((m) => <SelectItem key={m.id} value={m.id}>{m.code} — {m.title}</SelectItem>)}
                  </SelectContent>
                </Select>
                <Input className="h-8 w-28" placeholder="2026/27" value={academicYear} onChange={(e) => setAcademicYear(e.target.value)} />
                <Button size="sm" disabled={!enrolModuleId || !academicYear || enrol.isPending}
                  onClick={async () => {
                    try { await enrol.mutateAsync({ moduleId: enrolModuleId, academicYear }); setEnrolModuleId(''); toast({ title: 'Enrolled' }) } catch (e) { err(e) }
                  }}>
                  <Plus className="h-3.5 w-3.5 mr-1" /> Enrol
                </Button>
                {(modules.data ?? []).length === 0 && <span className="text-helper">No modules defined on this programme yet.</span>}
              </div>
            )}
          </div>

          {/* Dissertation */}
          <div className="space-y-2 border-t border-border/60 pt-4">
            <p className="text-label">Dissertation</p>
            {data?.dissertation ? (
              <div className="flex flex-wrap items-center gap-3 text-sm">
                <span className="font-medium">{data.dissertation.title ?? 'Untitled'}</span>
                {data.dissertation.supervisorName && <span className="text-helper">supervised by {data.dissertation.supervisorName}</span>}
                <span>mark <span className="num font-medium">{num(data.dissertation.mark)}</span></span>
              </div>
            ) : <p className="text-helper">No dissertation recorded.</p>}
            {canChange && (
              <div className="flex flex-wrap items-center gap-2">
                <Input className="h-8 w-64" placeholder="Dissertation title"
                  value={dissTitle || data?.dissertation?.title || ''} onChange={(e) => setDissTitle(e.target.value)} />
                <Input className="h-8 w-24" type="number" placeholder="Mark" value={dissMark} onChange={(e) => setDissMark(e.target.value)} />
                <Button size="sm" variant="secondary" disabled={upsertDiss.isPending}
                  onClick={async () => {
                    try {
                      await upsertDiss.mutateAsync({
                        title: (dissTitle || data?.dissertation?.title) ?? undefined,
                        mark: dissMark || undefined,
                      })
                      setDissMark('')
                      toast({ title: 'Dissertation saved' })
                    } catch (e) { err(e) }
                  }}>Save dissertation</Button>
              </div>
            )}
          </div>

          {/* Manage modules (admin.configure) */}
          {canConfigure && programmeId && (
            <div className="border-t border-border/60 pt-4">
              <button type="button" className="text-label flex items-center gap-1.5 hover:text-primary"
                onClick={() => setManageOpen((v) => !v)}>
                {manageOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                <Settings2 className="h-3.5 w-3.5" /> Manage programme modules
              </button>
              {manageOpen && <ModuleManager programmeId={programmeId} />}
            </div>
          )}
        </div>
      )}
    </PageSection>
  )
}

function ModuleManager({ programmeId }: { programmeId: string }) {
  const { toast } = useToast()
  const modules = useProgrammeModules(programmeId)
  const createModule = useCreateModule(programmeId)
  const addAssessment = useAddAssessment(programmeId)
  const [mod, setMod] = useState({ code: '', title: '', credits: '' })
  const [asmt, setAsmt] = useState<Record<string, { title: string; assessmentType: AssessmentType; weightPct: string }>>({})
  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as Error).message, variant: 'destructive' })

  return (
    <div className="mt-2 space-y-3">
      {(modules.data ?? []).map((m) => {
        const a = asmt[m.id] ?? { title: '', assessmentType: 'essay' as AssessmentType, weightPct: '' }
        return (
          <div key={m.id} className="rounded-md border border-border/60 p-2 text-sm">
            <div className="flex items-center gap-2">
              <span className="font-medium">{m.code} — {m.title}</span>
              <span className="text-helper num">{m.credits} cr</span>
            </div>
            <div className="mt-1 pl-2 text-helper">
              {m.assessments.length > 0
                ? m.assessments.map((x) => `${x.title} (${x.assessmentType}, ${Number(x.weightPct).toFixed(0)}%)`).join(' · ')
                : 'No assessments yet.'}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <Input className="h-7 w-40" placeholder="Assessment title" value={a.title}
                onChange={(e) => setAsmt((s) => ({ ...s, [m.id]: { ...a, title: e.target.value } }))} />
              <Select value={a.assessmentType} onValueChange={(v) => setAsmt((s) => ({ ...s, [m.id]: { ...a, assessmentType: v as AssessmentType } }))}>
                <SelectTrigger className="h-7 w-32"><SelectValue /></SelectTrigger>
                <SelectContent>{ASSESSMENT_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
              </Select>
              <Input className="h-7 w-20" type="number" placeholder="weight%" value={a.weightPct}
                onChange={(e) => setAsmt((s) => ({ ...s, [m.id]: { ...a, weightPct: e.target.value } }))} />
              <Button size="sm" className="h-7" disabled={!a.title || addAssessment.isPending}
                onClick={async () => {
                  try {
                    await addAssessment.mutateAsync({ moduleId: m.id, body: { title: a.title, assessmentType: a.assessmentType, weightPct: a.weightPct || undefined } })
                    setAsmt((s) => ({ ...s, [m.id]: { title: '', assessmentType: 'essay', weightPct: '' } }))
                    toast({ title: 'Assessment added' })
                  } catch (e) { err(e) }
                }}>Add assessment</Button>
            </div>
          </div>
        )
      })}
      <div className="flex flex-wrap items-center gap-2">
        <Input className="h-8 w-28" placeholder="Code" value={mod.code} onChange={(e) => setMod((s) => ({ ...s, code: e.target.value }))} />
        <Input className="h-8 w-56" placeholder="Module title" value={mod.title} onChange={(e) => setMod((s) => ({ ...s, title: e.target.value }))} />
        <Input className="h-8 w-24" type="number" placeholder="Credits" value={mod.credits} onChange={(e) => setMod((s) => ({ ...s, credits: e.target.value }))} />
        <Button size="sm" disabled={!mod.code || !mod.title || createModule.isPending}
          onClick={async () => {
            try {
              await createModule.mutateAsync({ code: mod.code, title: mod.title, credits: mod.credits ? Number(mod.credits) : 0 })
              setMod({ code: '', title: '', credits: '' })
              toast({ title: 'Module created' })
            } catch (e) { err(e) }
          }}>
          <Plus className="h-3.5 w-3.5 mr-1" /> Add module
        </Button>
      </div>
    </div>
  )
}
