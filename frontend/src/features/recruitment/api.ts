'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type ListResponse } from '@/shared/api/client'

export type OpportunityStatus = 'draft' | 'approved' | 'open' | 'recruiting' | 'paused' | 'filled' | 'closed'
// W1.1 — explicit funding shape
export type OpportunityFunding = 'funded' | 'partially_funded' | 'unfunded'
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
  positionsFilled: number
  // Phase 6.1 — provenance: the demand this position answers and the award funding it.
  researchDemandId: string | null
  researchAwardId: string | null
  status: OpportunityStatus
  /** W1.1 — funded / partially_funded / unfunded (defaults to funded on the server). */
  opportunityType: OpportunityFunding
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
  personName?: string | null
  route: 'opportunity_led' | 'student_led'
  researchOpportunityId: string | null
  currentStage: CandidateStage
  submittedAt: string | null
  createdAt: string
  history: StageHistory[]
  assessments: Assessment[]
  // F3 — fee status + visa gate
  feeStatus?: string | null
  visaRequired?: boolean
  visaCheckCompletedAt?: string | null
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

export interface UseApplicationsParams {
  stage?: string
  search?: string
  limit?: number
  offset?: number
}

export const useApplications = (params: UseApplicationsParams = {}) => {
  const { stage, search, limit = 50, offset = 0 } = params
  const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (stage) qs.set('stage', stage)
  if (search) qs.set('search', search)
  return useQuery({
    queryKey: ['applications', stage ?? 'all', search ?? '', limit, offset],
    queryFn: () => api.get<ListResponse<Application>>(`/applications?${qs.toString()}`),
  })
}

export const useApplication = (id: string) =>
  useQuery({ queryKey: ['application', id], queryFn: () => api.get<Application>(`/applications/${id}`), enabled: !!id })

export const useOfferForApplication = (id: string) =>
  useQuery({ queryKey: ['offer', id], queryFn: () => api.get<Offer | null>(`/applications/${id}/offer`), enabled: !!id })

export const usePipeline = () =>
  useQuery({ queryKey: ['pipeline'], queryFn: () => api.get<Pipeline>('/recruitment/pipeline') })

// --- Mutations ---
export function useUpdateOpportunity() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: {
      id: string
      body: Partial<{ title: string; stipendAmount: string; eligibility: string; positionsAvailable: number }>
    }) => api.patch<Opportunity>(`/opportunities/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['opportunities'] }),
  })
}

export function useCreateOpportunity() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: {
      title: string
      stipendAmount?: number
      currency?: string
      eligibility?: string
      researchDemandId?: string
      researchAwardId?: string
      opportunityType?: OpportunityFunding
    }) => api.post<Opportunity>('/opportunities', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['opportunities'] })
      qc.invalidateQueries({ queryKey: ['research-demands'] })
    },
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
/** Create a Person (used by the New Application dialog for candidates who
 *  don't exist yet as a Person). */
export function useCreatePersonQuick() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { givenName: string; familyName: string; email?: string | null; nationality?: string | null }) =>
      api.post<{ id: string; givenName: string; familyName: string; email: string | null }>('/persons', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['persons'] }),
  })
}

/** Create an Application (opportunity-led or student-led). */
export function useCreateApplication() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: {
      personId: string
      route: 'opportunity_led' | 'student_led'
      researchOpportunityId?: string | null
      researchAreaId?: string | null
      proposalDocumentRef?: string | null
    }) => api.post<Application>('/applications', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['applications'] })
      qc.invalidateQueries({ queryKey: ['pipeline'] })
    },
  })
}

/** F3 — update fee status / visa flag / complete the visa check. */
export function useVisaCheck(applicationId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: {
      feeStatus?: string | null
      visaRequired?: boolean
      completeVisaCheck?: boolean
    }) =>
      api.patch<{
        applicationId: string
        feeStatus: string | null
        visaRequired: boolean
        visaCheckCompletedAt: string | null
      }>(`/applications/${applicationId}/visa-check`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['application', applicationId] })
      qc.invalidateQueries({ queryKey: ['applications'] })
    },
  })
}

export function useAcceptOffer(applicationId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (offerId: string) => api.post<{ id: string; studentRef: string; personId: string }>(`/offers/${offerId}/accept`, {}),
    onSuccess: () => invalidateOffer(qc, applicationId),
  })
}
