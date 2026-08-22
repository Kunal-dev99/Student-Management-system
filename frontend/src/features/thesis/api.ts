'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export type ThesisStatus =
  | 'preparation' | 'intention_to_submit' | 'submitted' | 'under_examination'
  | 'corrections' | 'resubmission' | 'approved' | 'failed'
export type ExaminationOutcome =
  | 'pass' | 'pass_with_corrections' | 'major_corrections' | 'resubmission' | 'fail'
export type VivaFormat = 'in_person' | 'online' | 'hybrid'
export type CorrectionKind = 'minor' | 'major'

export interface Examination {
  id: string
  vivaDate: string | null
  vivaLocation: string | null
  vivaFormat: VivaFormat | null
  vivaScheduledAt: string | null
  outcome: ExaminationOutcome | null
  decidedAt: string | null
}

export interface Thesis {
  id: string
  studentId: string
  title: string | null
  status: ThesisStatus
  intentionToSubmitAt: string | null
  submittedAt: string | null
  documentRef: string | null
  examination: Examination | null
}

export type ExaminerType = 'internal' | 'external' | 'independent_chair'
export interface ExaminerNomination {
  id: string
  examinerPersonId: string
  examinerName: string
  examinerType: ExaminerType
  approved: boolean
  affiliation: string | null
  conflictOfInterest: boolean
  conflictNote: string | null
}

export interface ThesisCorrection {
  id: string
  kind: CorrectionKind
  deadline: string | null
  submittedAt: string | null
  approvedAt: string | null
}

export const useThesis = (studentId: string) =>
  useQuery({ queryKey: ['thesis', studentId], queryFn: () => api.get<Thesis | null>(`/students/${studentId}/thesis`), enabled: !!studentId })

export const useExaminers = (thesisId: string | undefined) =>
  useQuery({
    queryKey: ['examiners', thesisId],
    queryFn: () => api.get<ExaminerNomination[]>(`/theses/${thesisId}/examiners`),
    enabled: !!thesisId,
  })

export interface NominateExaminerInput {
  examinerPersonId: string
  examinerType: ExaminerType
  affiliation?: string
  conflictOfInterest?: boolean
  conflictNote?: string
}

export function useNominateExaminer(studentId: string, thesisId: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: NominateExaminerInput) =>
      api.post<ExaminerNomination>(`/theses/${thesisId}/examiners`, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['examiners', thesisId] }) },
  })
}

export function useApproveNomination(thesisId: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.post<ExaminerNomination>(`/examiner-nominations/${id}/approve`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['examiners', thesisId] }) },
  })
}

function inv(qc: ReturnType<typeof useQueryClient>, studentId: string) {
  qc.invalidateQueries({ queryKey: ['thesis', studentId] })
  qc.invalidateQueries({ queryKey: ['completion', studentId] })
}

export function useDeclareIntention(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (title?: string) => api.post<Thesis>(`/students/${studentId}/thesis/intention`, { title }),
    onSuccess: () => inv(qc, studentId),
  })
}
export function useSubmitThesis(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, documentRef }: { id: string; documentRef?: string }) =>
      api.post<Thesis>(`/theses/${id}/submit`, { documentRef }),
    onSuccess: () => inv(qc, studentId),
  })
}
export function useRecordOutcome(studentId: string, thesisId?: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, outcome }: { id: string; outcome: ExaminationOutcome }) =>
      api.post<Thesis>(`/theses/${id}/examination/outcome`, { outcome }),
    onSuccess: () => {
      inv(qc, studentId)
      qc.invalidateQueries({ queryKey: ['thesis-corrections', thesisId] })
    },
  })
}

// --- Phase 4B.4 — viva scheduling + corrections ---

export interface ScheduleVivaInput {
  vivaDate: string
  vivaFormat: VivaFormat
  location?: string
}

/** Requires an APPROVED examiner first — the API answers 422 with the reason otherwise. */
export function useScheduleViva(studentId: string, thesisId: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: ScheduleVivaInput) => api.post<Thesis>(`/theses/${thesisId}/viva`, body),
    onSuccess: () => inv(qc, studentId),
  })
}

export const useCorrections = (thesisId: string | undefined) =>
  useQuery({
    queryKey: ['thesis-corrections', thesisId],
    queryFn: () => api.get<ThesisCorrection[]>(`/theses/${thesisId}/corrections`),
    enabled: !!thesisId,
  })

export function useSubmitCorrections(studentId: string, thesisId: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<ThesisCorrection>(`/theses/${thesisId}/corrections/submit`),
    onSuccess: () => {
      inv(qc, studentId)
      qc.invalidateQueries({ queryKey: ['thesis-corrections', thesisId] })
    },
  })
}

export function useApproveCorrections(studentId: string, thesisId: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<Thesis>(`/theses/${thesisId}/corrections/approve`),
    onSuccess: () => {
      inv(qc, studentId)
      qc.invalidateQueries({ queryKey: ['thesis-corrections', thesisId] })
    },
  })
}
