'use client'

/**
 * ICR G2 — the direct enrolment door.
 *
 * Enrol an already-accepted student without a recruitment offer chain. Two paths: create a
 * brand-new person, or attach to an EXISTING person (applicant/alumni/staff already on the
 * register) so we don't create duplicate people. Funding/cohort import live elsewhere.
 */
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { UserPlus, Search, Check } from 'lucide-react'
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
import { usePersons, type Person } from '@/features/persons/api'
import { PersonaTags } from '@/features/persons/PersonaTags'
import { useEnrolStudent, type StudentStatus } from '@/features/students/api'

const EMPTY = {
  givenName: '', familyName: '', email: '', programmeId: '', startDate: '',
  studyMode: 'full_time' as 'full_time' | 'part_time',
  status: 'registered' as StudentStatus,
}
const emailOk = (e: string) => !e || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e)

export function EnrolStudentDialog() {
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState<'new' | 'existing'>('new')
  const [form, setForm] = useState(EMPTY)
  const [personQuery, setPersonQuery] = useState('')
  const [picked, setPicked] = useState<Person | null>(null)
  const { data: programmes } = useProgrammes()
  const persons = usePersons(personQuery, { enabled: mode === 'existing' && personQuery.trim().length >= 2 })
  const enrol = useEnrolStudent()
  const { toast } = useToast()
  const router = useRouter()

  const set = <K extends keyof typeof EMPTY>(k: K, v: (typeof EMPTY)[K]) =>
    setForm((f) => ({ ...f, [k]: v }))

  const resetForm = () => {
    setForm(EMPTY); setMode('new'); setPersonQuery(''); setPicked(null)
  }

  const personReady = mode === 'new'
    ? form.givenName.trim() && form.familyName.trim() && emailOk(form.email.trim())
    : !!picked
  const canSubmit = personReady && form.programmeId

  const doEnrol = async (addAnother: boolean) => {
    try {
      const student = await enrol.mutateAsync({
        ...(mode === 'existing' && picked
          ? { personId: picked.id }
          : {
              person: {
                givenName: form.givenName.trim(),
                familyName: form.familyName.trim(),
                ...(form.email.trim() ? { email: form.email.trim() } : {}),
              },
            }),
        programmeId: form.programmeId,
        studyMode: form.studyMode,
        status: form.status,
        ...(form.startDate ? { startDate: form.startDate } : {}),
      })
      const who = mode === 'existing' && picked ? `${picked.givenName} ${picked.familyName}` : `${form.givenName} ${form.familyName}`
      toast({ title: 'Student enrolled', description: `${who} — ${student.studentRef}` })
      if (addAnother) {
        resetForm()
      } else {
        resetForm(); setOpen(false); router.push(`/students/${student.id}`)
      }
    } catch (err) {
      toast({ title: 'Could not enrol', description: (err as Error)?.message ?? 'Please check the details and try again.', variant: 'destructive' })
    }
  }

  const results = persons.data?.data ?? []

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) resetForm() }}>
      <DialogTrigger asChild>
        <Button><UserPlus className="mr-2 h-4 w-4" />Enrol student</Button>
      </DialogTrigger>
      <DialogContent className="flex max-h-[88vh] max-w-md flex-col overflow-hidden">
        <DialogHeader className="flex-none"><DialogTitle>Enrol a student</DialogTitle></DialogHeader>

        <div className="-mr-2 flex-1 space-y-4 overflow-y-auto py-2 pr-2">
          {/* Person: new vs existing */}
          <div className="space-y-2">
            <div className="inline-flex rounded-md border border-border p-0.5 text-sm">
              <button type="button"
                className={`rounded px-3 py-1 ${mode === 'new' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'}`}
                onClick={() => { setMode('new'); setPicked(null) }}>New person</button>
              <button type="button"
                className={`rounded px-3 py-1 ${mode === 'existing' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'}`}
                onClick={() => setMode('existing')}>Existing person</button>
            </div>

            {mode === 'new' ? (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="enrol-given">First name</Label>
                    <Input id="enrol-given" value={form.givenName} onChange={(e) => set('givenName', e.target.value)} />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="enrol-family">Last name</Label>
                    <Input id="enrol-family" value={form.familyName} onChange={(e) => set('familyName', e.target.value)} />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="enrol-email">Email <span className="text-muted-foreground">(optional)</span></Label>
                  <Input id="enrol-email" type="email" value={form.email} onChange={(e) => set('email', e.target.value)} />
                  {!emailOk(form.email.trim()) && (
                    <p className="text-xs text-[hsl(var(--destructive))]">Enter a valid email address.</p>
                  )}
                </div>
              </>
            ) : (
              <div className="space-y-1.5">
                <Label>Find an existing person</Label>
                <div className="relative">
                  <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input className="pl-8" placeholder="Search by name or email…" value={personQuery}
                    onChange={(e) => { setPersonQuery(e.target.value); setPicked(null) }} />
                </div>
                {picked ? (
                  <div className="flex items-start justify-between gap-2 rounded-md border border-border bg-muted/30 px-3 py-2 text-sm">
                    <span className="space-y-1">
                      <span className="block"><span className="font-medium">{picked.givenName} {picked.familyName}</span>
                        {picked.email && <span className="text-muted-foreground"> · {picked.email}</span>}</span>
                      <PersonaTags relationships={picked.relationships} emptyLabel="No recorded roles yet" />
                    </span>
                    <Button variant="ghost" size="sm" className="shrink-0" onClick={() => setPicked(null)}>Change</Button>
                  </div>
                ) : personQuery.trim().length >= 2 && (
                  <div className="max-h-40 overflow-auto rounded-md border border-border">
                    {persons.isPending && <p className="px-3 py-2 text-sm text-muted-foreground">Searching…</p>}
                    {!persons.isPending && results.length === 0 && (
                      <p className="px-3 py-2 text-sm text-muted-foreground">No match — switch to “New person” to create one.</p>
                    )}
                    {results.map((p) => (
                      <button key={p.id} type="button" onClick={() => setPicked(p)}
                        className="flex w-full items-start justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-muted">
                        <span className="space-y-1">
                          <span className="block"><span className="font-medium">{p.givenName} {p.familyName}</span>
                            {p.email && <span className="text-muted-foreground"> · {p.email}</span>}</span>
                          <PersonaTags relationships={p.relationships} />
                        </span>
                        <Check className="h-4 w-4 shrink-0 opacity-0" />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="space-y-1.5">
            <Label>Programme</Label>
            <Select value={form.programmeId} onValueChange={(v) => set('programmeId', v)}>
              <SelectTrigger><SelectValue placeholder="Choose a programme…" /></SelectTrigger>
              <SelectContent>
                {programmes?.map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.code} — {p.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="enrol-start">Start date</Label>
              <Input id="enrol-start" type="date" value={form.startDate} onChange={(e) => set('startDate', e.target.value)} />
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

        <DialogFooter className="flex-none gap-2 sm:justify-between">
          <Button variant="outline" onClick={() => { setOpen(false); resetForm() }}>Cancel</Button>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => doEnrol(true)} disabled={!canSubmit || enrol.isPending}>
              Enrol &amp; add another
            </Button>
            <Button onClick={() => doEnrol(false)} disabled={!canSubmit || enrol.isPending}>
              {enrol.isPending ? 'Enrolling…' : 'Enrol student'}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
