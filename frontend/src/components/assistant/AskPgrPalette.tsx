'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { ArrowRight, CornerDownLeft, HelpCircle, Loader2, Search, Sparkles, Zap } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { ApiError } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import {
  useAskAssistant,
  useCapabilities,
  type AssistantAnswer,
  type AssistantStudentRow,
} from '@/features/assistant/api'

/**
 * "Ask PGR" — the one-sentence command palette (Phase 5.1, read-only).
 *
 * Opens on Cmd/Ctrl+K. Answers come from the backend assistant, which runs as the signed-in user
 * and applies that user's row scope, so nothing shown here is beyond what they could already see.
 */

interface Turn {
  question: string
  answer: AssistantAnswer | null
  error?: string
}

/** Rows a cohort/find tool returned — the highest-value output, so render it properly. */
function StudentRows({ rows, onNavigate }: { rows: AssistantStudentRow[]; onNavigate: () => void }) {
  return (
    <ul className="mt-3 space-y-1.5">
      {rows.map((r, i) => (
        <li key={r.studentId ?? i}>
          <Link
            href={r.link ?? '#'}
            onClick={onNavigate}
            className="block rounded-md border border-border/60 px-3 py-2 transition-colors hover:bg-surface-2"
          >
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">{r.personName ?? r.studentRef}</span>
              {r.studentRef && r.personName && (
                <span className="font-mono text-xs text-muted-foreground">{r.studentRef}</span>
              )}
              {r.status && <Badge variant="secondary">{r.status.replace('_', ' ')}</Badge>}
            </div>
            {r.reasons && r.reasons.length > 0 && (
              <ul className="mt-1 space-y-0.5">
                {r.reasons.map((reason, j) => (
                  <li key={j} className="text-helper">— {reason}</li>
                ))}
              </ul>
            )}
          </Link>
        </li>
      ))}
    </ul>
  )
}

