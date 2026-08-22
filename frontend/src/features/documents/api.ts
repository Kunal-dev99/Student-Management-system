'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, uploadFile, downloadFile } from '@/shared/api/client'

export interface DocumentItem {
  id: string
  ownerType: string
  ownerId: string
  docType: string | null
  filename: string
  contentType: string | null
  sizeBytes: number | null
  scanStatus: string | null
  uploadedBy: string | null
  createdAt: string
}

export const useDocuments = (ownerType: string, ownerId: string) =>
  useQuery({
    queryKey: ['documents', ownerType, ownerId],
    queryFn: () => api.get<DocumentItem[]>(`/documents?ownerType=${ownerType}&ownerId=${ownerId}`),
    enabled: !!ownerId,
  })

export function useUploadDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (args: { ownerType: string; ownerId: string; docType?: string; file: File }) => {
      const form = new FormData()
      form.append('ownerType', args.ownerType)
      form.append('ownerId', args.ownerId)
      if (args.docType) form.append('docType', args.docType)
      form.append('file', args.file)
      return uploadFile<DocumentItem>('/documents', form)
    },
    onSuccess: (_data, vars) =>
      qc.invalidateQueries({ queryKey: ['documents', vars.ownerType, vars.ownerId] }),
  })
}

export function useDeleteDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (args: { id: string; ownerType: string; ownerId: string }) =>
      api.del<void>(`/documents/${args.id}`),
    onSuccess: (_data, vars) =>
      qc.invalidateQueries({ queryKey: ['documents', vars.ownerType, vars.ownerId] }),
  })
}

export function downloadDocument(doc: DocumentItem) {
  return downloadFile(`/documents/${doc.id}/download`, doc.filename)
}
