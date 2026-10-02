'use client'

/** Effective dating, Phase 9 — units of assessment and the dated UOA of people (supervisors). */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export interface UnitOfAssessment {
  id: string
  code: string
  name: string
  panel: string | null
  isActive: boolean
}

export interface PersonUoaPeriod {
  id: string
  uoaId: string
  uoa: string | null
  validFrom: string
  /** Exclusive; null = still in force. */
  validTo: string | null
  reason: string | null
  recordedAt: string | null
}

export const useUoas = () =>
  useQuery({ queryKey: ['units-of-assessment'], queryFn: () => api.get<UnitOfAssessment[]>('/units-of-assessment') })

export function useCreateUoa() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { code: string; name: string; panel?: string }) => api.post<UnitOfAssessment>('/units-of-assessment', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['units-of-assessment'] }),
  })
}

export function useUpdateUoa() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; name?: string; panel?: string | null; isActive?: boolean }) =>
      api.patch<UnitOfAssessment>(`/units-of-assessment/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['units-of-assessment'] }),
  })
}

export const usePersonUoa = (personId: string) =>
  useQuery({
    queryKey: ['person', personId, 'uoa'],
    queryFn: () => api.get<{ personId: string; currentUoaId: string | null; current: string | null; periods: PersonUoaPeriod[] }>(
      `/persons/${personId}/uoa`),
    enabled: !!personId,
  })

export function useChangePersonUoa(personId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { uoaId: string; effectiveDate?: string; reason?: string }) =>
      api.post(`/persons/${personId}/uoa`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['person', personId, 'uoa'] }),
  })
}
