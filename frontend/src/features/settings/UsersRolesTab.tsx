'use client'

/**
 * "Users & roles" tab.
 *
 * Two backend rules this UI leans on rather than re-implements:
 * - No password field exists anywhere — inviting a user emails them a
 *   set-password link. The copy says so explicitly.
 * - Self-lockout (deactivating yourself, dropping your own admin role) is
 *   refused with a 409 whose message we surface verbatim.
 */

import { useState } from 'react'
import { KeyRound, Pencil, ShieldCheck, UserPlus, Users } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { useToast } from '@/components/ui/use-toast'
import { ApiError } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import {
  useAdminRoles, useAdminUsers, useInviteUser, useSendPasswordReset, useUpdateUser,
  type AdminRole, type AdminUser,
} from '@/features/settings/api'

const fmtDate = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : null)

/* ------------------------------------------------------------------ */

function RolePicker({ roles, selected, onToggle }: {
  roles: AdminRole[]
  selected: string[]
  onToggle: (name: string, checked: boolean) => void
}) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {roles.map((r) => (
        <div key={r.id} className="flex items-center gap-2">
          <Checkbox
            id={`role-${r.name}`}
            checked={selected.includes(r.name)}
            onCheckedChange={(v) => onToggle(r.name, v === true)}
          />
          <Label htmlFor={`role-${r.name}`} className="cursor-pointer font-normal">{r.name}</Label>
        </div>
      ))}
    </div>
  )
}

