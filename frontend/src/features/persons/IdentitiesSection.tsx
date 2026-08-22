'use client'

/**
 * Person identities (Phase 6.4).
 *
 * The point this screen has to make: ONE person_id holds several identities at once.
 * A PGR who picks up a demonstrating contract becomes an employee *as well as* a student —
 * not a second person record to be reconciled later.
 */

import { useState } from 'react'
import { Layers, Plus } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { ApiError } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import { RelationshipBadge } from './RelationshipBadge'
import {
  RELATIONSHIP_TYPES, useCloseRelationship, useOpenRelationship, usePersonRelationships,
  type RelationshipType,
} from './api'

function AddIdentityDialog({ personId }: { personId: string }) {
  const { toast } = useToast()
  const open_ = useOpenRelationship(personId)
  const [open, setOpen] = useState(false)
  const [relationshipType, setRelationshipType] = useState<RelationshipType>('employee')
  const [validFrom, setValidFrom] = useState('')
  const [sourceSystem, setSourceSystem] = useState('')

  const reset = () => { setRelationshipType('employee'); setValidFrom(''); setSourceSystem('') }

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) reset() }}>
      <DialogTrigger asChild>
        <Button size="sm"><Plus className="h-4 w-4 mr-1" /> Add identity</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Add an identity</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Identity</Label>
            <Select value={relationshipType} onValueChange={(v) => setRelationshipType(v as RelationshipType)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {RELATIONSHIP_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="id-from">Valid from (optional — defaults to today)</Label>
              <Input id="id-from" type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="id-src">Source system (optional)</Label>
              <Input id="id-src" value={sourceSystem} onChange={(e) => setSourceSystem(e.target.value)}
                placeholder="hr, research, sits…" />
            </div>
          </div>
          <p className="text-helper">
            This <strong>opens</strong> an identity without closing the others. The same{' '}
            <span className="font-mono text-xs">person_id</span> can be a student and an employee at
            the same time — a PGR taking a demonstrating contract does not become a second person.
          </p>
        </div>
        <DialogFooter>
          <Button
            disabled={open_.isPending}
            onClick={async () => {
              try {
                await open_.mutateAsync({
                  relationshipType,
                  validFrom: validFrom || undefined,
                  sourceSystem: sourceSystem.trim() || undefined,
                })
                toast({
                  title: `Identity opened: ${relationshipType}`,
                  description: 'Existing identities were left open — nothing was overwritten.',
                })
                setOpen(false); reset()
              } catch (e) {
                toast({ title: 'Could not add identity', description: (e as ApiError).message, variant: 'destructive' })
              }
            }}
          >
            {open_.isPending ? 'Saving…' : 'Add identity'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function IdentitiesSection({ personId }: { personId: string }) {
  const { toast } = useToast()
  const { hasPermission } = useAuth()
  const rels = usePersonRelationships(personId)
  const close = useCloseRelationship(personId)
  // Hiding the controls is convenience only — the API enforces the permission.
  const canWrite = hasPermission('person.write')
  const [closingType, setClosingType] = useState<RelationshipType | null>(null)

  const rows = (rels.data ?? []).slice().sort((a, b) => a.validFrom.localeCompare(b.validFrom))
  const currentCount = rows.filter((r) => r.validTo === null).length

  return (
    <PageSection
      icon={Layers}
      title="Identities"
      accent="accent"
      description="One person_id, several identities held at once — applicant, student, employee, alumni, researcher."
      headerRight={currentCount > 1 ? <Badge variant="info">{currentCount} held concurrently</Badge> : undefined}
      actions={canWrite ? <AddIdentityDialog personId={personId} /> : undefined}
    >
      {rels.isLoading ? (
        <Skeleton className="h-20 w-full" />
      ) : rels.isError ? (
        <p className="text-sm text-[hsl(var(--destructive))]">{(rels.error as ApiError)?.message}</p>
      ) : rows.length === 0 ? (
        <p className="text-helper">No identities recorded for this person yet.</p>
      ) : (
        <div className="space-y-2">
          {rows.map((r) => (
            <div key={r.id} className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 last:border-0 pb-2 last:pb-0">
              <div className="flex flex-wrap items-center gap-2">
                <RelationshipBadge type={r.relationshipType} />
                {r.validTo === null && <Badge variant="success">current</Badge>}
                <span className="text-sm text-muted-foreground num">
                  {r.validFrom} → {r.validTo ?? 'open'}
                </span>
                {r.sourceSystem && (
                  <span className="text-helper">from {r.sourceSystem}</span>
                )}
              </div>
              {canWrite && r.validTo === null && (
                <Button
                  size="sm" variant="ghost"
                  disabled={close.isPending && closingType === r.relationshipType}
                  onClick={async () => {
                    setClosingType(r.relationshipType)
                    try {
                      await close.mutateAsync(r.relationshipType)
                      toast({
                        title: `Identity closed: ${r.relationshipType}`,
                        description: 'The record is dated, not deleted — the history stays.',
                      })
                    } catch (e) {
                      toast({ title: 'Could not close identity', description: (e as ApiError).message, variant: 'destructive' })
                    } finally {
                      setClosingType(null)
                    }
                  }}
                >
                  {close.isPending && closingType === r.relationshipType ? 'Closing…' : 'Close'}
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
      <p className="text-helper mt-3">
        Identities are additive. Closing one dates it and leaves it in place; the others carry on,
        so a person&apos;s history is never rewritten to fit their current role.
      </p>
    </PageSection>
  )
}
