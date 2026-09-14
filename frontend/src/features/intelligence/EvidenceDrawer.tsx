'use client'

/**
 * Uniform Evidence Ledger drawer (spec §18).
 *
 * Every AI card, narrative sentence, ranking and document finding opens the same drawer.
 * A "claim" is one row: what we're saying, where it comes from, how fresh it is, and
 * whether it's verified/needs review/missing. The technical trace (router tokens, prompt
 * template version, fallback path) is a collapsed advanced section — the user sees
 * evidence first, wiring last.
 */
import { useEffect, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { intelligenceApi, type EvidenceClaim } from './api'
import { NarratedParagraph, type Narration } from './NarratedParagraph'

export interface EvidenceDrawerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  artefactId: string | null
  title?: string
  /**
   * Optional summary printed at the top — e.g. the claim the user opened the drawer for.
   * Keep short; the ledger below carries the detail.
   */
  headline?: string
  /** Plain-English AI narration of the case. Rendered above the evidence table. */
  narratedSummary?: Narration | null
  /** Suppress the "loading…" empty state while the parent is still fetching context. */
  loading?: boolean
  missingSources?: Array<{ source: string; reason: string }>
}

function StatusBadge({ status }: { status: string }) {
  const tone =
    status === 'verified' ? 'success'
    : status === 'review'  ? 'warning'
    : status === 'stale'   ? 'warning'
    : 'secondary'
  return <Badge variant={tone as never}>{status}</Badge>
}

function relative(iso: string): string {
  const then = new Date(iso).getTime()
  const now = Date.now()
  const diffH = Math.round((now - then) / 3_600_000)
  if (diffH < 1)  return 'now'
  if (diffH < 24) return `${diffH}h`
  const diffD = Math.round(diffH / 24)
  return diffD === 1 ? '1d' : `${diffD}d`
}

export function EvidenceDrawer({
  open, onOpenChange, artefactId, title, headline, narratedSummary,
  loading: parentLoading, missingSources,
}: EvidenceDrawerProps) {
  const [claims, setClaims] = useState<EvidenceClaim[] | null>(null)
  const [selfLoading, setSelfLoading] = useState(false)
  const loading = selfLoading || Boolean(parentLoading)
  const [error, setError] = useState<string | null>(null)
  const [showTrace, setShowTrace] = useState(false)

  useEffect(() => {
    if (!open || !artefactId) return
    let cancelled = false
    setSelfLoading(true)
    setError(null)
    intelligenceApi.evidenceForArtefact(artefactId)
      .then((rows) => { if (!cancelled) setClaims(rows) })
      .catch((e: Error) => { if (!cancelled) setError(e.message) })
      .finally(() => { if (!cancelled) setSelfLoading(false) })
    return () => { cancelled = true }
  }, [open, artefactId])

  const llmClaims = claims?.filter((c) => c.sourceType === 'model').length ?? 0

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-2xl overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{title ?? 'Evidence Ledger'}</SheetTitle>
          <SheetDescription>
            Every conclusion expands into a source-linked evidence ledger.
          </SheetDescription>
        </SheetHeader>

        {headline ? (
          <p className="mt-4 text-sm font-medium">{headline}</p>
        ) : null}

        {/* AI narration — the plain-English "why" reads before any table of rows. */}
        {narratedSummary || loading ? (
          <div className="mt-4">
            <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">
              In plain English
            </p>
            <NarratedParagraph narration={narratedSummary ?? null} loading={loading && !narratedSummary} />
          </div>
        ) : null}

        <div className="mt-4 text-xs text-muted-foreground flex flex-wrap gap-x-4 gap-y-1">
          <span>LLM-generated facts: <strong>{llmClaims}</strong></span>
          {missingSources && missingSources.length > 0 ? (
            <span>Missing: {missingSources.map((m) => m.source).join(', ')}</span>
          ) : null}
        </div>

        <div className="mt-4">
          {loading ? (
            <div className="space-y-2"><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-3/4" /></div>
          ) : error ? (
            <p className="text-sm text-destructive">Could not load evidence: {error}</p>
          ) : !artefactId ? (
            <p className="text-sm text-muted-foreground">No source rows recorded for this view yet.</p>
          ) : claims && claims.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Claim</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead className="w-24">Freshness</TableHead>
                  <TableHead className="w-24">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {claims.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell className="text-sm">{c.claimType}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      <div>{c.sourceType}</div>
                      {c.sourceId ? <div className="font-mono opacity-70">{c.sourceId.slice(0, 8)}…</div> : null}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{relative(c.asOf)}</TableCell>
                    <TableCell><StatusBadge status={c.status} /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-sm text-muted-foreground">No evidence claims recorded for this artefact yet.</p>
          )}
        </div>

        {missingSources && missingSources.length > 0 ? (
          <div className="mt-6">
            <h4 className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-2">Missing information</h4>
            <ul className="space-y-1 text-sm">
              {missingSources.map((m) => (
                <li key={m.source} className="flex gap-2">
                  <span className="font-medium">{m.source}:</span>
                  <span className="text-muted-foreground">{m.reason}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <button
          type="button"
          onClick={() => setShowTrace((v) => !v)}
          className="mt-6 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          {showTrace ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          Technical trace
        </button>
        {showTrace ? (
          <pre className="mt-2 rounded-md bg-muted/50 p-3 text-[11px] overflow-x-auto">
{JSON.stringify({ artefactId, claimCount: claims?.length ?? 0, llmClaims }, null, 2)}
          </pre>
        ) : null}
      </SheetContent>
    </Sheet>
  )
}
