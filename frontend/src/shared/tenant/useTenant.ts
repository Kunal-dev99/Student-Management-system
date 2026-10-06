'use client'

import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'

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
 * The institution to brand the app with (sidebar colour, short logo, name).
 *
 * Signed in, it is ALWAYS the account's own institution (from /me): the login page's picker
 * only sets branding for the login screen itself, and must never make one institution's
 * session look like another's. Before sign-in, the picker's choice (localStorage) is used.
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

  const { principal } = useAuth()
  const list = q.data ?? []
  const own = principal?.tenantId ? list.find((t) => t.id === principal.tenantId) : undefined
  if (own) return own
  if (id) {
    const hit = list.find((t) => t.id === id)
    if (hit) return hit
  }
  // Fall back to ICR if present (demo default), then first tenant.
  return list.find((t) => t.subdomain === 'icr') ?? list[0] ?? null
}
