'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import Image from 'next/image'
import { useQuery } from '@tanstack/react-query'
import { Building2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { ApiError, api } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import { homeRoute } from '@/shared/auth/homeRoute'

interface TenantOption {
  id: string
  name: string
  subdomain: string
  logoText: string | null
  primaryColor: string | null
  tagline: string | null
}

const TENANT_STORAGE_KEY = 'pgr.login.tenant'

export default function LoginPage() {
  const router = useRouter()
  const { login, principal, loading } = useAuth()
  const [email, setEmail] = useState('admin@example.com')
  const [password, setPassword] = useState('admin123')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [tenantId, setTenantId] = useState<string>('')

  // Public tenants list — feeds the selector. Public endpoint, no auth needed.
  const tenants = useQuery({
    queryKey: ['tenants'],
    queryFn: () => api.get<TenantOption[]>('/tenants'),
  })

  // Persist the last-picked tenant so a demo reload keeps the branding.
  useEffect(() => {
    if (!tenants.data?.length) return
    try {
      const saved = localStorage.getItem(TENANT_STORAGE_KEY)
      if (saved && tenants.data.some((t) => t.id === saved)) {
        setTenantId(saved)
        return
      }
    } catch { /* ignore */ }
    // Default to ICR if present (demo default), otherwise the first tenant.
    const icr = tenants.data.find((t) => t.subdomain === 'icr')
    setTenantId((icr ?? tenants.data[0]).id)
  }, [tenants.data])

  useEffect(() => {
    if (tenantId) {
      try { localStorage.setItem(TENANT_STORAGE_KEY, tenantId) } catch { /* ignore */ }
    }
  }, [tenantId])

  const active = useMemo(
    () => tenants.data?.find((t) => t.id === tenantId) ?? null,
    [tenants.data, tenantId],
  )

  // Already signed in -> go to the role's home screen. This also fires right
  // after a successful login, once the principal (and its roles) has loaded.
  useEffect(() => {
    if (!loading && principal?.authenticated) router.replace(homeRoute(principal.roles))
  }, [loading, principal, router])

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(email, password)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Login failed')
    } finally {
      setSubmitting(false)
    }
  }

  const accent = active?.primaryColor ?? '#2b3a55'

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-6">
          <div className="flex items-center justify-center rounded-md bg-[#15171A] px-4 py-2 shadow-sm mb-3">
            <Image src="/brand/logo.png" alt="Fusion Practices" width={150} height={30} priority className="h-7 w-auto" />
          </div>
          <h1 className="text-page-title">PGR Platform</h1>
          <p className="text-helper">Sign in to continue</p>
        </div>

        {/* Tenant chip — big enough to read the "ICR" text logo at a glance. */}
        {active && (
          <div className="card-elevated flex items-center gap-3 p-3 mb-3">
            <div
              className="h-11 w-11 rounded-md flex items-center justify-center text-lg font-bold text-white shrink-0"
              style={{ backgroundColor: accent }}
              aria-hidden
            >
              {active.logoText ?? active.name.slice(0, 3).toUpperCase()}
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold truncate">{active.name}</p>
              {active.tagline && (
                <p className="text-xs text-muted-foreground truncate">{active.tagline}</p>
              )}
            </div>
          </div>
        )}

        <form onSubmit={onSubmit} className="card-elevated p-6 space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="tenant">Institution</Label>
            <Select value={tenantId} onValueChange={setTenantId} disabled={tenants.isLoading || submitting}>
              <SelectTrigger id="tenant">
                <SelectValue placeholder={tenants.isLoading ? 'Loading…' : 'Pick your institution'} />
              </SelectTrigger>
              <SelectContent>
                {tenants.data?.map((t) => (
                  <SelectItem key={t.id} value={t.id}>
                    <span className="flex items-center gap-2">
                      <span
                        className="h-5 w-5 rounded-sm flex items-center justify-center text-[10px] font-bold text-white"
                        style={{ backgroundColor: t.primaryColor ?? '#2b3a55' }}
                      >
                        {t.logoText ?? t.name.slice(0, 2).toUpperCase()}
                      </span>
                      <span>{t.name}</span>
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-helper text-xs flex items-center gap-1">
              <Building2 className="h-3 w-3" />
              Demo: multi-tenant plumbing is in place; users sign in against the same
              directory today.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
            <div className="text-right">
              <Link href="/forgot-password" className="text-xs text-muted-foreground hover:text-foreground">Forgot password?</Link>
            </div>
          </div>

          {error && (
            <p className="text-sm text-[hsl(var(--destructive))] bg-[hsl(var(--destructive)/0.08)] border border-[hsl(var(--destructive)/0.25)] rounded-md px-3 py-2">
              {error}
            </p>
          )}

          <Button
            type="submit"
            className="w-full"
            disabled={submitting}
            style={{ backgroundColor: accent }}
          >
            {submitting ? 'Signing in…' : 'Sign in'}
          </Button>

          <p className="text-helper text-center pt-1">
            Demo: <span className="font-mono text-xs">admin@example.com</span> / <span className="font-mono text-xs">admin123</span>
          </p>
        </form>
      </div>
    </div>
  )
}
