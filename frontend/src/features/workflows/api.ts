'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export interface WorkflowDefinition {
  id: string
  key: string
  version: number
  name: string
  initialState: string
  states: string[]
  transitions: { from: string; on: string; to: string; action?: unknown }[]
  active: boolean
}
export interface WorkflowInstance {
  id: string
  definitionId: string
  aggregateType: string
  aggregateId: string
  currentState: string
  context: Record<string, unknown> | null
  createdAt: string
}

export const useDefinitions = () =>
  useQuery({ queryKey: ['wf-definitions'], queryFn: () => api.get<WorkflowDefinition[]>('/workflow-definitions') })
export const useInstances = () =>
  useQuery({ queryKey: ['wf-instances'], queryFn: () => api.get<WorkflowInstance[]>('/workflow-instances') })

function invAll(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ['wf-definitions'] })
  qc.invalidateQueries({ queryKey: ['wf-instances'] })
}

export function useCreateDefinition() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: unknown) => api.post<WorkflowDefinition>('/workflow-definitions', body),
    onSuccess: () => invAll(qc),
  })
}
export function useActivateDefinition() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.post<WorkflowDefinition>(`/workflow-definitions/${id}/activate`),
    onSuccess: () => invAll(qc),
  })
}
export function useStartInstance() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (key: string) => api.post<WorkflowInstance>('/workflow-instances', {
      key, aggregateType: 'demo', aggregateId: crypto.randomUUID(),
    }),
    onSuccess: () => invAll(qc),
  })
}
export function useDispatchEvent() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, event }: { id: string; event: string }) =>
      api.post<WorkflowInstance>(`/workflow-instances/${id}/events`, { event }),
    onSuccess: () => invAll(qc),
  })
}
