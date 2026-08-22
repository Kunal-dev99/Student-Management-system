'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export type FundingType = 'research_council' | 'university_scholarship' | 'external' | 'self_funded'
export type FundingStatus = 'planned' | 'active' | 'changed' | 'ended'
export type PaymentFrequency = 'monthly' | 'quarterly' | 'termly' | 'annual' | 'one_off'
export type PaymentStatus = 'scheduled' | 'approved' | 'paid' | 'held' | 'cancelled'
export type WaiverKind = 'full_fee' | 'partial_fee' | 'bench_fee'

export interface FundingSource { id: string; name: string; funderType: string | null }

export interface Arrangement {
  id: string
  studentId: string
  fundingType: FundingType
  fundingSourceId: string | null
  fundingSourceName: string | null
  stipendAmount: string | null
  currency: string | null
  validFrom: string
  validTo: string | null
  status: FundingStatus
  // Phase 4B.7 — finance detail for reconciliation and blended funding.
  costCentre: string | null
  projectCode: string | null
  funderReference: string | null
  contributionPct: number | null
  paymentFrequency: PaymentFrequency | null
  researchAwardId: string | null
}

export interface FundingInput {
  fundingType: FundingType
  fundingSourceId?: string
  stipendAmount?: string
  currency?: string
  costCentre?: string
  projectCode?: string
  funderReference?: string
  contributionPct?: number
  /** Phase 6.3 — ties the money to the research award it is drawn from. */
  researchAwardId?: string
}

export const useFundingSources = () =>
  useQuery({ queryKey: ['funding-sources'], queryFn: () => api.get<FundingSource[]>('/funding-sources') })

export const useFunding = (studentId: string) =>
  useQuery({
    queryKey: ['funding', studentId],
    queryFn: () => api.get<Arrangement[]>(`/students/${studentId}/funding`),
    enabled: !!studentId,
  })

function invalidate(qc: ReturnType<typeof useQueryClient>, studentId: string) {
  qc.invalidateQueries({ queryKey: ['funding', studentId] })
  qc.invalidateQueries({ queryKey: ['student', studentId, 'summary'] })
  // The chain and its findings are derived from the arrangements — always re-derive.
  qc.invalidateQueries({ queryKey: ['funding-lineage', studentId] })
}

export function useCreateFunding(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: FundingInput) => api.post<Arrangement>(`/students/${studentId}/funding`, body),
    onSuccess: () => invalidate(qc, studentId),
  })
}
export function useChangeFunding(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: FundingInput }) => api.post<Arrangement>(`/funding/${id}/change`, body),
    onSuccess: () => invalidate(qc, studentId),
  })
}
export function useEndFunding(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.post<Arrangement>(`/funding/${id}/end`),
    onSuccess: () => invalidate(qc, studentId),
  })
}

// --- Phase 4B.7 — stipend payment schedule ---

export interface Payment {
  id: string
  arrangementId: string
  studentId: string
  sequence: number
  dueDate: string
  amount: string
  currency: string | null
  status: PaymentStatus
  paidOn: string | null
  financeReference: string | null
  note: string | null
}

export interface PaymentSummary {
  studentId: string
  instalments: number
  paidTotal: string
  committedTotal: string
  outstandingTotal: string
  currency: string | null
  overdue: Payment[]
}

export const usePayments = (arrangementId: string | undefined, enabled = true) =>
  useQuery({
    queryKey: ['funding-payments', arrangementId],
    queryFn: () => api.get<Payment[]>(`/funding/${arrangementId}/payments`),
    enabled: !!arrangementId && enabled,
  })

export const usePaymentSummary = (studentId: string) =>
  useQuery({
    queryKey: ['payment-summary', studentId],
    queryFn: () => api.get<PaymentSummary>(`/students/${studentId}/payment-summary`),
    enabled: !!studentId,
  })

function invalidatePayments(qc: ReturnType<typeof useQueryClient>, studentId: string, arrangementId?: string) {
  qc.invalidateQueries({ queryKey: ['funding-payments', arrangementId] })
  qc.invalidateQueries({ queryKey: ['payment-summary', studentId] })
}

export interface ScheduleInput {
  frequency: PaymentFrequency
  instalments?: number
  firstDue?: string
  annualAmount?: string
}

/** 409 when the arrangement already has paid instalments. */
export function useGenerateSchedule(studentId: string, arrangementId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: ScheduleInput) => api.post<Payment[]>(`/funding/${arrangementId}/payments/schedule`, body),
    onSuccess: () => {
      invalidatePayments(qc, studentId, arrangementId)
      invalidate(qc, studentId)
    },
  })
}

export function useApprovePayment(studentId: string, arrangementId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (paymentId: string) => api.post<Payment>(`/funding/payments/${paymentId}/approve`),
    onSuccess: () => invalidatePayments(qc, studentId, arrangementId),
  })
}

