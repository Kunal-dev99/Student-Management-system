'use client'

/** Small pieces shared by the custom-attribute dialog, catalogue and detail views. */
import { useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import type { CustomFieldStatus } from '@/features/statutory/customFields'

const STATUS_BADGE: Record<CustomFieldStatus, { label: string; variant: 'warning' | 'info' | 'destructive' | 'success' | 'secondary' }> = {
  pending: { label: 'Awaiting decision', variant: 'warning' },
  approved: { label: 'Approved — not active', variant: 'info' },
  rejected: { label: 'Rejected', variant: 'destructive' },
  active: { label: 'Active', variant: 'success' },
  review: { label: 'Under review', variant: 'warning' },
  retired: { label: 'Retired', variant: 'secondary' },
}

export const ACTION_LABEL: Record<string, string> = {
  requested: 'Requested', approved: 'Approved', rejected: 'Rejected', activated: 'Activated',
  withdrawn: 'Withdrawn', migrated: 'Carried over (pre-governance)', assessed: 'Checked',
  review_started: 'Put under review', kept: 'Kept (review closed)', retired: 'Retired', restored: 'Restored',
}

export const fmt = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleString() : '')

export function StatusBadge({ status }: { status: CustomFieldStatus }) {
  const b = STATUS_BADGE[status] ?? { label: status, variant: 'secondary' as const }
  return <Badge variant={b.variant}>{b.label}</Badge>
}

export function CopyPath({ path }: { path: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button type="button" title="Copy the mapping path"
      className="inline-flex items-center gap-1 font-mono text-xs text-muted-foreground hover:text-foreground"
      onClick={() => { navigator.clipboard?.writeText(path).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1200) }) }}>
      {path}{copied ? <Check className="h-3 w-3 text-[hsl(var(--success))]" /> : <Copy className="h-3 w-3" />}
    </button>
  )
}
