'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  CornerDownLeft,
  HelpCircle,
  Loader2,
  Search,
  ShieldCheck,
  Sparkles,
  Zap,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { ApiError } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import {
  useAskAssistant,
  useAssistantHelp,
  useConfirmWrite,
  type AssistantAnswer,
  type AssistantChip,
  type AssistantTrace,
} from '@/features/assistant/api'
import { AssistantCard } from '@/components/assistant/cards'

/**
 * "Ask PGR" — deterministic fuzzy+BoW assistant palette.
 *
 * Opens on Cmd/Ctrl+K. Runs as the signed-in user; no data leaves the server. Every answer
 * carries a trace so the interpretation is auditable, and every write intent stages a pending
 * record that the user must confirm before anything changes.
 */

interface Turn {
  question: string
  answer: AssistantAnswer | null
  error?: string
}

// -------- kind → visual language ---------------------------------------------

const KIND_META = {
  answer:          { icon: CheckCircle2,  tone: 'text-[hsl(var(--success))]' },
  clarify:         { icon: HelpCircle,    tone: 'text-[hsl(var(--warning))]' },
  not_understood:  { icon: AlertTriangle, tone: 'text-muted-foreground' },
  confirm_write:   { icon: ShieldCheck,   tone: 'text-[hsl(var(--warning))]' },
} as const

// -------- Confirm-write card -------------------------------------------------

interface ConfirmData {
  pendingId: string
  action: string
  target: { label: string }
  diff: Record<string, unknown>
  expiresInSeconds?: number
}

function ConfirmWriteCard({
  data, onConfirm, pending,
}: {
  data: ConfirmData
  onConfirm: (pendingId: string) => void
  pending: boolean
}) {
  const before = (data.diff.before ?? {}) as Record<string, unknown>
  const after = (data.diff.after ?? {}) as Record<string, unknown>
  const meta = Object.fromEntries(
    Object.entries(data.diff).filter(([k]) => k !== 'before' && k !== 'after'),
  )
  const changedKeys = Array.from(new Set([...Object.keys(before), ...Object.keys(after)]))

  return (
    <div className="mt-4 rounded-lg border border-[hsl(var(--warning)/0.4)] bg-[hsl(var(--warning)/0.06)] p-4">
      <div className="mb-3 flex items-center gap-2">
        <Zap className="h-4 w-4 text-[hsl(var(--warning))]" />
        <p className="text-[11px] uppercase tracking-wider text-[hsl(var(--warning))]">Action ready</p>
      </div>
      <p className="mb-3 text-sm font-medium">{data.target.label}</p>

      {changedKeys.length > 0 && (
        <div className="rounded-md border border-border/50 bg-surface-1 px-3 py-2">
          {changedKeys.map((k, i) => (
            <div key={k}
              className={`flex items-center gap-3 text-xs ${i > 0 ? 'mt-1 pt-1 border-t border-border/40' : ''}`}
            >
              <span className="w-24 shrink-0 text-muted-foreground">{k}</span>
              <span className="font-mono line-through opacity-60">{String(before[k] ?? '—')}</span>
              <ArrowRight className="h-3 w-3 shrink-0 text-muted-foreground" />
              <span className="font-mono font-medium">{String(after[k] ?? '—')}</span>
            </div>
          ))}
        </div>
      )}

      {Object.keys(meta).length > 0 && (
        <p className="mt-2 text-xs text-muted-foreground">
          {Object.entries(meta).map(([k, v]) => `${k} ${String(v)}`).join(' · ')}
        </p>
      )}

      <div className="mt-4 flex items-center gap-2">
        <Button size="sm" onClick={() => onConfirm(data.pendingId)} disabled={pending}>
          {pending
            ? <><Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> Working…</>
            : <><ShieldCheck className="h-3.5 w-3.5 mr-1" /> Confirm &amp; run</>}
        </Button>
        <p className="ml-1 text-xs text-muted-foreground">
          Nothing has changed yet
          {typeof data.expiresInSeconds === 'number' && ` · expires in ${Math.round(data.expiresInSeconds / 60)}m`}
        </p>
      </div>
    </div>
  )
}

// -------- Trace (inline, minimal) --------------------------------------------

