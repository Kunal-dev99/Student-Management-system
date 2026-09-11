'use client'

/**
 * SSE-driven reasoning trace.
 *
 * Every step corresponds to real server work (no faked steps). The reveal holds at the
 * last step until the actual response arrives — a fast model call doesn't blow past the
 * reasoning, and a slow one doesn't feel abandoned.
 *
 * `onResult` and `onError` are called by the parent to drive the page's reveal state; the
 * trace itself only knows how to display the steps.
 */

import { useEffect, useRef, useState } from 'react'
import {
  Calculator, Check, Database, Layout, Loader2, PenLine, Sparkles,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '@/lib/utils'

export interface TraceStep {
  label: string
  detail?: string | null
  icon?: string | null
  done: boolean
}

const ICONS: Record<string, LucideIcon> = {
  database: Database,
  calculator: Calculator,
  sparkles: Sparkles,
  pen: PenLine,
  layout: Layout,
}

export interface UseTraceOptions<T> {
  /** Called to open the stream. Auth belongs to the caller's shared api client. */
  fetcher: ((signal: AbortSignal) => Promise<Response>) | null
  key: unknown
  onResult: (payload: T) => void
  /** Optional early result — deterministic data available before the AI part finishes. */
  onPartial?: (payload: T) => void
  onError?: (message: string) => void
}

/** Hook: open an SSE stream, collect steps, pass the final payload to the caller. */
export function useReasoningTrace<T>({ fetcher, key, onResult, onPartial, onError }: UseTraceOptions<T>) {
  const [steps, setSteps] = useState<TraceStep[]>([])
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!fetcher) return
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setSteps([])
    setError(null)
    setRunning(true)

    let currentSteps: TraceStep[] = []

    const run = async () => {
      try {
        const response = await fetcher(ctrl.signal)
        if (!response.ok || !response.body) {
          throw new Error(`HTTP ${response.status}`)
        }
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        while (true) {
          const { value, done } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          let idx: number
          while ((idx = buffer.indexOf('\n\n')) >= 0) {
            const frame = buffer.slice(0, idx)
            buffer = buffer.slice(idx + 2)
            const line = frame.split('\n').find((l) => l.startsWith('data: '))
            if (!line) continue
            const event = JSON.parse(line.slice(6))
            if (event.type === 'step') {
              // Close the previous step as done, add the new one as running.
              currentSteps = currentSteps.map((s) => ({ ...s, done: true }))
              currentSteps = [...currentSteps, {
                label: event.label, detail: event.detail, icon: event.icon, done: false,
              }]
              setSteps(currentSteps)
            } else if (event.type === 'partial') {
              onPartial?.(event.payload as T)
            } else if (event.type === 'result') {
              currentSteps = currentSteps.map((s) => ({ ...s, done: true }))
              setSteps(currentSteps)
              onResult(event.payload as T)
              setRunning(false)
            } else if (event.type === 'error') {
              setError(event.message)
              onError?.(event.message)
              setRunning(false)
            }
          }
        }
      } catch (err) {
        if ((err as { name?: string }).name === 'AbortError') return
        const message = err instanceof Error ? err.message : String(err)
        setError(message)
        onError?.(message)
        setRunning(false)
      }
    }
    void run()
    return () => ctrl.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  return { steps, error, running }
}

/**
 * Presentation: the step list.
 *
 * Each step animates in, carries an icon that hints at the kind of work happening
 * (database, calculator, sparkles, pen, layout), and shows a soft pulse on the active
 * one. Completed steps subside so the eye lands on the current work.
 */
export function ReasoningTrace({ steps, running }: { steps: TraceStep[]; running: boolean }) {
  if (steps.length === 0 && !running) return null
  // First-frame placeholder: the SSE handshake takes ~30-100ms before the server emits
  // step 1. Without this, the trace pane briefly renders blank on cold visits.
  if (steps.length === 0 && running) {
    return (
      <ol className="reasoning-trace space-y-2.5">
        <li className="reasoning-step flex items-start gap-3">
          <span className="reasoning-icon reasoning-pulse relative mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary" aria-hidden>
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          </span>
          <span className="min-w-0 pt-1">
            <span className="block text-sm font-medium leading-tight text-foreground">
              Waking things up
            </span>
            <span className="mt-0.5 block text-xs text-muted-foreground leading-snug">
              opening a stream to the server…
            </span>
          </span>
        </li>
      </ol>
    )
  }
  return (
    <ol className="reasoning-trace space-y-2.5">
      {steps.map((step, i) => {
        const isLast = i === steps.length - 1
        const active = running && isLast && !step.done
        const IconComponent = step.icon ? ICONS[step.icon] : null
        return (
          <li
            key={i}
            className="reasoning-step flex items-start gap-3"
            style={{ animationDelay: `${i * 40}ms` }}
          >
            <span
              className={cn(
                'reasoning-icon relative mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full',
                step.done && 'bg-primary/10 text-primary',
                active && 'bg-primary/15 text-primary reasoning-pulse',
                !step.done && !active && 'bg-muted text-muted-foreground',
              )}
              aria-hidden
            >
              {step.done ? (
                <Check className="h-3.5 w-3.5" />
              ) : active ? (
                IconComponent ? (
                  <IconComponent className="h-3.5 w-3.5 animate-pulse" />
                ) : (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                )
              ) : IconComponent ? (
                <IconComponent className="h-3.5 w-3.5" />
              ) : (
                <span className="h-1.5 w-1.5 rounded-full bg-current" />
              )}
            </span>
            <span className="min-w-0 pt-1">
              <span
                className={cn(
                  'block text-sm font-medium leading-tight',
                  step.done && 'text-foreground/85',
                  active && 'text-foreground',
                  !step.done && !active && 'text-muted-foreground',
                )}
              >
                {step.label}
              </span>
              {step.detail && (
                <span className="mt-0.5 block text-xs text-muted-foreground leading-snug">
                  {step.detail}
                </span>
              )}
            </span>
          </li>
        )
      })}
    </ol>
  )
}
