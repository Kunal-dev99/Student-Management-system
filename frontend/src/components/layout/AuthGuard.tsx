'use client'

import { useEffect, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/shared/auth/AuthContext'

/** Gate the authenticated app shell — redirect to /login when there's no session. */
export function AuthGuard({ children }: { children: ReactNode }) {
  const { principal, loading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!loading && !principal?.authenticated) router.replace('/login')
  }, [loading, principal, router])

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-helper">Loading…</div>
    )
  }
  if (!principal?.authenticated) return null
  return <>{children}</>
}
