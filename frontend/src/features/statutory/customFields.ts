'use client'

/**
 * Admin-defined custom student attributes — the HESA gap-capture feature.
 *
 * When a statutory return needs an attribute the core model doesn't hold, an admin creates a
 * custom attribute here (one click, no code release) and types its value per student. The
 * statutory mapping picker then offers it as `custom.<key>`, so the field can be mapped instead
 * of being deleted.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export type CustomFieldType = 'string' | 'number' | 'date' | 'code'

export interface CustomField {
  id: string
  key: string
  label: string
  dataType: CustomFieldType
  reason: string
  sourcePath: string   // "custom.<key>" — paste straight into a mapping
  createdAt: string | null
}

export interface CustomFieldValueRow {
  studentId: string
  studentRef: string
  studentName: string
  value: string | null
}

export const useCustomFields = () =>
  useQuery({
    queryKey: ['custom-fields'],
    queryFn: () => api.get<CustomField[]>('/students/custom-fields'),
  })

export const useCreateCustomField = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { label: string; dataType: CustomFieldType; reason: string }) =>
      api.post<CustomField>('/students/custom-fields', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['custom-fields'] })
      // The mapping picker lists custom paths from the record-schema catalog — refresh it.
      qc.invalidateQueries({ queryKey: ['report-profile-record-schema'] })
    },
  })
}

export const useDeleteCustomField = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.del(`/students/custom-fields/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['custom-fields'] })
      qc.invalidateQueries({ queryKey: ['report-profile-record-schema'] })
    },
  })
}

export const useCustomFieldValues = (fieldId: string | null) =>
  useQuery({
    queryKey: ['custom-fields', fieldId, 'values'],
    queryFn: () => api.get<{ field: CustomField; rows: CustomFieldValueRow[] }>(
      `/students/custom-fields/${fieldId}/values`,
    ),
    enabled: !!fieldId,
  })

export const useSetCustomFieldValues = (fieldId: string | null) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (values: { studentId: string; value: string | null }[]) =>
      api.put<{ filled: number }>(`/students/custom-fields/${fieldId}/values`, { values }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['custom-fields', fieldId, 'values'] }),
  })
}
