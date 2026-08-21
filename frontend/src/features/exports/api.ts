'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, downloadFile } from '@/shared/api/client'

export interface ExportJob {
  id: string
  kind: string
  status: 'queued' | 'running' | 'complete' | 'failed'
  filename: string | null
  rowCount: number | null
  error: string | null
  createdAt: string
  completedAt: string | null
}

export const useExports = () =>
  useQuery({ queryKey: ['exports'], queryFn: () => api.get<ExportJob[]>('/exports') })

export function useCreateExport() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (kind: string) => api.post<ExportJob>('/exports', { kind }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['exports'] }),
  })
}

export const downloadExport = (job: ExportJob) =>
  downloadFile(`/exports/${job.id}/download`, job.filename ?? 'export.csv')
