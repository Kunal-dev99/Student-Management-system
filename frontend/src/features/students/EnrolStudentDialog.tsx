'use client'

/**
 * ICR G2 — the direct enrolment door.
 *
 * ICR runs recruitment in a separate system, so the register must let an admin create an
 * already-accepted student without an opportunity/offer chain. A small form: who they are,
 * which programme, when they start, and their study mode/status. Funding and cohort (CSV)
 * import are handled elsewhere; this is the single-student path.
 */
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { UserPlus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { useProgrammes } from '@/features/progression/api'
import { useEnrolStudent, type StudentStatus } from '@/features/students/api'

const EMPTY = {
  givenName: '',
  familyName: '',
  email: '',
  programmeId: '',
  startDate: '',
  studyMode: 'full_time' as 'full_time' | 'part_time',
  status: 'registered' as StudentStatus,
}

export function EnrolStudentDialog() {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const { data: programmes } = useProgrammes()
  const enrol = useEnrolStudent()
  const { toast } = useToast()
  const router = useRouter()

  const set = <K extends keyof typeof EMPTY>(k: K, v: (typeof EMPTY)[K]) =>
    setForm((f) => ({ ...f, [k]: v }))

  const canSubmit = form.givenName.trim() && form.familyName.trim() && form.programmeId

  const submit = async () => {
    try {
      const student = await enrol.mutateAsync({
        person: {
          givenName: form.givenName.trim(),
          familyName: form.familyName.trim(),
          ...(form.email.trim() ? { email: form.email.trim() } : {}),
        },
        programmeId: form.programmeId,
        studyMode: form.studyMode,
        status: form.status,
        ...(form.startDate ? { startDate: form.startDate } : {}),
      })
      toast({
        title: 'Student enrolled',
        description: `${form.givenName} ${form.familyName} — ${student.studentRef}`,
      })
      setForm(EMPTY)
      setOpen(false)
      router.push(`/students/${student.id}`)
    } catch (err) {
      toast({
        title: 'Could not enrol',
        description: (err as Error)?.message ?? 'Please check the details and try again.',
        variant: 'destructive',
      })
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button><UserPlus className="mr-2 h-4 w-4" />Enrol student</Button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Enrol a student</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground -mt-1">
          For an already-accepted student — no recruitment offer needed.
        </p>

        <div className="space-y-4 py-2">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="enrol-given">First name</Label>
              <Input id="enrol-given" value={form.givenName}
                onChange={(e) => set('givenName', e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="enrol-family">Last name</Label>
              <Input id="enrol-family" value={form.familyName}
                onChange={(e) => set('familyName', e.target.value)} />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="enrol-email">Email <span className="text-muted-foreground">(optional)</span></Label>
            <Input id="enrol-email" type="email" value={form.email}
              onChange={(e) => set('email', e.target.value)} />
          </div>

          <div className="space-y-1.5">
            <Label>Programme</Label>
            <Select value={form.programmeId} onValueChange={(v) => set('programmeId', v)}>
              <SelectTrigger><SelectValue placeholder="Choose a programme…" /></SelectTrigger>
              <SelectContent>
                {programmes?.map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="enrol-start">Start date</Label>
              <Input id="enrol-start" type="date" value={form.startDate}
                onChange={(e) => set('startDate', e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Study mode</Label>
              <Select value={form.studyMode} onValueChange={(v) => set('studyMode', v as typeof form.studyMode)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="full_time">Full time</SelectItem>
                  <SelectItem value="part_time">Part time</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Status</Label>
            <Select value={form.status} onValueChange={(v) => set('status', v as StudentStatus)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="registered">Registered</SelectItem>
                <SelectItem value="prospective">Prospective (pre-enrolment)</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
          <Button onClick={submit} disabled={!canSubmit || enrol.isPending}>
            {enrol.isPending ? 'Enrolling…' : 'Enrol student'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
