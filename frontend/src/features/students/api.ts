'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, uploadFile, type ListResponse } from '@/shared/api/client'

export type StudentStatus =
  | 'prospective' | 'registered' | 'active' | 'writing_up' | 'on_leave' | 'suspended'
  | 'completed' | 'withdrawn' | 'terminated'

/** Badge tone per status — shared by the students list and the student record. */
export const STUDENT_STATUS_TONE: Record<StudentStatus, 'secondary' | 'info' | 'success' | 'warning' | 'destructive'> = {
  prospective: 'secondary',
  registered: 'info',
  active: 'success',
  writing_up: 'success',
  on_leave: 'warning',
  suspended: 'warning',
  completed: 'success',
  withdrawn: 'destructive',
  terminated: 'destructive',
}

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
  /** Effective dating, Phase 6 — today's value of the dated facts (null = not recorded). */
  feeStatus?: string | null
  studyLocation?: string | null
  /** Phase 8b — the programme version the student is pinned to (detail endpoint only). */
  programmeVersion?: string | null
  /** Phase 9 — today's unit of assessment (id, and "code name" on the detail endpoint). */
  uoaId?: string | null
  uoa?: string | null
  /** Phase 10 — HESA Engagement fields (today's value for the dated ones). */
  feeEligibility?: string | null
  primarilyOutsideUk?: boolean | null
  studyIntention?: string | null
  incomingExchange?: boolean | null
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

/** Whole-cohort fallbacks for blank cells, chosen in the import dialog. */
export interface ImportDefaults {
  programme?: string
  startDate?: string
  funder?: string
}
export interface ImportPayload {
  file: File
  defaults?: ImportDefaults
}

const toForm = ({ file, defaults }: ImportPayload) => {
  const fd = new FormData()
  fd.append('file', file)
  if (defaults?.programme) fd.append('default_programme', defaults.programme)
  if (defaults?.startDate) fd.append('default_start_date', defaults.startDate)
  if (defaults?.funder) fd.append('default_funder', defaults.funder)
  return fd
}

// --- Settings-configurable import template (which columns the cohort import expects) ---

export type ImportTemplateField =
  | 'studentRef' | 'firstName' | 'surname' | 'email'
  | 'programme' | 'startDate' | 'studyMode' | 'status' | 'funder'

export interface ImportTemplateColumn {
  field: ImportTemplateField
  label: string
  enabled: boolean
  required: boolean
}

export interface ImportTemplate {
  columns: ImportTemplateColumn[]
}

export const useImportTemplate = () =>
  useQuery({
    queryKey: ['students', 'import-template'],
    queryFn: () => api.get<ImportTemplate>('/students/import/template'),
    staleTime: 5 * 60 * 1000,
  })

export const useSetImportTemplate = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (columns: ImportTemplateColumn[]) =>
      api.put<ImportTemplate>('/students/import/template', { columns }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['students', 'import-template'] }),
  })
}

/** Validate a cohort CSV without writing anything. */
export const useImportPreview = () =>
  useMutation({ mutationFn: (p: ImportPayload) => uploadFile<ImportResult>('/students/import/preview', toForm(p)) })

/** Enrol the cohort (idempotent on student ref). */
export const useImportCommit = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (p: ImportPayload) => uploadFile<ImportResult>('/students/import/commit', toForm(p)),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['students'] }),
  })
}