function InviteUserDialog({ roles }: { roles: AdminRole[] }) {
  const { toast } = useToast()
  const invite = useInviteUser()
  const [open, setOpen] = useState(false)
  const [email, setEmail] = useState('')
  const [selected, setSelected] = useState<string[]>([])

  const toggle = (name: string, checked: boolean) =>
    setSelected((prev) => checked ? [...new Set([...prev, name])] : prev.filter((n) => n !== name))

  const submit = async () => {
    try {
      await invite.mutateAsync({ email: email.trim(), roleNames: selected })
      toast({
        title: 'Invitation sent',
        description: `${email.trim()} will receive an email with a link to set their own password.`,
      })
      setOpen(false)
    } catch (e) {
      toast({ title: 'Could not invite user', description: (e as ApiError).message, variant: 'destructive' })
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (o) { setEmail(''); setSelected([]) } }}>
      <DialogTrigger asChild>
        <Button size="sm"><UserPlus className="h-4 w-4 mr-1" /> Invite user</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Invite a user</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="inv-email">Email</Label>
            <Input
              id="inv-email" type="email" value={email}
              onChange={(e) => setEmail(e.target.value)} placeholder="name@institution.ac.uk"
            />
          </div>
          <div className="space-y-1.5">
            <Label>Roles</Label>
            <RolePicker roles={roles} selected={selected} onToggle={toggle} />
          </div>
          <p className="text-helper">
            There is no password to set here: the new user receives an email with a link to choose
            their own password. Administrators never know or set anyone&apos;s password.
          </p>
        </div>
        <DialogFooter>
          <Button
            disabled={!email.trim() || selected.length === 0 || invite.isPending}
            onClick={submit}
          >
            {invite.isPending ? 'Inviting…' : 'Send invitation'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function EditRolesDialog({ user, roles }: { user: AdminUser; roles: AdminRole[] }) {
  const { toast } = useToast()
  const update = useUpdateUser()
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState<string[]>(user.roles)

  const toggle = (name: string, checked: boolean) =>
    setSelected((prev) => checked ? [...new Set([...prev, name])] : prev.filter((n) => n !== name))

  const submit = async () => {
    try {
      await update.mutateAsync({ id: user.id, body: { roleNames: selected } })
      toast({ title: `Roles updated for ${user.email}` })
      setOpen(false)
    } catch (e) {
      // 409 self-lockout ("You cannot remove your own administrator access") — verbatim.
      toast({ title: 'Roles not changed', description: (e as ApiError).message, variant: 'destructive' })
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (o) setSelected(user.roles) }}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" className="h-7 px-2" title="Edit roles">
          <Pencil className="h-3.5 w-3.5" />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Edit roles — {user.email}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <RolePicker roles={roles} selected={selected} onToggle={toggle} />
          <p className="text-helper">A user needs at least one role.</p>
        </div>
        <DialogFooter>
          <Button disabled={selected.length === 0 || update.isPending} onClick={submit}>
            {update.isPending ? 'Saving…' : 'Save roles'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/* ------------------------------------------------------------------ */

function UserRow({ user, roles }: { user: AdminUser; roles: AdminRole[] }) {
  const { toast } = useToast()
  const { principal } = useAuth()
  const update = useUpdateUser()
  const sendReset = useSendPasswordReset()
  const isSelf = principal?.userId === user.id
  const locked = !!user.lockedUntil && new Date(user.lockedUntil) > new Date()

  const toggleActive = async () => {
    try {
      await update.mutateAsync({ id: user.id, body: { isActive: !user.isActive } })
      toast({ title: `${user.email} ${user.isActive ? 'deactivated' : 'activated'}` })
    } catch (e) {
      // 409 "You cannot deactivate your own account" — verbatim.
      toast({ title: 'Not changed', description: (e as ApiError).message, variant: 'destructive' })
    }
  }

  const reset = async () => {
    try {
      await sendReset.mutateAsync(user.id)
      toast({ title: 'Password reset sent', description: `An email is on its way to ${user.email}.` })
    } catch (e) {
      toast({ title: 'Reset not sent', description: (e as ApiError).message, variant: 'destructive' })
    }
  }

  return (
    <TableRow>
      <TableCell className="font-medium">
        {user.email}
        {isSelf && <span className="text-helper ml-1.5">(you)</span>}
      </TableCell>
      <TableCell>
        <div className="flex flex-wrap gap-1">
          {user.roles.map((r) => <Badge key={r} variant="secondary">{r}</Badge>)}
        </div>
      </TableCell>
      <TableCell>
        <div className="flex flex-wrap gap-1">
          {user.isActive
            ? <Badge variant="success">Active</Badge>
            : <Badge variant="secondary" className="text-muted-foreground">Inactive</Badge>}
          {!user.hasPassword && (
            <Badge variant="info" title="Invited — they have not yet set a password via the emailed link.">
              No password yet — invited
            </Badge>
          )}
          {locked && <Badge variant="warning" title={`Locked until ${fmtDate(user.lockedUntil)}`}>Locked</Badge>}
        </div>
      </TableCell>
      <TableCell className="text-muted-foreground whitespace-nowrap">
        {fmtDate(user.lastLoginAt) ?? 'Never'}
      </TableCell>
      <TableCell className="text-right">
        <div className="flex items-center justify-end gap-1">
          <EditRolesDialog user={user} roles={roles} />
          <Button
            variant="ghost" size="sm" className="h-7 px-2"
            title="Send a password-reset email"
            disabled={sendReset.isPending}
            onClick={reset}
          >
            <KeyRound className="h-3.5 w-3.5" />
          </Button>
          {/* Enabled even for yourself — the backend's 409 explains why it refuses. */}
          <Button
            variant="outline" size="sm" className="h-7"
            disabled={update.isPending}
            onClick={toggleActive}
          >
            {user.isActive ? 'Deactivate' : 'Activate'}
          </Button>
        </div>
      </TableCell>
    </TableRow>
  )
}

export function UsersRolesTab() {
  const users = useAdminUsers()
  const roles = useAdminRoles()

  return (
    <div className="space-y-4">
      <PageSection
        icon={Users}
        title="User accounts"
        description="Invited users set their own password via email — no password is ever typed on this screen."
        accent="primary"
        actions={<InviteUserDialog roles={roles.data ?? []} />}
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Email</TableHead>
              <TableHead>Roles</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Last login</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.isLoading && (
              <TableRow><TableCell colSpan={5}><Skeleton className="h-5 w-full" /></TableCell></TableRow>
            )}
            {users.data?.map((u) => <UserRow key={u.id} user={u} roles={roles.data ?? []} />)}
            {users.data && users.data.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-muted-foreground text-center py-8">
                  No user accounts yet.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </PageSection>

      <PageSection
        icon={ShieldCheck}
        title="Roles & permissions"
        description="Permissions are attached to roles in code and are not editable here."
        accent="primary"
      >
        {roles.isLoading && <Skeleton className="h-32 w-full" />}
        <div className="grid gap-3 md:grid-cols-2">
          {roles.data?.map((r) => (
            <div key={r.id} className="rounded-md border border-border bg-surface-1 p-4 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-medium">{r.name}</p>
                <Badge variant="secondary">
                  {r.userCount} user{r.userCount === 1 ? '' : 's'}
                </Badge>
              </div>
              <div className="flex flex-wrap gap-1">
                {r.permissions.map((p) => (
                  <Badge key={p} variant="outline" className="font-mono text-[11px] font-normal text-muted-foreground">
                    {p}
                  </Badge>
                ))}
                {r.permissions.length === 0 && <p className="text-helper">No permissions.</p>}
              </div>
            </div>
          ))}
        </div>
      </PageSection>
    </div>
  )
}
