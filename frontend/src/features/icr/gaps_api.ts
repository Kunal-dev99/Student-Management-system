'use client'

/**
 * ICR gaps 2-5 typed API — hangs off /api/v1/icr/… endpoints.
 *
 * Gap 2 clinical placements, gap 3 independent tutor + private notes, gap 4 bench-fee
 * allocations + draw-downs, gap 5 partner affiliations with compliance flags.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'


// --------------------------- Gap 2 -----------------------------------------

export interface ClinicalPlacement {
  id: string
  studentId: string
  trustName: string
  specialty: string
  grade: string
  supervisorName: string | null
  validFrom: string
  validTo: string | null
  sessionsPerWeek: number | null
  notes: string | null
}

export const usePlacements = (studentId: string | null) =>
  useQuery({
    queryKey: ['icr', 'placements', studentId],
    queryFn: () => api.get<ClinicalPlacement[]>(`/icr/students/${studentId}/placements`),
    enabled: !!studentId,
  })

export function useOpenPlacement(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Omit<ClinicalPlacement, 'id' | 'studentId' | 'validTo'>) =>
      api.post<ClinicalPlacement>(`/icr/students/${studentId}/placements`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['icr', 'placements', studentId] }),
  })
}

export function useEndPlacement(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, validTo }: { id: string; validTo: string }) =>
      api.post<ClinicalPlacement>(`/icr/placements/${id}/end`, { validTo }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['icr', 'placements', studentId] }),
  })
}


// --------------------------- Gap 3 -----------------------------------------

export interface IndependentTutor {
  id: string
  studentId: string
  tutorPersonId: string
  tutorDepartmentId: string | null
  assignedAt: string
  endedAt: string | null
}

export interface TutorNote {
  id: string
  tutorId: string
  body: string
  authoredByUserId: string | null
  authoredAt: string
}

export const useCurrentTutor = (studentId: string | null) =>
  useQuery({
    queryKey: ['icr', 'tutor', studentId],
    queryFn: () => api.get<{ currentTutor: IndependentTutor | null }>(`/icr/students/${studentId}/independent-tutor`),
    enabled: !!studentId,
  })

export function useAssignTutor(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { tutorPersonId: string; tutorDepartmentId: string | null }) =>
      api.post<IndependentTutor>(`/icr/students/${studentId}/independent-tutor`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['icr', 'tutor', studentId] }),
  })
}

export function useEndTutor(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (tutorId: string) =>
      api.post<IndependentTutor>(`/icr/independent-tutor/${tutorId}/end`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['icr', 'tutor', studentId] }),
  })
}

export const useTutorNotes = (tutorId: string | null) =>
  useQuery({
    queryKey: ['icr', 'tutor-notes', tutorId],
    queryFn: () => api.get<TutorNote[]>(`/icr/independent-tutor/${tutorId}/notes`),
    enabled: !!tutorId,
  })

export function useAddTutorNote(tutorId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: string) =>
      api.post<TutorNote>(`/icr/independent-tutor/${tutorId}/notes`, { body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['icr', 'tutor-notes', tutorId] }),
  })
}


// --------------------------- Gap 4 -----------------------------------------

export interface BenchFeeAllocation {
  id: string
  totalAmount: string
  currency: string
  validFrom: string
  validTo: string | null
  costCentre: string | null
  notes: string | null
  drawnAmount: string
  remainingAmount: string
}

export interface BenchFeeDrawdown {
  id: string
  allocationId: string
  amount: string
  category: string
  description: string
  drawnAt: string
  invoiceRef: string | null
}

export const useBenchFees = (studentId: string | null) =>
  useQuery({
    queryKey: ['icr', 'bench-fees', studentId],
    queryFn: () => api.get<{ allocations: BenchFeeAllocation[] }>(`/icr/students/${studentId}/bench-fees`),
    enabled: !!studentId,
  })

export function useAllocateBenchFee(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { totalAmount: string; currency?: string; validFrom: string; costCentre?: string; notes?: string }) =>
      api.post<{ id: string }>(`/icr/students/${studentId}/bench-fees`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['icr', 'bench-fees', studentId] }),
  })
}

export const useDrawdowns = (allocationId: string | null) =>
  useQuery({
    queryKey: ['icr', 'bench-drawdowns', allocationId],
    queryFn: () => api.get<BenchFeeDrawdown[]>(`/icr/bench-fees/${allocationId}/drawdowns`),
    enabled: !!allocationId,
  })

export function useAddDrawdown(studentId: string, allocationId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { amount: string; category: string; description: string; drawnAt: string; invoiceRef?: string }) =>
      api.post<BenchFeeDrawdown>(`/icr/bench-fees/${allocationId}/drawdowns`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['icr', 'bench-drawdowns', allocationId] })
      qc.invalidateQueries({ queryKey: ['icr', 'bench-fees', studentId] })
    },
  })
}


// --------------------------- Gap 5 -----------------------------------------

export type ComplianceStatus = 'ok' | 'expiring' | 'expired'

export interface ComplianceFlag {
  key: string
  date: string
  status: ComplianceStatus
  daysUntil?: number
  daysOverdue?: number
}

export interface PartnerAffiliation {
  id: string
  studentId: string
  partnerName: string
  affiliationKind: string
  partnerRef: string | null
  validFrom: string
  validTo: string | null
  compliance: Record<string, string> | null
  active: boolean
  complianceFlags: ComplianceFlag[]
}

export const useAffiliations = (studentId: string | null) =>
  useQuery({
    queryKey: ['icr', 'affiliations', studentId],
    queryFn: () => api.get<{ affiliations: PartnerAffiliation[]; allowedKinds: string[] }>(
      `/icr/students/${studentId}/partner-affiliations`,
    ),
    enabled: !!studentId,
  })

export function useAddAffiliation(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: {
      partnerName: string; affiliationKind: string; validFrom: string;
      validTo?: string | null; partnerRef?: string; compliance?: Record<string, string>
    }) => api.post<PartnerAffiliation>(`/icr/students/${studentId}/partner-affiliations`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['icr', 'affiliations', studentId] }),
  })
}

export function useEndAffiliation(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, validTo }: { id: string; validTo: string }) =>
      api.post<PartnerAffiliation>(`/icr/partner-affiliations/${id}/end`, { validTo }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['icr', 'affiliations', studentId] }),
  })
}