function InlineTrace({ trace }: { trace: AssistantTrace }) {
  const [open, setOpen] = useState(false)
  // Confirm-write responses carry a leaner trace ({executed, pendingId}) with no intents
  // array — defend against that shape rather than crashing the whole palette.
  const top = trace.intents?.[0]
  if (!top) return null
  return (
    <div className="mt-3 text-xs">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-muted-foreground/80 hover:text-foreground transition-colors"
      >
        {open ? '· hide reasoning' : '· why this answer'}
      </button>
      {open && (
        <div className="mt-2 space-y-1 rounded-md bg-surface-2/60 px-3 py-2 text-muted-foreground">
          <div className="flex items-center justify-between">
            <span className="font-mono text-foreground">{top.name}</span>
            <span className="relative h-1 w-24 overflow-hidden rounded-full bg-border/70">
              <span
                className="absolute inset-y-0 left-0 rounded-full bg-primary/70"
                style={{ width: `${Math.min(100, Math.round(top.score * 100))}%` }}
              />
            </span>
          </div>
          {top.core.length > 0 && (
            <p>matched <span className="font-mono">{top.core.join(' ')}</span>
              {top.entityAnchor && <span className="ml-1 text-primary">+ entity</span>}
            </p>
          )}
          {trace.entities && trace.entities.length > 0 && (
            <p>resolved {trace.entities.map((e) => e.name).join(', ')}</p>
          )}
          {trace.timeSlot && (
            <p>window <span className="num">{trace.timeSlot.from} → {trace.timeSlot.to}</span></p>
          )}
          {trace.intents && trace.intents.length > 1 && (
            <p>alternatives {trace.intents.slice(1).map((i) => `${i.name}·${i.score.toFixed(2)}`).join(' · ')}</p>
          )}
        </div>
      )}
    </div>
  )
}

// -------- Follow-up suggestions --------------------------------------------

/** Contextual "you might also ask…" chips shown under every answer so the flow keeps
 *  going. Reads the last answer's intent + resolved entity, and picks 2–4 next hops. */
function followupSuggestions(answer: AssistantAnswer): string[] {
  const intentName = answer.trace?.intents?.[0]?.name
  const entity = answer.trace?.entities?.[0]
  const person = entity?.name
  void person
  // Confirm-write and other minimal-trace answers — offer a couple of safe next hops.
  if (answer.trace?.executed) {
    return ['my tasks', 'who is at risk', 'mark all notifications as read']
  }
  const bySlot = (s: string) => `${person ? `${person}'s ` : ''}${s}`

  if (person && intentName === 'student_summary') {
    return [
      bySlot('funding'),
      bySlot('milestones'),
      bySlot('supervisors'),
      `how is ${person} progressing?`,
    ]
  }
  if (intentName === 'funding_gap' || intentName === 'held_payments'
      || intentName === 'overdue_payments' || intentName === 'funding_cashflow') {
    return [
      'unfunded students',
      'who is at risk',
      'students with funding expiring in 6 months',
      'held payments this quarter',
    ]
  }
  if (intentName === 'at_risk_students') {
    return [
      'unfunded students',
      'students with an overdue milestone',
      'students with no supervision meeting in 90 days',
      'who has funding expiring in 6 months',
    ]
  }
  if (intentName === 'milestones_overdue' || intentName === 'milestones_due') {
    return [
      'supervision meetings overdue',
      'who is at risk',
      'students with funding expiring in 6 months',
    ]
  }
  if (intentName === 'my_tasks') {
    return ['complete my next task', 'mark all notifications as read']
  }
  if (intentName === 'supervisor_workforce') {
    return [
      'supervision meetings overdue',
      'who is at risk',
      'assignment requests pending',
    ]
  }
  if (intentName === 'navigate') {
    return []
  }
  // Generic fall-through — always give SOMETHING so the thread never dead-ends.
  return [
    'who is at risk',
    'my tasks',
    'unfunded students',
  ]
}

function FollowupRow({ answer, onSuggest }: {
  answer: AssistantAnswer
  onSuggest: (q: string) => void
}) {
  const items = followupSuggestions(answer)
  if (items.length === 0) return null
  return (
    <div className="mt-4 border-t border-border/40 pt-3">
      <p className="mb-1.5 text-[11px] uppercase tracking-wider text-muted-foreground">
        You might also ask
      </p>
      <div className="flex flex-wrap gap-1.5">
        {items.map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => onSuggest(q)}
            className="rounded-full border border-border/60 bg-surface-2 px-3 py-1 text-xs text-muted-foreground transition-all hover:border-primary/50 hover:bg-primary/5 hover:text-foreground"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  )
}

