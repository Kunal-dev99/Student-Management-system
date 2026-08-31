'use client'

import Link from 'next/link'
import { CheckSquare, Bell, Timer, TimerOff } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/components/ui/use-toast'
import { useCan } from '@/shared/auth/Can'
import {
  useCompleteTask, useMarkNotificationRead, useNotifications, useSlaReport, useTasks,
  type Task,
} from '@/features/workflow/api'

/** F5 — small SLA pill next to a task title. */
function SlaPill({ t }: { t: Task }) {
  if (!t.slaTargetSeconds) return null
  if (t.slaBreached) {
    return <Badge variant="destructive" className="inline-flex items-center gap-1">
      <TimerOff className="h-3 w-3" /> SLA breached
    </Badge>
  }
  const hrs = Math.round(t.slaTargetSeconds / 3600)
  return <Badge variant="secondary" className="inline-flex items-center gap-1">
    <Timer className="h-3 w-3" /> SLA {hrs}h{t.slaWorkingDaysOnly ? ' (working)' : ''}
  </Badge>
}

export default function TasksPage() {
  const { toast } = useToast()
  const tasks = useTasks()
  const notifications = useNotifications()
  const complete = useCompleteTask()
  const markRead = useMarkNotificationRead()
  // The SLA report is reporting.read — students/supervisors see their task list without it.
  const sla = useSlaReport({ enabled: useCan('reporting.read') })

  return (
    <>
      <PageHeader title="Tasks & notifications" description="Work assigned to you and your roles." />
      <div className="px-6 pb-6 space-y-4">
        {sla.data && sla.data.total > 0 && (
          <PageSection icon={Timer} title="SLA snapshot (F5)" accent="primary"
            description="Turnaround against institutional service levels — the platform's own promise back to the department.">
            <div className="flex flex-wrap items-center gap-4">
              <div><div className="text-label">Tasks with SLA</div>
                <div className="text-2xl font-semibold num">{sla.data.total}</div></div>
              <div><div className="text-label">Open with SLA</div>
                <div className="text-2xl font-semibold num">{sla.data.openWithSla}</div></div>
              <div><div className="text-label">Breached</div>
                <div className={`text-2xl font-semibold num ${sla.data.breached > 0 ? 'text-[hsl(var(--destructive))]' : ''}`}>
                  {sla.data.breached}
                </div></div>
              <div><div className="text-label">Within-target rate</div>
                <div className="text-2xl font-semibold num">
                  {Math.round(sla.data.withinTargetRate * 100)}%
                </div></div>
            </div>
          </PageSection>
        )}

        <PageSection icon={CheckSquare} title="My task queue" accent="primary">
          {tasks.isLoading ? <Skeleton className="h-20 w-full" /> : (
            <div className="space-y-2">
              {tasks.data && tasks.data.length > 0 ? tasks.data.map((t) => (
                <div key={t.id} className="flex items-center justify-between border-b border-border/60 last:border-0 pb-2 last:pb-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium">{t.title}</span>
                    {t.assigneeRole && <Badge variant="secondary">{t.assigneeRole}</Badge>}
                    <SlaPill t={t} />
                    {t.aggregateType === 'student' && t.aggregateId && (
                      <Link href={`/students/${t.aggregateId}`} className="text-xs text-primary hover:underline">open student</Link>
                    )}
                  </div>
                  <Button size="sm" variant="secondary" disabled={complete.isPending}
                    onClick={async () => { try { await complete.mutateAsync(t.id); toast({ title: 'Task completed' }) } catch (e) { toast({ title: 'Failed', description: (e as Error).message, variant: 'destructive' }) } }}>
                    Complete
                  </Button>
                </div>
              )) : <p className="text-helper">Your queue is clear — no open tasks.</p>}
            </div>
          )}
        </PageSection>

        <PageSection icon={Bell} title="Notifications" accent="accent">
          {notifications.isLoading ? <Skeleton className="h-16 w-full" /> : (
            <div className="space-y-2">
              {notifications.data && notifications.data.length > 0 ? notifications.data.map((n) => (
                <div key={n.id} className="flex items-center justify-between border-b border-border/60 last:border-0 pb-2 last:pb-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm">{n.template}</span>
                    <Badge variant={n.status === 'read' ? 'outline' : 'info'}>{n.status}</Badge>
                  </div>
                  {n.status !== 'read' && (
                    <Button size="sm" variant="ghost" onClick={() => markRead.mutate(n.id)}>Mark read</Button>
                  )}
                </div>
              )) : <p className="text-helper">No notifications.</p>}
            </div>
          )}
        </PageSection>
      </div>
    </>
  )
}
