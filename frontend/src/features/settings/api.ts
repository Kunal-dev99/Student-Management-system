'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

/* ------------------------------------------------------------------ *
 * Institution settings (Phase 8) — GET/PUT/DELETE /settings/institution.
 * The backend registry is the single source of truth: keys, types,
 * ranges and defaults all come from the API, never hard-coded here.
 * ------------------------------------------------------------------ */

export type SettingType = 'int' | 'float' | 'bool' | 'str'
export type SettingValue = number | boolean | string

export interface InstitutionSetting {
  key: string
  label: string
  description: string
  type: SettingType
  default: SettingValue
  min: number | null
  max: number | null
  value: SettingValue
  overridden: boolean
  updatedAt: string | null
}

export interface InstitutionSettingGroup {
  group: string
  settings: InstitutionSetting[]
}

export const useInstitutionSettings = () =>
  useQuery({
    queryKey: ['settings', 'institution'],
    queryFn: () => api.get<{ groups: InstitutionSettingGroup[] }>('/settings/institution'),
  })

export function useSetInstitutionSetting() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ key, value }: { key: string; value: SettingValue }) =>
      api.put<{ key: string; value: SettingValue; overridden: boolean }>(
        `/settings/institution/${key}`, { value },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings', 'institution'] }),
  })
}

export function useResetInstitutionSetting() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (key: string) =>
      api.del<{ key: string; value: SettingValue; overridden: boolean }>(
        `/settings/institution/${key}`,
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings', 'institution'] }),
  })
}

/* ------------------------------------------------------------------ *
 * Reference data (LOVs) — /reference. The kind list and its editable
 * fields are served by the API, so a new LOV appears here without a
 * frontend change.
 * ------------------------------------------------------------------ */

export type LovKindId = 'departments' | 'research-areas' | 'programmes' | 'funding-sources'

export interface LovKind {
  kind: LovKindId
  label: string
  fields: string[] // camelCase editable fields, e.g. ["name", "code", "departmentId"]
}

export interface LovRow {
  id: string
  inUse: number
  [field: string]: string | number | null | undefined
}

export const useLovKinds = () =>
  useQuery({ queryKey: ['reference', 'kinds'], queryFn: () => api.get<LovKind[]>('/reference') })

export const useLovList = (kind: string, enabled = true) =>
  useQuery({
    queryKey: ['reference', kind],
    queryFn: () => api.get<LovRow[]>(`/reference/${kind}`),
    enabled: enabled && !!kind,
  })

export function useCreateLovRow() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ kind, body }: { kind: string; body: Record<string, string | null> }) =>
      api.post<{ id: string }>(`/reference/${kind}`, body),
    onSuccess: (_data, { kind }) => qc.invalidateQueries({ queryKey: ['reference', kind] }),
  })
}

export function useUpdateLovRow() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ kind, id, body }: { kind: string; id: string; body: Record<string, string | null> }) =>
      api.patch<{ id: string }>(`/reference/${kind}/${id}`, body),
    onSuccess: (_data, { kind }) => qc.invalidateQueries({ queryKey: ['reference', kind] }),
  })
}

export function useDeleteLovRow() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ kind, id }: { kind: string; id: string }) =>
      api.del<{ deleted: boolean }>(`/reference/${kind}/${id}`),
    onSuccess: (_data, { kind }) => qc.invalidateQueries({ queryKey: ['reference', kind] }),
  })
}

/** Platform-fixed enums (read-only by design — each value has code attached). */
export interface ValueSet {
  area: string
  name: string
  values: string[]
}

export const useValueSets = (enabled = true) =>
  useQuery({
    queryKey: ['reference', 'value-sets'],
    queryFn: () => api.get<ValueSet[]>('/reference/value-sets'),
    enabled,
  })

/* ------------------------------------------------------------------ *
 * Users & roles — /admin/users, /admin/roles. No password ever passes
 * through this client: creating a user triggers a set-password email.
 * ------------------------------------------------------------------ */

export interface AdminUser {
  id: string
  email: string
  isActive: boolean
  roles: string[]
  personId: string | null
  lastLoginAt: string | null
  lockedUntil: string | null
  hasPassword: boolean
}

export interface AdminRole {
  id: string
  name: string
  permissions: string[]
  userCount: number
}

export const useAdminUsers = () =>
  useQuery({ queryKey: ['admin', 'users'], queryFn: () => api.get<AdminUser[]>('/admin/users') })

export const useAdminRoles = () =>
  useQuery({ queryKey: ['admin', 'roles'], queryFn: () => api.get<AdminRole[]>('/admin/roles') })

export function useInviteUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { email: string; roleNames: string[]; personId?: string }) =>
      api.post<AdminUser & { invited: boolean }>('/admin/users', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'users'] })
      qc.invalidateQueries({ queryKey: ['admin', 'roles'] }) // userCount changed
    },
  })
}

export function useUpdateUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: { isActive?: boolean; roleNames?: string[] } }) =>
      api.patch<AdminUser>(`/admin/users/${id}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'users'] })
      qc.invalidateQueries({ queryKey: ['admin', 'roles'] })
    },
  })
}

export function useSendPasswordReset() {
  return useMutation({
    mutationFn: (id: string) => api.post<{ sent: boolean }>(`/admin/users/${id}/send-reset`),
  })
}
