'use client'

import { useQuery } from '@tanstack/react-query'
import { api, type ListResponse } from '@/shared/api/client'

export interface Relationship {
  id: string
  relationshipType: 'applicant' | 'student' | 'employee' | 'alumni' | 'researcher'
  validFrom: string
  validTo: string | null
  sourceSystem: string | null
}

export interface Person {
  id: string
  externalPersonRef: string | null
  givenName: string
  familyName: string
  preferredName: string | null
  email: string | null
  dateOfBirth: string | null
  nationality: string | null
  createdAt: string
  updatedAt: string
  relationships: Relationship[]
}

export interface TimelineEntry {
  kind: string
  label: string
  at: string
  detail: Record<string, unknown>
}
export interface Timeline {
  personId: string
  entries: TimelineEntry[]
}

export function usePersons(search: string) {
  return useQuery({
    queryKey: ['persons', search],
    queryFn: () =>
      api.get<ListResponse<Person>>(
        `/persons?limit=50${search ? `&search=${encodeURIComponent(search)}` : ''}`,
      ),
  })
}

export function usePerson(id: string) {
  return useQuery({
    queryKey: ['person', id],
    queryFn: () => api.get<Person>(`/persons/${id}`),
    enabled: !!id,
  })
}

export function usePersonTimeline(id: string) {
  return useQuery({
    queryKey: ['person', id, 'timeline'],
    queryFn: () => api.get<Timeline>(`/persons/${id}/timeline`),
    enabled: !!id,
  })
}
