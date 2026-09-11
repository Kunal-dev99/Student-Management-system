'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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

/**
 * Student confirms a supervision meeting they attended.
 * The confirm is a signed act on the joint record — server writes who + when.
 */
export function useConfirmMeeting() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (meetingId: string) =>
      api.post(`/portal/meetings/${meetingId}/confirm`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portal', 'journey'] }),
  })
}

/**
 * Student records intent to submit their thesis. Starts the examiner-nomination
 * workflow downstream.
 */
export function useDeclareIntentToSubmit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (title: string | null) =>
      api.post('/portal/thesis/intent-to-submit', { title }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portal', 'journey'] }),
  })
}

/**
 * Documents attached to the student's own record.
 */
export type DocumentCategory =
  | 'thesis'
  | 'milestone'
  | 'research'
  | 'training'
  | 'ethics'
  | 'meetings'
  | 'admin'
  | 'other'

export interface PortalDocument {
  id: string
  ownerType: string
  ownerId: string
  docType: string | null
  category: DocumentCategory
  filename: string
  contentType: string
  sizeBytes: number | null
  scanStatus: string | null
  createdAt: string | null
}

export const useMyDocuments = () =>
  useQuery({
    queryKey: ['portal', 'documents'],
    queryFn: () => api.get<PortalDocument[]>('/portal/documents'),
  })

/**
 * Fetch a document from the portal with the auth header and trigger a browser download.
 * A plain `<a href>` on a JWT-gated endpoint would 401 because the browser doesn't
 * include the bearer token on top-level navigations — this is the standard workaround.
 */
export async function downloadPortalDocument(docId: string, filename: string) {
  const res = await api.raw(`/portal/documents/${docId}/download`, { method: 'GET' })
  if (!res.ok) throw new Error(`Download failed: ${res.status}`)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  // Chrome sometimes needs the blob URL alive briefly after click; revoke on next tick.
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function useUploadMyDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ file, category }: { file: File; category?: DocumentCategory }) => {
      const form = new FormData()
      form.append('file', file)
      if (category) form.append('category', category)
      // api.raw sends the request without JSON body handling — needed for multipart.
      const res = await api.raw('/portal/documents', {
        method: 'POST',
        body: form,
      })
      if (!res.ok) throw new Error('Upload failed')
      return res.json() as Promise<PortalDocument>
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portal', 'documents'] }),
  })
}

/** For preview: fetch the raw response with auth. Caller chooses .blob() or
 * .arrayBuffer() depending on what the renderer needs. */
export async function fetchPortalDocumentResponse(docId: string): Promise<Response> {
  const res = await api.raw(`/portal/documents/${docId}/download`, { method: 'GET' })
  if (!res.ok) throw new Error(`Preview fetch failed: ${res.status}`)
  return res
}

/** Legacy: kept for callers that only need a blob URL. */
export async function fetchPortalDocumentBlobUrl(docId: string): Promise<{ url: string; contentType: string }> {
  const res = await fetchPortalDocumentResponse(docId)
  const contentType = res.headers.get('Content-Type') ?? 'application/octet-stream'
  const blob = await res.blob()
  return { url: URL.createObjectURL(blob), contentType }
}

/**
 * Milestone submission — upload a file that IS the submission and advance the
 * milestone state to `submitted` in one call. The supervisor's inbox picks it up
 * immediately.
 */
export function useSubmitMilestone() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ milestoneId, file }: { milestoneId: string; file: File }) => {
      const form = new FormData()
      form.append('file', file)
      const res = await api.raw(`/portal/milestones/${milestoneId}/submit`, {
        method: 'POST',
        body: form,
      })
      if (!res.ok) throw new Error('Submit failed')
      return res.json()
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portal', 'journey'] })
      qc.invalidateQueries({ queryKey: ['portal', 'documents'] })
    },
  })
}

/**
 * Student ↔ supervisor messaging.
 */
export interface MessageThread {
  supervisorPersonId: string
  supervisorName: string
  role: string
  lastMessage: {
    body: string | null
    authorRole: string | null
    createdAt: string | null
  } | null
  unreadCount: number
  totalMessages: number
}

export interface PortalMessage {
  id: string
  authorRole: 'student' | 'supervisor'
  body: string
  createdAt: string | null
  readAt: string | null
}

export const useMessageThreads = () =>
  useQuery({
    queryKey: ['portal', 'messages'],
    queryFn: () => api.get<MessageThread[]>('/portal/messages'),
  })

export const useThreadMessages = (supervisorPersonId: string | null) =>
  useQuery({
    queryKey: ['portal', 'messages', supervisorPersonId],
    queryFn: () =>
      api.get<PortalMessage[]>(`/portal/messages/${supervisorPersonId}`),
    enabled: !!supervisorPersonId,
  })

export function useSendMessage() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (args: { supervisorPersonId: string; body: string }) =>
      api.post<PortalMessage>('/portal/messages', {
        supervisorPersonId: args.supervisorPersonId,
        body: args.body,
      }),
    onSuccess: (_, args) => {
      qc.invalidateQueries({ queryKey: ['portal', 'messages'] })
      qc.invalidateQueries({ queryKey: ['portal', 'messages', args.supervisorPersonId] })
    },
  })
}