function AnswerBlock({
  turn,
  onSuggest,
  onNavigate,
}: {
  turn: Turn
  onSuggest: (q: string) => void
  /** Close the palette when the user follows a link, so it doesn't sit on top of the page. */
  onNavigate: () => void
}) {
  const { answer, error } = turn
  const rows = answer?.data?.students ?? answer?.data?.candidates ?? []
  // A single candidate is already summarised in the answer text + links; don't repeat it.
  const showRows = rows.length > 1 || (rows.length === 1 && Boolean(rows[0]?.reasons?.length))
  const suggestions = answer?.data?.didYouMean ?? []

  return (
    <div className="border-b border-border/60 px-1 pb-4 last:border-0">
      <div className="flex items-start gap-2">
        <Search className="mt-1 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">{turn.question}</p>
      </div>

      {error && <p className="mt-2 text-sm text-destructive">{error}</p>}

      {answer && (
        <div className="mt-2 pl-5">
          <p className="whitespace-pre-wrap text-sm">{answer.answer}</p>

          {/* Readback: how the question was interpreted, so the user can verify it. */}
          {answer.understood && (
            <p className="text-helper mt-1">Interpreted as: {answer.understood}</p>
          )}

          {suggestions.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {suggestions.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => onSuggest(s)}
                  className="rounded-md border border-border bg-surface-2 px-2.5 py-1 text-xs transition-colors hover:border-foreground/20"
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          {showRows && <StudentRows rows={rows} onNavigate={onNavigate} />}

          {answer.links.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {answer.links.slice(0, 6).map((l) => (
                <Link
                  key={l.href}
                  href={l.href}
                  onClick={onNavigate}
                  className="inline-flex items-center gap-1 rounded-md border border-border bg-surface-2 px-2 py-1 text-xs transition-colors hover:border-foreground/20"
                >
                  {l.label}
                  <ArrowRight className="h-3 w-3" />
                </Link>
              ))}
            </div>
          )}

          <div className="mt-2 flex items-center gap-2">
            {answer.path === 'rules' && (
              <Badge variant="secondary" className="gap-1" title="Answered on-premise — no data left the server">
                <Zap className="h-3 w-3" /> instant
              </Badge>
            )}
            {answer.path === 'guess' && (
              <Badge variant="warning" className="gap-1" title="Inferred from related words — check the interpretation">
                <HelpCircle className="h-3 w-3" /> best guess
              </Badge>
            )}
            {answer.path === 'model' && (
              <Badge variant="info" className="gap-1">
                <Sparkles className="h-3 w-3" /> AI
              </Badge>
            )}
            {answer.data?.filters && Array.isArray(answer.data.filters) && answer.data.filters.length > 0 && (
              <span className="text-helper">matched on: {(answer.data.filters as string[]).join(' · ')}</span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * Always-visible launcher. The palette is also on Cmd/Ctrl+K and the header search button, but a
 * feature nobody can see is a feature nobody uses — this is the discoverable affordance.
 */
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

export function AskPgrPalette({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { hasPermission } = useAuth()
  const allowed = hasPermission('assistant.use')
  const [value, setValue] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const ask = useAskAssistant()
  const caps = useCapabilities(open && allowed)
  const inputRef = useRef<HTMLInputElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Keep the newest answer in view.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [turns, ask.isPending])

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50)
  }, [open])

  const submit = useCallback(
    async (raw: string) => {
      const question = raw.trim()
      if (!question || ask.isPending) return
      setValue('')
      // History is the plain Q&A pairs, so a follow-up keeps context on the model path.
      const history = turns.flatMap((t) =>
        t.answer
          ? [
              { role: 'user' as const, content: t.question },
              { role: 'assistant' as const, content: t.answer.answer },
            ]
          : [],
      )
      setTurns((prev) => [...prev, { question, answer: null }])
      try {
        const answer = await ask.mutateAsync({ query: question, history })
        setTurns((prev) => prev.map((t, i) => (i === prev.length - 1 ? { ...t, answer } : t)))
      } catch (e) {
        const message =
          e instanceof ApiError && e.status === 403
            ? 'Not available for your role.'
            : (e as Error).message
        setTurns((prev) => prev.map((t, i) => (i === prev.length - 1 ? { ...t, error: message } : t)))
      }
    },
    [ask, turns],
  )

  // Unmount entirely when closed rather than letting Radix hold the panel for its exit
  // animation. Following a link triggers a route change that interrupts that animation, so
  // `animationend` never fires and the closed panel stays visible on top of the new page.
  // (All hooks above run unconditionally, so hook order is stable.)
  if (!open) return null

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl gap-0 p-0">
        <DialogHeader className="border-b border-border px-4 py-3">
          <DialogTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-4 w-4 text-primary" />
            Ask PGR
          </DialogTitle>
        </DialogHeader>

        {!allowed ? (
          <p className="px-4 py-6 text-sm text-muted-foreground">Not available for your role.</p>
        ) : (
          <>
            <form
              onSubmit={(e) => {
                e.preventDefault()
                void submit(value)
              }}
              className="flex items-center gap-2 border-b border-border px-4 py-3"
            >
              <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
              <Input
                ref={inputRef}
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder="Ask anything — or type a student ref…"
                className="border-0 px-0 shadow-none focus-visible:ring-0"
              />
              <Button type="submit" size="sm" disabled={!value.trim() || ask.isPending}>
                {ask.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <CornerDownLeft className="h-4 w-4" />
                )}
              </Button>
            </form>

            <div ref={scrollRef} className="max-h-[55vh] space-y-4 overflow-y-auto px-4 py-4">
              {turns.length === 0 && (
                <div>
                  <p className="text-helper mb-2">Try one of these:</p>
                  <div className="flex flex-wrap gap-1.5">
                    {(caps.data?.examples ?? []).map((ex) => (
                      <button
                        key={ex}
                        type="button"
                        onClick={() => void submit(ex)}
                        className="rounded-md border border-border bg-surface-2 px-2.5 py-1 text-xs transition-colors hover:border-foreground/20"
                      >
                        {ex}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {turns.map((t, i) => (
                <AnswerBlock
                  key={i}
                  turn={t}
                  onSuggest={(q) => void submit(q)}
                  onNavigate={() => onOpenChange(false)}
                />
              ))}

              {ask.isPending && (
                <div className="flex items-center gap-2 pl-5 text-sm text-muted-foreground">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> Thinking…
                </div>
              )}
            </div>

            <div className="border-t border-border px-4 py-2">
              <p className="text-helper">
                Read-only — I can&apos;t change anything. I&apos;ll point you to the right screen for that.
              </p>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
