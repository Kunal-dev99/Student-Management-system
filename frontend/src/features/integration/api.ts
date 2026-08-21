'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export interface IntegrationLog {
  id: string
  direction: 'inbound' | 'outbound'
  system: string
  eventType: string
  status: 'success' | 'failed' | 'skipped' | 'duplicate'
  sourceId: string | null
  detail: Record<string, unknown> | null
  createdAt: string
}
export interface IntegrationOverview {
  pending: number
  logs: IntegrationLog[]
}

export const useIntegration = () =>
  useQuery({ queryKey: ['integration'], queryFn: () => api.get<IntegrationOverview>('/integration/logs'), refetchInterval: 20_000 })

export function useDispatch() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<{ dispatched: number; outboundCalls: number }>('/integration/dispatch'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['integration'] }),
  })
}

export interface ScheduledRunResult {
  milestonesGenerated: number
  fundingExpiringFlagged: number
  overdueTasksEscalated: number
  viewsRefreshed: string
}

export function useRunScheduledJobs() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<ScheduledRunResult>('/admin/scheduled-jobs/run'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['integration'] })
    },
  })
}
