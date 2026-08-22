'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export type MilestoneStatus = 'not_started' | 'due' | 'submitted' | 'under_review' | 'decided' | 'overdue'
export type ProgressionOutcome =
  | 'progress' | 'progress_with_conditions' | 'further_review' | 'transfer_award' | 'withdraw' | 'terminate'
export type PanelRole =
  | 'chair' | 'internal_assessor' | 'independent_assessor' | 'supervisor_observer'
export type AppealStatus = 'submitted' | 'under_review' | 'upheld' | 'rejected' | 'withdrawn'
export type AppealDecision = Exclude<AppealStatus, 'submitted'>

/** Outcomes the API refuses without written conditions (422). */
export const CONDITIONAL_OUTCOMES: ProgressionOutcome[] = ['progress_with_conditions', 'further_review']

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

export interface PanelMember {
  id: string
  personId: string
  personName: string
  role: PanelRole
  isIndependent: boolean
}

export interface ReviewDetail {
  milestoneId: string
  reviewId?: string
  decided: boolean
  panelDecision?: ProgressionOutcome | null
  rationale?: string | null
  conditions?: string | null
  reReviewDue?: string | null
  conditionsMet?: boolean
  outcomeLetter?: string | null
  appealDeadline?: string | null
  panel: PanelMember[]
}

export interface Appeal {
  id: string
  reviewId: string
  studentId: string
  grounds: string
  status: AppealStatus
  submittedAt: string | null
  decidedAt: string | null
  decisionNote: string | null
}

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

export interface DecideInput {
  id: string
  outcome: ProgressionOutcome
  rationale?: string
  conditions?: string
  outcomeLetter?: string
}

/**
 * 422 when a conditional outcome carries no conditions, or when the milestone's
 * review panel is incomplete ("Panel is incomplete — missing: …").
 */
export function useDecideMilestone(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, outcome, rationale, conditions, outcomeLetter }: DecideInput) =>
      api.post<Milestone>(`/milestones/${id}/decide`, { outcome, rationale, conditions, outcomeLetter }),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['milestones', studentId] })
      qc.invalidateQueries({ queryKey: ['milestone-review', vars.id] })
      qc.invalidateQueries({ queryKey: ['milestone-appeals', vars.id] })
    },
  })
}

// --- Phase 4B.6 — panel, conditions, appeals ---

export const useReviewDetail = (milestoneId: string | undefined, enabled = true) =>
  useQuery({
    queryKey: ['milestone-review', milestoneId],
    queryFn: () => api.get<ReviewDetail>(`/milestones/${milestoneId}/review`),
    enabled: !!milestoneId && enabled,
  })

export const usePanel = (milestoneId: string | undefined, enabled = true) =>
  useQuery({
    queryKey: ['milestone-panel', milestoneId],
    queryFn: () => api.get<PanelMember[]>(`/milestones/${milestoneId}/panel`),
    enabled: !!milestoneId && enabled,
  })

export interface PanelMemberInput {
  personId: string
  role: PanelRole
  isIndependent?: boolean
}

/** 422 when a supervisor is added as independent assessor; 409 on a duplicate member. */
export function useAddPanelMember(milestoneId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: PanelMemberInput) => api.post<PanelMember[]>(`/milestones/${milestoneId}/panel`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['milestone-panel', milestoneId] })
      qc.invalidateQueries({ queryKey: ['milestone-review', milestoneId] })
    },
  })
}

export function useSignOffConditions(studentId: string, milestoneId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<ReviewDetail>(`/milestones/${milestoneId}/conditions/sign-off`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['milestone-review', milestoneId] })
      qc.invalidateQueries({ queryKey: ['milestones', studentId] })
    },
  })
}

export const useAppeals = (milestoneId: string | undefined, enabled = true) =>
  useQuery({
    queryKey: ['milestone-appeals', milestoneId],
    queryFn: () => api.get<Appeal[]>(`/milestones/${milestoneId}/appeals`),
    enabled: !!milestoneId && enabled,
  })

/** 409 when an appeal is already open, 422 outside the appeal window. */
export function useSubmitAppeal(milestoneId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (grounds: string) => api.post<Appeal>(`/milestones/${milestoneId}/appeals`, { grounds }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['milestone-appeals', milestoneId] }),
  })
}

export function useDecideAppeal(milestoneId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ appealId, status, decisionNote }: { appealId: string; status: AppealDecision; decisionNote?: string }) =>
      api.post<Appeal>(`/milestones/appeals/${appealId}/decide`, { status, decisionNote }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['milestone-appeals', milestoneId] }),
  })
}
