'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export type TaskStatus = 'open' | 'in_progress' | 'blocked' | 'done' | 'cancelled'

export interface Task {
  id: string
  title: string
  assigneeRole: string | null
  assigneeUserId: string | null
  dueAt: string | null
  status: TaskStatus
  aggregateType: string | null
  aggregateId: string | null
  payload: Record<string, unknown> | null
  createdAt: string
}

export interface Notification {
  id: string
  channel: string
  template: string
  payload: Record<string, unknown> | null
  status: 'queued' | 'sent' | 'read' | 'failed'
  createdAt: string
}

export const useTasks = () =>
  useQuery({ queryKey: ['tasks'], queryFn: () => api.get<Task[]>('/tasks'), refetchInterval: 30_000 })

export const useNotifications = () =>
  useQuery({ queryKey: ['notifications'], queryFn: () => api.get<Notification[]>('/notifications') })

export function useCompleteTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.post<Task>(`/tasks/${id}/complete`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tasks'] }),
  })
}

export function useMarkNotificationRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.post<Notification>(`/notifications/${id}/read`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  })
}
