'use client'

/** Effective dating, Phase 9 — units of assessment: the admin list (Settings) and a person's dated
 *  UOA (person page). A supervisor's UOA is dated, so a late change doesn't rewrite a period that
 *  was already reported, and a change after sign-off is listed against their students. */

import { useState } from 'react'
import { Landmark } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useToast } from '@/components/ui/use-toast'
import { useAuth } from '@/shared/auth/AuthContext'
import { todayIso } from '@/features/history/api'
import { useChangePersonUoa, useCreateUoa, usePersonUoa, useUoas, useUpdateUoa } from './api'

function dayBefore(iso: string | null): string | null {
  if (!iso) return null
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() - 1)
  return d.toISOString().slice(0, 10)
}

/** Settings → Units of assessment. */
export function UoaAdminTab() {
  const { toast } = useToast()
  const list = useUoas()
  const create = useCreateUoa()
  const update = useUpdateUoa()
  const [form, setForm] = useState({ code: '', name: '', panel: '' })
  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as Error).message, variant: 'destructive' })

  return (
    <div className="card-elevated p-4 space-y-3">
      <p className="text-sm text-muted-foreground">
        Units of assessment students and supervisors are attached to (e.g. REF UOA 1 Clinical Medicine).
        Their links are dated on the student and person records; retiring a UOA keeps history but
        stops new assignments.
      </p>
      {list.isLoading ? <Skeleton className="h-20 w-full" /> : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-24">Code</TableHead>
              <TableHead>Name</TableHead>
              <TableHead className="w-20">Panel</TableHead>
              <TableHead className="w-32 text-right" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {(list.data ?? []).map((u) => (
              <TableRow key={u.id} className={u.isActive ? undefined : 'opacity-60'}>
                <TableCell className="font-mono">{u.code}</TableCell>
                <TableCell>
                  {u.name}
                  {!u.isActive && <Badge variant="secondary" className="ml-2">retired</Badge>}
                </TableCell>
                <TableCell>{u.panel ?? '—'}</TableCell>
                <TableCell className="text-right">
                  <Button size="sm" variant="ghost" disabled={update.isPending}
                    onClick={async () => {
                      try { await update.mutateAsync({ id: u.id, isActive: !u.isActive }) } catch (e) { err(e) }
                    }}>{u.isActive ? 'Retire' : 'Reinstate'}</Button>
                </TableCell>
              </TableRow>
            ))}
            {list.data && list.data.length === 0 && (
              <TableRow><TableCell colSpan={4} className="text-helper">No units of assessment yet.</TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      )}
      <div className="flex flex-wrap items-end gap-2 pt-2 border-t border-border">
        <Input className="h-8 w-24" placeholder="Code" value={form.code}
          onChange={(e) => setForm((s) => ({ ...s, code: e.target.value }))} />
        <Input className="h-8 w-64" placeholder="Name" value={form.name}
          onChange={(e) => setForm((s) => ({ ...s, name: e.target.value }))} />
        <Input className="h-8 w-20" placeholder="Panel" value={form.panel}
          onChange={(e) => setForm((s) => ({ ...s, panel: e.target.value }))} />
        <Button size="sm" disabled={create.isPending || !form.code.trim() || !form.name.trim()}
          onClick={async () => {
            try {
              await create.mutateAsync({ code: form.code.trim(), name: form.name.trim(), panel: form.panel.trim() || undefined })
              setForm({ code: '', name: '', panel: '' })
              toast({ title: 'Unit of assessment added' })
            } catch (e) { err(e) }
          }}>Add</Button>
      </div>
    </div>
  )
}

/** Person page → their unit of assessment over time, with a dated change form. */
export function PersonUoaSection({ personId }: { personId: string }) {
  const { toast } = useToast()
  const { hasPermission } = useAuth()
  const canEdit = hasPermission('person.write')
  const q = usePersonUoa(personId)
  const uoas = useUoas()
  const change = useChangePersonUoa(personId)
  const [open, setOpen] = useState(false)
  const [uoaId, setUoaId] = useState('')
  const [date, setDate] = useState(todayIso())
  const [reason, setReason] = useState('')

  return (
    <PageSection icon={Landmark} title="Unit of assessment"
      description="Dated: a change applies from its date to every student this person supervises.">
      {q.isLoading ? <Skeleton className="h-10 w-full" /> : (
        <>
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm">{q.data?.current ?? <span className="text-muted-foreground">Not recorded</span>}</p>
            {canEdit && (
              <Button size="sm" variant="ghost" onClick={() => { setOpen(!open); setUoaId(q.data?.currentUoaId ?? '') }}>
                {q.data?.current ? 'Change' : 'Record'}
              </Button>
            )}
          </div>
          {open && (
            <div className="flex flex-wrap items-end gap-2 mt-2 bg-surface-2 rounded-md p-2">
              <div className="flex flex-col gap-1 min-w-[220px]">
                <span className="text-label">Unit of assessment</span>
                <Select value={uoaId} onValueChange={setUoaId}>
                  <SelectTrigger className="h-8"><SelectValue placeholder="Choose…" /></SelectTrigger>
                  <SelectContent>
                    {(uoas.data ?? []).filter((u) => u.isActive).map((u) => (
                      <SelectItem key={u.id} value={u.id}>{u.code} {u.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor="puoa-from" className="text-label">From</label>
                <Input id="puoa-from" type="date" className="h-8 w-40" value={date} onChange={(e) => setDate(e.target.value)} />
              </div>
              <Input className="h-8 w-56" placeholder="Reason (optional)" value={reason}
                onChange={(e) => setReason(e.target.value)} />
              <Button size="sm" disabled={change.isPending || !uoaId || uoaId === q.data?.currentUoaId}
                onClick={async () => {
                  try {
                    await change.mutateAsync({ uoaId, effectiveDate: date || undefined, reason: reason.trim() || undefined })
                    toast({ title: 'Unit of assessment recorded', description: `From ${date || 'today'}.` })
                    setOpen(false); setReason('')
                  } catch (e) {
                    toast({ title: 'Could not record', description: (e as Error).message, variant: 'destructive' })
                  }
                }}>Save</Button>
              <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            </div>
          )}
          {(q.data?.periods.length ?? 0) > 0 && (
            <ul className="mt-2 space-y-0.5 text-xs text-muted-foreground">
              {q.data!.periods.map((p) => (
                <li key={p.id} className="num">
                  {p.uoa ?? '—'}: {p.validFrom} → {dayBefore(p.validTo) ?? 'current'}
                  {p.reason ? ` · ${p.reason}` : ''}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </PageSection>
  )
}
