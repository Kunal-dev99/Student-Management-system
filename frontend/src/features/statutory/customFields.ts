'use client'

/**
 * Admin-defined custom student attributes — the HESA gap-capture feature.
 *
 * When a statutory return needs an attribute the core model doesn't hold, someone requests a
 * custom attribute here. A different person approves (or rejects, with a reason) and activates it
 * — maker-checker. Only an active attribute takes values per student and is offered by the
 * statutory mapping picker as `custom.<key>`.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export type CustomFieldType = 'string' | 'number' | 'date' | 'code'
export type CustomFieldStatus = 'pending' | 'approved' | 'rejected' | 'active' | 'review' | 'retired'

export interface CustomField {
  id: string
  key: string
  label: string
  dataType: CustomFieldType
  reason: string
  sourcePath: string   // "custom.<key>" — paste straight into a mapping
  /** Effective dating, Phase 6 — values are recorded with the date they took effect. One-way. */
  trackHistory: boolean
  status: CustomFieldStatus
  requestedBy: string | null
  requestedByEmail: string | null
  decidedBy: string | null
  decidedByEmail: string | null
  decidedAt: string | null
  decisionReason: string | null
  createdAt: string | null
  /** Latest necessity check (governance Phase 2); null if it hasn't run. */
  assessment?: CustomFieldAssessment | null
  /** Catalogue / detail only (Phase 3). */
  usage?: { valueCount: number; lastValueUpdate: string | null; mappingCount: number } | null
}

export interface CustomFieldDependency {
  profileId: string
  profileCode: string
  profileName: string
  academicYear: string
  profileActive: boolean
  signedOff: boolean
  mappingId: string
  targetField: string
  required: boolean
  /** A live, not-signed-off mapping — the attribute can't be retired while it exists. */
  blocksRetirement: boolean
}

export interface CustomFieldDetail extends CustomField {
  dependencies: CustomFieldDependency[]
  events: CustomFieldEvent[]
}

export type LifecycleAction = 'review' | 'keep' | 'retire' | 'restore'

export type AssessmentVerdict = 'duplicate' | 'review' | 'supported' | 'no_hesa_basis'

export interface HesaFieldMatch {
  pack: string
  academicYear: string
  version: number
  field: string
  description: string
  allowed: string[]
  required: boolean
  source: string
  keyedAt: string
  score: number
  match: 'exact' | 'near'
  how: 'named' | 'description'
}

export interface CustomFieldAssessment {
  id?: string
  at?: string | null
  verdict: AssessmentVerdict
  flags: string[]
  coreMatches: { path: string; label: string; type: string; score: number; match: 'exact' | 'near' }[]
  customMatches: { id: string; key: string; label: string; status: CustomFieldStatus; score: number; match: 'exact' | 'near' }[]
  hesa: {
    requirement: 'required' | 'optional' | 'already_sourced' | 'not_found'
    match: HesaFieldMatch | null
    alternatives: HesaFieldMatch[]
    specification: string | null
  }
  suggested: { dataType: CustomFieldType; allowedValues: string[] }
  method: string
}

export interface CustomFieldEvent {
  id: string
  customFieldId: string | null
  key: string
  label: string
  action: string
  fromStatus: string | null
  toStatus: string | null
  actorEmail: string | null
  notes: string | null
  at: string | null
}

export interface CustomFieldValueRow {
  studentId: string
  studentRef: string
  studentName: string
  value: string | null
}

const REQ = '/students/custom-attribute-requests'

/** Live attributes (active / under review) — the ones that take values and can be mapped. */
export const useCustomFields = () =>
  useQuery({
    queryKey: ['custom-fields'],
    queryFn: () => api.get<CustomField[]>('/students/custom-fields'),
  })

/** Requests awaiting or past a decision (pending, approved, rejected). */
export const useCustomFieldRequests = (enabled: boolean) =>
  useQuery({
    queryKey: ['custom-field-requests'],
    queryFn: () => api.get<CustomField[]>(REQ),
    enabled,
  })

export const useCustomFieldEvents = (enabled: boolean) =>
  useQuery({
    queryKey: ['custom-field-events'],
    queryFn: () => api.get<CustomFieldEvent[]>('/students/custom-attribute-events'),
    enabled,
  })

/** Every attribute that has been live (active, review, retired), with usage. */
export const useCustomFieldCatalogue = (status: string | null, enabled: boolean) =>
  useQuery({
    queryKey: ['custom-field-catalogue', status],
    queryFn: () => api.get<CustomField[]>(
      `/students/custom-attributes/catalogue${status ? `?status=${encodeURIComponent(status)}` : ''}`),
    enabled,
  })

