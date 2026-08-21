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
