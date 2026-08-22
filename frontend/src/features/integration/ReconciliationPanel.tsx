'use client'

import { useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, ArrowLeftRight, CheckCircle2, Inbox, RotateCcw, ShieldAlert, UserSearch } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useToast } from '@/components/ui/use-toast'
import { ApiError } from '@/shared/api/client'
import {
  useReconciliation,
  useReplayDeadLetter,
  type StatusCounts,
  type SystemTraffic,
} from '@/features/integration/api'

const STATUS_VARIANT: Record<string, 'success' | 'secondary' | 'destructive' | 'outline'> = {
  success: 'success', skipped: 'secondary', duplicate: 'outline', failed: 'destructive',
}

function when(iso: string | null | undefined) {
  return iso ? iso.slice(0, 19).replace('T', ' ') : '—'
}

/** Human age of a timestamp — a growing backlog is the signal, so show how old it is. */
function relativeAge(iso: string): string {
  const then = Date.parse(iso)
  if (Number.isNaN(then)) return iso
  const mins = Math.max(0, Math.floor((Date.now() - then) / 60_000))
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m`
  const hours = Math.floor(mins / 60)
  if (hours < 48) return `${hours}h`
  return `${Math.floor(hours / 24)}d`
}

function truncate(text: string | null | undefined, max: number) {
  if (!text) return '—'
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

function Tile({ label, value, tone, hint }: {
  label: string
  value: number
  tone?: 'danger' | 'warning'
  hint?: string
}) {
  const alert = !!tone && value > 0
  return (
    <div className="card-elevated p-4">
      <p className="text-label">{label}</p>
      <p
        className={
          'mt-1 text-2xl font-semibold tracking-tight num' +
          (alert ? (tone === 'danger' ? ' text-danger' : ' text-warning') : '')
        }
      >
        {value}
      </p>
      {hint && <p className="text-helper mt-0.5">{hint}</p>}
    </div>
  )
}

/** Flatten `inbound.bySystem` into one row per (system, direction, status). */
interface TrafficRow { system: string; direction: string; status: string; count: number }
function flattenTraffic(bySystem: Record<string, SystemTraffic> | undefined): TrafficRow[] {
  const rows: TrafficRow[] = []
  for (const [system, traffic] of Object.entries(bySystem ?? {})) {
    for (const direction of ['inbound', 'outbound'] as const) {
      const counts: StatusCounts | undefined = traffic?.[direction]
      if (!counts) continue
      for (const [status, count] of Object.entries(counts)) {
        if (typeof count !== 'number' || count === 0) continue
        rows.push({ system, direction, status, count })
      }
    }
  }
  return rows.sort(
    (a, b) => a.system.localeCompare(b.system) || a.direction.localeCompare(b.direction) || a.status.localeCompare(b.status),
  )
}

function personLabel(payload: Record<string, unknown> | null): string {
  const get = (k: string) => (typeof payload?.[k] === 'string' ? (payload[k] as string) : '')
  const name = [get('givenName'), get('familyName')].filter(Boolean).join(' ').trim()
  return name || get('email') || 'Unnamed record'
}
function personEmail(payload: Record<string, unknown> | null): string {
  return typeof payload?.email === 'string' ? payload.email : ''
}
function personReason(payload: Record<string, unknown> | null): string {
  return typeof payload?.reason === 'string' ? payload.reason : ''
}

export function ReconciliationPanel({ windowDays = 30 }: { windowDays?: number }) {
  const { toast } = useToast()
  const { data, isLoading, isError, error } = useReconciliation(windowDays)
  const replay = useReplayDeadLetter()
  const [replayingId, setReplayingId] = useState<string | null>(null)

  const onReplay = async (id: string, eventType: string) => {
    setReplayingId(id)
    try {
      const res = await replay.mutateAsync(id)
      const ok = res?.data?.replayed
      toast({
        title: ok ? 'Queued for replay' : 'Nothing to replay',
        description: ok
          ? `${eventType} will be retried on the next dispatch.`
          : `${eventType} is no longer dead-lettered.`,
        variant: ok ? undefined : 'destructive',
      })
    } catch (e) {
      const message = e instanceof ApiError ? e.message : (e as Error).message
      toast({ title: 'Replay failed', description: message, variant: 'destructive' })
    } finally {
      setReplayingId(null)
    }
  }

  if (isLoading) {
    return (
      <PageSection icon={ShieldAlert} title="Integration reconciliation" accent="primary">
        <div className="space-y-3">
          <Skeleton className="h-6 w-72" />
          <div className="grid gap-3 sm:grid-cols-3">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
          <Skeleton className="h-24 w-full" />
        </div>
      </PageSection>
    )
  }

  if (isError || !data) {
    const message = error instanceof ApiError ? error.message : 'Could not load the reconciliation report.'
    return (
      <PageSection icon={ShieldAlert} title="Integration reconciliation" accent="danger">
        <p className="text-sm text-danger">{message}</p>
        <p className="text-helper mt-1">This view requires the <span className="num">admin.configure</span> permission.</p>
      </PageSection>
    )
  }

  const { outbound, inbound, awaitingPeople, healthy, issueCount } = data
  const deadLetters = outbound?.deadLetters ?? []
  const failedInbound = inbound?.failed ?? []
  const unmatched = awaitingPeople?.unmatchedHrRecords ?? []
  const traffic = flattenTraffic(inbound?.bySystem)
  const showOldestPending = !!outbound?.oldestPendingAt && (outbound?.pending ?? 0) > 0

  return (
    <PageSection
      icon={ShieldAlert}
      title="Integration reconciliation"
      description={`What needs attention at the integration boundary — last ${data.windowDays} day(s).`}
      accent={healthy ? 'success' : 'warning'}
      attention={!healthy}
      headerRight={
        <Badge variant={healthy ? 'success' : 'warning'}>
          {healthy ? 'healthy' : `${issueCount} issue${issueCount === 1 ? '' : 's'}`}
        </Badge>
      }
    >
      {/* Health header */}
      {healthy ? (
        <div className="flex items-center gap-2 text-sm text-success">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          <span>Integration boundary is healthy — nothing pending or failed.</span>
        </div>
      ) : (
        <div className="flex items-center gap-2 text-sm text-warning">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>
            {issueCount} issue{issueCount === 1 ? '' : 's'} to review — dead letters, failed inbound
            messages, and records waiting on a person are listed below.
          </span>
        </div>
      )}

      {/* Outbound tiles */}
      <div className="grid gap-3 sm:grid-cols-3 mt-4">
        <Tile
          label="Pending"
          value={outbound?.pending ?? 0}
          tone="warning"
          hint={showOldestPending ? `oldest pending: ${relativeAge(outbound.oldestPendingAt as string)}` : 'nothing waiting to go out'}
        />
        <Tile
          label="Dispatched (in window)"
          value={outbound?.dispatchedInWindow ?? 0}
          hint={`last ${data.windowDays} day(s)`}
        />
        <Tile
          label="Dead-lettered"
          value={outbound?.deadLettered ?? 0}
          tone="danger"
          hint="exhausted retries — replay below"
        />
      </div>

      {/* Dead letters */}
      <div className="mt-6">
        <h3 className="text-label mb-2">Dead letters</h3>
        {deadLetters.length === 0 ? (
          <Card className="p-4 text-helper">No dead-lettered events. Every outbound event has been delivered or is still retrying.</Card>
        ) : (
          <div className="card-elevated overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Event</TableHead>
                  <TableHead>Attempts</TableHead>
                  <TableHead>Last error</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {deadLetters.map((d) => (
                  <TableRow key={d.id}>
                    <TableCell className="font-medium">{d.eventType}</TableCell>
                    <TableCell className="num">{d.attempts}</TableCell>
                    <TableCell className="text-muted-foreground max-w-[420px]" title={d.lastError ?? undefined}>
                      {truncate(d.lastError, 90)}
                    </TableCell>
                    <TableCell className="text-helper num">{when(d.createdAt)}</TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={replay.isPending && replayingId === d.id}
                        onClick={() => onReplay(d.id, d.eventType)}
                      >
                        <RotateCcw className="h-3.5 w-3.5 mr-1" />
                        {replayingId === d.id ? 'Replaying…' : 'Replay'}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      {/* Traffic by system */}
      <div className="mt-6">
        <h3 className="text-label mb-2 flex items-center gap-1.5">
          <ArrowLeftRight className="h-3.5 w-3.5" /> Traffic by system
        </h3>
        {traffic.length === 0 ? (
          <Card className="p-4 text-helper">
            No integration traffic in the last {data.windowDays} day(s).
          </Card>
        ) : (
          <div className="card-elevated overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>System</TableHead>
                  <TableHead>Direction</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Count</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {traffic.map((r) => (
                  <TableRow key={`${r.system}-${r.direction}-${r.status}`}>
                    <TableCell className="font-medium">{r.system}</TableCell>
                    <TableCell>
                      <Badge variant={r.direction === 'inbound' ? 'info' : 'secondary'}>{r.direction}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={STATUS_VARIANT[r.status] ?? 'secondary'}>{r.status}</Badge>
                    </TableCell>
                    <TableCell className="text-right num">{r.count}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      {/* Failed inbound */}
      <div className="mt-6">
        <h3 className="text-label mb-2 flex items-center gap-1.5">
          <Inbox className="h-3.5 w-3.5" /> Failed inbound messages
        </h3>
        {failedInbound.length === 0 ? (
          <Card className="p-4 text-helper">
            No inbound message failed in the last {data.windowDays} day(s).
          </Card>
        ) : (
          <div className="card-elevated overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>System</TableHead>
                  <TableHead>Event</TableHead>
                  <TableHead>Source id</TableHead>
                  <TableHead>Error</TableHead>
                  <TableHead>When</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {failedInbound.map((f) => (
                  <TableRow key={f.id}>
                    <TableCell className="font-medium">{f.system}</TableCell>
                    <TableCell className="text-muted-foreground">{f.eventType}</TableCell>
                    <TableCell className="text-helper num">{f.sourceId ?? '—'}</TableCell>
                    {/* Triage needs the whole message, so wrap it rather than truncate it away. */}
                    <TableCell className="text-danger whitespace-pre-wrap break-words max-w-[520px]">
                      {f.error ?? 'No error detail recorded.'}
                    </TableCell>
                    <TableCell className="text-helper num">{when(f.createdAt)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      {/* Awaiting people */}
      <div className="mt-6">
        <h3 className="text-label mb-2 flex items-center gap-1.5">
          <UserSearch className="h-3.5 w-3.5" /> Awaiting a person
        </h3>
        <p className="text-helper mb-2">
          Identity matching is deterministic and never guesses, so these HR records were queued
          deliberately for a human to match rather than merged onto the wrong person.
        </p>
        {unmatched.length === 0 ? (
          <Card className="p-4 text-helper">No HR records are waiting to be matched.</Card>
        ) : (
          <div className="space-y-2">
            {unmatched.map((u) => (
              <div
                key={u.taskId}
                className="flex items-center justify-between gap-4 border-b border-border/60 last:border-0 pb-2 last:pb-0"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium">{personLabel(u.payload)}</span>
                    {personEmail(u.payload) && (
                      <span className="text-helper num">{personEmail(u.payload)}</span>
                    )}
                    {personReason(u.payload) && (
                      <Badge variant="warning">{personReason(u.payload)}</Badge>
                    )}
                  </div>
                  <p className="text-helper truncate">
                    {u.title} · {when(u.createdAt)}
                  </p>
                </div>
                <Button size="sm" variant="ghost" asChild>
                  <Link href="/tasks">Open in tasks</Link>
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </PageSection>
  )
}
