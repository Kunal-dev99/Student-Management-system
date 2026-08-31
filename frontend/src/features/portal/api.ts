'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export interface Journey {
  linked: boolean
  person: { name: string; email: string | null; timeline: { label: string; at: string; kind: string }[] } | null
  student: {
    id: string; studentRef: string; status: string; studyMode: string
    startDate: string | null; researchTopic: string | null
  } | null
  milestones: { id: string; name: string; status: string; dueDate: string | null }[]
  funding: { id: string; fundingType: string; stipendAmount: string | null; currency: string | null; status: string }[]
  supervision: {
    team: { id: string; supervisorName: string; role: string; validFrom: string | null }[]
    recentMeetings: {
      id: string; supervisorName: string | null; metOn: string; format: string
      durationMinutes: number | null; nextMeetingOn: string | null; studentConfirmed: boolean
    }[]
    meetingCount: number
  } | null
  thesis: { status: string; title: string | null; submittedAt: string | null; outcome: string | null } | null
}

export const useMyJourney = () =>
  useQuery({ queryKey: ['portal', 'journey'], queryFn: () => api.get<Journey>('/portal/journey') })
