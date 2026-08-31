'use client'

/**
 * F2 — GDPR panel on the person detail screen.
 *
 * Two operations sit here: **subject-access export** (produce a JSON of every row this person
 * touches) and **erasure** (pseudonymise the row forever). Both live behind the person.gdpr
 * permission and are irreversible in the erasure case, so the erase action asks for a typed
 * confirmation before it fires.
 */

import { useState } from 'react'
import { Download, ShieldAlert, ShieldX } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useToast } from '@/components/ui/use-toast'
import { ApiError } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import { useGdprErase, useGdprExport, type Person } from '@/features/persons/api'

export function GdprSection({ person }: { person: Person }) {
  const { toast } = useToast()
  const { hasPermission } = useAuth()
  const canGdpr = hasPermission('person.gdpr')
  const exportOp = useGdprExport(person.id)
  const eraseOp = useGdprErase(person.id)
  const [confirm, setConfirm] = useState('')
  const [open, setOpen] = useState(false)
  const erased = 'pseudonymisedAt' in person && !!(person as unknown as { pseudonymisedAt?: string }).pseudonymisedAt

  if (!canGdpr) {
    return (
      <p className="text-helper">
        The GDPR actions (subject-access export, erasure) require the <span className="font-mono">person.gdpr</span>{' '}
        permission. Ask an Institution Administrator to grant it.
      </p>
    )
  }

  const downloadExport = async () => {
    try {
      const data = await exportOp.mutateAsync()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `person-${person.id}-subject-access.json`
      document.body.appendChild(a); a.click(); a.remove()
      URL.revokeObjectURL(url)
      toast({ title: 'Subject-access export downloaded' })
    } catch (e) { toast({ title: 'Export failed', description: (e as ApiError).message, variant: 'destructive' }) }
  }

  return (
    <div className="space-y-3">
      {erased ? (
        <p className="text-sm inline-flex items-center gap-2 text-muted-foreground">
          <ShieldX className="h-4 w-4" /> This person has been GDPR-erased. The row is preserved so
          audit and financial integrity hold; identifying fields are pseudonymised.
        </p>
      ) : (
        <p className="text-sm text-muted-foreground">
          Subject-access exports every row that references this person, walked from the schema so
          nothing is missed as new modules are added. Erasure pseudonymises the person and drops
          their contact channels — the row itself stays so audit and FKs remain intact.
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="outline" onClick={downloadExport}
          disabled={exportOp.isPending}>
          <Download className="h-4 w-4 mr-1" />
          {exportOp.isPending ? 'Preparing…' : 'Download subject-access export (JSON)'}
        </Button>
        {!erased && (
          <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) setConfirm('') }}>
            <DialogTrigger asChild>
              <Button size="sm" variant="destructive">
                <ShieldAlert className="h-4 w-4 mr-1" /> Erase this person
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Erase {person.givenName} {person.familyName}?</DialogTitle></DialogHeader>
              <div className="space-y-3">
                <p className="text-sm">
                  This pseudonymises the person: name becomes <span className="font-mono">erased</span>,
                  email becomes a one-way hash, contact channels are deleted. The action is
                  irreversible and satisfies a right-to-erasure request under GDPR.
                </p>
                <div className="space-y-1.5">
                  <Label htmlFor="e-conf">Type <span className="font-mono">ERASE</span> to confirm</Label>
                  <Input id="e-conf" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
                </div>
              </div>
              <DialogFooter>
                <Button variant="destructive" disabled={confirm !== 'ERASE' || eraseOp.isPending}
                  onClick={async () => {
                    try {
                      await eraseOp.mutateAsync()
                      toast({ title: 'Person erased' })
                      setOpen(false); setConfirm('')
                    } catch (e) { toast({ title: 'Erase failed', description: (e as ApiError).message, variant: 'destructive' }) }
                  }}>
                  {eraseOp.isPending ? 'Erasing…' : 'Erase permanently'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        )}
      </div>
    </div>
  )
}
