'use client'

import { Cable, Clock, Download, FileSpreadsheet, Send } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/components/ui/use-toast'
import { useDispatch, useIntegration, useRunScheduledJobs } from '@/features/integration/api'
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

  return (
    <>
      <PageHeader title="Integration hub" description="Outbox dispatcher, adapters, and inbound webhooks." />
      <div className="px-6 pb-6 space-y-4">
        <PageSection icon={Send} title="Outbox dispatcher" accent="primary">
          <div className="flex items-center gap-3">
            <span className="text-sm">Pending events</span>
            <Badge variant={data?.pending ? 'warning' : 'success'}>{data?.pending ?? '—'}</Badge>
            <Button size="sm" disabled={dispatch.isPending}
              onClick={async () => {
                try { const r = await dispatch.mutateAsync(); toast({ title: 'Dispatched', description: `${r.dispatched} event(s), ${r.outboundCalls} outbound call(s).` }) }
                catch (e) { toast({ title: 'Failed', description: (e as Error).message, variant: 'destructive' }) }
              }}>Dispatch pending</Button>
          </div>
          <p className="text-helper mt-2">
            Domain events are written to the outbox in the same transaction as the change (reliable,
            at-least-once). Dispatching routes them to the Finance/HR/Research adapters. Inbound
            partner messages arrive on signed, idempotent webhooks.
          </p>
        </PageSection>

        <PageSection icon={Clock} title="Scheduled jobs" accent="accent">
          <div className="flex items-center gap-3">
            <Button size="sm" variant="secondary" disabled={scheduled.isPending}
              onClick={async () => {
                try {
                  const r = await scheduled.mutateAsync()
                  toast({
                    title: 'Scheduled jobs ran',
                    description: `${r.milestonesGenerated} milestone(s) generated · ${r.fundingExpiringFlagged} funding flag(s) · ${r.overdueTasksEscalated} task(s) escalated.`,
                  })
                } catch (e) { toast({ title: 'Failed', description: (e as Error).message, variant: 'destructive' }) }
              }}>Run now</Button>
            <span className="text-helper">
              Generates due milestones, flags funding expiring within 90 days (creates tasks), and
              escalates overdue tasks. Worker-triggered in production; endpoint-triggered here.
            </span>
          </div>
        </PageSection>

        <PageSection icon={FileSpreadsheet} title="Statutory exports" accent="primary">
          <div className="flex items-center gap-3 mb-3">
            <Button size="sm" variant="secondary" disabled={createExport.isPending}
              onClick={async () => {
                try { const j = await createExport.mutateAsync('students_statutory'); toast({ title: 'Export ready', description: `${j.rowCount} row(s) — ${j.filename}` }) }
                catch (e) { toast({ title: 'Failed', description: (e as Error).message, variant: 'destructive' }) }
              }}>Students statutory CSV</Button>
            <Button size="sm" variant="secondary" disabled={createExport.isPending}
              onClick={async () => {
                try { const j = await createExport.mutateAsync('pgr_enterprise_360'); toast({ title: 'Export ready', description: `${j.rowCount} row(s) — ${j.filename}` }) }
                catch (e) { toast({ title: 'Failed', description: (e as Error).message, variant: 'destructive' }) }
              }}>PGR Enterprise 360 CSV</Button>
            <span className="text-helper">Runs as an async job; download when complete.</span>
          </div>
          <div className="space-y-2">
            {exportsQ.data?.map((j) => (
              <div key={j.id} className="flex items-center justify-between border-b border-border/60 last:border-0 pb-2 last:pb-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-mono">{j.filename ?? j.kind}</span>
                  <Badge variant={j.status === 'complete' ? 'success' : j.status === 'failed' ? 'destructive' : 'info'}>{j.status}</Badge>
                  {j.rowCount != null && <span className="text-helper">{j.rowCount} rows</span>}
                </div>
                {j.status === 'complete' && (
                  <Button size="sm" variant="ghost" onClick={() => downloadExport(j)}>
                    <Download className="h-4 w-4 mr-1" /> Download
                  </Button>
                )}
              </div>
            ))}
            {exportsQ.data && exportsQ.data.length === 0 && <p className="text-helper">No exports yet.</p>}
          </div>
        </PageSection>

        <PageSection icon={Cable} title="Integration log" accent="accent">
          {isLoading ? <Skeleton className="h-24 w-full" /> : (
            <div className="card-elevated overflow-hidden">
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
            </div>
          )}
        </PageSection>
      </div>
    </>
  )
}
