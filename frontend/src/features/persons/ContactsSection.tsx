'use client'

/**
 * F2 — Contacts card on the person detail screen.
 *
 * Anything with ``doNotContact = true`` is honoured by the notifier and by every screen that
 * chooses which channel to reach a person on. This is the single source of truth.
 */

import { useState } from 'react'
import { PhoneCall, Plus, Trash2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useToast } from '@/components/ui/use-toast'
import { ApiError } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import {
  useAddContact, useContacts, useDeleteContact, useUpdateContact,
  type ContactChannel,
} from '@/features/persons/api'

const CHANNELS: ContactChannel[] = ['email', 'phone', 'mobile', 'address', 'emergency']

export function ContactsSection({ personId }: { personId: string }) {
  const { toast } = useToast()
  const { hasPermission } = useAuth()
  const canWrite = hasPermission('person.write')
  const list = useContacts(personId)
  const add = useAddContact(personId)
  const update = useUpdateContact(personId)
  const remove = useDeleteContact(personId)

  const [open, setOpen] = useState(false)
  const [channel, setChannel] = useState<ContactChannel>('phone')
  const [value, setValue] = useState('')
  const [label, setLabel] = useState('')
  const [dnc, setDnc] = useState(false)

  if (list.isLoading) return <Skeleton className="h-16 w-full" />
  if (list.isError) return <p className="text-sm text-[hsl(var(--destructive))]">{(list.error as ApiError)?.message}</p>

  const rows = list.data ?? []

  return (
    <div className="space-y-3">
      {rows.length === 0 ? (
        <p className="text-helper">No extra contact channels. Add one when the primary email
          is not the right way to reach this person.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Channel</TableHead>
              <TableHead>Value</TableHead>
              <TableHead>Label</TableHead>
              <TableHead>Do not contact</TableHead>
              <TableHead className="text-right w-8" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.id}>
                <TableCell><Badge variant="secondary">{r.channel}</Badge></TableCell>
                <TableCell className="font-mono text-xs">{r.value}</TableCell>
                <TableCell className="text-sm text-muted-foreground">{r.label ?? '—'}</TableCell>
                <TableCell>
                  <Checkbox checked={r.doNotContact} disabled={!canWrite}
                    onCheckedChange={(c) => update.mutate({ id: r.id, body: { doNotContact: c === true } })} />
                </TableCell>
                <TableCell className="text-right">
                  {canWrite && (
                    <Button variant="ghost" size="icon"
                      onClick={() => remove.mutate(r.id)}><Trash2 className="h-4 w-4" /></Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {canWrite && (
        <Dialog open={open} onOpenChange={(o) => {
          setOpen(o)
          if (!o) { setValue(''); setLabel(''); setDnc(false); setChannel('phone') }
        }}>
          <DialogTrigger asChild>
            <Button size="sm" variant="outline"><Plus className="h-4 w-4 mr-1" /> Add contact</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>Add a contact channel</DialogTitle></DialogHeader>
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label>Channel</Label>
                  <Select value={channel} onValueChange={(v) => setChannel(v as ContactChannel)}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {CHANNELS.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="c-label">Label (optional)</Label>
                  <Input id="c-label" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="work" />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="c-value">Value</Label>
                <Input id="c-value" value={value} onChange={(e) => setValue(e.target.value)} placeholder="+44 7…" />
              </div>
              <div className="flex items-center gap-2">
                <Checkbox id="c-dnc" checked={dnc} onCheckedChange={(v) => setDnc(v === true)} />
                <Label htmlFor="c-dnc">Do not contact on this channel</Label>
              </div>
            </div>
            <DialogFooter>
              <Button
                disabled={!value.trim() || add.isPending}
                onClick={async () => {
                  try {
                    await add.mutateAsync({
                      channel, value: value.trim(), label: label.trim() || undefined, doNotContact: dnc,
                    })
                    toast({ title: 'Contact added' })
                    setOpen(false)
                  } catch (e) { toast({ title: 'Add failed', description: (e as ApiError).message, variant: 'destructive' }) }
                }}>
                <PhoneCall className="h-4 w-4 mr-1" />
                {add.isPending ? 'Saving…' : 'Add contact'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  )
}
