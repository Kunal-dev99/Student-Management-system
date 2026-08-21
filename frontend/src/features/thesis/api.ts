'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export type ThesisStatus =
  | 'preparation' | 'intention_to_submit' | 'submitted' | 'under_examination'
  | 'corrections' | 'resubmission' | 'approved' | 'failed'
export type ExaminationOutcome =
  | 'pass' | 'pass_with_corrections' | 'major_corrections' | 'resubmission' | 'fail'

export interface Thesis {
  id: string
  studentId: string
  title: string | null
  status: ThesisStatus
  intentionToSubmitAt: string | null
  submittedAt: string | null
  documentRef: string | null
  examination: { id: string; vivaDate: string | null; outcome: ExaminationOutcome | null; decidedAt: string | null } | null
}

export type ExaminerType = 'internal' | 'external'
export interface ExaminerNomination {
  id: string
  examinerPersonId: string
  examinerName: string
  examinerType: ExaminerType
  approved: boolean
}

export const useThesis = (studentId: string) =>
  useQuery({ queryKey: ['thesis', studentId], queryFn: () => api.get<Thesis | null>(`/students/${studentId}/thesis`), enabled: !!studentId })

export const useExaminers = (thesisId: string | undefined) =>
  useQuery({
    queryKey: ['examiners', thesisId],
    queryFn: () => api.get<ExaminerNomination[]>(`/theses/${thesisId}/examiners`),
    enabled: !!thesisId,
  })

export function useNominateExaminer(studentId: string, thesisId: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { examinerPersonId: string; examinerType: ExaminerType }) =>
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
export function useRecordOutcome(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, outcome }: { id: string; outcome: ExaminationOutcome }) =>
      api.post<Thesis>(`/theses/${id}/examination/outcome`, { outcome }),
    onSuccess: () => inv(qc, studentId),
  })
}
