'use client'

/**
 * Ask a question, get a dashboard.
 *
 * The composer picks from a fixed catalogue of data functions and a fixed catalogue of
 * blocks — it never writes a query and never invents a number. What arrives here has
 * already been validated server-side, so this page is mostly about the states around the
 * answer: not configured, thinking, refused, and the provenance of what came back.
 */

import { useRef, useState } from 'react'
import { Check, Database, Loader2, Sparkles, Wand2, X } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/components/ui/use-toast'
import { ApiError } from '@/shared/api/client'
import { CompositionView } from '@/features/composer/BlockRenderer'
import { streamCompose, useComposerStatus, type ProgressStep } from '@/features/composer/api'
import type { ComposeMeta, ComposerAction, Composition } from '@/features/composer/types'

/**
 * Demo-ready prompts, grouped by intent and chosen so each one lands on a DIFFERENT
 * block shape (KPI row, gauge, donut, bar, line, table, timeline, heatmap, tree,
 * roadmap, comparison, sparkline grid, alert + action). Click through the row to
 * walk an audience through every visualization the composer knows.
 */
const EXAMPLE_GROUPS: { label: string; prompts: string[] }[] = [
  {
    label: 'Overview & KPIs',
    prompts: [
      'Give me a KPI overview of the PGR programme this year',
      'How close are we to our completion target this year?',
      'How many students are finishing in the next six months?',
    ],
  },
  {
    label: 'Trends over time',
    prompts: [
      'Show me intake trend over the last five years',
      'Show me the completion trend as a line chart',
      'Draw a roadmap of upcoming vivas over the next six months',
    ],
  },
  {
    label: 'Breakdowns',
    prompts: [
      'Break down our students by funding type as a donut',
      'Show the application pipeline by stage as a stacked bar',
      'Show the completion pipeline stages',
    ],
  },
  {
    label: 'Health & risk',
    prompts: [
      'Which students run out of funding before they are due to submit?',
      'Show me a heatmap of overdue milestones by department',
      'Which applications need action right now?',
      'Show supervision compliance across the department',
    ],
  },
  {
    label: 'Supervisors',
    prompts: [
      'Compare supervisor caseloads against their caps',
      'Show me each supervisor’s recent workload as sparklines',
      'How is supervisor Elena Ford’s caseload looking?',
    ],
  },
  {
    label: 'Student deep-dives',
    prompts: [
      'How is Marcus Bell progressing?',
      'Show me Marcus Bell’s PGR journey as a timeline',
      'Show the funding lineage for Marcus Bell as a tree',
    ],
  },
]

/** Flat list is still handy internally (fallback + tests). */
const EXAMPLES = EXAMPLE_GROUPS.flatMap((g) => g.prompts)

/**
 * The live step list shown while a composition is being built.
 *
 * Every line is a step the backend has actually completed — the model deciding what it
 * needs, each data function as it runs, and what came back. It replaces a blank spinner
 * over a wait that is genuinely several seconds long.
 */
function ProgressTrail({ steps }: { steps: ProgressStep[] }) {
  return (
    <ol className="space-y-2">
      {steps.map((step, i) => {
        const last = i === steps.length - 1
        return (
          <li key={i} className="flex items-start gap-2.5 text-sm">
            <span className="mt-0.5 shrink-0">
              {step.failed ? (
                <X className="h-3.5 w-3.5 text-destructive" />
              ) : last ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
              ) : (
                <Check className="h-3.5 w-3.5 text-[hsl(var(--success))]" />
              )}
            </span>
            {step.kind === 'function' ? (
              <span className="flex items-center gap-1.5 min-w-0">
                <Database className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                <span className="font-mono text-xs">{step.message}</span>
              </span>
            ) : (
              <span className={step.kind === 'result'
                ? 'text-muted-foreground min-w-0'
                : 'min-w-0'}>
                {step.message}
              </span>
            )}
          </li>
        )
      })}
    </ol>
  )
}

