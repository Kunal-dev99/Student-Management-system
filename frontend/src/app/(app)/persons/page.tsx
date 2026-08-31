'use client'

import { useState } from 'react'
import Link from 'next/link'
import { GitMerge, Search } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { useToast } from '@/components/ui/use-toast'
import { ApiError } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import { useMergePersons, usePersons } from '@/features/persons/api'
import { RelationshipBadge } from '@/features/persons/RelationshipBadge'

function MergeDialog() {
  const { toast } = useToast()
  const merge = useMergePersons()
  const [open, setOpen] = useState(false)
  const [surviving, setSurviving] = useState('')
  const [losing, setLosing] = useState('')
  const [reason, setReason] = useState('')

  return (
    <Dialog open={open} onOpenChange={(o) => {
      setOpen(o); if (!o) { setSurviving(''); setLosing(''); setReason('') }
    }}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline"><GitMerge className="h-4 w-4 mr-1" /> Merge persons</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Merge two duplicate persons</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Every foreign key pointing at the losing person is rewritten to the surviving person
            in one transaction; the losing row is then deleted. An immutable merge record is
            written so the join can be audited later. Pseudonymised (erased) persons cannot be
            merged.
          </p>
          <div className="space-y-1.5">
            <Label htmlFor="m-surv">Surviving person id</Label>
            <Input id="m-surv" className="font-mono text-xs" value={surviving}
              onChange={(e) => setSurviving(e.target.value)} placeholder="uuid" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="m-los">Losing person id (will be deleted)</Label>
            <Input id="m-los" className="font-mono text-xs" value={losing}
              onChange={(e) => setLosing(e.target.value)} placeholder="uuid" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="m-reason">Reason (recorded on the merge record)</Label>
            <Textarea id="m-reason" className="min-h-[64px]" value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Same person — two applicant emails" />
          </div>
        </div>
        <DialogFooter>
          <Button
            disabled={!surviving.trim() || !losing.trim() || merge.isPending}
            onClick={async () => {
              try {
                const r = await merge.mutateAsync({
                  survivingPersonId: surviving.trim(),
                  losingPersonId: losing.trim(),
                  reason: reason.trim() || undefined,
                })
                toast({ title: `Merged — ${r.totalRowsRewritten} row(s) rewritten` })
                setOpen(false); setSurviving(''); setLosing(''); setReason('')
              } catch (e) { toast({ title: 'Merge failed', description: (e as ApiError).message, variant: 'destructive' }) }
            }}>
            {merge.isPending ? 'Merging…' : 'Merge'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function PersonsPage() {
  const { hasPermission } = useAuth()
  const [search, setSearch] = useState('')
  const { data, isLoading, isError, error } = usePersons(search)

  return (
    <>
      <PageHeader title="Persons" description="One person across every identity over time."
        actions={hasPermission('person.gdpr') ? <MergeDialog /> : undefined} />
      <div className="px-6 pb-6 space-y-4">
        <div className="relative max-w-sm">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by name or email…"
            className="pl-8"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="card-elevated overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Nationality</TableHead>
                <TableHead>Current identities</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading &&
                Array.from({ length: 3 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={4}><Skeleton className="h-5 w-full" /></TableCell>
                  </TableRow>
                ))}

              {isError && (
                <TableRow>
                  <TableCell colSpan={4} className="text-[hsl(var(--destructive))]">
                    {(error as Error)?.message ?? 'Failed to load persons'}
                  </TableCell>
                </TableRow>
              )}

              {data?.data.map((p) => {
                const current = p.relationships.filter((r) => r.validTo === null)
                return (
                  <TableRow key={p.id} className="cursor-pointer">
                    <TableCell className="font-medium">
                      <Link href={`/persons/${p.id}`} className="hover:text-primary">
                        {p.givenName} {p.familyName}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{p.email ?? '—'}</TableCell>
                    <TableCell className="text-muted-foreground">{p.nationality ?? '—'}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {current.length ? (
                          current.map((r) => (
                            <RelationshipBadge key={r.id} type={r.relationshipType} current />
                          ))
                        ) : (
                          <span className="text-muted-foreground text-sm">none</span>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}

              {data && data.data.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4} className="text-muted-foreground text-center py-8">
                    No persons match “{search}”.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
        {data?.page.total != null && (
          <p className="text-helper">{data.page.total} total</p>
        )}
      </div>
    </>
  )
}
