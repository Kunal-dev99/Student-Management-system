'use client'

/** Effective dating, Phase 5 — the student's dated history, the as-of view and the
 *  retrospective check against signed-off returns. */

import { useQuery } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export type HistoryFact =
  | 'status' | 'programme' | 'intensity' | 'expected_end' | 'fee_status' | 'fee_eligibility' | 'location'
  | 'outside_uk' | 'uoa' | 'module' | 'funding' | 'supervision' | 'custom' | 'supervisor_uoa'

export interface SignedReturn {
  profileId: string
  code: string
  name: string
  academicYear: string
  signedOffAt: string
}

export interface RetrospectiveWarning extends SignedReturn {
  message: string
}

export interface HistoryEntry {
  id: string | null
  fact: HistoryFact
  label: string
  value: string | number | null
  validFrom: string
  /** Exclusive — the first day no longer true. null = still in force. */
  validTo: string | null
  origin: string | null
  reason: string | null
  recordedAt: string | null
  recordedBy: string | null
  superseded: boolean
  /** Signed-off returns this period reached after their sign-off. */
  retrospective: SignedReturn[]
  detail: Record<string, unknown>
}

export interface StudentHistory {
  studentId: string
  startDate: string | null
  signedOffReturns: SignedReturn[]
  retrospectiveCount: number
  entries: HistoryEntry[]
}

export interface StudentAsOf {
  studentId: string
  asOf: string
  beforeStart: boolean
  status: string | null
  programmeId: string | null
  programmeName: string | null
  intensityPct: number | null
  studyMode: string | null
  feeStatus: string | null
  studyLocation: string | null
  /** Phase 9 — unit of assessment on that date ("code name"). */
  uoa: string | null
  /** Phase 10 — Engagement facts as held on that date. */
  expectedEndDate: string | null
  feeEligibility: string | null
  primarilyOutsideUk: boolean | null
  /** Custom attributes that keep dated history, as on that date. */
  custom: { key: string; label: string; value: string }[]
  modules: { moduleEnrolmentId: string; code: string; title: string; academicYear: string; status: string }[]
  funding: { id: string; type: string; source: string | null; contributionPct: number | null; validFrom: string; validTo: string | null }[]
  supervisors: { id: string; role: string; name: string; validFrom: string; validTo: string | null }[]
}

export interface RetrospectiveCheck {
  from: string
  to: string | null
  /** A signed-off return covers this period — changing it is a data amendment. */
  closed: boolean
  /** The user holds returns.amend. */
  canAmend: boolean
  warnings: RetrospectiveWarning[]
}

export interface RetrospectiveChange {
  fact: HistoryFact
  value: string | null
  validFrom: string
  validTo: string | null
  origin: string | null
  reason: string | null
  recordedAt: string | null
  recordedByUserId: string | null
  superseded: boolean
}

export interface RetrospectiveChanges {
  profileId: string
  code: string
  name: string
  academicYear: string
  signedOffAt: string | null
  signedOff: boolean
  changeCount: number
  students: { studentId: string; studentRef: string | null; name: string | null; changes: RetrospectiveChange[] }[]
}

export const useStudentHistory = (studentId: string, includeSuperseded = false) =>
  useQuery({
    queryKey: ['student', studentId, 'history', includeSuperseded],
    queryFn: () => api.get<StudentHistory>(
      `/students/${studentId}/history${includeSuperseded ? '?includeSuperseded=true' : ''}`),
    enabled: !!studentId,
  })

export const useStudentAsOf = (studentId: string, date: string | null) =>
  useQuery({
    queryKey: ['student', studentId, 'as-of', date],
    queryFn: () => api.get<StudentAsOf>(`/students/${studentId}/as-of?date=${date}`),
    enabled: !!studentId && !!date,
  })

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

/** Live check while a date is being chosen. Only runs for a complete date. */
export const useRetrospectiveCheck = (studentId: string | undefined, from: string | null | undefined, to?: string | null) =>
  useQuery({
    queryKey: ['student', studentId, 'retrospective-check', from, to ?? null],
    queryFn: () => {
      const qs = new URLSearchParams({ from: from as string })
      if (to && ISO_DATE.test(to)) qs.set('to', to)
      return api.get<RetrospectiveCheck>(`/students/${studentId}/retrospective-check?${qs.toString()}`)
    },
    enabled: !!studentId && !!from && ISO_DATE.test(from),
    staleTime: 60_000,
  })

export const useRetrospectiveChanges = (profileId: string | null, enabled = true) =>
  useQuery({
    queryKey: ['report-profile', profileId, 'retrospective-changes'],
    queryFn: () => api.get<RetrospectiveChanges>(`/report-profiles/${profileId}/retrospective-changes`),
    enabled: !!profileId && enabled,
  })

/** Inclusive end date for display: the day before the exclusive ``validTo``. */
export function inclusiveEnd(validTo: string | null): string | null {
  if (!validTo) return null
  const d = new Date(`${validTo}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() - 1)
  return d.toISOString().slice(0, 10)
}

/** Today in the user's own timezone, as YYYY-MM-DD. */
export function todayIso(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
