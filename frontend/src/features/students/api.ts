'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, uploadFile, type ListResponse } from '@/shared/api/client'

export type StudentStatus =
  | 'prospective' | 'registered' | 'active' | 'on_leave' | 'suspended'
  | 'completed' | 'withdrawn' | 'terminated'

export interface Student {
  id: string
  personId: string
  /** Joined for the register view — humans find students by name, not ref. */
  personName: string | null
  studentRef: string
  programmeId: string | null
  startDate: string | null
  expectedEndDate: string | null
  /** The end date agreed at registration, before any suspension/extension (Phase 6.5). */
  originalExpectedEndDate: string | null
  studyMode: 'full_time' | 'part_time'
  status: StudentStatus
  createdAt: string
  project: { id: string; researchTopic: string | null; researchGroup: string | null } | null
  /** ICR G2 — true if reached via the recruitment funnel (has an application), false if enrolled
   * directly. Only present on the single-student detail endpoint; drives the Applicant stage. */
  fromApplication?: boolean | null
}

export type ProgrammeType = 'research' | 'taught'

export interface StudentSummary {
  id: string
  studentRef: string
  personId: string
  personName: string
  status: StudentStatus
  studyMode: 'full_time' | 'part_time'
  startDate: string | null
  programmeId: string | null
  /** ICR G1 — drives whether the student-360 shows the research or taught panel set. */
  programmeType: ProgrammeType
  programmeName: string | null
  researchTopic: string | null
  supervisors: unknown[]
  funding: unknown[]
}

export interface UseStudentsParams {
  search?: string
  status?: StudentStatus | 'all'
  limit?: number
  offset?: number
}

export const useStudents = (params: UseStudentsParams = {}) => {
  const { search, status, limit = 50, offset = 0 } = params
  const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (search) qs.set('search', search)
  if (status && status !== 'all') qs.set('status', status)
  return useQuery({
    queryKey: ['students', search ?? '', status ?? 'all', limit, offset],
    queryFn: () => api.get<ListResponse<Student>>(`/students?${qs.toString()}`),
  })
}

export const useStudent = (id: string) =>
  useQuery({ queryKey: ['student', id], queryFn: () => api.get<Student>(`/students/${id}`), enabled: !!id })

export const useStudentSummary = (id: string) =>
  useQuery({ queryKey: ['student', id, 'summary'], queryFn: () => api.get<StudentSummary>(`/students/${id}/summary`), enabled: !!id })

// --- ICR G2 — enrol an already-accepted student directly (no recruitment funnel) ---

export interface EnrolStudentPayload {
  /** Supply exactly one of personId (attach existing) or person (create new). */
  personId?: string
  person?: { givenName: string; familyName: string; email?: string }
  programmeId?: string
  startDate?: string
  studyMode?: 'full_time' | 'part_time'
  status?: StudentStatus
  expectedEndDate?: string
}

export const useEnrolStudent = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: EnrolStudentPayload) => api.post<Student>('/students/enrol', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['students'] }),
  })
}

// --- ICR G2 (slice B) — cohort CSV import ---

export type ImportAction = 'create' | 'attach' | 'skip' | 'error'

export interface ImportRow {
  line: number
  name: string
  email: string | null
  studentRef: string | null
  programmeCode: string | null
  programmeName: string | null
  studyMode: string
  status: string
  funder: string | null
  action: ImportAction
  messages: string[]
}

export interface ImportResult {
  committed: boolean
  total: number
  toCreate: number
  skipped: number
  errors: number
  rows: ImportRow[]
}

const toForm = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return fd
}

/** Validate a cohort CSV without writing anything. */
export const useImportPreview = () =>
  useMutation({ mutationFn: (file: File) => uploadFile<ImportResult>('/students/import/preview', toForm(file)) })

/** Enrol the cohort (idempotent on student ref). */
export const useImportCommit = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => uploadFile<ImportResult>('/students/import/commit', toForm(file)),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['students'] }),
  })
}