// -------- Chip -------------------------------------------------------------

function ChipButton({ chip, onSuggest }: { chip: AssistantChip; onSuggest: (q: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onSuggest(chip.label)}
      className="rounded-full border border-border/60 bg-surface-2 px-3 py-1 text-xs transition-all hover:border-primary/50 hover:bg-primary/5"
      title={chip.description ? `${chip.description} (${chip.intent})` : chip.intent}
    >
      {chip.label}
    </button>
  )
}

// -------- One turn ----------------------------------------------------------

function AnswerBlock({
  turn, onSuggest, onNavigate, onConfirm, confirmPending,
}: {
  turn: Turn
  onSuggest: (q: string) => void
  onNavigate: () => void
  onConfirm: (pendingId: string) => void
  confirmPending: boolean
}) {
  const { answer, error } = turn
  const meta = answer ? (KIND_META[answer.kind ?? 'answer'] ?? KIND_META.answer) : KIND_META.answer
  const Icon = meta.icon

  return (
    <div className="space-y-3">
      {/* Question — right-aligned bubble, chat style */}
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-primary/10 px-4 py-2 text-sm text-foreground">
          {turn.question}
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-3 rounded-lg bg-destructive/5 px-4 py-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
          <p className="text-sm text-destructive">{error}</p>
        </div>
      )}

      {answer && (
        <div className="flex gap-3">
          <Icon className={`mt-1 h-4 w-4 shrink-0 ${meta.tone}`} />
          <div className="min-w-0 flex-1">
            <p className="whitespace-pre-wrap text-[15px] leading-relaxed">{answer.answer}</p>

            {answer.kind === 'confirm_write' && answer.card && (
              <ConfirmWriteCard
                data={answer.card.data as unknown as ConfirmData}
                onConfirm={onConfirm}
                pending={confirmPending}
              />
            )}

            {answer.kind === 'answer' && (
              <AssistantCard answer={answer} onNavigate={onNavigate} onSuggest={onSuggest} />
            )}

            {answer.chips && answer.chips.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {answer.chips.map((chip) => (
                  <ChipButton key={chip.intent} chip={chip} onSuggest={onSuggest} />
                ))}
              </div>
            )}

            {answer.links.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {answer.links.slice(0, 6).map((l) => (
                  <Link
                    key={l.href}
                    href={l.href}
                    onClick={onNavigate}
                    className="inline-flex items-center gap-1 rounded-full border border-border/60 bg-surface-2 px-3 py-1 text-xs transition-all hover:border-primary/50 hover:bg-primary/5"
                  >
                    {l.label}
                    <ArrowRight className="h-3 w-3" />
                  </Link>
                ))}
              </div>
            )}

            {answer.trace && <InlineTrace trace={answer.trace} />}

            {/* Contextual follow-ups so the conversation keeps rolling. Skip on write
             *  confirmations (the primary action is Confirm, not another question). */}
            {answer.kind !== 'confirm_write' && (
              <FollowupRow answer={answer} onSuggest={onSuggest} />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// -------- Empty state -------------------------------------------------------

const GROUP_LABEL: Record<string, string> = {
  finance: 'Finance', people: 'People', progression: 'Progression',
  recruitment: 'Recruitment', admin: 'Admin', meta: 'Meta',
}

/** A doer chip. Distinct look so users can spot actions vs questions at a glance. */
function DoerChip({ label, description, onClick }: {
  label: string; description?: string; onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={description}
      className="inline-flex items-center gap-1.5 rounded-full border border-[hsl(var(--warning)/0.4)] bg-[hsl(var(--warning)/0.08)] px-3 py-1.5 text-sm text-foreground transition-all hover:border-[hsl(var(--warning))] hover:bg-[hsl(var(--warning)/0.14)]"
    >
      <Zap className="h-3 w-3 text-[hsl(var(--warning))]" />
      {label}
    </button>
  )
}

/** Intent name → true if it's a write action (heuristic; the intent library also carries
 *  a `writeAction` flag but the /help endpoint doesn't return it yet). */
const DOER_NAMES = new Set([
  'approve_payment', 'hold_payment', 'submit_signoff',
  'complete_task', 'mark_notifications_read', 'transition_opportunity',
  'add_supervision_meeting', 'assign_supervisor',
])

function EmptyState({ onSuggest }: { onSuggest: (q: string) => void }) {
  const help = useAssistantHelp()
  const groups = help.data?.groups ?? []
  const [showAll, setShowAll] = useState(false)

  // Peel doers off into their own top section so users see there ARE actions, not
  // just questions.
  const doerExamples: { name: string; example: string; description: string }[] = []
  for (const g of groups) {
    for (const i of g.intents) {
      if (DOER_NAMES.has(i.name) && i.examples.length) {
        doerExamples.push({ name: i.name, example: i.examples[0], description: i.description })
      }
    }
  }

  return (
    <div className="space-y-7">
      <div>
        <p className="text-lg font-medium text-foreground">Ask, or tell me what to do.</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Answers come with the reasoning behind them. Actions stage a confirmation first —
          nothing changes until you click Confirm. Deterministic; nothing leaves the server.
        </p>
      </div>

      {doerExamples.length > 0 && (
        <div>
          <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-[hsl(var(--warning))]">
            <Zap className="h-3 w-3" /> Do — actions the assistant can perform for you
          </p>
          <div className="flex flex-wrap gap-2">
            {doerExamples.map((d) => (
              <DoerChip key={d.name} label={d.example} description={d.description}
                onClick={() => onSuggest(d.example)} />
            ))}
          </div>
          <p className="mt-2 text-[11px] text-muted-foreground">
            Each will show a confirm card with a before/after diff. Nothing runs without your click.
          </p>
        </div>
      )}

      {groups.length === 0 ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Loading intent library…
        </div>
      ) : (
        <div className="space-y-5">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Ask — questions the assistant can answer
          </p>
          {groups.map((g) => {
            const askIntents = g.intents.filter((i) => !DOER_NAMES.has(i.name))
            const items = showAll ? askIntents : askIntents.slice(0, 4)
            if (items.length === 0) return null
            return (
              <div key={g.name}>
                <p className="mb-2 text-[11px] uppercase tracking-wider text-muted-foreground/80">
                  {GROUP_LABEL[g.name] ?? g.name}
                </p>
                <div className="flex flex-wrap gap-2">
                  {items.flatMap((i) =>
                    i.examples.slice(0, 1).map((ex) => (
                      <button
                        key={`${i.name}-${ex}`}
                        type="button"
                        onClick={() => onSuggest(ex)}
                        className="rounded-full border border-border/60 bg-surface-2 px-3 py-1.5 text-sm transition-all hover:border-primary/50 hover:bg-primary/5"
                        title={i.description}
                      >
                        {ex}
                      </button>
                    )),
                  )}
                </div>
              </div>
            )
          })}
          <button
            type="button"
            onClick={() => setShowAll((v) => !v)}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            {showAll ? '· show fewer' : '· show more'}
          </button>
        </div>
      )}
    </div>
  )
}

// -------- Launcher ---------------------------------------------------------

export function AskPgrLauncher({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Ask PGR (Ctrl+K)"
      className="group fixed bottom-6 right-6 z-40 flex items-center gap-2 rounded-full bg-primary py-3 pl-4 pr-4 text-primary-foreground shadow-lg transition-all hover:shadow-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 md:pr-5"
    >
      <Sparkles className="h-5 w-5 shrink-0" />
      <span className="hidden text-sm font-medium md:inline">Ask PGR</span>
      <kbd className="ml-1 hidden rounded border border-primary-foreground/30 px-1.5 py-0.5 text-[10px] font-medium opacity-80 lg:inline">
        ⌘K
      </kbd>
    </button>
  )
}

// -------- Palette ----------------------------------------------------------

export function AskPgrPalette({
  open, onOpenChange,
}: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { hasPermission } = useAuth()
  const allowed = hasPermission('assistant.use')
  const [value, setValue] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const sessionIdRef = useRef<string>(
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2),
  )
  const ask = useAskAssistant()
  const confirmWrite = useConfirmWrite()
  const inputRef = useRef<HTMLInputElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [turns, ask.isPending])

  useEffect(() => {
    if (open) {
      // Each open = a fresh session: new slot-memory bucket on the server, empty transcript
      // client-side. Prevents accidental context leak from a previous conversation.
      sessionIdRef.current =
        typeof crypto !== 'undefined' && 'randomUUID' in crypto
          ? crypto.randomUUID()
          : Math.random().toString(36).slice(2)
      setTurns([])
      setValue('')
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  const submit = useCallback(
    async (raw: string) => {
      const question = raw.trim()
      if (!question || ask.isPending) return
      setValue('')
      setTurns((prev) => [...prev, { question, answer: null }])
      try {
        const answer = await ask.mutateAsync({ query: question, sessionId: sessionIdRef.current })
        setTurns((prev) => prev.map((t, i) => (i === prev.length - 1 ? { ...t, answer } : t)))
      } catch (e) {
        const message =
          e instanceof ApiError && e.status === 403
            ? 'Not available for your role.'
            : (e as Error).message
        setTurns((prev) => prev.map((t, i) => (i === prev.length - 1 ? { ...t, error: message } : t)))
      }
      // Keep the input ready for the next question — the conversation should
      // never dead-end at "you asked one thing, now click somewhere else".
      setTimeout(() => inputRef.current?.focus(), 50)
    },
    [ask],
  )

  const confirmHandler = useCallback(
    async (pendingId: string) => {
      try {
        const answer = await confirmWrite.mutateAsync({ pendingId })
        setTurns((prev) => [...prev, { question: '(confirmed)', answer }])
      } catch (e) {
        const message =
          e instanceof ApiError && e.status === 403
            ? 'Not permitted.'
            : (e as Error).message
        setTurns((prev) => [...prev, { question: '(confirmed)', answer: null, error: message }])
      }
    },
    [confirmWrite],
  )

  if (!open) return null

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[97vh] w-[98vw] max-w-none flex-col gap-0 overflow-hidden p-0 sm:rounded-xl">
        {/* Header */}
        <DialogHeader className="border-b border-border/60 px-6 py-3">
          <DialogTitle className="flex items-center justify-between gap-3 text-base font-medium">
            <span className="inline-flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" />
              Ask PGR
            </span>
            <span className="hidden items-center gap-1.5 text-xs font-normal text-muted-foreground md:inline-flex">
              <kbd className="rounded border border-border bg-surface-2 px-1.5 py-0.5 font-mono text-[10px]">esc</kbd>
              close
            </span>
          </DialogTitle>
        </DialogHeader>

        {!allowed ? (
          <div className="flex flex-1 items-center justify-center px-6 py-8">
            <p className="text-sm text-muted-foreground">Not available for your role.</p>
          </div>
        ) : (
          <>
            {/* Input — the same centered column as the thread */}
            <form
              onSubmit={(e) => { e.preventDefault(); void submit(value) }}
              className="border-b border-border/60 px-6 py-5 md:px-10"
            >
              <div className="mx-auto flex w-full max-w-3xl items-center gap-3">
                <Search className="h-5 w-5 shrink-0 text-muted-foreground" />
                <Input
                  ref={inputRef}
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                  placeholder="Ask anything — or type a student name / ref…"
                  className="h-10 border-0 bg-transparent px-0 text-lg shadow-none focus-visible:ring-0"
                />
                <Button type="submit" size="sm" variant="ghost" disabled={!value.trim() || ask.isPending}>
                  {ask.isPending
                    ? <Loader2 className="h-4 w-4 animate-spin" />
                    : <CornerDownLeft className="h-4 w-4" />}
                </Button>
              </div>
            </form>

            {/* Message thread — content centred + capped for readability at the wide dialog */}
            <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-8 md:px-10 md:py-10">
              <div className="mx-auto w-full max-w-4xl space-y-10">
                {turns.length === 0 && <EmptyState onSuggest={(q) => void submit(q)} />}

                {turns.map((t, i) => (
                  <AnswerBlock
                    key={i}
                    turn={t}
                    onSuggest={(q) => void submit(q)}
                    onNavigate={() => onOpenChange(false)}
                    onConfirm={confirmHandler}
                    confirmPending={confirmWrite.isPending}
                  />
                ))}

                {ask.isPending && (
                  <div className="flex items-center gap-3 text-sm text-muted-foreground">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    <span>Reading your question…</span>
                  </div>
                )}
              </div>
            </div>

            {/* Footer — single subtle line */}
            <div className="border-t border-border/60 bg-surface-2/40 px-6 py-2 text-xs text-muted-foreground">
              Deterministic · nothing leaves this server · write intents confirm first
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
