'use client'

import { useMemo, useState } from 'react'
import { Award, BookOpen, ChevronDown, ChevronRight, GraduationCap, Plus, RotateCcw, Settings2, Sparkles } from 'lucide-react'
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
  useAddAssessment, useComputeAward, useCondoneModule, useCreateModule, useEnrolModule,
  useProgrammeModules, useRecordResult, useSetEnrolmentStatus, useTaughtBoardSummary, useTaughtRecord,
  useUpsertDissertation,
  type AssessmentType, type ClassificationBand, type Enrolment, type ModuleOutcome,
} from './api'

const BAND_VARIANT: Record<ClassificationBand, 'success' | 'info' | 'secondary' | 'destructive'> = {
  distinction: 'success', merit: 'info', pass: 'secondary', fail: 'destructive',
}
const STATUS_VARIANT: Record<Enrolment['status'], 'secondary' | 'success' | 'warning' | 'destructive'> = {
  enrolled: 'secondary', completed: 'success', withdrawn: 'warning', failed: 'destructive',
}
const OUTCOME_VARIANT: Record<ModuleOutcome, 'secondary' | 'success' | 'info' | 'destructive'> = {
  pending: 'secondary', passed: 'success', condoned: 'info', failed: 'destructive',
}
// A coloured left border per outcome, so the module list reads at a glance.
const OUTCOME_ACCENT: Record<ModuleOutcome, string> = {
  pending: 'border-l-border',
  passed: 'border-l-[hsl(var(--success))]',
  condoned: 'border-l-[hsl(var(--info,var(--primary)))]',
  failed: 'border-l-[hsl(var(--destructive))]',
}
// Classification header tint by band.
const BAND_TINT: Record<ClassificationBand, string> = {
  distinction: 'bg-[hsl(var(--success)/0.08)] border-[hsl(var(--success)/0.4)]',
  merit: 'bg-[hsl(var(--success)/0.06)] border-[hsl(var(--success)/0.3)]',
  pass: 'bg-surface-2/40 border-border/60',
  fail: 'bg-[hsl(var(--destructive)/0.06)] border-[hsl(var(--destructive)/0.4)]',
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
  const summary = useTaughtBoardSummary(studentId)
  const modules = useProgrammeModules(programmeId)

  const enrol = useEnrolModule(studentId)
  const recordResult = useRecordResult(studentId)
  const setStatus = useSetEnrolmentStatus(studentId)
  const condone = useCondoneModule(studentId)
  const upsertDiss = useUpsertDissertation(studentId)
  const computeAward = useComputeAward(studentId)

  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [enrolModuleId, setEnrolModuleId] = useState('')
  const [academicYear, setAcademicYear] = useState(currentAcademicYear())
  const [resultDraft, setResultDraft] = useState<Record<string, { assessmentId: string; mark: string; isResit: boolean }>>({})
  const [dissTitle, setDissTitle] = useState('')
  const [dissFirst, setDissFirst] = useState('')
  const [dissSecond, setDissSecond] = useState('')
  const [dissMark, setDissMark] = useState('')
  const [dissWords, setDissWords] = useState('')
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
          {/* AI board assistant — grounded standing + recommended next actions. */}
          {summary.data && (
            <div className="rounded-md border border-primary/25 bg-primary/[0.04] p-3">
              <div className="flex items-center gap-2 mb-1">
                <Sparkles className="h-4 w-4 text-primary" />
                <span className="text-label text-primary">Board assistant</span>
                <Badge variant={summary.data.narrationSource === 'model' ? 'info' : 'secondary'} className="text-[10px]">
                  {summary.data.narrationSource === 'model' ? 'AI summary' : 'summary'}
                </Badge>
              </div>
              <p className="text-sm">{summary.data.narration}</p>
              {summary.data.recommendations.length > 0 && (
                <ul className="mt-2 space-y-0.5">
                  {summary.data.recommendations.map((r, i) => (
                    <li key={i} className="text-xs text-muted-foreground flex items-start gap-1.5">
                      <span className="text-primary mt-[3px]">•</span>{r}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Award summary */}
          <div className={`flex flex-wrap items-center gap-4 rounded-md border p-3 ${data?.award?.classification ? BAND_TINT[data.award.classification] : 'bg-surface-2/30 border-border/60'}`}>
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
                <div key={e.id} className={`border border-border border-l-4 rounded-md p-3 ${OUTCOME_ACCENT[e.outcome]}`}>
                  <div className="flex items-center justify-between gap-2">
                    <button type="button" className="flex items-center gap-2 hover:text-primary min-w-0"
                      onClick={() => setExpanded((s) => ({ ...s, [e.id]: !s[e.id] }))}>
                      {isOpen ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
                      <span className="text-sm font-medium truncate">{e.moduleCode} — {e.moduleTitle}</span>
                      {mod && <Badge variant="outline">L{mod.level}{mod.isCore ? ' · core' : ' · optional'}</Badge>}
                      <span className="text-helper num whitespace-nowrap">{e.credits ?? 0} cr · {e.academicYear}</span>
                    </button>
                    <div className="flex items-center gap-2 shrink-0">
                      <Badge variant={OUTCOME_VARIANT[e.outcome]}>
                        {e.outcome}{e.condoned ? ' (condoned)' : ''}
                      </Badge>
                      <span className="text-sm whitespace-nowrap">
                        <span className="num font-medium">{num(e.moduleMark)}</span>
                        {e.creditsAwarded != null && <span className="text-helper"> · {e.creditsAwarded} cr awarded</span>}
                      </span>
                    </div>
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
                                {a && Number(r.mark) < Number(a.passMark) && r.mark != null && (
                                  <span className="text-[10px] font-medium text-[hsl(var(--destructive))]">below pass {Number(a.passMark).toFixed(0)}</span>
                                )}
                                {r.attemptNumber > 1 && <span className="text-helper">attempt {r.attemptNumber}</span>}
                                {r.isResit && <Badge variant="outline">resit</Badge>}
                                {r.capped && <Badge variant="warning">capped</Badge>}
                                {/* A failed first sit can be resat: pre-fill the record form (assessment + resit
                                    ticked) so recording the second attempt is one step. */}
                                {canChange && a && a.resitAllowed && !r.isResit && Number(r.mark) < Number(a.passMark) && r.mark != null && (
                                  <Button size="sm" variant="outline" className="h-6 px-2 ml-1"
                                    title={`Record a resit for ${a.title}. A resit is a second attempt at a failed assessment; its mark is capped at ${a.resitCap ? Number(a.resitCap).toFixed(0) : 'the module cap'}.`}
                                    onClick={() => setResultDraft((s) => ({ ...s, [e.id]: { assessmentId: r.assessmentId, mark: '', isResit: true } }))}>
                                    <RotateCcw className="h-3 w-3 mr-1" /> Resit
                                  </Button>
                                )}
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
                          <label className="flex items-center gap-1 text-helper cursor-help"
                            title="A resit is a second attempt at a failed assessment. Ticking this records the mark as a resit — it counts as the next attempt and is capped at the module's resit cap.">
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
                        <div className="flex flex-wrap items-center gap-2 pt-1">
                          <span className="text-helper">Set status:</span>
                          {(['enrolled', 'completed', 'withdrawn', 'failed'] as const).map((st) => (
                            <Button key={st} size="sm" variant={e.status === st ? 'secondary' : 'ghost'} className="h-7"
                              disabled={setStatus.isPending}
                              onClick={async () => { try { await setStatus.mutateAsync({ enrolmentId: e.id, status: st }); toast({ title: `Marked ${st}` }) } catch (er) { err(er) } }}>
                              {st}
                            </Button>
                          ))}
                          {/* Board condonement — only relevant when the module has failed. */}
                          {(e.outcome === 'failed' || e.condoned) && (
                            <Button size="sm" variant={e.condoned ? 'ghost' : 'secondary'} className="h-7 ml-2"
                              disabled={condone.isPending}
                              onClick={async () => {
                                try {
                                  await condone.mutateAsync({ enrolmentId: e.id, condoned: !e.condoned })
                                  toast({ title: e.condoned ? 'Condonement removed' : 'Module condoned — credits awarded' })
                                } catch (er) { err(er) }
                              }}>
                              {e.condoned ? 'Un-condone' : 'Condone fail'}
                            </Button>
                          )}
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
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                <span className="font-medium">{data.dissertation.title ?? 'Untitled'}</span>
                {data.dissertation.supervisorName && <span className="text-helper">supervisor {data.dissertation.supervisorName}</span>}
                {data.dissertation.secondMarkerName && <span className="text-helper">2nd marker {data.dissertation.secondMarkerName}</span>}
                {(data.dissertation.firstMark || data.dissertation.secondMark) && (
                  <span className="text-helper num">
                    1st {num(data.dissertation.firstMark)} · 2nd {num(data.dissertation.secondMark)}
                  </span>
                )}
                <span>agreed <span className="num font-medium">{num(data.dissertation.mark)}</span></span>
                {data.dissertation.wordCount != null && <span className="text-helper num">{data.dissertation.wordCount.toLocaleString()} words</span>}
              </div>
            ) : <p className="text-helper">No dissertation recorded.</p>}
            {canChange && (
              <div className="flex flex-wrap items-center gap-2">
                <Input className="h-8 w-56" placeholder="Dissertation title"
                  value={dissTitle || data?.dissertation?.title || ''} onChange={(e) => setDissTitle(e.target.value)} />
                <Input className="h-8 w-20" type="number" placeholder="1st" value={dissFirst} onChange={(e) => setDissFirst(e.target.value)} title="First marker's mark" />
                <Input className="h-8 w-20" type="number" placeholder="2nd" value={dissSecond} onChange={(e) => setDissSecond(e.target.value)} title="Second marker's mark" />
                <Input className="h-8 w-24" type="number" placeholder="Agreed" value={dissMark} onChange={(e) => setDissMark(e.target.value)} title="Agreed mark (used for classification)" />
                <Input className="h-8 w-24" type="number" placeholder="Words" value={dissWords} onChange={(e) => setDissWords(e.target.value)} />
                <Button size="sm" variant="secondary" disabled={upsertDiss.isPending}
                  onClick={async () => {
                    try {
                      await upsertDiss.mutateAsync({
                        title: (dissTitle || data?.dissertation?.title) ?? undefined,
                        firstMark: dissFirst || undefined,
                        secondMark: dissSecond || undefined,
                        mark: dissMark || undefined,
                        wordCount: dissWords ? Number(dissWords) : undefined,
                      })
                      setDissFirst(''); setDissSecond(''); setDissMark(''); setDissWords('')
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
  const [mod, setMod] = useState({ code: '', title: '', credits: '', level: '7', isCore: true })
  const [asmt, setAsmt] = useState<Record<string, { title: string; assessmentType: AssessmentType; weightPct: string; passMark: string; resitCap: string }>>({})
  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as Error).message, variant: 'destructive' })

  return (
    <div className="mt-2 space-y-3">
      {(modules.data ?? []).map((m) => {
        const a = asmt[m.id] ?? { title: '', assessmentType: 'essay' as AssessmentType, weightPct: '', passMark: '', resitCap: '' }
        return (
          <div key={m.id} className="rounded-md border border-border/60 p-2 text-sm">
            <div className="flex items-center gap-2">
              <span className="font-medium">{m.code} — {m.title}</span>
              <span className="text-helper num">{m.credits} cr</span>
              <Badge variant="outline">L{m.level}{m.isCore ? ' · core' : ' · optional'}</Badge>
            </div>
            <div className="mt-1 pl-2 text-helper">
              {m.assessments.length > 0
                ? m.assessments.map((x) => `${x.title} (${x.assessmentType}, ${Number(x.weightPct).toFixed(0)}%, pass ${Number(x.passMark).toFixed(0)}${x.resitCap ? `, resit cap ${Number(x.resitCap).toFixed(0)}` : x.resitAllowed ? '' : ', no resit'})`).join(' · ')
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
              <Input className="h-7 w-20" type="number" placeholder="pass" value={a.passMark}
                onChange={(e) => setAsmt((s) => ({ ...s, [m.id]: { ...a, passMark: e.target.value } }))} />
              <Input className="h-7 w-24" type="number" placeholder="resit cap" value={a.resitCap}
                onChange={(e) => setAsmt((s) => ({ ...s, [m.id]: { ...a, resitCap: e.target.value } }))} />
              <Button size="sm" className="h-7" disabled={!a.title || addAssessment.isPending}
                onClick={async () => {
                  try {
                    await addAssessment.mutateAsync({ moduleId: m.id, body: {
                      title: a.title, assessmentType: a.assessmentType, weightPct: a.weightPct || undefined,
                      passMark: a.passMark || undefined, resitCap: a.resitCap || null,
                    } })
                    setAsmt((s) => ({ ...s, [m.id]: { title: '', assessmentType: 'essay', weightPct: '', passMark: '', resitCap: '' } }))
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
        <Input className="h-8 w-20" type="number" placeholder="Level" value={mod.level} onChange={(e) => setMod((s) => ({ ...s, level: e.target.value }))} />
        <label className="flex items-center gap-1.5 text-sm text-helper">
          <input type="checkbox" checked={mod.isCore} onChange={(e) => setMod((s) => ({ ...s, isCore: e.target.checked }))} /> Core
        </label>
        <Button size="sm" disabled={!mod.code || !mod.title || createModule.isPending}
          onClick={async () => {
            try {
              await createModule.mutateAsync({
                code: mod.code, title: mod.title, credits: mod.credits ? Number(mod.credits) : 0,
                level: mod.level ? Number(mod.level) : undefined, isCore: mod.isCore,
              })
              setMod({ code: '', title: '', credits: '', level: '7', isCore: true })
              toast({ title: 'Module created' })
            } catch (e) { err(e) }
          }}>
          <Plus className="h-3.5 w-3.5 mr-1" /> Add module
        </Button>
      </div>
    </div>
  )
}
