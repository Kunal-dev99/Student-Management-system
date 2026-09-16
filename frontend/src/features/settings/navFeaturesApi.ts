'use client'

/**
 * Configurable navigation (runtime park mechanism) — admin toggles for every sidebar feature.
 * Off removes the item from the nav and blocks its route; the code stays put. Tenant-wide,
 * persisted as institution settings. admin.configure gated server-side.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export interface NavFeature {
  route: string
  label: string
  group: string
  core: boolean
  enabled: boolean
}

export interface NavFeatureGroup {
  group: string
  items: NavFeature[]
}

export const useNavFeatures = () =>
  useQuery({
    queryKey: ['nav-features'],
    queryFn: () => api.get<{ groups: NavFeatureGroup[] }>('/settings/nav-features'),
  })

export function useSetNavFeature() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ route, enabled }: { route: string; enabled: boolean }) =>
      api.put<{ route: string; enabled: boolean }>('/settings/nav-features', { route, enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['nav-features'] }),
  })
}