export const useCustomFieldDetail = (id: string | null) =>
  useQuery({
    queryKey: ['custom-field-detail', id],
    queryFn: () => api.get<CustomFieldDetail>(`/students/custom-attributes/${id}`),
    enabled: !!id,
  })

/** Anything that changes an attribute's status refreshes every list that shows it, plus the
 *  mapping picker (it lists live custom paths from the record-schema catalog). */
const useInvalidateAll = () => {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: ['custom-fields'] })
    qc.invalidateQueries({ queryKey: ['custom-field-requests'] })
    qc.invalidateQueries({ queryKey: ['custom-field-events'] })
    qc.invalidateQueries({ queryKey: ['custom-field-catalogue'] })
    qc.invalidateQueries({ queryKey: ['custom-field-detail'] })
    qc.invalidateQueries({ queryKey: ['report-profile-record-schema'] })
  }
}

/** Review / keep / retire / restore (Phase 3). Retire and restore need a reason. */
export const useCustomFieldLifecycle = () => {
  const invalidate = useInvalidateAll()
  return useMutation({
    mutationFn: ({ id, action, reason }: { id: string; action: LifecycleAction; reason?: string }) =>
      api.post<CustomField>(`/students/custom-attributes/${id}/${action}`, { reason: reason || null }),
    onSuccess: invalidate,
  })
}

export const useRequestCustomField = () => {
  const invalidate = useInvalidateAll()
  return useMutation({
    mutationFn: (body: { label: string; dataType: CustomFieldType; reason: string; trackHistory?: boolean }) =>
      api.post<CustomField>(REQ, body),
    onSuccess: invalidate,
  })
}

export const useApproveCustomField = () => {
  const invalidate = useInvalidateAll()
  return useMutation({
    mutationFn: ({ id, reason, activate }: { id: string; reason?: string; activate?: boolean }) =>
      api.post<CustomField>(`${REQ}/${id}/approve`, { reason: reason || null, activate: !!activate }),
    onSuccess: invalidate,
  })
}

export const useRejectCustomField = () => {
  const invalidate = useInvalidateAll()
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      api.post<CustomField>(`${REQ}/${id}/reject`, { reason }),
    onSuccess: invalidate,
  })
}

export const useActivateCustomField = () => {
  const invalidate = useInvalidateAll()
  return useMutation({
    mutationFn: (id: string) => api.post<CustomField>(`${REQ}/${id}/activate`),
    onSuccess: invalidate,
  })
}

/** Preview the necessity check for a request that hasn't been raised (nothing is saved). */
export const useCheckCustomField = (body: { label: string; reason: string; dataType: CustomFieldType }, enabled: boolean) =>
  useQuery({
    queryKey: ['custom-field-check', body.label, body.reason, body.dataType],
    queryFn: () => api.post<CustomFieldAssessment>(`${REQ}/check`, body),
    enabled,
    staleTime: 60_000,
  })

/** Re-run the check for a raised request (e.g. after a new spec version was accepted). */
export const useReassessCustomField = () => {
  const invalidate = useInvalidateAll()
  return useMutation({
    mutationFn: (id: string) => api.post<CustomFieldAssessment>(`${REQ}/${id}/assess`),
    onSuccess: invalidate,
  })
}

/** Withdraw a pending request (the requester, or an approver). */
export const useWithdrawCustomField = () => {
  const invalidate = useInvalidateAll()
  return useMutation({
    mutationFn: (id: string) => api.del(`${REQ}/${id}`),
    onSuccess: invalidate,
  })
}

/** Start keeping dated history for an attribute (one-way). */
export const useEnableCustomFieldHistory = () => {
  const invalidate = useInvalidateAll()
  return useMutation({
    mutationFn: (id: string) => api.post<CustomField>(`/students/custom-fields/${id}/track-history`),
    onSuccess: invalidate,
  })
}

export const useCustomFieldValues = (fieldId: string | null) =>
  useQuery({
    queryKey: ['custom-fields', fieldId, 'values'],
    queryFn: () => api.get<{ field: CustomField; rows: CustomFieldValueRow[] }>(
      `/students/custom-fields/${fieldId}/values`,
    ),
    enabled: !!fieldId,
  })

export const useSetCustomFieldValues = (fieldId: string | null) => {
  const qc = useQueryClient()
  return useMutation({
    /** ``effectiveDate`` applies to attributes that keep history (default today). */
    mutationFn: ({ values, effectiveDate }: { values: { studentId: string; value: string | null }[]; effectiveDate?: string }) =>
      api.put<{ filled: number }>(`/students/custom-fields/${fieldId}/values`,
        effectiveDate ? { values, effectiveDate } : { values }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['custom-fields', fieldId, 'values'] })
      qc.invalidateQueries({ queryKey: ['student'] })
    },
  })
}
