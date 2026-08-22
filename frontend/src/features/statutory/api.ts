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
import { api } from '@/shared/api/client'

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
  issues: ValidationIssue[]
  valid: boolean
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
