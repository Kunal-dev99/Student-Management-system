'use client'

/**
 * The "Integration Hub" surface — one tile per external adapter (Finance, HR,
 * Research office …). Admins can point each adapter at its partner endpoint
 * and toggle it on/off without touching code or restarting the backend.
 *
 * Each tile shows: label + description, live URL (or "Not configured"),
 * a status badge, and a Configure button that opens the edit dialog.
 *
 * Registering a NEW adapter is intentionally still a code change — anti-
 * corruption translation code has to live somewhere. But once registered,
 * its runtime target is admin-editable via this UI.
 */

import { useEffect, useState } from 'react'
import { Cable, Cog, Landmark, Microscope, Users } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/components/ui/use-toast'
import { ApiError } from '@/shared/api/client'
import {
  useAdapterTargets, useUpsertAdapterTarget, type AdapterTarget,
} from '@/features/integration/api'

const ICONS: Record<string, LucideIcon> = {
  finance: Landmark,
  hr: Users,
  research: Microscope,
}

function statusBadge(t: AdapterTarget) {
  if (!t.url) return <Badge variant="secondary">Not configured</Badge>
  if (!t.active) return <Badge variant="warning">Disabled</Badge>
  return <Badge variant="success">Live</Badge>
}

function EditTargetDialog({ target, open, onOpenChange }: {
  target: AdapterTarget
  open: boolean
  onOpenChange: (o: boolean) => void
}) {
  const { toast } = useToast()
  const save = useUpsertAdapterTarget()
  const [url, setUrl] = useState(target.url ?? '')
  const [active, setActive] = useState(target.active)

  useEffect(() => {
    if (open) { setUrl(target.url ?? ''); setActive(target.active) }
  }, [open, target.url, target.active])

  const invalid = !!url.trim() && !/^https?:\/\//i.test(url.trim())

  const submit = async () => {
    try {
      await save.mutateAsync({
        system: target.system,
        url: url.trim() || null,
        active,
      })
      toast({ title: `${target.label} target saved` })
      onOpenChange(false)
    } catch (e) {
      toast({ title: 'Could not save', description: (e as ApiError).message, variant: 'destructive' })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Configure {target.label} adapter</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <p className="text-helper">{target.description}</p>
          <div className="space-y-1.5">
            <Label htmlFor="target-url">Endpoint URL</Label>
            <Input
              id="target-url" value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://finance.myinstitution.ac.uk/webhooks/pgr"
              className="font-mono text-sm"
            />
            {invalid && (
              <p className="text-xs text-danger">URL must start with http:// or https://</p>
            )}
            <p className="text-xs text-muted-foreground">
              Leave blank to unconfigure — the adapter will fall back to translate-only mode
              (messages are logged but not sent anywhere).
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Checkbox id="target-active" checked={active}
                      onCheckedChange={(v) => setActive(v === true)} />
            <Label htmlFor="target-active" className="font-normal cursor-pointer">
              Enabled — dispatch events to this endpoint
            </Label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} disabled={invalid || save.isPending}>
            {save.isPending ? 'Saving…' : 'Save target'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function TargetTile({ target }: { target: AdapterTarget }) {
  const [open, setOpen] = useState(false)
  const Icon = ICONS[target.system] ?? Cable
  return (
    <>
      <div className="card-elevated p-4 flex flex-col gap-3 h-full">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <Icon className="h-4 w-4 text-primary" />
            <span className="text-sm font-medium">{target.label}</span>
          </div>
          {statusBadge(target)}
        </div>
        <p className="text-helper flex-1">{target.description}</p>
        <div className="space-y-1">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Endpoint</p>
          {target.url ? (
            <p className="text-xs font-mono break-all">{target.url}</p>
          ) : (
            <p className="text-xs text-muted-foreground italic">Not configured — messages logged only</p>
          )}
          {target.source === 'env' && (
            <p className="text-[11px] text-muted-foreground">Set via environment variable</p>
          )}
        </div>
        <div className="flex items-center justify-end">
          <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
            <Cog className="h-3.5 w-3.5 mr-1" /> Configure
          </Button>
        </div>
      </div>
      <EditTargetDialog target={target} open={open} onOpenChange={setOpen} />
    </>
  )
}

export function AdapterTargets() {
  const { data, isLoading } = useAdapterTargets()
  return (
    <div>
      {isLoading && <Skeleton className="h-40 w-full" />}
      {data && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((t) => <TargetTile key={t.system} target={t} />)}
        </div>
      )}
    </div>
  )
}
