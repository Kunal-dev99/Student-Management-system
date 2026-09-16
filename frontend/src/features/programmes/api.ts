'use client'

/** ICR G3 — programme + milestone-template administration (admin.configure). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export type ProgrammeType = 'research' | 'taught'

/** Per-programme overrides on the default taught grading policy (all optional). */
export interface GradingPolicy {
  passMark?: number
  resitCap?: number
  condonementCredits?: number
  distinctionMark?: number
  meritMark?: number
  passMarkAward?: number
}

export interface ProgrammeDetail {
  id: string
  name: string
  code: string
  departmentId: string | null
  programmeType: ProgrammeType
  taughtTotalCredits: number | null
  durationMonths: number | null
  supervisionMeetingIntervalDays: number | null
  gradingPolicy: GradingPolicy | null
}

export interface ProgrammeInput {
  name: string
  code: string
  programmeType?: ProgrammeType
  taughtTotalCredits?: number | null
  durationMonths?: number | null
  supervisionMeetingIntervalDays?: number | null
}

export interface MilestoneDefinition {
  id: string
  programmeId: string
  name: string
  dueOffsetDays: number
}

export const useProgrammesAdmin = () =>
  useQuery({ queryKey: ['programmes'], queryFn: () => api.get<ProgrammeDetail[]>('/programmes') })

export function useCreateProgramme() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: ProgrammeInput) => api.post<ProgrammeDetail>('/programmes', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['programmes'] }),
  })
}

export function useUpdateProgramme() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Partial<ProgrammeInput> }) =>
      api.patch<ProgrammeDetail>(`/programmes/${id}`, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['programmes'] }),
  })
}

export const useDefinitions = (programmeId: string | null) =>
  useQuery({
    queryKey: ['milestone-definitions', programmeId],
    queryFn: () => api.get<MilestoneDefinition[]>(`/programmes/${programmeId}/milestone-definitions`),
    enabled: !!programmeId,
  })

export function useCreateDefinition(programmeId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; dueOffsetDays: number }) =>
      api.post<MilestoneDefinition>(`/programmes/${programmeId}/milestone-definitions`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['milestone-definitions', programmeId] }),
  })
}

export function useUpdateDefinition(programmeId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: { name?: string; dueOffsetDays?: number } }) =>
      api.patch<MilestoneDefinition>(`/programmes/${programmeId}/milestone-definitions/${id}`, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['milestone-definitions', programmeId] }),
  })
}

export function useDeleteDefinition(programmeId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      api.del<void>(`/programmes/${programmeId}/milestone-definitions/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['milestone-definitions', programmeId] }),
  })
}
