'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export type MeetingFormat = 'in_person' | 'online' | 'hybrid'

export interface SupervisionMeeting {
  id: string
  studentId: string
  supervisorPersonId: string | null
  supervisorName: string | null
  metOn: string
  format: MeetingFormat
  durationMinutes: number | null
  notes: string | null
  actions: string | null
  nextMeetingOn: string | null
  studentConfirmed: boolean
}

export interface MeetingInput {
  supervisorPersonId?: string
  metOn: string
  format: MeetingFormat
  durationMinutes?: number
  notes?: string
  actions?: string
  nextMeetingOn?: string
}

export interface SupervisionCompliance {
  lastMeetingOn: string | null
  daysSince: number | null
  overdue: boolean
  expectedIntervalDays: number
}

export const useSupervisionMeetings = (studentId: string) =>
  useQuery({
    queryKey: ['supervision-meetings', studentId],
    queryFn: () => api.get<SupervisionMeeting[]>(`/students/${studentId}/supervision-meetings`),
    enabled: !!studentId,
  })

export const useSupervisionCompliance = (studentId: string) =>
  useQuery({
    queryKey: ['supervision-compliance', studentId],
    queryFn: () => api.get<SupervisionCompliance>(`/students/${studentId}/supervision-compliance`),
    enabled: !!studentId,
  })

function invalidate(qc: ReturnType<typeof useQueryClient>, studentId: string) {
  qc.invalidateQueries({ queryKey: ['supervision-meetings', studentId] })
  qc.invalidateQueries({ queryKey: ['supervision-compliance', studentId] })
  qc.invalidateQueries({ queryKey: ['caseload'] })
}

/** 422 when `metOn` is in the future — the message explains why. */
export function useRecordMeeting(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: MeetingInput) =>
      api.post<SupervisionMeeting>(`/students/${studentId}/supervision-meetings`, body),
    onSuccess: () => invalidate(qc, studentId),
  })
}

export function useConfirmMeeting(studentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (meetingId: string) =>
      api.post<SupervisionMeeting>(`/supervisors/meetings/${meetingId}/confirm`),
    onSuccess: () => invalidate(qc, studentId),
  })
}
