'use client'

/**
 * Inline evidence link. Every AI-narrated fact should be flanked by one of these so the
 * user can jump to the source in the Evidence Drawer without leaving their place.
 */
import { FileText, ExternalLink } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface SourceChipProps {
  label: string
  freshness?: string
  status?: 'verified' | 'review' | 'stale' | 'missing'
  onOpen?: () => void
  className?: string
}

const STATUS_TONE: Record<NonNullable<SourceChipProps['status']>, string> = {
  verified: 'border-emerald-300 text-emerald-800 dark:border-emerald-700 dark:text-emerald-200',
  review:   'border-amber-300 text-amber-800 dark:border-amber-700 dark:text-amber-200',
  stale:    'border-orange-300 text-orange-800 dark:border-orange-700 dark:text-orange-200',
  missing:  'border-dashed border-muted-foreground/50 text-muted-foreground',
}

export function SourceChip({ label, freshness, status = 'verified', onOpen, className }: SourceChipProps) {
  const Wrapper = onOpen ? 'button' : 'span'
  return (
    <Wrapper
      type={onOpen ? 'button' : undefined}
      onClick={onOpen}
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs bg-background',
        onOpen && 'hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        STATUS_TONE[status],
        className,
      )}
      aria-label={onOpen ? `Open evidence for ${label}` : undefined}
    >
      <FileText className="h-3 w-3" aria-hidden />
      <span className="truncate max-w-[14rem]">{label}</span>
      {freshness ? <span className="text-[10px] opacity-70">· {freshness}</span> : null}
      {onOpen ? <ExternalLink className="h-3 w-3 opacity-60" aria-hidden /> : null}
    </Wrapper>
  )
}
