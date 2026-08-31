'use client'

/**
 * Settings — the institution configuration area (Phase 8).
 *
 * Four tabs: reference lists (LOVs), institution policy settings, user & role
 * administration, and the signed-in user's own notification preferences.
 * The first three require `admin.configure` (enforced server-side; hidden here
 * as a convenience via /me permissions). "My preferences" works for everyone.
 */

import { useEffect, useState } from 'react'
import { Bell, ListChecks, ShieldAlert, SlidersHorizontal, Users } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useToast } from '@/components/ui/use-toast'
import { useAuth } from '@/shared/auth/AuthContext'
import {
  usePreferences, useUpdatePreferences, type NotificationPreferences,
} from '@/features/notifications/api'
import { LovTab } from '@/features/settings/LovTab'
import { InstitutionPolicyTab } from '@/features/settings/InstitutionPolicyTab'
import { UsersRolesTab } from '@/features/settings/UsersRolesTab'

/* ------------------------------------------------------------------ *
 * Shown in place of an admin tab when the signed-in user lacks
 * admin.configure. The server enforces regardless (403).
 * ------------------------------------------------------------------ */

function NoPermission({ what }: { what: string }) {
  return (
    <Card className="card-elevated">
      <CardContent className="py-12 text-center space-y-2">
        <ShieldAlert className="h-8 w-8 mx-auto text-muted-foreground" />
        <p className="font-medium">Administrator access required</p>
        <p className="text-helper max-w-md mx-auto">
          {what} can only be managed by users with administrator access
          (the <span className="font-mono text-xs">admin.configure</span> permission).
          Your own notification preferences are still available under &ldquo;My preferences&rdquo;.
        </p>
      </CardContent>
    </Card>
  )
}

/* ------------------------------------------------------------------ *
 * "My preferences" — the pre-Phase-8 Settings page content, moved here
 * unchanged: personal notification preferences.
 * ------------------------------------------------------------------ */

// F6 — helpers for the quiet-hours HH:mm ↔ minutes-since-midnight conversion
function minutesToHHmm(m: number): string {
  const h = Math.floor(m / 60), mm = m % 60
  return `${String(h).padStart(2, '0')}:${String(mm).padStart(2, '0')}`
}
function hhmmToMinutes(s: string): number {
  const [h, m] = s.split(':').map((v) => parseInt(v, 10) || 0)
  return h * 60 + m
}

const MUTABLE_EVENTS: { template: string; label: string }[] = [
  { template: 'milestone.decided', label: 'Milestone decided' },
  { template: 'task.assigned', label: 'Task assigned' },
  { template: 'task.escalated', label: 'Task escalated' },
  { template: 'funding.expiring', label: 'Funding expiring' },
  { template: 'thesis.outcome', label: 'Thesis outcome' },
  { template: 'supervision.assigned', label: 'Supervisor assigned' },
]

