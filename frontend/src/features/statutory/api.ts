'use client'

/**
 * Statutory report profiles (Phase 6.6).
 *
 * A statutory return is **configuration, not code**. HESA is an external specification that
 * changes every year; the PGR lifecycle does not. So a return is a versioned profile of field
 * mappings — target field ← source expression + transform + validation — and amending next
 * year's return means editing configuration, not shipping Python.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, uploadFile } from '@/shared/api/client'

export interface ReportProfile {
  id: string
  code: string
  name: string
  academicYear: string
  version: number
  description: string | null
  isActive: boolean
  /** Present on the list endpoint only. */
  fieldCount?: number
  /** F1 — sign-off. When true, the profile is immutable until unsigned. */
  signedOff: boolean
  signedOffAt: string | null
  signedOffBy: string | null
  signedOffNotes: string | null
}

export interface FieldMapping {
  id: string
  targetField: string
  position: number
  sourceExpression: string
  transform: string | null
  defaultValue: string | null
  required: boolean
  allowedValues: string[] | null
  /** ICR G5 — where this value is captured on the student record (from the spec), if known. */
  keyedAt?: string | null
}

export interface ProfileDetail extends ReportProfile {
  fields: FieldMapping[]
}

export interface ValidationIssue {
  studentRef: string
  field: string
  severity: string
  message: string
  sourceExpression?: string
  allowed?: string[]
}

export interface ValidationResult {
  errors: number
  warnings?: number
  issues: ValidationIssue[]
  valid: boolean
}

export interface SpecPack {
  key: string
  code: string
  name: string
  academicYear: string
  version: number
  fieldCount: number
}

export interface ValidationReport {
  profile: ReportProfile
  rowCount: number
  validation: ValidationResult
}

export interface GenerateResult {
  job: { id: string; filename: string | null; rowCount: number | null; status: string }
  profile: ReportProfile
  validation: ValidationResult
}

export const useProfiles = () =>
  useQuery({ queryKey: ['report-profiles'], queryFn: () => api.get<ReportProfile[]>('/report-profiles') })

export const useProfile = (profileId: string | null) =>
  useQuery({
    queryKey: ['report-profile', profileId],
    queryFn: () => api.get<ProfileDetail>(`/report-profiles/${profileId}`),
    enabled: !!profileId,
  })

/** The transforms a mapping may name. Server-owned, so never hard-coded here. */
export const useTransforms = () =>
  useQuery({
    queryKey: ['report-profile-transforms'],
    queryFn: () => api.get<{ transforms: string[] }>('/report-profiles/transforms'),
    staleTime: 60 * 60 * 1000,
  })

export interface ProfileInput {
  code: string
  name: string
  academicYear: string
  description?: string
}

/** 409 when that code/year/version already exists — clone it instead. */
export function useCreateProfile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: ProfileInput) => api.post<ReportProfile>('/report-profiles', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['report-profiles'] }),
  })
}

/** ICR G5 — the published spec packs a profile can be created pre-mapped from. */
export const useSpecs = () =>
  useQuery({
    queryKey: ['report-profile-specs'],
    queryFn: () => api.get<{ specs: SpecPack[] }>('/report-profiles/specs'),
    staleTime: 60 * 60 * 1000,
  })

/** ICR G5 — create a profile pre-mapped from a published HESA spec pack. */
export function useCreateFromSpec() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { specKey: string; academicYear?: string; name?: string }) =>
      api.post<ProfileDetail>('/report-profiles/from-spec', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['report-profiles'] }),
  })
}

export interface FieldInput {
  targetField: string
  sourceExpression: string
  position?: number
  transform?: string
  defaultValue?: string
  required?: boolean
  allowedValues?: string[]
}

/** 409 when the target field is already mapped; 422 for an unknown transform. */
export function useAddField(profileId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: FieldInput) => api.post<FieldMapping>(`/report-profiles/${profileId}/fields`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['report-profile', profileId] })
      qc.invalidateQueries({ queryKey: ['report-profiles'] })
    },
  })
}