export default function ComposerPage() {
  const { toast } = useToast()
  const status = useComposerStatus()

  const [question, setQuestion] = useState('')
  const [result, setResult] = useState<{ composition: Composition; meta: ComposeMeta } | null>(null)
  const [steps, setSteps] = useState<ProgressStep[]>([])
  const [running, setRunning] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const ask = async (text: string) => {
    const q = text.trim()
    if (q.length < 3 || running) return

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setQuestion(q)
    setResult(null)
    setSteps([])
    setRunning(true)

    try {
      await streamCompose(q, {
        signal: controller.signal,
        onStep: (step) => setSteps((prev) => [...prev, step]),
        onDone: (response) => setResult(response),
        onError: (message) =>
          toast({
            title: 'Could not compose an answer',
            description: message,
            variant: 'destructive',
          }),
      })
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        toast({
          title: 'Could not compose an answer',
          description: (e as ApiError).message,
          variant: 'destructive',
        })
      }
    } finally {
      setRunning(false)
    }
  }

  const onAction = (action: ComposerAction) => {
    // Writes are staged, never executed from a generated button. Until the staging
    // registry is wired through, say so plainly rather than pretending.
    toast({
      title: action.label,
      description:
        `This would stage "${action.tool}" for confirmation. Staged writes arrive in the ` +
        `next iteration — nothing has been changed.`,
    })
  }

  const blocked = status.data && !status.data.enabled

  return (
    <>
      <PageHeader
        title="Composer"
        description="Ask a question and get a dashboard built from live data."
      />

      <div className="px-6 pb-6 space-y-4">
        <PageSection icon={Wand2} title="Ask" accent="primary">
          <div className="flex flex-wrap items-center gap-2">
            <Input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') ask(question) }}
              placeholder="e.g. which students run out of funding before they submit?"
              className="flex-1 min-w-[280px]"
              disabled={running || blocked}
            />
            <Button
              onClick={() => ask(question)}
              disabled={running || blocked || question.trim().length < 3}
            >
              {running
                ? <><Loader2 className="h-4 w-4 mr-1 animate-spin" /> Composing…</>
                : <><Sparkles className="h-4 w-4 mr-1" /> Compose</>}
            </Button>
          </div>

          {!blocked && (
            <div className="mt-3 space-y-2">
              <p className="text-helper text-xs">
                Demo prompts — one click, each lands on a different visualization.
              </p>
              {EXAMPLE_GROUPS.map((group) => (
                <div key={group.label} className="flex flex-wrap items-baseline gap-1.5">
                  <span className="text-[10px] uppercase tracking-wider text-muted-foreground w-28 shrink-0">
                    {group.label}
                  </span>
                  {group.prompts.map((example) => (
                    <button
                      key={example}
                      type="button"
                      onClick={() => ask(example)}
                      disabled={running}
                      className="rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground transition hover:text-foreground hover:border-border-strong disabled:opacity-50"
                    >
                      {example}
                    </button>
                  ))}
                </div>
              ))}
            </div>
          )}

          {status.isLoading && <Skeleton className="h-5 w-64 mt-3" />}

          {blocked && (
            <div className="mt-3 rounded-md border border-[hsl(var(--warning)/0.35)] bg-[hsl(var(--warning)/0.08)] px-3 py-2.5">
              <p className="text-sm">{status.data?.reason}</p>
              {!status.data?.providerLive && (
                <p className="text-helper mt-1">
                  A model also needs configuring on this deployment before compositions can
                  be generated.
                </p>
              )}
            </div>
          )}

          {status.data?.enabled && (
            <p className="text-helper mt-3">
              {status.data.functions.length} data functions available to you. Every figure
              shown comes from one of them — nothing is estimated.
            </p>
          )}
        </PageSection>

        {(running || (steps.length > 0 && !result)) && (
          <PageSection icon={Sparkles} title="Composing" accent="accent">
            {steps.length === 0
              ? <p className="text-helper">Starting…</p>
              : <ProgressTrail steps={steps} />}
          </PageSection>
        )}

        {result && !running && (
          <div className="card-elevated px-5 py-5">
            <CompositionView
              composition={result.composition}
              onAction={onAction}
              footer={
                <div className="flex flex-wrap items-center gap-2 border-t border-border/60 pt-3">
                  <span className="text-helper">Built from</span>
                  {/* Badges title-case by default, which is right for status pills and
                      wrong for identifiers — these are function names, shown verbatim. */}
                  {[...new Set(result.meta.functionsCalled)].map((fn) => (
                    <Badge key={fn} variant="secondary" className="font-mono normal-case">
                      {fn}
                    </Badge>
                  ))}
                  <span className="text-helper ml-auto num">
                    {result.meta.latencyMs.toLocaleString()} ms ·{' '}
                    {(result.meta.tokensIn + result.meta.tokensOut).toLocaleString()} tokens
                  </span>
                </div>
              }
            />
          </div>
        )}
      </div>
    </>
  )
}