function MyPreferencesTab() {
  const { toast } = useToast()
  const { data, isLoading } = usePreferences()
  const update = useUpdatePreferences()

  const [emailEnabled, setEmailEnabled] = useState(true)
  const [digest, setDigest] = useState(false)
  const [muted, setMuted] = useState<string[]>([])
  // F6 — quiet hours picker; empty string means "no quiet window"
  const [quietStart, setQuietStart] = useState('')
  const [quietEnd, setQuietEnd] = useState('')

  useEffect(() => {
    if (data) {
      setEmailEnabled(data.emailEnabled)
      setDigest(data.digest)
      setMuted(data.mutedEvents ?? [])
      setQuietStart(data.quietStart == null ? '' : minutesToHHmm(data.quietStart))
      setQuietEnd(data.quietEnd == null ? '' : minutesToHHmm(data.quietEnd))
    }
  }, [data])

  const toggleMute = (template: string, checked: boolean) => {
    setMuted((prev) => checked ? [...new Set([...prev, template])] : prev.filter((t) => t !== template))
  }

  const save = async () => {
    const body: NotificationPreferences = {
      emailEnabled, digest, mutedEvents: muted,
      quietStart: quietStart ? hhmmToMinutes(quietStart) : null,
      quietEnd: quietEnd ? hhmmToMinutes(quietEnd) : null,
    }
    try {
      await update.mutateAsync(body)
      toast({ title: 'Preferences saved' })
    } catch (e) {
      toast({ title: 'Save failed', description: (e as Error).message, variant: 'destructive' })
    }
  }

  return (
    <PageSection icon={Bell} title="Notifications" accent="primary">
      {isLoading ? <Skeleton className="h-40 w-full" /> : (
        <div className="space-y-5">
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Checkbox id="emailEnabled" checked={emailEnabled} onCheckedChange={(v) => setEmailEnabled(v === true)} />
              <Label htmlFor="emailEnabled" className="cursor-pointer">Email notifications enabled</Label>
            </div>
            <div className="flex items-center gap-2">
              <Checkbox id="digest" checked={digest} onCheckedChange={(v) => setDigest(v === true)} />
              <Label htmlFor="digest" className="cursor-pointer">Daily digest (batch into one email)</Label>
            </div>
          </div>

          {/* F6 — quiet hours picker */}
          <div>
            <p className="text-label mb-2">Quiet hours (F6)</p>
            <p className="text-helper mb-2">
              Non-urgent emails are suppressed inside this window. In-app notifications still arrive.
              Leave blank to disable.
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-2">
                <Label htmlFor="q-start">From</Label>
                <input
                  id="q-start"
                  type="time"
                  value={quietStart}
                  onChange={(e) => setQuietStart(e.target.value)}
                  className="border border-input rounded-md h-9 px-2 bg-background text-sm"
                />
              </div>
              <div className="flex items-center gap-2">
                <Label htmlFor="q-end">To</Label>
                <input
                  id="q-end"
                  type="time"
                  value={quietEnd}
                  onChange={(e) => setQuietEnd(e.target.value)}
                  className="border border-input rounded-md h-9 px-2 bg-background text-sm"
                />
              </div>
              {(quietStart || quietEnd) && (
                <button
                  type="button"
                  className="text-xs text-muted-foreground hover:text-foreground underline"
                  onClick={() => { setQuietStart(''); setQuietEnd('') }}
                >clear</button>
              )}
            </div>
          </div>

          <div>
            <p className="text-label mb-2">Mute specific events</p>
            <div className="grid gap-2 sm:grid-cols-2">
              {MUTABLE_EVENTS.map((ev) => (
                <div key={ev.template} className="flex items-center gap-2">
                  <Checkbox
                    id={`mute-${ev.template}`}
                    checked={muted.includes(ev.template)}
                    onCheckedChange={(v) => toggleMute(ev.template, v === true)}
                  />
                  <Label htmlFor={`mute-${ev.template}`} className="cursor-pointer font-normal">{ev.label}</Label>
                </div>
              ))}
            </div>
          </div>

          <div className="pt-2 border-t border-border">
            <Button size="sm" disabled={update.isPending} onClick={save}>
              {update.isPending ? 'Saving…' : 'Save preferences'}
            </Button>
          </div>
        </div>
      )}
    </PageSection>
  )
}

/* ------------------------------------------------------------------ */

export default function SettingsPage() {
  const { hasPermission } = useAuth()
  const admin = hasPermission('admin.configure')

  return (
    <>
      <PageHeader
        title="Settings"
        description="Institution configuration, reference data, user administration and your personal preferences."
      />
      <div className="px-6 pb-6">
        {/* Admin tabs are hidden entirely without admin.configure — advertising
            empty tabs invites clicks that go nowhere. */}
        <Tabs defaultValue={admin ? 'lov' : 'preferences'}>
          <TabsList>
            {admin && <TabsTrigger value="lov"><ListChecks className="h-4 w-4 mr-1.5" /> List of values</TabsTrigger>}
            {admin && <TabsTrigger value="policy"><SlidersHorizontal className="h-4 w-4 mr-1.5" /> Institution policy</TabsTrigger>}
            {admin && <TabsTrigger value="users"><Users className="h-4 w-4 mr-1.5" /> Users &amp; roles</TabsTrigger>}
            <TabsTrigger value="preferences"><Bell className="h-4 w-4 mr-1.5" /> My preferences</TabsTrigger>
          </TabsList>
          {admin && (
            <TabsContent value="lov" className="mt-4">
              <LovTab />
            </TabsContent>
          )}
          {admin && (
            <TabsContent value="policy" className="mt-4">
              <InstitutionPolicyTab />
            </TabsContent>
          )}
          {admin && (
            <TabsContent value="users" className="mt-4">
              <UsersRolesTab />
            </TabsContent>
          )}
          <TabsContent value="preferences" className="mt-4">
            <MyPreferencesTab />
          </TabsContent>
        </Tabs>
      </div>
    </>
  )
}
