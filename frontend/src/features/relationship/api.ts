'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export type RelationshipLabel = 'thriving' | 'steady' | 'drifting' | 'strained'

export interface RelationshipEvidenceItem {
  kind: 'message' | 'meeting'
  at: string
  author: string
  text: string
}

export interface RelationshipSignal {
  studentId: string
  supervisorPersonId: string
  label: RelationshipLabel
  reasoning: string
  provenance: {
    source: 'model' | 'fallback'
    model: string | null
  }
  evidenceTotals: { messages: number; meetings: number }
  evidence: RelationshipEvidenceItem[]
}

export const useRelationshipSignal = (studentId: string | null) =>
  useQuery({
    queryKey: ['relationship-signal', studentId],
    queryFn: () =>
      api.get<RelationshipSignal>(`/supervision/relationship-signal/${studentId}`),
    enabled: !!studentId,
    // Cheap-ish call (deterministic assembly + AI); 5 min stale window is fine.
    staleTime: 5 * 60 * 1000,
  })
