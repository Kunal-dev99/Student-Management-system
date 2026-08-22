'use client'

/**
 * PGR exception lifecycle (Phase 6.5) — suspensions, extensions, mode changes.
 *
 * Requesting an event changes nothing; only approval moves dates. Approval returns the
 * recalculation alongside the event so the UI can explain the arithmetic in plain English.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export type LifecycleEventType = 'suspension' | 'extension' | 'mode_change'
export type LifecycleEventStatus = 'requested' | 'approved' | 'rejected' | 'cancelled'
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
  reason: string | null
  daysApplied: number | null
  decisionNote: string | null
  decidedAt: string | null
}

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
  qc.invalidateQueries({ queryKey: ['milestones', studentId] })
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
