'use client'

import { ShieldOff, AlertCircle } from 'lucide-react'
import { ApiError } from '@/shared/api/client'

/**
 * Uniform query-error rendering. 403s get the access message (already translated
 * centrally by ApiError); everything else shows the error's own message.
 */
export function ErrorState({ error, className = '' }: { error: unknown; className?: string }) {
  if (!error) return null
  const is403 = error instanceof ApiError && error.status === 403
  const Icon = is403 ? ShieldOff : AlertCircle
  const message = error instanceof Error ? error.message : 'Something went wrong.'
  return (
    <div className={`flex items-center gap-2 text-sm text-muted-foreground py-2 ${className}`}>
      <Icon className="h-4 w-4 shrink-0" />
      <span>{message}</span>
    </div>
  )
}
