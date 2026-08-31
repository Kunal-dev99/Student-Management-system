'use client'

/**
 * W2 — SupervisorProfile + assignment-request workflow hooks.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'


export type SupervisorAvailability = 'available' | 'full' | 'on_leave'

export interface SupervisorProfile {
  personId: string
  maxStudents: number
  availability: SupervisorAvailability
  acceptingNew: boolean
  sabbaticalFrom: string | null
  sabbaticalTo: string | null
  bio: string | null
  researchAreaIds: string[]
}

// --- W5 — Workforce lens (institution-wide capacity) ---

export interface WorkforceRow {
  personId: string
  personName: string
  email: string | null
  hasProfile: boolean
  maxStudents: number
  caseload: number
  primary: number
  co: number
  headroom: number
  overCapacity: boolean
  availability: SupervisorAvailability
  acceptingNew: boolean
  onSabbatical: boolean
  sabbaticalFrom: string | null
  sabbaticalTo: string | null
  pendingRequests: number
  link: string
}

export interface WorkforceReport {
  totals: {
    supervisors: number
    overCapacity: number
    onSabbatical: number
    notAcceptingNew: number
    unavailable: number
    pendingRequests: number
    totalActiveSupervisees: number
    totalCapacity: number
    utilisationPct: number
    defaultCap: number
  }
  supervisors: WorkforceRow[]
}

export const useSupervisorWorkforce = () =>
  useQuery({
    queryKey: ['supervisor', 'workforce'],
    queryFn: () => api.get<WorkforceReport>('/reports/supervisor-workforce'),
  })


export const useSupervisorProfile = (personId: string | null) =>
  useQuery({
    queryKey: ['supervisor', 'profile', personId],
    queryFn: () => api.get<{ profile: SupervisorProfile | null }>(
      `/supervisors/${personId}/profile`,
    ),
    enabled: !!personId,
  })

export function useUpsertSupervisorProfile(personId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Partial<SupervisorProfile>) =>
      api.put<SupervisorProfile>(`/supervisors/${personId}/profile`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['supervisor', 'profile', personId] }),
  })
}


export interface MatchReason { factor: string; points: number; detail?: string }
export interface Recommendation {
  personId: string
  name?: string
  score: number
  reasons: MatchReason[]
  current?: number
  capacity?: number
  available?: boolean
}

export const useRecommend = (studentId: string | null) =>
  useQuery({
    queryKey: ['supervisor', 'recommend', studentId],
    queryFn: () => api.get<{ suggestions: Recommendation[]; criteria?: unknown }>(
      `/supervisors/recommend?studentId=${studentId}`,
    ),
    enabled: !!studentId,
  })


export type AssignmentRequestState =
  | 'recommended' | 'requested' | 'academic_review' | 'approved' | 'rejected' | 'withdrawn'

export interface AssignmentRequest {
  id: string
  studentId: string
  proposedSupervisorPersonId: string
  proposedRole: 'primary' | 'co_supervisor'
  state: AssignmentRequestState
  matchScore: number | null
  matchReasons: MatchReason[] | null
  rejectionReason: string | null
  requestedByUserId: string | null
  reviewedByUserId: string | null
  decidedByUserId: string | null
  reviewedAt: string | null
  decidedAt: string | null
  note: string | null
  createdAt: string
}

export const useStudentSupervisorRequests = (studentId: string | null) =>
  useQuery({
    queryKey: ['supervisor', 'requests', 'student', studentId],
    queryFn: () => api.get<{ requests: AssignmentRequest[] }>(
      `/students/${studentId}/supervisor-requests`,
    ),
    enabled: !!studentId,
  })

export const useAssignmentQueue = (state?: AssignmentRequestState) =>
  useQuery({
    queryKey: ['supervisor', 'requests', 'queue', state ?? 'all'],
    queryFn: () => api.get<{ requests: AssignmentRequest[] }>(
      `/supervisor-requests${state ? `?state=${state}` : ''}`,
    ),
  })


function inv(qc: ReturnType<typeof useQueryClient>, studentId?: string) {
  qc.invalidateQueries({ queryKey: ['supervisor', 'requests'] })
  if (studentId) qc.invalidateQueries({ queryKey: ['supervisor', 'requests', 'student', studentId] })
}

export function useCreateAssignmentRequest(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: {
      supervisorPersonId: string
      role: 'primary' | 'co_supervisor'
      matchScore?: number
      matchReasons?: MatchReason[]
      note?: string
    }) => api.post<AssignmentRequest>(`/students/${studentId}/supervisor-requests`, body),
    onSuccess: () => inv(qc, studentId),
  })
}

export function useReviewRequest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.post<AssignmentRequest>(`/supervisor-requests/${id}/review`, {}),
    onSuccess: (r) => inv(qc, r.studentId),
  })
}

export function useApproveRequest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.post<AssignmentRequest & { relationshipId: string }>(
      `/supervisor-requests/${id}/approve`, {},
    ),
    onSuccess: (r) => {
      inv(qc, r.studentId)
      qc.invalidateQueries({ queryKey: ['student', r.studentId] })
    },
  })
}

export function useRejectRequest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      api.post<AssignmentRequest>(`/supervisor-requests/${id}/reject`, { reason }),
    onSuccess: (r) => inv(qc, r.studentId),
  })
}

export function useWithdrawRequest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.post<AssignmentRequest>(`/supervisor-requests/${id}/withdraw`, {}),
    onSuccess: (r) => inv(qc, r.studentId),
  })
}
