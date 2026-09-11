'use client'

/**
 * Integration hub — the seam between PGR Platform and every partner system.
 *
 * Layout, top-to-bottom:
 *   1. Adapter targets (the "Integration Hub" — configure endpoints here)
 *   2. Reconciliation ("what needs my attention")
 *   3. Quick actions (Dispatch outbox · Run scheduled jobs · Statutory exports)
 *   4. Activity log (collapsed by default so the page stays scannable)
 */

import { useState } from 'react'
import { Activity, Cable, ChevronDown, ChevronRight, Clock, Download, FileSpreadsheet, Send, Zap } from 'lucide-react'
import { cn } from '@/lib/utils'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/components/ui/use-toast'
import { useDispatch, useIntegration, useRunScheduledJobs } from '@/features/integration/api'
import { AdapterTargets } from '@/features/integration/AdapterTargets'
import { ReconciliationPanel } from '@/features/integration/ReconciliationPanel'
import { downloadExport, useCreateExport, useExports } from '@/features/exports/api'

const STATUS: Record<string, 'success' | 'secondary' | 'destructive' | 'outline'> = {
  success: 'success', skipped: 'secondary', duplicate: 'outline', failed: 'destructive',
}

export default function IntegrationPage() {
  const { toast } = useToast()
  const { data, isLoading } = useIntegration()
  const dispatch = useDispatch()
  const scheduled = useRunScheduledJobs()
  const exportsQ = useExports()
  const createExport = useCreateExport()
  const [logOpen, setLogOpen] = useState(false)

  const err = (e: unknown) => toast({ title: 'Failed', description: (e as Error).message, variant: 'destructive' })

  return (
    <>
      <PageHeader
        title="Integration hub"
        description="Point each adapter at its partner system. Every event is delivered reliably or held for retry."
      />
      <div className="px-6 pb-6 space-y-4">
        {/* 1 · Adapter targets — the reason this page exists */}
        <PageSection icon={Cable} title="Adapter targets" accent="primary"
          description="One tile per external system. Configure the endpoint — the platform handles delivery, retries, and dead-lettering automatically.">
          <AdapterTargets />
        </PageSection>

        {/* 2 · What needs a human right now */}
        <ReconciliationPanel />

        {/* 3 · Quick actions — dispatch + scheduled + exports in one strip */}
        <PageSection icon={Zap} title="Quick actions" accent="accent">
          <div className="grid gap-3 md:grid-cols-3">
            <div className="rounded-md border border-border/60 p-3 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <Send className="h-4 w-4 text-primary" /> Outbox
                </div>
                <Badge variant={data?.pending ? 'warning' : 'success'}>
                  {data?.pending ?? '—'} pending
                </Badge>
              </div>
              <p className="text-helper">Every state change becomes an event, delivered at-least-once.</p>
              <Button size="sm" className="w-full" disabled={dispatch.isPending}
                onClick={async () => {
                  try { const r = await dispatch.mutateAsync(); toast({ title: 'Dispatched', description: `${r.dispatched} event(s), ${r.outboundCalls} outbound call(s).` }) }
                  catch (e) { err(e) }
                }}>Dispatch pending</Button>
            </div>

            <div className="rounded-md border border-border/60 p-3 space-y-2">
              <div className="flex items-center gap-2 text-sm font-medium">
                <Clock className="h-4 w-4 text-primary" /> Scheduled jobs
              </div>
              <p className="text-helper">Milestones, funding-expiring flags, overdue task escalation.</p>
              <Button size="sm" variant="secondary" className="w-full" disabled={scheduled.isPending}
                onClick={async () => {
                  try {
                    const r = await scheduled.mutateAsync()
                    toast({
                      title: 'Scheduled jobs ran',
                      description: `${r.milestonesGenerated} milestone(s) · ${r.fundingExpiringFlagged} funding flag(s) · ${r.overdueTasksEscalated} escalation(s).`,
                    })
                  } catch (e) { err(e) }
                }}>Run now</Button>
            </div>

            <div className="rounded-md border border-border/60 p-3 space-y-2">
              <div className="flex items-center gap-2 text-sm font-medium">
                <FileSpreadsheet className="h-4 w-4 text-primary" /> Statutory exports
              </div>
              <p className="text-helper">HESA-shape and PGR Enterprise 360 CSVs.</p>
              <div className="flex flex-col gap-1.5">
                <Button size="sm" variant="secondary" disabled={createExport.isPending}
                  onClick={async () => {
                    try { const j = await createExport.mutateAsync('students_statutory'); toast({ title: 'Export ready', description: `${j.rowCount} row(s) — ${j.filename}` }) }
                    catch (e) { err(e) }
                  }}>Students statutory</Button>
                <Button size="sm" variant="ghost" disabled={createExport.isPending}
                  onClick={async () => {
                    try { const j = await createExport.mutateAsync('pgr_enterprise_360'); toast({ title: 'Export ready', description: `${j.rowCount} row(s) — ${j.filename}` }) }
                    catch (e) { err(e) }
                  }}>PGR Enterprise 360</Button>
              </div>
            </div>
          </div>

          {/* Recent exports — inline, compact, only shows if there are any */}
          {exportsQ.data && exportsQ.data.length > 0 && (
            <div className="mt-4 space-y-1.5">
              <p className="text-label">Recent exports</p>
              {exportsQ.data.slice(0, 5).map((j) => (
                <div key={j.id} className="flex items-center justify-between text-sm border-b border-border/60 last:border-0 pb-1.5 last:pb-0">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="font-mono text-xs truncate">{j.filename ?? j.kind}</span>
                    <Badge variant={j.status === 'complete' ? 'success' : j.status === 'failed' ? 'destructive' : 'info'}>{j.status}</Badge>
                    {j.rowCount != null && <span className="text-helper">{j.rowCount} rows</span>}
                  </div>
                  {j.status === 'complete' && (
                    <Button size="sm" variant="ghost" className="h-7" onClick={() => downloadExport(j)}>
                      <Download className="h-3.5 w-3.5 mr-1" /> Download
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </PageSection>

        {/* 4 · Activity log — collapsed by default */}
        <Collapsible open={logOpen} onOpenChange={setLogOpen} className="card-elevated">
          <CollapsibleTrigger asChild>
            <button className="flex w-full items-center gap-2 px-4 py-3 text-left hover:bg-surface-2/50 rounded-t-md">
              <ChevronRight className={cn('h-4 w-4 text-muted-foreground transition-transform', logOpen && 'rotate-90')} />
              <Activity className="h-4 w-4 text-primary" />
              <span className="text-sm font-medium">Activity log</span>
              {data && (
                <span className="text-helper ml-auto">
                  {data.logs.length} recent event{data.logs.length === 1 ? '' : 's'}
                </span>
              )}
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="border-t border-border/60">
              {isLoading ? <Skeleton className="h-24 w-full" /> : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Direction</TableHead><TableHead>System</TableHead>
                      <TableHead>Event</TableHead><TableHead>Status</TableHead><TableHead>When</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data?.logs.map((l) => (
                      <TableRow key={l.id}>
                        <TableCell><Badge variant={l.direction === 'inbound' ? 'info' : 'secondary'}>{l.direction}</Badge></TableCell>
                        <TableCell className="font-medium">{l.system}</TableCell>
                        <TableCell className="text-muted-foreground">{l.eventType}</TableCell>
                        <TableCell><Badge variant={STATUS[l.status] ?? 'secondary'}>{l.status}</Badge></TableCell>
                        <TableCell className="text-helper num">{l.createdAt.slice(0, 19).replace('T', ' ')}</TableCell>
                      </TableRow>
                    ))}
                    {data && data.logs.length === 0 && (
                      <TableRow><TableCell colSpan={5} className="text-muted-foreground text-center py-8">
                        No integration activity yet. Change funding for a student or graduate someone, then dispatch.
                      </TableCell></TableRow>
                    )}
                  </TableBody>
                </Table>
              )}
            </div>
          </CollapsibleContent>
        </Collapsible>
      </div>
    </>
  )
}
