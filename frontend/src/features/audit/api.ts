'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export interface AuditRow {
  id: string
  actorEmail: string | null
  action: string | null
  method: string | null
  entityType: string | null
  entityId: string | null
  statusCode: number | null
  requestId: string | null
  detail: Record<string, unknown> | null
  createdAt: string
}

export interface AuditParams {
  entityType?: string
  entityId?: string
  actorEmail?: string
  limit?: number
}

export const useAudit = (params: AuditParams) => {
  const qs = new URLSearchParams()
  if (params.entityType) qs.set('entityType', params.entityType)
  if (params.entityId) qs.set('entityId', params.entityId)
  if (params.actorEmail) qs.set('actorEmail', params.actorEmail)
  if (params.limit) qs.set('limit', String(params.limit))
  const query = qs.toString()
  return useQuery({
    queryKey: ['audit', params],
    queryFn: () => api.get<AuditRow[]>(`/audit${query ? `?${query}` : ''}`),
  })
}
