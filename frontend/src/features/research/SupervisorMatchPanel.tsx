'use client'

/**
 * Supervisor matching (Phase 7 R5).
 *
 * The product here is the *explanation*, not the ranking. Every point a
 * supervisor scores is attributed to a named factor, and the breakdown is
 * rendered inline under each result — not tucked behind a disclosure — because
 * a supervisor allocation is a decision people contest, and "why was I not
 * suggested?" must have a visible answer.
 *
 * Two consequences the UI must honour:
 *  - a supervisor at capacity is scored down, never hidden;
 *  - the backend's advisory note is rendered verbatim, and nothing on this
 *    screen may imply the score decides anything.
 */

import { useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, ExternalLink, Info, Search, Sparkles, UserSearch } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { ApiError } from '@/shared/api/client'
import {
  useResearchAreas, useSupervisorSuggestions,
  type MatchReason, type SupervisorSuggestion,
} from './api'

/** Score is out of 100 by construction (the backend weights sum to 100). */
function ScoreBar({ score, muted }: { score: number; muted: boolean }) {
  const pct = Math.max(0, Math.min(100, score))
  return (
    <div className="w-28 shrink-0">
      <div className="flex items-baseline justify-between">
        <span className={`text-lg font-semibold num ${muted ? 'text-muted-foreground' : 'text-primary'}`}>
          {score}
        </span>
        <span className="text-xs text-muted-foreground num">/ 100</span>
      </div>
      <div
        className="mt-1 h-1.5 w-full rounded-sm bg-surface-3 overflow-hidden"
        role="meter"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Match score ${score} out of 100`}
      >
        <div
          className={`h-full rounded-sm ${muted ? 'bg-muted-foreground/50' : 'bg-primary'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

/**
 * One attributed contribution. A zero-point reason (at capacity) is the most
 * informative row on the panel, so it renders like the rest — just unemphasised.
 */
function ReasonRow({ reason }: { reason: MatchReason }) {
  const zero = reason.points === 0
  return (
    <div className="flex items-baseline gap-2 text-xs">
      <span
        className={`num font-medium w-9 shrink-0 text-right ${
          zero ? 'text-muted-foreground' : 'text-[hsl(var(--success))]'
        }`}
      >
        +{reason.points}
      </span>
      <span className="font-medium shrink-0">{reason.factor}</span>
      <span className="text-muted-foreground min-w-0">{reason.detail}</span>
    </div>
  )
}

function SuggestionRow({ s }: { s: SupervisorSuggestion }) {
  return (
    <div
      className={`rounded-md border px-3 py-2.5 ${
        s.atCapacity ? 'border-dashed border-border bg-transparent opacity-70' : 'border-border bg-surface-2'
      }`}
    >
      <div className="flex items-start gap-4">
        <ScoreBar score={s.score} muted={s.atCapacity} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Link href={s.link} className="text-sm font-medium text-primary hover:underline">
              {s.personName}
            </Link>
            <ExternalLink className="h-3 w-3 text-muted-foreground" aria-hidden />
            <span className="text-helper num">
              {s.currentSupervisees} current supervisee{s.currentSupervisees === 1 ? '' : 's'}
            </span>
            {s.atCapacity && (
              <Badge variant="warning" title="Listed and scored down, never hidden — the decision stays with a human.">
                at capacity
              </Badge>
            )}
          </div>
          <div className="mt-1.5 space-y-0.5">
            {s.reasons.length > 0 ? (
              s.reasons.map((r, i) => <ReasonRow key={`${r.factor}-${i}`} reason={r} />)
            ) : (
              <p className="text-xs text-muted-foreground italic">
                Nothing in this person&apos;s record matched the criteria.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export function SupervisorMatchPanel() {
  const { toast } = useToast()
  const areas = useResearchAreas()
  const suggest = useSupervisorSuggestions()
  const [areaId, setAreaId] = useState('')
  const [proposal, setProposal] = useState('')

  const result = suggest.data
  const error = suggest.error as ApiError | null
  const forbidden = error?.status === 403
  const areasUnavailable = areas.isError
  const canRun = !!areaId || proposal.trim().length > 0

  const run = async () => {
    try {
      await suggest.mutateAsync({
        researchAreaId: areaId || undefined,
        proposalText: proposal.trim() || undefined,
        limit: 10,
      })
    } catch (e) {
      const err = e as ApiError
      toast({
        title: err.status === 403 ? 'Not permitted' : 'Could not rank supervisors',
        description: err.message,
        variant: 'destructive',
      })
    }
  }

  return (
    <PageSection
      icon={UserSearch}
      title="Supervisor match"
      accent="primary"
      description="Rank supervisors for a proposal or an advertised position, with every point of the score explained."
    >
      <div className="space-y-4">
        {/* --- criteria --- */}
        <div className="grid gap-3 md:grid-cols-[minmax(0,18rem)_1fr] md:items-start">
          <div className="space-y-1.5">
            <Label>Research area</Label>
            {areas.isLoading ? (
              <Skeleton className="h-9 w-full" />
            ) : areasUnavailable ? (
              <p className="text-helper">
                Research-area lookup is unavailable, so matching runs on the proposal text alone.
                No <span className="font-mono text-xs">GET /api/v1/research-areas</span> endpoint
                exists yet — raised with the backend.
              </p>
            ) : (
              <Select value={areaId} onValueChange={setAreaId}>
                <SelectTrigger><SelectValue placeholder="Any research area" /></SelectTrigger>
                <SelectContent>
                  {areas.data?.map((a) => (
                    <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            {areaId && (
              <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => setAreaId('')}>
                Clear area
              </Button>
            )}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="match-proposal">Proposal or position text</Label>
            <Textarea
              id="match-proposal"
              className="min-h-[88px]"
              value={proposal}
              onChange={(e) => setProposal(e.target.value)}
              placeholder="Paste the research proposal or the advert. Words of four letters or more are matched against what each supervisor's students actually work on."
            />
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Button onClick={run} disabled={!canRun || suggest.isPending}>
            <Search className="h-4 w-4 mr-1.5" />
            {suggest.isPending ? 'Ranking…' : 'Suggest supervisors'}
          </Button>
          {!canRun && (
            <p className="text-helper">Give a research area, some proposal text, or both.</p>
          )}
        </div>

        {/* --- results --- */}
        {suggest.isPending && (
          <div className="space-y-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        )}

        {forbidden && (
          <div className="rounded-md border border-[hsl(var(--warning)/0.3)] bg-[hsl(var(--warning)/0.1)] px-3 py-2 flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0 text-[hsl(var(--warning))]" />
            <div>
              <p className="text-sm font-medium text-[hsl(var(--warning))]">
                You do not have permission to see supervisor suggestions
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Matching reads student and supervision records, so it needs the{' '}
                <span className="font-mono">student.read</span> permission. Ask an administrator to
                add it to your role.
              </p>
            </div>
          </div>
        )}

        {error && !forbidden && (
          <p className="text-sm text-[hsl(var(--destructive))]">
            {error.message}{' '}
            <span className="font-mono text-xs text-muted-foreground">({error.requestId})</span>
          </p>
        )}

        {result && !suggest.isPending && (
          <div className="space-y-3">
            {/* What the engine actually matched on — this is what makes a bad
                result diagnosable rather than mysterious. */}
            <div className="rounded-md border border-border bg-surface-2 px-3 py-2 space-y-1.5">
              <p className="text-label">Matched on</p>
              <div className="flex flex-wrap items-center gap-1.5">
                {result.criteria.researchArea ? (
                  <Badge variant="info">area: {result.criteria.researchArea}</Badge>
                ) : (
                  <span className="text-helper italic">no research area</span>
                )}
                {result.criteria.maxSupervisees !== undefined && (
                  <Badge variant="secondary">
                    capacity ceiling {result.criteria.maxSupervisees}
                  </Badge>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                {result.criteria.keywords && result.criteria.keywords.length > 0 ? (
                  result.criteria.keywords.map((k) => (
                    <span
                      key={k}
                      className="rounded-sm border border-border bg-surface-1 px-1.5 py-0.5 text-xs font-mono"
                    >
                      {k}
                    </span>
                  ))
                ) : (
                  <span className="text-helper italic">
                    No keywords were extracted — common words are dropped, so a short proposal can
                    yield none.
                  </span>
                )}
              </div>
            </div>

            {/* The backend's caveat, verbatim. */}
            <div className="flex items-start gap-2 rounded-md border border-[hsl(var(--info)/0.3)] bg-[hsl(var(--info)/0.1)] px-3 py-2">
              <Info className="h-4 w-4 mt-0.5 shrink-0 text-[hsl(var(--info))]" />
              <p className="text-xs text-[hsl(var(--info))]">{result.note}</p>
            </div>

            {result.suggestions.length > 0 ? (
              <div className="space-y-2">
                {result.suggestions.map((s) => <SuggestionRow key={s.personId} s={s} />)}
              </div>
            ) : (
              <div className="rounded-md border border-dashed border-border px-3 py-6 text-center">
                <Sparkles className="h-5 w-5 mx-auto text-muted-foreground" aria-hidden />
                <p className="text-sm mt-2">No supervisor could be ranked for these criteria.</p>
                <p className="text-helper mt-0.5">
                  Ranking is built from supervision history, so someone who has never supervised
                  cannot appear. Widen the proposal text or clear the research area.
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </PageSection>
  )
}
