'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export interface IntegrationLog {
  id: string
  direction: 'inbound' | 'outbound'
  system: string
  eventType: string
  status: 'success' | 'failed' | 'skipped' | 'duplicate'
  sourceId: string | null
  detail: Record<string, unknown> | null
  createdAt: string
}
export interface IntegrationOverview {
  pending: number
  logs: IntegrationLog[]
}

export const useIntegration = () =>
  useQuery({ queryKey: ['integration'], queryFn: () => api.get<IntegrationOverview>('/integration/logs'), refetchInterval: 20_000 })

export function useDispatch() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<{ dispatched: number; outboundCalls: number }>('/integration/dispatch'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['integration'] }),
  })
}

/* ------------------------------------------------------------------ *
 * Reconciliation (Phase 7 R3) — "is the boundary healthy, and what
 * needs a human?" Backed by GET /integration/reconciliation.
 * ------------------------------------------------------------------ */

export interface DeadLetter {
  id: string
  eventType: string
  attempts: number
  lastError: string | null
  createdAt: string | null
}

export interface FailedInbound {
  id: string
  system: string
  eventType: string
  sourceId: string | null
  error: string | null
  createdAt: string | null
}

export interface UnmatchedHrRecord {
  taskId: string
  title: string
  /** Free-form task payload; keys seen so far: givenName, familyName, email, reason. */
  payload: Record<string, unknown> | null
  createdAt: string | null
}

/** status -> count. A system may report only one direction, so both are optional. */
export type StatusCounts = Record<string, number>
export interface SystemTraffic {
  inbound?: StatusCounts
  outbound?: StatusCounts
}

export interface ReconciliationReport {
  windowDays: number
  outbound: {
    pending: number
    dispatchedInWindow: number
    deadLettered: number
    oldestPendingAt: string | null
    deadLetters: DeadLetter[]
  }
  inbound: {
    bySystem: Record<string, SystemTraffic>
    failed: FailedInbound[]
  }
  awaitingPeople: { unmatchedHrRecords: UnmatchedHrRecord[] }
  healthy: boolean
  issueCount: number
}

export const useReconciliation = (windowDays = 30) =>
  useQuery({
    queryKey: ['integration', 'reconciliation', windowDays],
    queryFn: () => api.get<ReconciliationReport>(`/integration/reconciliation?windowDays=${windowDays}`),
    refetchInterval: 60_000,
  })

/** F5 — bulk replay of dead-letters in one audited call. */
export interface BulkReplayResult {
  requested: number
  replayed: number
  results: Record<string, boolean>
}

export function useReplayDeadLettersBulk() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ids: string[]) =>
      api.post<BulkReplayResult>('/integration/dead-letters/replay', { ids }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['integration'] }),
  })
}


/** Reset a dead-lettered outbox event so the next dispatch retries it. */
export function useReplayDeadLetter() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (eventId: string) =>
      api.post<{ data: { replayed: boolean } }>(`/integration/dead-letters/${eventId}/replay`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['integration'] })
      qc.invalidateQueries({ queryKey: ['integration', 'reconciliation'] })
    },
  })
}

export interface ScheduledRunResult {
  milestonesGenerated: number
  fundingExpiringFlagged: number
  overdueTasksEscalated: number
  viewsRefreshed: string
}

export function useRunScheduledJobs() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<ScheduledRunResult>('/admin/scheduled-jobs/run'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['integration'] })
    },
  })
}
