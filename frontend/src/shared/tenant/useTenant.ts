'use client'

import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

export interface Tenant {
  id: string
  name: string
  subdomain: string
  logoText: string | null
  primaryColor: string | null
  tagline: string | null
}

export const TENANT_STORAGE_KEY = 'pgr.login.tenant'

/**
 * The current tenant — chosen on the login page, stored in localStorage.
 * Used by the app shell to brand the sidebar with the tenant's colour + short logo.
 *
 * Data is still shared today (MT-2 will spread tenant_id across the domain and enable
 * RLS). This hook only reads branding so the UI visibly matches the tenant the user
 * signed in against.
 */
export function useTenant(): Tenant | null {
  const q = useQuery({
    queryKey: ['tenants'],
    queryFn: () => api.get<Tenant[]>('/tenants'),
    staleTime: 5 * 60_000,
  })
  const [id, setId] = useState<string | null>(null)

  useEffect(() => {
    try {
      const saved = localStorage.getItem(TENANT_STORAGE_KEY)
      if (saved) setId(saved)
    } catch { /* ignore */ }
    // Listen for changes from other tabs / the login page.
    const onStorage = (e: StorageEvent) => {
      if (e.key === TENANT_STORAGE_KEY) setId(e.newValue)
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  const list = q.data ?? []
  if (id) {
    const hit = list.find((t) => t.id === id)
    if (hit) return hit
  }
  // Fall back to ICR if present (demo default), then first tenant.
  return list.find((t) => t.subdomain === 'icr') ?? list[0] ?? null
}
