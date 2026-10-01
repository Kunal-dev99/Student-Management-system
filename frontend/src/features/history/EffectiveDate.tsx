'use client'

/** Effective dating, Phase 5 — the "from when?" input every change form shares, plus the
 *  warnings that go with it:
 *  - the date reaches a return that has already been signed off (it may need resubmitting);
 *  - the date is before the open reporting year, which needs the history-correction permission.
 *  The server enforces both; this only says so before the user presses the button. */

import { AlertTriangle, Lock } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { type RetrospectiveWarning, useRetrospectiveCheck, todayIso } from './api'

export function RetrospectiveWarnings({ warnings, className }: { warnings?: RetrospectiveWarning[]; className?: string }) {
  if (!warnings || warnings.length === 0) return null
  return (
    <div className={cn('space-y-1', className)}>
      {warnings.map((w) => (
        <p key={w.profileId} className="flex items-start gap-1.5 text-xs text-[hsl(var(--warning))]">
          <AlertTriangle className="h-3.5 w-3.5 mt-px shrink-0" />
          <span>{w.message}</span>
        </p>
      ))}
    </div>
  )
}

/** Shows the check for a chosen date (and optional exclusive end). Renders nothing when clear. */
export function EffectiveDateCheck({
  studentId, from, to, className,
}: { studentId: string | undefined; from: string | null | undefined; to?: string | null; className?: string }) {
  const check = useRetrospectiveCheck(studentId, from, to)
  const c = check.data
  if (!c) return null
  const blocked = c.beforeOpenYear && !c.canBackdate
  if (!c.beforeOpenYear && c.warnings.length === 0) return null
  return (
    <div className={cn('space-y-1', className)}>
      {c.beforeOpenYear && (
        <p className={cn('flex items-start gap-1.5 text-xs',
          blocked ? 'text-[hsl(var(--destructive))]' : 'text-muted-foreground')}>
          <Lock className="h-3.5 w-3.5 mt-px shrink-0" />
          <span>
            Before the open reporting year (from {c.openYearStart}).{' '}
            {blocked
              ? 'Back-dating into a closed year needs history-correction rights — ask Registry.'
              : 'You can back-date this because you hold history-correction rights.'}
          </span>
        </p>
      )}
      <RetrospectiveWarnings warnings={c.warnings} />
    </div>
  )
}

/** A labelled date input (defaults to today when empty) with the live check underneath.
 *  ``allowFuture`` false caps the picker at today — funding and supervision can't be
 *  future-dated yet. */
export function EffectiveDateField({
  studentId, value, onChange, label = 'Effective from', allowFuture = true, id, className, inputClassName,
}: {
  studentId: string | undefined
  value: string
  onChange: (v: string) => void
  label?: string
  allowFuture?: boolean
  id?: string
  className?: string
  inputClassName?: string
}) {
  const today = todayIso()
  const inputId = id ?? `eff-${label.replace(/\W+/g, '-').toLowerCase()}`
  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <label htmlFor={inputId} className="text-label">{label}</label>
      <Input id={inputId} type="date" className={cn('h-8 w-40', inputClassName)}
        value={value} max={allowFuture ? undefined : today}
        onChange={(e) => onChange(e.target.value)} />
      <EffectiveDateCheck studentId={studentId} from={value || today} className="max-w-sm" />
    </div>
  )
}
