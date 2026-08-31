'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import Image from 'next/image'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ApiError } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import { homeRoute } from '@/shared/auth/homeRoute'

export default function LoginPage() {
  const router = useRouter()
  const { login, principal, loading } = useAuth()
  const [email, setEmail] = useState('admin@example.com')
  const [password, setPassword] = useState('admin123')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

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

        <form onSubmit={onSubmit} className="card-elevated p-6 space-y-4">
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

          <Button type="submit" className="w-full" disabled={submitting}>
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
