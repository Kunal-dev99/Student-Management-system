'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type ListResponse } from '@/shared/api/client'

export type RelationshipType = 'applicant' | 'student' | 'employee' | 'alumni' | 'researcher'

export const RELATIONSHIP_TYPES: RelationshipType[] = [
  'applicant', 'student', 'employee', 'alumni', 'researcher',
]

export interface Relationship {
  id: string
  relationshipType: RelationshipType
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
  /** F2 — set when the person has been GDPR-erased. */
  pseudonymisedAt?: string | null
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

export function usePersons(search: string, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['persons', search],
    queryFn: () =>
      api.get<ListResponse<Person>>(
        `/persons?limit=50${search ? `&search=${encodeURIComponent(search)}` : ''}`,
      ),
    enabled: opts?.enabled ?? true,
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

// --- Phase 6.4 — identities held concurrently against ONE person_id ---
//
// A PGR who takes a demonstrating contract becomes an employee *as well as* a student.
// Opening a relationship never closes another, and nothing is overwritten, so the
// timeline keeps its full history.

export interface OpenRelationshipInput {
  relationshipType: RelationshipType
  validFrom?: string
  sourceSystem?: string
}

/** The API answers both mutations with the full identity picture for the person. */
export interface RelationshipsPayload {
  personId: string
  relationships: Array<{
    relationshipType: RelationshipType
    validFrom: string
    validTo: string | null
    sourceSystem: string | null
    current: boolean
  }>
  currentTypes: RelationshipType[]
}

export function usePersonRelationships(personId: string) {
  return useQuery({
    queryKey: ['person', personId, 'relationships'],
    queryFn: () => api.get<Relationship[]>(`/persons/${personId}/relationships`),
    enabled: !!personId,
  })
}

function invalidateIdentity(qc: ReturnType<typeof useQueryClient>, personId: string) {
  qc.invalidateQueries({ queryKey: ['person', personId, 'relationships'] })
  // Opening or closing an identity is itself a lifecycle event.
  qc.invalidateQueries({ queryKey: ['person', personId, 'timeline'] })
  qc.invalidateQueries({ queryKey: ['person', personId] })
}

/** 409 when that identity is already open. */
export function useOpenRelationship(personId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: OpenRelationshipInput) =>
      api.post<RelationshipsPayload>(`/persons/${personId}/relationships`, body),
    onSuccess: () => invalidateIdentity(qc, personId),
  })
}

export function useCloseRelationship(personId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (relationshipType: RelationshipType) =>
      api.post<RelationshipsPayload>(
        `/persons/${personId}/relationships/${relationshipType}/close`,
      ),
    onSuccess: () => invalidateIdentity(qc, personId),
  })
}


// -------- F2 — contacts + GDPR (merge / export / erase) --------

export type ContactChannel = 'email' | 'phone' | 'mobile' | 'address' | 'emergency'

export interface PersonContact {
  id: string
  channel: ContactChannel
  value: string
  label: string | null
  doNotContact: boolean
  verifiedAt: string | null
}

export const useContacts = (personId: string | null) =>
  useQuery({
    queryKey: ['person', personId, 'contacts'],
    queryFn: () => api.get<PersonContact[]>(`/persons/${personId}/contacts`),
    enabled: !!personId,
  })

export function useAddContact(personId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { channel: ContactChannel; value: string; label?: string; doNotContact?: boolean }) =>
      api.post<PersonContact>(`/persons/${personId}/contacts`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['person', personId, 'contacts'] }),
  })
}

export function useUpdateContact(personId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<{ value: string; label: string; doNotContact: boolean; verified: boolean }> }) =>
      api.patch<PersonContact>(`/persons/${personId}/contacts/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['person', personId, 'contacts'] }),
  })
}

export function useDeleteContact(personId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.del<void>(`/persons/${personId}/contacts/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['person', personId, 'contacts'] }),
  })
}

export interface MergeResult {
  mergeId: string
  survivingPersonId: string
  losingPersonId: string
  touched: Record<string, number>
  totalRowsRewritten: number
  mergedAt: string
}

export function useMergePersons() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { survivingPersonId: string; losingPersonId: string; reason?: string }) =>
      api.post<MergeResult>('/persons/merge', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['persons'] }),
  })
}

export interface GdprExport {
  personId: string
  generatedAt: string
  person: Record<string, unknown>
  related: Record<string, Record<string, unknown>[]>
}

export function useGdprExport(personId: string) {
  return useMutation({
    mutationFn: () => api.get<GdprExport>(`/persons/${personId}/export`),
  })
}

export function useGdprErase(personId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<{ personId: string; erasedAt: string }>(`/persons/${personId}/erase`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['person', personId] }),
  })
}
