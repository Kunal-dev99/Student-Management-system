'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export type CompletionStatus = 'pending' | 'requirements_met' | 'award_confirmed' | 'graduated'

export interface Completion {
  id: string
  studentId: string
  status: CompletionStatus
  requirementsMetAt: string | null
  awardConfirmedAt: string | null
  graduationDate: string | null
  award: { id: string; title: string; awardType: string | null; conferredAt: string | null } | null
}

export const useCompletion = (studentId: string) =>
  useQuery({ queryKey: ['completion', studentId], queryFn: () => api.get<Completion | null>(`/students/${studentId}/completion`), enabled: !!studentId })

function inv(qc: ReturnType<typeof useQueryClient>, studentId: string) {
  qc.invalidateQueries({ queryKey: ['completion', studentId] })
  qc.invalidateQueries({ queryKey: ['student', studentId] })
  qc.invalidateQueries({ queryKey: ['student', studentId, 'summary'] })
  qc.invalidateQueries({ queryKey: ['students'] })
  qc.invalidateQueries({ queryKey: ['funding', studentId] })
}

export function useConfirmCompletion(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<Completion>(`/students/${studentId}/completion/confirm`),
    onSuccess: () => inv(qc, studentId),
  })
}
export function useGraduate(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<Completion>(`/students/${studentId}/graduation`),
    onSuccess: () => inv(qc, studentId),
  })
}


// -------- F4 — classification workflow + certificate --------

export type ClassificationState = 'none' | 'draft' | 'proposed' | 'confirmed' | 'published'

export interface Classification {
  studentId: string
  classification: string | null
  classificationState: ClassificationState
  classificationTitle?: string
  proposedByUserId: string | null
  confirmedByUserId: string | null
  publishedAt: string | null
  certificateDocumentId: string | null
  options: string[]
}

export const useClassification = (studentId: string) =>
  useQuery({
    queryKey: ['classification', studentId],
    queryFn: () => api.get<Classification>(`/students/${studentId}/classification`),
    enabled: !!studentId,
  })

export function useProposeClassification(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (classification: string) =>
      api.post<Classification>(`/students/${studentId}/classification/propose`, { classification }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['classification', studentId] }),
  })
}

export function useConfirmClassification(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<Classification>(`/students/${studentId}/classification/confirm`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['classification', studentId] }),
  })
}

export function usePublishClassification(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<Classification>(`/students/${studentId}/classification/publish`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['classification', studentId] })
      qc.invalidateQueries({ queryKey: ['completion', studentId] })
    },
  })
}

export function certificateUrl(studentId: string): string {
  return `/api/v1/students/${studentId}/certificate`
}
