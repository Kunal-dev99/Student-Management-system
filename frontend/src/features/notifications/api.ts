'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export interface NotificationPreferences {
  emailEnabled: boolean
  digest: boolean
  mutedEvents: string[]
}

export const useUnreadCount = () =>
  useQuery({
    queryKey: ['notifications', 'unread-count'],
    queryFn: () => api.get<{ unread: number }>('/notifications/unread-count'),
    refetchInterval: 30_000,
  })

export const usePreferences = () =>
  useQuery({
    queryKey: ['notifications', 'preferences'],
    queryFn: () => api.get<NotificationPreferences>('/notifications/preferences'),
  })

export function useUpdatePreferences() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: NotificationPreferences) =>
      api.put<NotificationPreferences>('/notifications/preferences', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications', 'preferences'] }),
  })
}
