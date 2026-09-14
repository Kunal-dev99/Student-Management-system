'use client'

/**
 * Uniform banner for the five AI-degraded states enumerated in the frontend spec §22.
 * Every AI-driven region renders this instead of a spinner when the model can't help.
 * Keep copy exactly as the spec dictates so the user learns one phrase per state.
 */
import { AlertCircle, CircleOff, Clock, Info, RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'

type State = 'model_off' | 'missing_data' | 'stale_evidence' | 'stale_model' | 'error' | 'job_queued'

const COPY: Record<State, { title: string; icon: typeof Info; tone: string }> = {
  model_off:      { title: 'AI narration is unavailable. Showing rule-based results.',        icon: CircleOff, tone: 'text-muted-foreground bg-muted/40 border-border' },
  missing_data:   { title: 'Some source is not available, so this conclusion is limited.',     icon: Info,      tone: 'text-amber-800 bg-amber-50 border-amber-200 dark:text-amber-200 dark:bg-amber-950/30 dark:border-amber-900' },
  stale_evidence: { title: 'This explanation was generated before the record changed. Refresh analysis.', icon: RefreshCw, tone: 'text-amber-800 bg-amber-50 border-amber-200 dark:text-amber-200 dark:bg-amber-950/30 dark:border-amber-900' },
  stale_model:    { title: 'Prediction model is under review. Treat this score as advisory.',  icon: AlertCircle, tone: 'text-orange-800 bg-orange-50 border-orange-200 dark:text-orange-200 dark:bg-orange-950/30 dark:border-orange-900' },
  error:          { title: 'AI narration failed. Deterministic result is unchanged.',          icon: AlertCircle, tone: 'text-destructive bg-destructive/10 border-destructive/30' },
  job_queued:     { title: 'Comparison queued. You can continue working; results appear here.',icon: Clock,     tone: 'text-muted-foreground bg-muted/40 border-border' },
}

export interface AIStateBannerProps {
  state: State
  detail?: string
  action?: { label: string; onClick: () => void }
  className?: string
}

export function AIStateBanner({ state, detail, action, className }: AIStateBannerProps) {
  const { title, icon: Icon, tone } = COPY[state]
  return (
    <div className={cn('flex items-start gap-2 rounded-md border px-3 py-2 text-sm', tone, className)} role="status">
      <Icon className="h-4 w-4 mt-0.5 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="font-medium leading-snug">{title}</p>
        {detail ? <p className="mt-0.5 text-xs opacity-80 leading-snug">{detail}</p> : null}
      </div>
      {action ? (
        <button
          type="button"
          onClick={action.onClick}
          className="text-xs font-medium underline underline-offset-2 hover:no-underline shrink-0"
        >
          {action.label}
        </button>
      ) : null}
    </div>
  )
}
