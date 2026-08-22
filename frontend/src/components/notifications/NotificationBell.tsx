'use client'

import { Bell, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useUnreadCount } from '@/features/notifications/api'
import {
  useNotifications, useMarkNotificationRead, type Notification,
} from '@/features/workflow/api'

const TEMPLATE_TITLES: Record<string, string> = {
  'milestone.decided': 'Milestone decided',
  'task.assigned': 'Task assigned',
  'task.escalated': 'Task escalated',
  'funding.expiring': 'Funding expiring',
  'thesis.outcome': 'Thesis outcome',
  'supervision.assigned': 'Supervisor assigned',
}

function friendlyTitle(template: string): string {
  return TEMPLATE_TITLES[template] ?? template.replace(/[._]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const diff = Date.now() - then
  const min = Math.round(diff / 60000)
  if (min < 1) return 'just now'
  if (min < 60) return `${min}m ago`
  const hr = Math.round(min / 60)
  if (hr < 24) return `${hr}h ago`
  const day = Math.round(hr / 24)
  if (day < 30) return `${day}d ago`
  return new Date(iso).toLocaleDateString()
}

function summarise(payload: Record<string, unknown> | null): string {
  if (!payload) return ''
  const parts: string[] = []
  for (const key of ['message', 'title', 'name', 'studentRef', 'status', 'outcome']) {
    const v = payload[key]
    if (typeof v === 'string' || typeof v === 'number') { parts.push(String(v)); if (parts.length >= 2) break }
  }
  if (parts.length) return parts.join(' · ')
  const first = Object.values(payload).find((v) => typeof v === 'string' || typeof v === 'number')
  return first != null ? String(first) : ''
}

export function NotificationBell() {
  const count = useUnreadCount()
  const notifications = useNotifications()
  const markRead = useMarkNotificationRead()

  const unread = count.data?.unread ?? 0
  const items = notifications.data ?? []
  const openItems = items.filter((n) => n.status !== 'read')

  const markAll = async () => {
    await Promise.all(openItems.map((n) => markRead.mutateAsync(n.id).catch(() => undefined)))
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className="relative h-9 w-9" aria-label="Notifications">
          <Bell className="h-[18px] w-[18px]" />
          {unread > 0 && (
            <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-[hsl(var(--destructive))] px-1 text-[10px] font-semibold text-[hsl(var(--destructive-foreground))]">
              {unread > 99 ? '99+' : unread}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0">
        <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
          <span className="text-sm font-semibold">Notifications</span>
          {openItems.length > 0 && (
            <Button variant="ghost" size="sm" className="h-7 text-xs" disabled={markRead.isPending} onClick={markAll}>
              Mark all read
            </Button>
          )}
        </div>
        <ScrollArea className="max-h-96">
          {items.length === 0 ? (
            <p className="text-helper px-4 py-8 text-center">No notifications.</p>
          ) : (
            <div className="divide-y divide-border/60">
              {items.map((n: Notification) => {
                const isRead = n.status === 'read'
                const summary = summarise(n.payload)
                return (
                  <div key={n.id} className={`flex items-start gap-2 px-4 py-2.5 ${isRead ? 'opacity-60' : ''}`}>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        {!isRead && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />}
                        <span className="text-sm font-medium truncate">{friendlyTitle(n.template)}</span>
                      </div>
                      {summary && <p className="text-helper truncate mt-0.5">{summary}</p>}
                      <p className="text-[10px] text-muted-foreground mt-0.5 num">{relativeTime(n.createdAt)}</p>
                    </div>
                    {!isRead && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 shrink-0"
                        aria-label="Mark read"
                        disabled={markRead.isPending}
                        onClick={() => markRead.mutate(n.id)}
                      >
                        <Check className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </ScrollArea>
      </PopoverContent>
    </Popover>
  )
}
