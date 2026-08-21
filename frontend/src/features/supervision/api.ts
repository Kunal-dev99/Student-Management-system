'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export type SupervisorRole = 'primary' | 'co_supervisor' | 'additional'

export interface Supervisor {
  id: string
  supervisorPersonId: string
  supervisorName: string
  role: SupervisorRole
  status: string
  validFrom: string
  validTo: string | null
}

export interface CaseloadItem {
  relationshipId: string
  studentId: string
  studentRef: string
  personName: string
  role: SupervisorRole
}

export const useSupervisors = (studentId: string) =>
  useQuery({
    queryKey: ['supervisors', studentId],
    queryFn: () => api.get<Supervisor[]>(`/students/${studentId}/supervisors`),
    enabled: !!studentId,
  })

export const useCaseload = (personId: string | null | undefined) =>
  useQuery({
    queryKey: ['caseload', personId],
    queryFn: () => api.get<CaseloadItem[]>(`/supervisors/${personId}/students`),
    enabled: !!personId,
  })

export function useAssignSupervisor(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { supervisorPersonId: string; role: SupervisorRole }) =>
      api.post<Supervisor>(`/students/${studentId}/supervisors`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['supervisors', studentId] })
      qc.invalidateQueries({ queryKey: ['student', studentId, 'summary'] })
      qc.invalidateQueries({ queryKey: ['caseload'] })
      qc.invalidateQueries({ queryKey: ['students'] })
    },
  })
}

export function useEndSupervisor(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (relId: string) => api.post<Supervisor>(`/supervisors/${relId}/end`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['supervisors', studentId] })
      qc.invalidateQueries({ queryKey: ['student', studentId, 'summary'] })
      qc.invalidateQueries({ queryKey: ['caseload'] })
      qc.invalidateQueries({ queryKey: ['students'] })
    },
  })
}
