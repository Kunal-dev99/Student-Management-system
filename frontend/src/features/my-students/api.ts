'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export interface NextMilestone {
  name: string
  status: string
  dueDate: string | null
  daysUntilDue: number | null
}

export interface MyStudentRow {
  relationshipId: string
  studentId: string
  studentRef: string
  personName: string
  role: string
  lastMeetingOn: string | null
  nextMilestone: NextMilestone | null
  openFlags: string[]
}

export interface MyStudentsPayload {
  students: MyStudentRow[]
  summary: { total: number; flagged: number }
}

export const useMyStudents = () =>
  useQuery({
    queryKey: ['my-students'],
    queryFn: () => api.get<MyStudentsPayload>('/my/students'),
  })
