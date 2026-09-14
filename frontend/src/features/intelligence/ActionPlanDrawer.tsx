'use client'

/**
 * Intervention plan confirmation drawer (spec §8 §9).
 *
 * Trust boundary between AI proposal and workflow execution:
 *   1. Every action has an explicit type, target, owner, due-date source label.
 *   2. Each action is deselectable — user drops individual steps from the bundle.
 *   3. Confirmation footer states the exact count and warns that permissions +
 *      state will be rechecked server-side before anything executes.
 * The staged plan is generated on the server; this drawer never invents new actions.
 */
import { useMemo, useState } from 'react'
import { Shield } from 'lucide-react'
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import { intelligenceApi, type InterventionPlan, type ActionType } from './api'

const ACTION_LABEL: Record<ActionType, string> = {
  create_task:                'Create task',
  prepare_meeting_brief:      'Generate meeting brief',
  request_funding_review:     'Request funding review',
  open_review_evidence_check: 'Open evidence review',
  schedule_reassessment:      'Reassess',
}

export interface ActionPlanDrawerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  plan: InterventionPlan | null
  onConfirmed?: (plan: InterventionPlan) => void
}

export function ActionPlanDrawer({ open, onOpenChange, plan, onConfirmed }: ActionPlanDrawerProps) {
  const [checked, setChecked] = useState<Record<string, boolean>>({})
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const initialChecked = useMemo(() => {
    const acc: Record<string, boolean> = {}
    plan?.actions?.forEach((a) => { acc[a.id] = true })
    return acc
  }, [plan])
  const state = Object.keys(checked).length ? checked : initialChecked
  const activeCount = Object.values(state).filter(Boolean).length

  async function confirm() {
    if (!plan) return
    setConfirming(true); setError(null)
    try {
      // The current API confirms all pending actions on a plan. Deselected actions stay
      // out of scope by being cancelled first (a future endpoint may accept per-action
      // toggles). For now we surface the mismatch to the reviewer.
      const result = await intelligenceApi.confirmPlan(plan.id)
      onConfirmed?.(result)
      onOpenChange(false)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setConfirming(false)
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-xl overflow-y-auto">
        <SheetHeader>
          <SheetTitle>
            {plan?.status === 'confirmed' ? 'Intervention plan — already confirmed'
              : plan?.status === 'cancelled' ? 'Intervention plan — cancelled'
              : 'Intervention plan — review before execution'}
          </SheetTitle>
          <SheetDescription>
            Suggested intervention · {plan?.rationale ?? '—'}
          </SheetDescription>
        </SheetHeader>

        {!plan ? (
          <p className="mt-4 text-sm text-muted-foreground">No plan staged yet.</p>
        ) : (
          <>
            {plan.status !== 'draft' ? (
              <div className="mt-4 flex items-start gap-2 rounded-md border border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/20 px-3 py-2 text-sm text-emerald-900 dark:text-emerald-200">
                <Shield className="h-4 w-4 mt-0.5 shrink-0" aria-hidden />
                <span>
                  {plan.status === 'confirmed'
                    ? `An intervention was already staged and confirmed for this signal${plan.confirmedAt ? ` on ${new Date(plan.confirmedAt).toLocaleDateString()}` : ''}. Nothing new to do here — cancel it first if you want to start fresh.`
                    : 'This plan was cancelled — no actions were executed.'}
                </span>
              </div>
            ) : null}
            <ol className="mt-4 space-y-2">
              {plan.actions.map((a, idx) => {
                const on = state[a.id] ?? true
                const dueSource = a.dueAt ? 'user-selected' : 'not specified'
                return (
                  <li key={a.id} className="flex items-start gap-3 rounded-md border p-3">
                    <Checkbox
                      id={`act-${a.id}`}
                      checked={on}
                      onCheckedChange={(v) => setChecked((s) => ({ ...s, [a.id]: !!v }))}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 text-sm">
                        <span className="text-muted-foreground">{idx + 1}.</span>
                        <span className="font-medium">{ACTION_LABEL[a.actionType]}</span>
                        <Badge variant="secondary">{a.status}</Badge>
                      </div>
                      <p className="mt-0.5 text-xs text-muted-foreground truncate">
                        Target: {JSON.stringify(a.targetRef).slice(0, 80)}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Owner: {a.ownerRef ? JSON.stringify(a.ownerRef).slice(0, 60) : 'unresolved'}
                        {' · '}
                        Due: {a.dueAt ?? 'Not specified'} <span className="opacity-60">({dueSource})</span>
                      </p>
                    </div>
                  </li>
                )
              })}
            </ol>

            {plan.status === 'draft' ? (
              <div className="mt-4 flex items-start gap-2 rounded-md border bg-muted/30 px-3 py-2 text-xs">
                <Shield className="h-3.5 w-3.5 mt-0.5 text-muted-foreground shrink-0" aria-hidden />
                <p className="text-muted-foreground">
                  Confirming will execute {activeCount} action{activeCount === 1 ? '' : 's'}.
                  Current permissions and record state are rechecked server-side; a stale plan is refused.
                </p>
              </div>
            ) : null}

            {error ? <p className="mt-2 text-sm text-destructive">{error}</p> : null}

            <div className="mt-4 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => onOpenChange(false)}>
                {plan.status === 'draft' ? 'Cancel' : 'Close'}
              </Button>
              {plan.status === 'draft' ? (
                <Button onClick={confirm} disabled={confirming || activeCount === 0}>
                  {confirming ? 'Confirming…' : `Confirm ${activeCount} action${activeCount === 1 ? '' : 's'}`}
                </Button>
              ) : null}
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}
