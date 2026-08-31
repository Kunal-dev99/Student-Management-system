'use client'

/**
 * Research context (Phase 6.1) — awards, demand and position lineage.
 *
 * Awards are *references*: a record whose `readOnly` is true is mastered in the Research
 * system and must not be offered an edit affordance here.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export type DemandStatus = 'identified' | 'approved' | 'positioned' | 'filled' | 'withdrawn'

export interface ResearchAward {
  id: string
  awardRef: string
  title: string
  funderId: string | null
  principalInvestigatorId: string | null
  startDate: string | null
  endDate: string | null
  value: string | null
  currency: string | null
  status: string
  sourceSystem: string | null
  externalRef: string | null
  readOnly: boolean
}

export interface ResearchDemand {
  id: string
  title: string
  researchAwardId: string | null
  researchAreaId: string | null
  departmentId: string | null
  requestedPlaces: number
  justification: string | null
  targetStartDate: string | null
  status: DemandStatus
}

export interface LineageApplication {
  applicationId: string
  route: string
  stage: string
  student: { studentId: string; studentRef: string; personName: string; link: string } | null
}

export interface PositionLineage {
  award: ResearchAward | null
  funder: { id: string; name: string } | null
  demand: ResearchDemand | null
  position: {
    id: string
    title: string
    status: string
    positionsAvailable: number
    positionsFilled: number
    positionsRemaining: number
    expectedDurationMonths: number | null
  }
  applications: LineageApplication[]
  studentsProduced: number
  /** Broken hops in the chain — rendered, never hidden. */
  gaps: string[]
}

/** Legal next states, mirroring the backend FSM (research/constants.py). */
export const DEMAND_NEXT: Record<DemandStatus, DemandStatus[]> = {
  identified: ['approved', 'withdrawn'],
  approved: ['positioned', 'withdrawn'],
  positioned: ['filled', 'withdrawn'],
  filled: [],
  withdrawn: [],
}

// --- awards ---

export const useAwards = (opts?: { enabled?: boolean }) =>
  useQuery({
    queryKey: ['research-awards'],
    queryFn: () => api.get<ResearchAward[]>('/research-awards'),
    enabled: opts?.enabled ?? true,
  })

export interface AwardInput {
  awardRef: string
  title: string
  funderId?: string
  startDate?: string
  endDate?: string
  value?: number
  currency?: string
}

/** 409 when the award reference already exists. */
export function useCreateAward() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: AwardInput) => api.post<ResearchAward>('/research-awards', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['research-awards'] }),
  })
}

// --- demand ---

export const useDemands = (status?: DemandStatus) =>
  useQuery({
    queryKey: ['research-demands', status ?? 'all'],
    queryFn: () => api.get<ResearchDemand[]>(`/research-demands${status ? `?status=${status}` : ''}`),
  })

export interface DemandInput {
  title: string
  researchAwardId?: string
  researchAreaId?: string
  departmentId?: string
  requestedPlaces: number
  justification?: string
  targetStartDate?: string
}

export function useCreateDemand() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: DemandInput) => api.post<ResearchDemand>('/research-demands', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['research-demands'] }),
  })
}

/** 422 when the move is not legal for the demand's current status; the message lists what is. */
export function useTransitionDemand() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, toStatus }: { id: string; toStatus: DemandStatus }) =>
      api.post<ResearchDemand>(`/research-demands/${id}/transition`, { toStatus }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['research-demands'] }),
  })
}

// --- lineage ---

export const usePositionLineage = (opportunityId: string | null) =>
  useQuery({
    queryKey: ['position-lineage', opportunityId],
    queryFn: () => api.get<PositionLineage>(`/opportunities/${opportunityId}/lineage`),
    enabled: !!opportunityId,
  })

/* ------------------------------------------------------------------ *
 * Supervisor matching (Phase 7 R5) — POST /research/supervisor-suggestions.
 *
 * The score is the *explanation*, not the number: every point is attributed
 * to a named reason, so "why was I not suggested?" has an answer. Reasons
 * worth zero points (a supervisor at capacity) are part of that answer and
 * are rendered like any other.
 * ------------------------------------------------------------------ */