export function useMarkPaymentPaid(studentId: string, arrangementId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ paymentId, paidOn, financeReference }: { paymentId: string; paidOn?: string; financeReference?: string }) =>
      api.post<Payment>(`/funding/payments/${paymentId}/paid`, { paidOn, financeReference }),
    onSuccess: () => invalidatePayments(qc, studentId, arrangementId),
  })
}

export function useSetPaymentStatus(studentId: string, arrangementId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ paymentId, status, note }: { paymentId: string; status: PaymentStatus; note?: string }) =>
      api.post<Payment>(`/funding/payments/${paymentId}/status`, { status, note }),
    onSuccess: () => invalidatePayments(qc, studentId, arrangementId),
  })
}

// --- Phase 4B.7 — fee waivers ---

export interface FeeWaiver {
  id: string
  studentId: string
  arrangementId: string | null
  kind: WaiverKind
  amount: string | null
  percentage: number | null
  currency: string | null
  academicYear: string | null
  approved: boolean
  note: string | null
}

export interface WaiverInput {
  kind: WaiverKind
  amount?: string
  percentage?: number
  currency?: string
  academicYear?: string
  note?: string
}

export const useFeeWaivers = (studentId: string) =>
  useQuery({
    queryKey: ['fee-waivers', studentId],
    queryFn: () => api.get<FeeWaiver[]>(`/students/${studentId}/fee-waivers`),
    enabled: !!studentId,
  })

/** 422 when neither an amount nor a percentage is supplied. */
export function useCreateWaiver(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: WaiverInput) => api.post<FeeWaiver>(`/students/${studentId}/fee-waivers`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['fee-waivers', studentId] }),
  })
}

/** 409 when the waiver is already approved. */
export function useApproveWaiver(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (waiverId: string) => api.post<FeeWaiver>(`/funding/fee-waivers/${waiverId}/approve`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['fee-waivers', studentId] }),
  })
}

// --- Phase 6.3 — funding lineage and integrity ---
//
// Student → research project → research award → funder → arrangements → stipend.
// Every finding carries the dates or amounts that produced it, so it can be defended
// rather than merely displayed.

export type FindingSeverity = 'error' | 'warning' | 'info'

export interface FundingFinding {
  code: string
  severity: FindingSeverity
  message: string
  /** Evidence for the finding. Keys vary by `code`; `from_` carries a trailing underscore. */
  detail: Record<string, unknown>
}

export interface LineageAward {
  id: string
  awardRef: string
  title: string
  value: string | null
  currency: string | null
  startDate: string | null
  endDate: string | null
  funder: { id: string; name: string } | null
  sourceSystem: string | null
}

export interface LineageArrangement {
  id: string
  fundingType: FundingType
  status: FundingStatus
  validFrom: string
  validTo: string | null
  stipendAmount: string | null
  currency: string | null
  contributionPct: number | null
  costCentre: string | null
  projectCode: string | null
  funderReference: string | null
  fundingSource: { id: string; name: string } | null
  award: LineageAward | null
  instalments: number
  paidTotal: string
  committedTotal: string
}

export interface LineageProject {
  id: string
  researchTopic: string | null
  researchGroup: string | null
  startDate: string | null
  endDate: string | null
  award: LineageAward | null
}

export interface LineageStudent {
  id: string
  studentRef: string
  personName: string
  status: string
  startDate: string | null
  expectedEndDate: string | null
  link: string
}

export interface FundingLineage {
  student: LineageStudent
  project: LineageProject | null
  arrangements: LineageArrangement[]
  totals: { paid: string; committed: string; currency: string | null }
  findings: FundingFinding[]
  /** True when no `error`-severity finding was raised. */
  complete: boolean
}

export const useFundingLineage = (studentId: string) =>
  useQuery({
    queryKey: ['funding-lineage', studentId],
    queryFn: () => api.get<FundingLineage>(`/students/${studentId}/funding-lineage`),
    enabled: !!studentId,
  })

/** A student in the cohort report — the lineage `student` block plus its findings. */
export interface FundingIntegrityStudent extends LineageStudent {
  findings: FundingFinding[]
  worstSeverity: 'error' | 'warning'
}

export interface FundingIntegrityReport {
  checked: number
  withFindings: number
  errors: number
  warnings: number
  students: FundingIntegrityStudent[]
}

/** Cohort-wide funding integrity. Row-scoped by the API like every other read. */
export const useFundingIntegrity = (severity?: 'error') =>
  useQuery({
    queryKey: ['funding-integrity', severity ?? 'all'],
    queryFn: () =>
      api.get<FundingIntegrityReport>(
        `/reports/funding-integrity${severity ? `?severity=${severity}` : ''}`,
      ),
  })
