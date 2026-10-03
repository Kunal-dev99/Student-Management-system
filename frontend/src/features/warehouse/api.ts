'use client'

/**
 * Data warehouse export — the institution's publications (scheduled files), their runs, and the
 * API consumers that pull data. Backed by /warehouse/* (see backend app/modules/warehouse).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export interface CatalogueColumn {
  name: string
  type: string
  personal: boolean
  description?: string
}
export interface CatalogueObject {
  name: string
  description: string
  key: string
  changeColumn: string
  columns: CatalogueColumn[]
  personalColumns: string[]
}

export interface Publication {
  id: string
  name: string
  objects: string[] | null
  fileFormat: 'parquet' | 'csv'
  frequency: 'daily' | 'hourly'
  runAtHour: number
  personalData: boolean
  fullEveryDays: number
  enabled: boolean
  nextRunAt: string | null
  lastFullAt: string | null
}
export type PublicationInput = Omit<Publication, 'id' | 'nextRunAt' | 'lastFullAt'>

export interface Run {
  id: string
  publicationId: string
  status: 'running' | 'succeeded' | 'failed'
  mode: 'full' | 'incremental'
  triggeredBy: 'schedule' | 'manual'
  startedAt: string
  finishedAt: string | null
  windowTo: string | null
  location: string | null
  error: string | null
  rows: number | null
  deletedRows: number | null
}

export interface Consumer {
  id: string
  name: string
  clientId: string
  objects: string[] | null
  personalData: boolean
  active: boolean
  lastUsedAt: string | null
  clientSecret?: string
}

const KEY = ['warehouse']

export const useCatalogue = () =>
  useQuery({ queryKey: [...KEY, 'catalogue'], queryFn: () => api.get<CatalogueObject[]>('/warehouse/catalogue'),
             staleTime: 10 * 60_000 })

export const usePublications = () =>
  useQuery({ queryKey: [...KEY, 'publications'], queryFn: () => api.get<Publication[]>('/warehouse/publications') })

export const useRuns = (publicationId: string | null) =>
  useQuery({
    queryKey: [...KEY, 'runs', publicationId],
    queryFn: () => api.get<Run[]>(`/warehouse/publications/${publicationId}/runs`),
    enabled: !!publicationId,
  })

export const useConsumers = (enabled: boolean) =>
  useQuery({ queryKey: [...KEY, 'consumers'], queryFn: () => api.get<Consumer[]>('/warehouse/consumers'), enabled })

function useInvalidate() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries({ queryKey: KEY })
}

export function useSavePublication() {
  const done = useInvalidate()
  return useMutation({
    mutationFn: ({ id, ...body }: Partial<PublicationInput> & { id?: string }) =>
      id ? api.patch<Publication>(`/warehouse/publications/${id}`, body)
         : api.post<Publication>('/warehouse/publications', body),
    onSuccess: done,
  })
}

export function useDeletePublication() {
  const done = useInvalidate()
  return useMutation({ mutationFn: (id: string) => api.del<void>(`/warehouse/publications/${id}`), onSuccess: done })
}

export function useRunPublication() {
  const done = useInvalidate()
  return useMutation({ mutationFn: (id: string) => api.post<Run>(`/warehouse/publications/${id}/run`), onSuccess: done })
}

export function useCreateConsumer() {
  const done = useInvalidate()
  return useMutation({
    mutationFn: (body: { name: string; objects: string[] | null; personalData: boolean }) =>
      api.post<Consumer>('/warehouse/consumers', body),
    onSuccess: done,
  })
}

export function useConsumerAction() {
  const done = useInvalidate()
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'rotate' | 'revoke' | 'delete' }) =>
      action === 'delete' ? api.del<Consumer>(`/warehouse/consumers/${id}`)
                          : api.post<Consumer>(`/warehouse/consumers/${id}/${action}`),
    onSuccess: done,
  })
}