/** Carrying a return forward to a new year — the usual way a statutory change is handled. */
export function useCloneProfile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, academicYear }: { id: string; academicYear: string }) =>
      api.post<ReportProfile>(`/report-profiles/${id}/clone`, { academicYear }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['report-profiles'] }),
  })
}

/**
 * Lazy on purpose: validating walks the whole student population, so it runs only when an
 * administrator asks. Call `refetch()`.
 */
export const useValidateProfile = (profileId: string | null) =>
  useQuery({
    queryKey: ['report-profile', profileId, 'validate'],
    queryFn: () => api.get<ValidationReport>(`/report-profiles/${profileId}/validate`),
    enabled: false,
    gcTime: 0,
  })

/** Produces the file as an export job; the validation report travels with it. */
export function useGenerateProfile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (profileId: string) => api.post<GenerateResult>(`/report-profiles/${profileId}/generate`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['exports'] }),
  })
}


// -------- F1 — sign-off, immutability, mandatory-field gap report --------

export interface CompileMissing {
  field: string
  description: string
  allowed: string[] | null
}

export interface CompileReport {
  profile: ReportProfile
  specCode: string
  specFieldCount: number
  mappedFieldCount: number
  missing: CompileMissing[]
  signOffReady: boolean
}

export const useCompileProfile = (profileId: string | null) =>
  useQuery({
    queryKey: ['report-profile', profileId, 'compile'],
    queryFn: () => api.get<CompileReport>(`/report-profiles/${profileId}/compile`),
    enabled: !!profileId,
  })

export function useUpdateField(profileId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<FieldInput> }) =>
      api.patch<FieldMapping>(`/report-profiles/${profileId}/fields/${id}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['report-profile', profileId] })
      qc.invalidateQueries({ queryKey: ['report-profile', profileId, 'compile'] })
    },
  })
}

export function useDeleteField(profileId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.del<void>(`/report-profiles/${profileId}/fields/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['report-profile', profileId] })
      qc.invalidateQueries({ queryKey: ['report-profile', profileId, 'compile'] })
      qc.invalidateQueries({ queryKey: ['report-profiles'] })
    },
  })
}

export function useSignOffProfile(profileId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (notes: string | undefined) =>
      api.post<ReportProfile>(`/report-profiles/${profileId}/sign-off`, { notes }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['report-profile', profileId] })
      qc.invalidateQueries({ queryKey: ['report-profile', profileId, 'compile'] })
      qc.invalidateQueries({ queryKey: ['report-profiles'] })
    },
  })
}

// -------- ICR G5 — data-quality fix assistant (rule-based suggest → accept → apply) --------

export interface FixSample { studentRef: string; before: string; after: string }
export interface FixSuggestion {
  field: string
  type: string
  label: string
  description: string
  transform: string
  applicable: boolean
  count: number
  samples: FixSample[]
}

/** Lazy: scans the cohort for data-quality issues and proposes rule-based fixes. Call refetch(). */
export const useFixSuggestions = (profileId: string | null) =>
  useQuery({
    queryKey: ['report-profile', profileId, 'fixes'],
    queryFn: () => api.get<{ suggestions: FixSuggestion[] }>(`/report-profiles/${profileId}/fix-suggestions`),
    enabled: false,
    gcTime: 0,
  })

/** Apply an accepted fix — cleans the return output (non-destructive); refused if signed off. */
export function useApplyFix(profileId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { field: string; transform: string }) =>
      api.post<{ field: string; transform: string; applied: boolean }>(`/report-profiles/${profileId}/apply-fix`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['report-profile', profileId] })
    },
  })
}

// ---------------------------------------------------------------- intelligent default suggestions

export interface DefaultSuggestion {
  field: string
  mappingId: string
  keyedAt: string | null
  required: boolean
  current: string | null
  allowedValues: string[]
  suggested: string | null
  reason: string
  /** Where the suggested value comes from: the cohort's own data, a spec convention, or nothing. */
  source: 'data' | 'convention' | 'skip'
  applicable: boolean
  evidence: {
    total: number
    populated: number
    empty: number
    unique: number
    topValues: { value: string; count: number }[]
  }
}

