'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export type FundingType = 'research_council' | 'university_scholarship' | 'external' | 'self_funded'
export type FundingStatus = 'planned' | 'active' | 'changed' | 'ended'

export interface FundingSource { id: string; name: string; funderType: string | null }

export interface Arrangement {
  id: string
  studentId: string
  fundingType: FundingType
  fundingSourceId: string | null
  fundingSourceName: string | null
  stipendAmount: string | null
  currency: string | null
  validFrom: string
  validTo: string | null
  status: FundingStatus
}

export interface FundingInput {
  fundingType: FundingType
  fundingSourceId?: string
  stipendAmount?: string
  currency?: string
}

export const useFundingSources = () =>
  useQuery({ queryKey: ['funding-sources'], queryFn: () => api.get<FundingSource[]>('/funding-sources') })

export const useFunding = (studentId: string) =>
  useQuery({
    queryKey: ['funding', studentId],
    queryFn: () => api.get<Arrangement[]>(`/students/${studentId}/funding`),
    enabled: !!studentId,
  })

function invalidate(qc: ReturnType<typeof useQueryClient>, studentId: string) {
  qc.invalidateQueries({ queryKey: ['funding', studentId] })
  qc.invalidateQueries({ queryKey: ['student', studentId, 'summary'] })
}

export function useCreateFunding(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: FundingInput) => api.post<Arrangement>(`/students/${studentId}/funding`, body),
    onSuccess: () => invalidate(qc, studentId),
  })
}
export function useChangeFunding(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: FundingInput }) => api.post<Arrangement>(`/funding/${id}/change`, body),
    onSuccess: () => invalidate(qc, studentId),
  })
}
export function useEndFunding(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.post<Arrangement>(`/funding/${id}/end`),
    onSuccess: () => invalidate(qc, studentId),
  })
}
