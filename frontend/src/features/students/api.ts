'use client'

import { useQuery } from '@tanstack/react-query'
import { api, type ListResponse } from '@/shared/api/client'

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
}

export interface StudentSummary {
  id: string
  studentRef: string
  personId: string
  personName: string
  status: StudentStatus
  studyMode: 'full_time' | 'part_time'
  startDate: string | null
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