/** One attributed contribution to a score. `points` may legitimately be 0. */
export interface MatchReason {
  factor: string
  points: number
  detail: string
}

export interface SupervisorSuggestion {
  personId: string
  personName: string
  /** Out of 100 — the backend weights are chosen to sum to 100. */
  score: number
  currentSupervisees: number
  atCapacity: boolean
  link: string
  reasons: MatchReason[]
}

/**
 * `criteria` comes back empty (`{}`) when neither an area nor a proposal was
 * supplied, so every field is optional.
 */
export interface MatchCriteria {
  researchArea?: string | null
  keywords?: string[]
  maxSupervisees?: number
}

export interface SupervisorSuggestionResult {
  criteria: MatchCriteria
  suggestions: SupervisorSuggestion[]
  /** Advisory-only caveat. Render verbatim; the UI must not contradict it. */
  note: string
}

export interface SuggestInput {
  researchAreaId?: string
  proposalText?: string
  limit?: number
}

/**
 * A mutation rather than a query: the request is driven by a form the user
 * submits, and re-running it is an explicit act, not a cache refresh.
 * 403 when the caller lacks `student.read`.
 */
export function useSupervisorSuggestions() {
  return useMutation({
    mutationFn: (body: SuggestInput) =>
      api.post<SupervisorSuggestionResult>('/research/supervisor-suggestions', body),
  })
}

/* ------------------------------------------------------------------ *
 * Relationship graph (Phase 7 R5) — GET /research/graph.
 * ------------------------------------------------------------------ */

export type GraphNodeKind = 'student' | 'project' | 'supervisor' | 'award' | 'funder' | 'funding'

export interface GraphNode {
  /** `"{kind}:{uuid}"` — edges reference this. */
  id: string
  kind: GraphNodeKind
  label: string
  sub?: string | null
  link?: string | null
  status?: string | null
}

export interface GraphEdge {
  source: string
  target: string
  label: string
}

export interface RelationshipGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
  /** Absent when nothing was in scope — `note` explains why instead. */
  counts?: { nodes: number; edges: number; students: number }
  note?: string
}

export interface GraphParams {
  studentId?: string
  awardId?: string
  limit?: number
}

/**
 * Row-scoped server-side: the caller only ever sees students they may see.
 * `enabled` lets a collapsed panel avoid fetching a graph nobody is looking at.
 */
export const useRelationshipGraph = (params: GraphParams & { enabled?: boolean } = {}) => {
  const { studentId, awardId, limit, enabled = true } = params
  const qs = new URLSearchParams()
  if (studentId) qs.set('studentId', studentId)
  if (awardId) qs.set('awardId', awardId)
  if (limit) qs.set('limit', String(limit))
  const query = qs.toString()
  return useQuery({
    queryKey: ['research-graph', studentId ?? 'all', awardId ?? 'all', limit ?? 40],
    queryFn: () => api.get<RelationshipGraph>(`/research/graph${query ? `?${query}` : ''}`),
    enabled,
  })
}

/* ------------------------------------------------------------------ *
 * Research areas — reference lookup.
 *
 * NOTE: there is no `GET /research-areas` endpoint on the backend yet
 * (grepped app/api/v1/routes.py; ResearchArea is a model with no router).
 * The hook is written against the shape the reference tables use elsewhere
 * and does not retry; SupervisorMatchPanel degrades to proposal-text-only
 * matching and says so when the call fails, rather than faking a list.
 * Flagged to the solution-architect for the backend-engineer.
 * ------------------------------------------------------------------ */

export interface ResearchArea {
  id: string
  name: string
  code?: string | null
}

export const useResearchAreas = () =>
  useQuery({
    queryKey: ['research-areas'],
    queryFn: () => api.get<ResearchArea[]>('/research-areas'),
    retry: false,
    staleTime: 5 * 60_000,
  })