/** GET grounded per-field default suggestions (AI classify + rule fallback). */
export const useSuggestDefaults = (profileId: string | null) =>
  useQuery({
    queryKey: ['report-profile', profileId, 'suggest-defaults'],
    queryFn: () => api.get<{ suggestions: DefaultSuggestion[]; applicableCount: number }>(
      `/report-profiles/${profileId}/suggest-defaults`,
    ),
    enabled: false,
    gcTime: 0,
  })

/** Apply the accepted default picks in one call. */
export function useApplyDefaults(profileId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (picks: { field: string; value: string }[]) =>
      api.post<{ applied: string[]; count: number }>(`/report-profiles/${profileId}/apply-defaults`, { picks }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['report-profile', profileId] })
    },
  })
}

export function useUnsignProfile(profileId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<ReportProfile>(`/report-profiles/${profileId}/unsign`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['report-profile', profileId] })
      qc.invalidateQueries({ queryKey: ['report-profile', profileId, 'compile'] })
      qc.invalidateQueries({ queryKey: ['report-profiles'] })
    },
  })
}


// -------- ICR G5 — statutory advisory ingestion (ingest → recommend → accept) --------

export type AdvisoryStatus = 'ingested' | 'accepted' | 'rejected'
export type ChangeType =
  | 'field_added' | 'field_removed' | 'coding_changed'
  | 'description_changed' | 'rule_added' | 'rule_removed'

export interface AdvisoryChange {
  type: ChangeType
  field: string | null
  // before/after are shape-dependent (a coding list, a description, a rule object) — the UI
  // renders them defensively, so they stay loosely typed here.
  before: unknown
  after: unknown
  note: string
}

export interface Advisory {
  id: string
  packCode: string
  academicYear: string
  title: string
  status: AdvisoryStatus
  source: string
  baseVersion: number
  parseSource: string
  changes: AdvisoryChange[]
  proposedFields: Record<string, unknown>[]
  proposedRules: Record<string, unknown>[]
  createdAt: string
  decidedAt: string | null
  decisionNote: string | null
  /** Present only on a freshly-ingested response. */
  parseWarnings?: string[]
}

export const useAdvisories = () =>
  useQuery({
    queryKey: ['report-advisories'],
    queryFn: () => api.get<{ advisories: Advisory[] }>('/report-advisories'),
  })

export interface IngestInput {
  packCode: string
  academicYear?: string
  title?: string
  rawText: string
}

/** Parse a pasted advisory into a diff for review. Admin-configure gated server-side. */
export function useIngestAdvisory() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: IngestInput) => api.post<Advisory>('/report-advisories/ingest', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['report-advisories'] }),
  })
}

/** Assisted ingest — fetch a published advisory from a URL; the server AI-drafts the changes. */
export function useIngestAdvisoryFromUrl() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { packCode: string; academicYear?: string; title?: string; url: string }) =>
      api.post<Advisory>('/report-advisories/ingest-from-url', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['report-advisories'] }),
  })
}

/** Assisted ingest — upload a published advisory (PDF/notice); the server AI-drafts the changes. */
export function useIngestAdvisoryUpload() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (form: FormData) => uploadFile<Advisory>('/report-advisories/ingest-upload', form),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['report-advisories'] }),
  })
}

/** Accept an advisory — makes its proposed pack the active spec version (reports.signoff). */
export function useAcceptAdvisory() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, note }: { id: string; note?: string }) =>
      api.post<{ id: string; version: number; academicYear: string }>(
        `/report-advisories/${id}/accept`, { note }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['report-advisories'] })
      qc.invalidateQueries({ queryKey: ['report-profile-specs'] })
    },
  })
}

/** Reject an advisory — no change to the pack (reports.signoff). */
export function useRejectAdvisory() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, note }: { id: string; note?: string }) =>
      api.post<Advisory>(`/report-advisories/${id}/reject`, { note }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['report-advisories'] }),
  })
}
