'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type ListResponse } from '@/shared/api/client'

export type OpportunityStatus = 'draft' | 'approved' | 'open' | 'recruiting' | 'filled' | 'closed'
export type CandidateStage =
  | 'prospect' | 'applicant' | 'under_assessment' | 'shortlisted' | 'interview'
  | 'selected' | 'offer_made' | 'offer_accepted' | 'rejected' | 'withdrawn' | 'converted'
export type OfferStatus = 'draft' | 'issued' | 'accepted' | 'declined' | 'expired' | 'withdrawn'

export interface Opportunity {
  id: string
  title: string
  stipendAmount: string | null
  currency: string | null
  eligibility: string | null
  positionsAvailable: number
  status: OpportunityStatus
  createdAt: string
}

export interface StageHistory {
  id: string
  fromStage: CandidateStage | null
  toStage: CandidateStage
  reason: string | null
  movedAt: string
}
export interface Assessment {
  id: string
  decision: string | null
  rationale: string | null
  assessedAt: string
}
export interface Application {
  id: string
  personId: string
  route: 'opportunity_led' | 'student_led'
  researchOpportunityId: string | null
  currentStage: CandidateStage
  submittedAt: string | null
  createdAt: string
  history: StageHistory[]
  assessments: Assessment[]
}
export interface Offer {
  id: string
  applicationId: string
  status: OfferStatus
  issuedAt: string | null
  respondedAt: string | null
  createdAt: string
}
export interface Pipeline {
  counts: Record<string, number>
  total: number
}

// --- Queries ---
export const useOpportunities = () =>
  useQuery({ queryKey: ['opportunities'], queryFn: () => api.get<ListResponse<Opportunity>>('/opportunities?limit=100') })

export const useApplications = (stage?: string) =>
  useQuery({
    queryKey: ['applications', stage ?? 'all'],
    queryFn: () => api.get<ListResponse<Application>>(`/applications?limit=100${stage ? `&stage=${stage}` : ''}`),
  })

export const useApplication = (id: string) =>
  useQuery({ queryKey: ['application', id], queryFn: () => api.get<Application>(`/applications/${id}`), enabled: !!id })

export const useOfferForApplication = (id: string) =>
  useQuery({ queryKey: ['offer', id], queryFn: () => api.get<Offer | null>(`/applications/${id}/offer`), enabled: !!id })

export const usePipeline = () =>
  useQuery({ queryKey: ['pipeline'], queryFn: () => api.get<Pipeline>('/recruitment/pipeline') })

// --- Mutations ---
export function useCreateOpportunity() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { title: string; stipendAmount?: number; currency?: string; eligibility?: string }) =>
      api.post<Opportunity>('/opportunities', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['opportunities'] }),
  })
}

export function useTransitionOpportunity() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, toStatus }: { id: string; toStatus: OpportunityStatus }) =>
      api.post<Opportunity>(`/opportunities/${id}/transition`, { toStatus }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['opportunities'] }),
  })
}

export function useAdvance(applicationId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { toStage: CandidateStage; reason?: string }) =>
      api.post<Application>(`/applications/${applicationId}/advance`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['application', applicationId] })
      qc.invalidateQueries({ queryKey: ['applications'] })
      qc.invalidateQueries({ queryKey: ['pipeline'] })
    },
  })
}

export function useAssess(applicationId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { decision: string; rationale?: string }) =>
      api.post<Application>(`/applications/${applicationId}/assess`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['application', applicationId] })
      qc.invalidateQueries({ queryKey: ['pipeline'] })
    },
  })
}

function invalidateOffer(qc: ReturnType<typeof useQueryClient>, applicationId: string) {
  qc.invalidateQueries({ queryKey: ['offer', applicationId] })
  qc.invalidateQueries({ queryKey: ['application', applicationId] })
  qc.invalidateQueries({ queryKey: ['applications'] })
  qc.invalidateQueries({ queryKey: ['pipeline'] })
  qc.invalidateQueries({ queryKey: ['students'] })
}

export function useCreateOffer(applicationId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<Offer>(`/applications/${applicationId}/offer`, {}),
    onSuccess: () => invalidateOffer(qc, applicationId),
  })
}
export function useIssueOffer(applicationId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (offerId: string) => api.post<Offer>(`/offers/${offerId}/issue`),
    onSuccess: () => invalidateOffer(qc, applicationId),
  })
}
export function useDeclineOffer(applicationId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (offerId: string) => api.post<Offer>(`/offers/${offerId}/decline`),
    onSuccess: () => invalidateOffer(qc, applicationId),
  })
}
export function useAcceptOffer(applicationId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (offerId: string) => api.post<{ id: string; studentRef: string; personId: string }>(`/offers/${offerId}/accept`, {}),
    onSuccess: () => invalidateOffer(qc, applicationId),
  })
}
