'use client'

/**
 * PGR exception lifecycle (Phase 6.5) — suspensions, extensions, mode changes.
 *
 * Requesting an event changes nothing; only approval moves dates. Approval returns the
 * recalculation alongside the event so the UI can explain the arithmetic in plain English.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export type LifecycleEventType =
  | 'suspension' | 'extension' | 'mode_change' | 'intensity_change' | 'programme_change'
export type LifecycleEventStatus = 'requested' | 'approved' | 'rejected' | 'cancelled'

export type LeaveCategory = 'medical' | 'personal' | 'academic' | 'other'
export const LEAVE_CATEGORIES: readonly LeaveCategory[] = ['medical', 'personal', 'academic', 'other']
export type StudyMode = 'full_time' | 'part_time'

export interface LifecycleEvent {
  id: string
  studentId: string
  eventType: LifecycleEventType
  status: LifecycleEventStatus
  startDate: string
  endDate: string | null
  actualEndDate: string | null
  extensionDays: number | null
  previousMode: StudyMode | null
  newMode: StudyMode | null
  previousIntensityPct: number | null
  intensityPct: number | null
  /** ICR programme-transfer — the old/new programme ids on an approved programme_change event. */
  previousProgrammeId: string | null
  newProgrammeId: string | null
  /** Effective date of a programme_change (equal to startDate on the wire, exposed separately for clarity). */
  effectiveDate: string | null
  reason: string | null
  /** Suspension only — medical / personal / academic / other. Null on non-suspensions. */
  leaveCategory: LeaveCategory | null
  daysApplied: number | null
  decisionNote: string | null
  decidedAt: string | null
  /** ICR G6 — deterministic "what will this do" preview, present on a requested intensity change. */
  impact: IntensityImpact | null
}

export interface ImpactMilestone {
  name: string
  currentDue: string
  projectedDue: string
}

export interface IntensityImpact {
  daysDelta: number
  projectedEnd: string | null
  milestonesAffected: number
  summary: string
  previousPct?: number
  newPct?: number
  startDate?: string | null
  currentEnd?: string | null
  milestones?: ImpactMilestone[]
}

export interface IntensityImpactNarrated extends IntensityImpact {
  narration: string
  narrationSource: 'model' | 'fallback'
  model: string | null
}

/** ICR G6 — lazy: the AI-worded impact of a pending intensity change, fetched when the approver
 * opens the decision. Grounded on the deterministic figures; falls back to them if the model is off. */
export const useIntensityImpact = (eventId: string, enabled: boolean) =>
  useQuery({
    queryKey: ['intensity-impact', eventId],
    queryFn: () => api.get<IntensityImpactNarrated>(`/lifecycle-events/${eventId}/impact`),
    enabled: enabled && !!eventId,
    staleTime: 5 * 60 * 1000,
  })

export interface IntensityPeriod { from: string; to: string; pct: number }
export interface IntensityOverview {
  studentId: string
  currentPct: number | null
  periods: IntensityPeriod[]
}

export const useStudentIntensity = (studentId: string) =>
  useQuery({
    queryKey: ['intensity', studentId],
    queryFn: () => api.get<IntensityOverview>(`/students/${studentId}/intensity`),
    enabled: !!studentId,
  })

export interface RecalculationBreakdown {
  eventType: LifecycleEventType
  days: number
  from: string
}

export interface Recalculation {
  originalExpectedEnd: string | null
  newExpectedEnd: string | null
  totalDaysApplied: number
  breakdown: RecalculationBreakdown[]
  milestonesShifted: number
  note: string
}

/** Decisions and returns both answer with the event plus the arithmetic that moved the dates. */
export interface LifecycleDecisionResult {
  event: LifecycleEvent
  recalculation: Recalculation | null
}

export interface LifecycleEventRequest {
  eventType: LifecycleEventType
  reason: string
  startDate: string
  endDate?: string
  extensionDays?: number
  newMode?: StudyMode
  intensityPct?: number
  /** Required for a programme_change — startDate is the effective date. */
  newProgrammeId?: string
  /** Suspension only — medical / personal / academic / other. Silently dropped on other types. */
  leaveCategory?: LeaveCategory
}

export const useLifecycleEvents = (studentId: string) =>
  useQuery({
    queryKey: ['lifecycle', studentId],
    queryFn: () => api.get<LifecycleEvent[]>(`/students/${studentId}/lifecycle-events`),
    enabled: !!studentId,
  })

/**
 * Approving an event shifts the expected end date *and* every undecided milestone, so the
 * student record and the milestone list are both stale the moment a decision lands.
 */
function invalidate(qc: ReturnType<typeof useQueryClient>, studentId: string) {
  qc.invalidateQueries({ queryKey: ['lifecycle', studentId] })
  qc.invalidateQueries({ queryKey: ['student', studentId] })
  qc.invalidateQueries({ queryKey: ['intensity', studentId] })
  qc.invalidateQueries({ queryKey: ['milestones', studentId] })
  // Programme-change approvals shift programmeId + taught state; refresh both so the
  // Programme tab and journey tracker reflect the new programme without a page reload.
  qc.invalidateQueries({ queryKey: ['taught', studentId] })
  qc.invalidateQueries({ queryKey: ['students'] })
  qc.invalidateQueries({ queryKey: ['tasks'] })
}

/** 422 when the dates or the student status make the request impossible; 409 on overlap. */
export function useRequestLifecycleEvent(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: LifecycleEventRequest) =>
      api.post<LifecycleEvent>(`/students/${studentId}/lifecycle-events`, body),
    onSuccess: () => invalidate(qc, studentId),
  })
}

/** Programme-change requests piggy-back on the shared lifecycle request endpoint; this thin
 * wrapper makes the call-site read like what it does and forces the payload shape. */
export interface ProgrammeChangeRequestBody {
  newProgrammeId: string
  /** The date the new programme is treated as starting from. */
  effectiveDate: string
  reason: string
}

export function useRequestProgrammeChange(studentId: string) {
  const request = useRequestLifecycleEvent(studentId)
  return {
    ...request,
    mutateAsync: (body: ProgrammeChangeRequestBody) =>
      request.mutateAsync({
        eventType: 'programme_change',
        reason: body.reason,
        startDate: body.effectiveDate,
        newProgrammeId: body.newProgrammeId,
      }),
  }
}

/** 409 when the request has already been decided. */
export function useApproveLifecycleEvent(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ eventId, note }: { eventId: string; note?: string }) =>
      api.post<LifecycleDecisionResult>(`/lifecycle-events/${eventId}/approve`, { note }),
    onSuccess: () => invalidate(qc, studentId),
  })
}

export function useRejectLifecycleEvent(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ eventId, note }: { eventId: string; note?: string }) =>
      api.post<LifecycleDecisionResult>(`/lifecycle-events/${eventId}/reject`, { note }),
    onSuccess: () => invalidate(qc, studentId),
  })
}

/** 422 when the student is not currently suspended. */
export function useRecordReturn(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { returnedOn?: string }) =>
      api.post<LifecycleDecisionResult>(`/students/${studentId}/return`, body),
    onSuccess: () => invalidate(qc, studentId),
  })
}
