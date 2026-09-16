'use client'

/**
 * Group-level taught configuration on the Programmes admin page (ICR G1).
 *
 * Set the programme's modules, their assessments and the grading policy once, here — the taught
 * parallel to milestone templates. Core modules then flow to students automatically on enrol, and
 * the "Enrol cohort on core modules" action applies them to the existing group in one go.
 */
import { useState } from 'react'
import { BookOpen, Plus, Users } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { ApiError } from '@/shared/api/client'
import {
  useAddAssessment, useCreateModule, useEnrolCohort, useProgrammeModules,
  type AssessmentType,
} from '@/features/taught/api'

const ASSESSMENT_TYPES: AssessmentType[] = ['essay', 'exam', 'coursework', 'presentation', 'dissertation']

export function ProgrammeModulesEditor({ programmeId }: { programmeId: string }) {
  const { toast } = useToast()
  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as ApiError).message, variant: 'destructive' })
  const modules = useProgrammeModules(programmeId)
  const createModule = useCreateModule(programmeId)
  const addAssessment = useAddAssessment(programmeId)
  const enrolCohort = useEnrolCohort(programmeId)

  const [mod, setMod] = useState({ code: '', title: '', credits: '', level: '7', isCore: true })
  const [asmt, setAsmt] = useState<Record<string, { title: string; assessmentType: AssessmentType; weightPct: string; passMark: string; resitCap: string }>>({})
  const [year, setYear] = useState('')

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-sm font-medium flex items-center gap-1.5"><BookOpen className="h-4 w-4" /> Taught modules &amp; assessments</h4>
        <div className="flex items-center gap-2">
          <Input className="h-8 w-28" placeholder="year (opt.)" value={year} onChange={(e) => setYear(e.target.value)} />
          <Button size="sm" variant="outline" disabled={enrolCohort.isPending}
            title="Enrol every student on this programme on its core modules (idempotent — skips anyone already enrolled)."
            onClick={async () => {
              try {
                const r = await enrolCohort.mutateAsync({ academicYear: year.trim() || undefined })
                toast({
                  title: `Cohort enrolled`,
                  description: `${r.enrolmentsCreated} new enrolment(s) across ${r.studentsEnrolled} of ${r.studentsConsidered} students.`,
                })
              } catch (e) { err(e) }
            }}>
            <Users className="h-3.5 w-3.5 mr-1" /> {enrolCohort.isPending ? 'Enrolling…' : 'Enrol cohort on core modules'}
          </Button>
        </div>
      </div>

      <div className="card-elevated p-3 space-y-3">
        {modules.isLoading ? <Skeleton className="h-20 w-full" /> : (
          <>
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
                      ? m.assessments.map((x) => `${x.title} (${x.assessmentType}, ${Number(x.weightPct).toFixed(0)}%, pass ${Number(x.passMark).toFixed(0)}${x.resitCap ? `, cap ${Number(x.resitCap).toFixed(0)}` : ''})`).join(' · ')
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
            {modules.data && modules.data.length === 0 && (
              <p className="text-helper">No modules yet. Add the programme&apos;s modules below — core ones enrol students automatically.</p>
            )}

            <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-border/50">
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
          </>
        )}
      </div>
      <p className="text-helper mt-2">
        Core modules are laid down for a taught student the moment they enrol (like milestones).
        Use <span className="font-medium">Enrol cohort on core modules</span> to apply them to
        students already on the programme; it skips anyone already enrolled.
      </p>
    </div>
  )
}
