'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

// Marks/weights are Decimal server-side and serialize to strings to preserve precision.
export type AssessmentType = 'essay' | 'exam' | 'coursework' | 'presentation' | 'dissertation'
export type ModuleEnrolmentStatus = 'enrolled' | 'completed' | 'withdrawn' | 'failed'
export type ClassificationBand = 'distinction' | 'merit' | 'pass' | 'fail'

export interface Assessment {
  id: string
  moduleId: string
  title: string
  assessmentType: AssessmentType
  weightPct: string
  maxMark: string
  dueDate: string | null
}

export interface TaughtModule {
  id: string
  programmeId: string
  code: string
  title: string
  credits: number
  term: string | null
  assessments: Assessment[]
}

export interface AssessmentResult {
  id: string
  assessmentId: string
  mark: string | null
  grade: string | null
  isResit: boolean
  submittedAt: string | null
  markedAt: string | null
}

export interface Enrolment {
  id: string
  studentId: string
  moduleId: string
  moduleCode: string | null
  moduleTitle: string | null
  credits: number | null
  academicYear: string
  status: ModuleEnrolmentStatus
  moduleMark: string | null
  results: AssessmentResult[]
}

export interface Dissertation {
  id: string
  studentId: string
  title: string | null
  supervisorPersonId: string | null
  supervisorName: string | null
  submittedAt: string | null
  markedAt: string | null
  mark: string | null
  grade: string | null
}

export interface TaughtAward {
  studentId: string
  finalMark: string | null
  classification: ClassificationBand | null
  creditsAchieved: number | null
  decidedAt: string | null
}

export interface TaughtRecord {
  studentId: string
  programmeType: 'research' | 'taught'
  totalCreditsTarget: number | null
  creditsEnrolled: number
  enrolments: Enrolment[]
  dissertation: Dissertation | null
  award: TaughtAward | null
}

// --- queries ---

export const useTaughtRecord = (studentId: string, enabled = true) =>
  useQuery({
    queryKey: ['taught', studentId],
    queryFn: () => api.get<TaughtRecord>(`/students/${studentId}/taught`),
    enabled: !!studentId && enabled,
  })

export const useProgrammeModules = (programmeId: string | null | undefined) =>
  useQuery({
    queryKey: ['taught-modules', programmeId],
    queryFn: () => api.get<TaughtModule[]>(`/programmes/${programmeId}/modules`),
    enabled: !!programmeId,
  })

function invalidate(qc: ReturnType<typeof useQueryClient>, studentId: string) {
  qc.invalidateQueries({ queryKey: ['taught', studentId] })
  qc.invalidateQueries({ queryKey: ['student', studentId, 'summary'] })
}

// --- module / assessment configuration (admin.configure) ---

export interface ModuleInput { code: string; title: string; credits?: number; term?: string }
export interface AssessmentInput {
  title: string
  assessmentType: AssessmentType
  weightPct?: string
  maxMark?: string
  dueDate?: string
}

export function useCreateModule(programmeId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: ModuleInput) => api.post<TaughtModule>(`/programmes/${programmeId}/modules`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['taught-modules', programmeId] }),
  })
}

export function useAddAssessment(programmeId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ moduleId, body }: { moduleId: string; body: AssessmentInput }) =>
      api.post<Assessment>(`/taught-modules/${moduleId}/assessments`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['taught-modules', programmeId] }),
  })
}

// --- enrolments / results / dissertation / award (taught.change) ---

export function useEnrolModule(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { moduleId: string; academicYear: string }) =>
      api.post<Enrolment>(`/students/${studentId}/module-enrolments`, body),
    onSuccess: () => invalidate(qc, studentId),
  })
}

export function useRecordResult(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ enrolmentId, body }: {
      enrolmentId: string
      body: { assessmentId: string; mark?: string; grade?: string; isResit?: boolean }
    }) => api.post<Enrolment>(`/module-enrolments/${enrolmentId}/results`, body),
    onSuccess: () => invalidate(qc, studentId),
  })
}

export function useSetEnrolmentStatus(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ enrolmentId, status }: { enrolmentId: string; status: ModuleEnrolmentStatus }) =>
      api.patch<Enrolment>(`/module-enrolments/${enrolmentId}/status`, { status }),
    onSuccess: () => invalidate(qc, studentId),
  })
}

export function useUpsertDissertation(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: {
      title?: string; supervisorPersonId?: string; submittedAt?: string; mark?: string; grade?: string
    }) => api.put<Dissertation>(`/students/${studentId}/dissertation`, body),
    onSuccess: () => invalidate(qc, studentId),
  })
}

export function useComputeAward(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<TaughtAward>(`/students/${studentId}/taught-award`),
    onSuccess: () => invalidate(qc, studentId),
  })
}
