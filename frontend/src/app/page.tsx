'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/shared/auth/AuthContext'
import { homeRoute } from '@/shared/auth/homeRoute'

// Auth lives client-side, so the root redirect must wait for the principal to
// know which home screen this role gets.
export default function Home() {
  const router = useRouter()
  const { principal, loading } = useAuth()

  useEffect(() => {
    if (loading) return
    router.replace(principal?.authenticated ? homeRoute(principal.roles) : '/login')
  }, [loading, principal, router])

  return null
}
