'use client'

import type { ReactNode } from 'react'
import { useAuth } from '@/shared/auth/AuthContext'

/**
 * Micro-level permission gating for controls and sections.
 *
 * Gate on the exact permission code the underlying endpoint requires
 * (see backend require_permission). Hiding is convenience only — the
 * API remains the enforcement layer.
 */
export function useCan(...codes: string[]): boolean {
  const { hasPermission } = useAuth()
  if (codes.length === 0) return true
  return codes.some((c) => hasPermission(c))
}

/** Renders children only when the user holds `perm` (or ANY of `anyOf`). */
export function Can({ perm, anyOf, children }: {
  perm?: string
  anyOf?: string[]
  children: ReactNode
}) {
  const { hasPermission } = useAuth()
  const codes = anyOf ?? (perm ? [perm] : [])
  const ok = codes.length === 0 || codes.some((c) => hasPermission(c))
  return ok ? <>{children}</> : null
}
