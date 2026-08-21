'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export type MilestoneStatus = 'not_started' | 'due' | 'submitted' | 'under_review' | 'decided' | 'overdue'
export type ProgressionOutcome =
  | 'progress' | 'progress_with_conditions' | 'further_review' | 'transfer_award' | 'withdraw' | 'terminate'

export interface Milestone {
  id: string
  studentId: string
  milestoneDefinitionId: string
  name: string
  dueDate: string | null
  status: MilestoneStatus
  review: {
    id: string
    studentSubmissionRef: string | null
    panelDecision: ProgressionOutcome | null
    decidedAt: string | null
    rationale: string | null
  } | null
}

export interface MilestoneDefinition {
  id: string
  programmeId: string
  name: string
  dueOffsetDays: number
  trigger: Record<string, unknown> | null
  possibleOutcomes: Record<string, unknown> | null
}

export interface Programme { id: string; name: string; code: string }

export const useProgrammes = () =>
  useQuery({ queryKey: ['programmes'], queryFn: () => api.get<Programme[]>('/programmes') })

export const useMilestoneDefinitions = (programmeId: string) =>
  useQuery({
    queryKey: ['milestone-definitions', programmeId],
    queryFn: () => api.get<MilestoneDefinition[]>(`/programmes/${programmeId}/milestone-definitions`),
    enabled: !!programmeId,
  })

export const useMilestones = (studentId: string) =>
  useQuery({
    queryKey: ['milestones', studentId],
    queryFn: () => api.get<Milestone[]>(`/students/${studentId}/milestones`),
    enabled: !!studentId,
  })

export function useSubmitMilestone(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ref }: { id: string; ref?: string }) =>
      api.post<Milestone>(`/milestones/${id}/submit`, { studentSubmissionRef: ref }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['milestones', studentId] }),
  })
}

export function useDecideMilestone(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, outcome, rationale }: { id: string; outcome: ProgressionOutcome; rationale?: string }) =>
      api.post<Milestone>(`/milestones/${id}/decide`, { outcome, rationale }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['milestones', studentId] }),
  })
}
