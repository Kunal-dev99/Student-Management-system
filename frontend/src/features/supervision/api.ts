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
  /** Phase 4B.5 — supervision-record health, surfaced on the caseload. */
  lastMeetingOn: string | null
  meetingOverdue: boolean
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

function invalidateSupervision(qc: ReturnType<typeof useQueryClient>, studentId: string) {
  qc.invalidateQueries({ queryKey: ['supervisors', studentId] })
  qc.invalidateQueries({ queryKey: ['student', studentId, 'summary'] })
  qc.invalidateQueries({ queryKey: ['student', studentId, 'history'] })
  qc.invalidateQueries({ queryKey: ['student', studentId, 'as-of'] })
  qc.invalidateQueries({ queryKey: ['caseload'] })
  qc.invalidateQueries({ queryKey: ['students'] })
}

export function useAssignSupervisor(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    /** ``validFrom`` — first day of supervision; default today, back-dating allowed. */
    mutationFn: (body: { supervisorPersonId: string; role: SupervisorRole; validFrom?: string }) =>
      api.post<Supervisor>(`/students/${studentId}/supervisors`, body),
    onSuccess: () => invalidateSupervision(qc, studentId),
  })
}

export function useEndSupervisor(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    /** A bare id ends today; ``effectiveDate`` is the first day no longer supervising. */
    mutationFn: (arg: string | { id: string; effectiveDate?: string; reason?: string }) => {
      const { id, ...body } = typeof arg === 'string' ? { id: arg } : arg
      return api.post<Supervisor>(`/supervisors/${id}/end`, Object.keys(body).length ? body : undefined)
    },
    onSuccess: () => invalidateSupervision(qc, studentId),
  })
}

/** Change supervisor: end this relationship and start the new one on the same day, same role. */
export function useReplaceSupervisor(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; newSupervisorPersonId: string; reason: string; effectiveDate?: string }) =>
      api.post<Supervisor>(`/supervisors/${id}/replace`, body),
    onSuccess: () => invalidateSupervision(qc, studentId),
  })
}
