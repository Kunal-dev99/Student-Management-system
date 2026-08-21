'use client'

import { Badge } from '@/components/ui/badge'
import type { CandidateStage, OfferStatus, OpportunityStatus } from './api'

type Variant = 'default' | 'secondary' | 'success' | 'info' | 'warning' | 'destructive' | 'outline'

const OPP: Record<OpportunityStatus, Variant> = {
  draft: 'secondary', approved: 'info', open: 'success', recruiting: 'info',
  filled: 'warning', closed: 'outline',
}
const STAGE: Record<CandidateStage, Variant> = {
  prospect: 'secondary', applicant: 'info', under_assessment: 'warning', shortlisted: 'info',
  interview: 'info', selected: 'success', offer_made: 'success', offer_accepted: 'success',
  rejected: 'destructive', withdrawn: 'outline', converted: 'success',
}
const OFFER: Record<OfferStatus, Variant> = {
  draft: 'secondary', issued: 'info', accepted: 'success', declined: 'destructive',
  expired: 'outline', withdrawn: 'outline',
}

const label = (s: string) => s.replace(/_/g, ' ')

export const OpportunityPill = ({ status }: { status: OpportunityStatus }) => (
  <Badge variant={OPP[status]}>{label(status)}</Badge>
)
export const StagePill = ({ stage }: { stage: CandidateStage }) => (
  <Badge variant={STAGE[stage]}>{label(stage)}</Badge>
)
export const OfferPill = ({ status }: { status: OfferStatus }) => (
  <Badge variant={OFFER[status]}>{label(status)}</Badge>
)
