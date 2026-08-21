'use client'

import Link from 'next/link'
import { CheckSquare, Bell } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/components/ui/use-toast'
import {
  useCompleteTask, useMarkNotificationRead, useNotifications, useTasks,
} from '@/features/workflow/api'

export default function TasksPage() {
  const { toast } = useToast()
  const tasks = useTasks()
  const notifications = useNotifications()
  const complete = useCompleteTask()
  const markRead = useMarkNotificationRead()

  return (
    <>
      <PageHeader title="Tasks & notifications" description="Work assigned to you and your roles." />
      <div className="px-6 pb-6 space-y-4">
        <PageSection icon={CheckSquare} title="My task queue" accent="primary">
          {tasks.isLoading ? <Skeleton className="h-20 w-full" /> : (
            <div className="space-y-2">
              {tasks.data && tasks.data.length > 0 ? tasks.data.map((t) => (
                <div key={t.id} className="flex items-center justify-between border-b border-border/60 last:border-0 pb-2 last:pb-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium">{t.title}</span>
                    {t.assigneeRole && <Badge variant="secondary">{t.assigneeRole}</Badge>}
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
