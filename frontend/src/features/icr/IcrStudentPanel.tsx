'use client'

/**
 * ICR gap 2-5 panel — mounted on the ICR student detail page.
 *
 * Four cards: Clinical placement (SpR rotation), Independent tutor + notes, Bench fees
 * (allocation + draw-downs), Partner affiliations with expiry flags.
 */

import { useState } from 'react'
import {
  BadgeCheck, Calendar, DollarSign, Stethoscope, Lock, Plus, Send, ShieldAlert,
  ShieldCheck, ShieldOff, StickyNote, UserRound,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { PageSection } from '@/components/common/PageSection'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useToast } from '@/components/ui/use-toast'
import { ApiError } from '@/shared/api/client'
import {
  useAddAffiliation, useAddDrawdown, useAddTutorNote, useAffiliations, useAllocateBenchFee,
  useAssignTutor, useBenchFees, useCurrentTutor, useDrawdowns, useEndAffiliation, useEndPlacement,
  useEndTutor, useOpenPlacement, usePlacements, useTutorNotes,
  type ComplianceStatus,
} from '@/features/icr/gaps_api'

const TODAY = new Date().toISOString().slice(0, 10)


// ------------------------------------------------------------------ Gap 2

function ClinicalPlacementSection({ studentId }: { studentId: string }) {
  const { toast } = useToast()
  const q = usePlacements(studentId)
  const open = useOpenPlacement(studentId)
  const end = useEndPlacement(studentId)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [trust, setTrust] = useState('')
  const [specialty, setSpecialty] = useState('')
  const [grade, setGrade] = useState('')
  const [validFrom, setValidFrom] = useState(TODAY)
  const [sessions, setSessions] = useState('')
  const [supervisor, setSupervisor] = useState('')

  const submit = async () => {
    try {
      await open.mutateAsync({
        trustName: trust.trim(), specialty: specialty.trim(), grade: grade.trim(),
        validFrom, supervisorName: supervisor.trim() || null,
        sessionsPerWeek: sessions ? parseInt(sessions, 10) : null,
        notes: null,
      })
      toast({ title: 'Placement opened' })
      setDialogOpen(false); setTrust(''); setSpecialty(''); setGrade(''); setSessions(''); setSupervisor('')
    } catch (e) {
      toast({ title: 'Failed to open placement', description: (e as ApiError).message, variant: 'destructive' })
    }
  }

  const endRow = async (id: string) => {
    try {
      await end.mutateAsync({ id, validTo: TODAY })
      toast({ title: 'Placement ended' })
    } catch (e) {
      toast({ title: 'Failed to end', description: (e as ApiError).message, variant: 'destructive' })
    }
  }

  return (
    <PageSection icon={Stethoscope} title="Clinical placement (ICR gap 2)" accent="primary"
      description="Specialist Registrar rotation posts held alongside the studentship. Concurrent — the ICR MD(Res) model runs both in parallel.">
      {q.isLoading ? <Skeleton className="h-16 w-full" /> : (
        <div className="space-y-3">
          {q.data && q.data.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Trust</TableHead>
                  <TableHead>Specialty · Grade</TableHead>
                  <TableHead>Supervisor</TableHead>
                  <TableHead>Sessions/wk</TableHead>
                  <TableHead>Dates</TableHead>
                  <TableHead className="text-right"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {q.data.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="font-medium">{p.trustName}</TableCell>
                    <TableCell>{p.specialty} · <Badge variant="secondary">{p.grade}</Badge></TableCell>
                    <TableCell className="text-sm text-muted-foreground">{p.supervisorName ?? '—'}</TableCell>
                    <TableCell className="num text-sm">{p.sessionsPerWeek ?? '—'}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {p.validFrom} → {p.validTo ?? <Badge variant="success">current</Badge>}
                    </TableCell>
                    <TableCell className="text-right">
                      {p.validTo === null && (
                        <Button size="sm" variant="ghost" onClick={() => endRow(p.id)}>End</Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-helper">No clinical placements. Open one when the SpR rotation begins.</p>
          )}
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button size="sm" variant="outline"><Plus className="h-4 w-4 mr-1" /> Open placement</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Open a clinical placement</DialogTitle></DialogHeader>
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label htmlFor="trust">Trust</Label>
                  <Input id="trust" value={trust} onChange={(e) => setTrust(e.target.value)}
                    placeholder="Royal Marsden NHS Foundation Trust" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="spec">Specialty</Label>
                    <Input id="spec" value={specialty} onChange={(e) => setSpecialty(e.target.value)}
                      placeholder="Medical Oncology" />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="grade">Grade</Label>
                    <Input id="grade" value={grade} onChange={(e) => setGrade(e.target.value)}
                      placeholder="ST5" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="vf">Valid from</Label>
                    <Input id="vf" type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="sess">Sessions/week (optional)</Label>
                    <Input id="sess" type="number" min={0} max={10} value={sessions}
                      onChange={(e) => setSessions(e.target.value)} placeholder="4" />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="sup">Clinical supervisor (optional)</Label>
                  <Input id="sup" value={supervisor} onChange={(e) => setSupervisor(e.target.value)}
                    placeholder="Dr M. Consultant" />
                </div>
              </div>
              <DialogFooter>
                <Button disabled={!trust.trim() || !specialty.trim() || !grade.trim() || open.isPending}
                  onClick={submit}>
                  {open.isPending ? 'Opening…' : 'Open placement'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      )}
    </PageSection>
  )
}


// ------------------------------------------------------------------ Gap 3

function IndependentTutorSection({ studentId }: { studentId: string }) {
  const { toast } = useToast()
  const q = useCurrentTutor(studentId)
  const assign = useAssignTutor(studentId)
  const end = useEndTutor(studentId)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [tutorPersonId, setTutorPersonId] = useState('')
  const [tutorDepartmentId, setTutorDepartmentId] = useState('')

  const tutor = q.data?.currentTutor ?? null
  const notes = useTutorNotes(tutor?.id ?? null)
  const addNote = useAddTutorNote(tutor?.id ?? '')
  const [noteText, setNoteText] = useState('')

  const submit = async () => {
    try {
      await assign.mutateAsync({
        tutorPersonId: tutorPersonId.trim(),
        tutorDepartmentId: tutorDepartmentId.trim() || null,
      })
      toast({ title: 'Tutor assigned' })
      setDialogOpen(false); setTutorPersonId(''); setTutorDepartmentId('')
    } catch (e) {
      toast({ title: 'Assignment refused', description: (e as ApiError).message, variant: 'destructive' })
    }
  }

  return (
    <PageSection icon={UserRound} title="Independent tutor (ICR gap 3)" accent="accent"
      description="Outside-the-lab tutor. The platform enforces department independence — a tutor in the student's own department is refused.">
      {q.isLoading ? <Skeleton className="h-16 w-full" /> : (
        <div className="space-y-3">
          {tutor ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="success" className="inline-flex items-center gap-1">
                  <BadgeCheck className="h-3 w-3" /> Assigned
                </Badge>
                <span className="text-sm">Tutor id <span className="font-mono text-xs">{tutor.tutorPersonId.slice(0,8)}…</span></span>
                <span className="text-helper">since {new Date(tutor.assignedAt).toLocaleDateString()}</span>
                <Button size="sm" variant="ghost" className="ml-auto"
                  onClick={async () => {
                    try { await end.mutateAsync(tutor.id); toast({ title: 'Tutor ended' }) }
                    catch (e) { toast({ title: 'Failed to end', description: (e as ApiError).message, variant: 'destructive' }) }
                  }}>
                  End
                </Button>
              </div>
              <div className="pt-3 border-t border-border space-y-2">
                <p className="text-label inline-flex items-center gap-1">
                  <StickyNote className="h-3 w-3" /> Private tutor notes
                </p>
                {notes.isLoading ? <Skeleton className="h-8 w-full" /> : notes.data && notes.data.length > 0 ? (
                  <div className="space-y-2">
                    {notes.data.map((n) => (
                      <div key={n.id} className="p-2 rounded-md bg-surface-2 border border-border">
                        <p className="text-xs text-muted-foreground">
                          {new Date(n.authoredAt).toLocaleString()}
                        </p>
                        <p className="text-sm whitespace-pre-wrap">{n.body}</p>
                      </div>
                    ))}
                  </div>
                ) : <p className="text-helper">No notes yet.</p>}
                <div className="flex items-start gap-2">
                  <Textarea value={noteText} onChange={(e) => setNoteText(e.target.value)}
                    className="min-h-[60px]" placeholder="Add a private tutor note (not visible to the supervisor)…" />
                  <Button size="sm" disabled={!noteText.trim() || addNote.isPending}
                    onClick={async () => {
                      try {
                        await addNote.mutateAsync(noteText.trim())
                        setNoteText(''); toast({ title: 'Note added' })
                      } catch (e) { toast({ title: 'Failed', description: (e as ApiError).message, variant: 'destructive' }) }
                    }}>
                    <Send className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </>
          ) : (
            <p className="text-helper">No independent tutor assigned.</p>
          )}
          {!tutor && (
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button size="sm" variant="outline"><Plus className="h-4 w-4 mr-1" /> Assign tutor</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader><DialogTitle>Assign an independent tutor</DialogTitle></DialogHeader>
                <div className="space-y-3">
                  <p className="text-helper">The platform refuses a tutor from the student&apos;s own department.</p>
                  <div className="space-y-1.5">
                    <Label htmlFor="tpid">Tutor person id</Label>
                    <Input id="tpid" className="font-mono text-xs" value={tutorPersonId}
                      onChange={(e) => setTutorPersonId(e.target.value)} placeholder="uuid" />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="tdid">Tutor department id (optional)</Label>
                    <Input id="tdid" className="font-mono text-xs" value={tutorDepartmentId}
                      onChange={(e) => setTutorDepartmentId(e.target.value)} placeholder="uuid (leave blank if unknown)" />
                  </div>
                </div>
                <DialogFooter>
                  <Button disabled={!tutorPersonId.trim() || assign.isPending} onClick={submit}>
                    {assign.isPending ? 'Assigning…' : 'Assign'}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          )}
        </div>
      )}
    </PageSection>
  )
}


// ------------------------------------------------------------------ Gap 4

function BenchFeesSection({ studentId }: { studentId: string }) {
  const { toast } = useToast()
  const q = useBenchFees(studentId)
  const allocate = useAllocateBenchFee(studentId)
  const [allocOpen, setAllocOpen] = useState(false)
  const [amount, setAmount] = useState('')
  const [validFrom, setValidFrom] = useState(TODAY)
  const [costCentre, setCostCentre] = useState('')

  const submit = async () => {
    try {
      await allocate.mutateAsync({
        totalAmount: amount, currency: 'GBP', validFrom,
        costCentre: costCentre.trim() || undefined,
      })
      toast({ title: 'Bench-fee allocation created' })
      setAllocOpen(false); setAmount(''); setCostCentre('')
    } catch (e) {
      toast({ title: 'Failed', description: (e as ApiError).message, variant: 'destructive' })
    }
  }

  return (
    <PageSection icon={DollarSign} title="Bench fees (ICR gap 4)" accent="primary"
      description="Per-student experimental budget separate from the stipend. Draw-downs are refused if they would exceed the allocation.">
      {q.isLoading ? <Skeleton className="h-16 w-full" /> : (
        <div className="space-y-4">
          {q.data && q.data.allocations.length > 0 ? q.data.allocations.map((a) => (
            <AllocationCard key={a.id} studentId={studentId} alloc={a} />
          )) : (
            <p className="text-helper">No bench-fee allocations yet.</p>
          )}
          <Dialog open={allocOpen} onOpenChange={setAllocOpen}>
            <DialogTrigger asChild>
              <Button size="sm" variant="outline"><Plus className="h-4 w-4 mr-1" /> Allocate bench fee</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Allocate a bench-fee budget</DialogTitle></DialogHeader>
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="amt">Total (GBP)</Label>
                    <Input id="amt" type="number" step="0.01" min={0} value={amount}
                      onChange={(e) => setAmount(e.target.value)} placeholder="10000.00" />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="vf">Valid from</Label>
                    <Input id="vf" type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="cc">Cost centre (optional)</Label>
                  <Input id="cc" value={costCentre} onChange={(e) => setCostCentre(e.target.value)}
                    placeholder="CC-BENCH" />
                </div>
              </div>
              <DialogFooter>
                <Button disabled={!amount || allocate.isPending} onClick={submit}>
                  {allocate.isPending ? 'Allocating…' : 'Allocate'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      )}
    </PageSection>
  )
}

function AllocationCard({ studentId, alloc }: {
  studentId: string
  alloc: { id: string; totalAmount: string; currency: string; drawnAmount: string; remainingAmount: string; validFrom: string; costCentre: string | null }
}) {
  const { toast } = useToast()
  const drawdowns = useDrawdowns(alloc.id)
  const addDrawdown = useAddDrawdown(studentId, alloc.id)
  const [open, setOpen] = useState(false)
  const [amount, setAmount] = useState('')
  const [category, setCategory] = useState('sequencing')
  const [description, setDescription] = useState('')
  const [drawnAt, setDrawnAt] = useState(TODAY)

  const remaining = parseFloat(alloc.remainingAmount || '0')
  const pct = Math.max(0, Math.min(100, 100 * (1 - remaining / parseFloat(alloc.totalAmount || '1'))))

  const submit = async () => {
    try {
      await addDrawdown.mutateAsync({
        amount, category, description: description.trim(), drawnAt,
      })
      toast({ title: 'Draw-down recorded' })
      setOpen(false); setAmount(''); setDescription('')
    } catch (e) {
      toast({ title: 'Draw-down refused', description: (e as ApiError).message, variant: 'destructive' })
    }
  }

  return (
    <div className="card-elevated p-3 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">£{alloc.totalAmount} {alloc.currency}</span>
        {alloc.costCentre && <Badge variant="secondary">{alloc.costCentre}</Badge>}
        <span className="text-helper">valid from {alloc.validFrom}</span>
        <span className="ml-auto text-sm">
          <span className="text-muted-foreground">drawn</span> £{alloc.drawnAmount} ·{' '}
          <span className="text-muted-foreground">remaining</span> <b>£{alloc.remainingAmount}</b>
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-surface-2 overflow-hidden">
        <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
      </div>
      {drawdowns.data && drawdowns.data.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Date</TableHead>
              <TableHead>Category</TableHead>
              <TableHead>Description</TableHead>
              <TableHead className="text-right">Amount</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {drawdowns.data.map((d) => (
              <TableRow key={d.id}>
                <TableCell className="num text-xs">{d.drawnAt}</TableCell>
                <TableCell><Badge variant="secondary">{d.category}</Badge></TableCell>
                <TableCell className="text-sm">{d.description}</TableCell>
                <TableCell className="text-right num">£{d.amount}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger asChild>
          <Button size="sm" variant="outline"><Plus className="h-4 w-4 mr-1" /> Record draw-down</Button>
        </DialogTrigger>
        <DialogContent>
          <DialogHeader><DialogTitle>Record a bench-fee draw-down</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="amt2">Amount (GBP)</Label>
                <Input id="amt2" type="number" step="0.01" min={0} value={amount}
                  onChange={(e) => setAmount(e.target.value)} placeholder="4000.00" />
              </div>
              <div className="space-y-1.5">
                <Label>Category</Label>
                <Select value={category} onValueChange={setCategory}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {['sequencing','mass_spec','reagents','consumables','equipment','other'].map((c) =>
                      <SelectItem key={c} value={c}>{c}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="desc">Description</Label>
              <Input id="desc" value={description} onChange={(e) => setDescription(e.target.value)}
                placeholder="10x Genomics run — 2 samples" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="dat">Drawn at</Label>
              <Input id="dat" type="date" value={drawnAt} onChange={(e) => setDrawnAt(e.target.value)} />
            </div>
            <p className="text-helper">Remaining: <b>£{alloc.remainingAmount}</b>. A draw-down that would exceed this is refused.</p>
          </div>
          <DialogFooter>
            <Button disabled={!amount || !description.trim() || addDrawdown.isPending} onClick={submit}>
              {addDrawdown.isPending ? 'Recording…' : 'Record'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}


// ------------------------------------------------------------------ Gap 5

const KIND_ALLOWED = ['honorary_contract', 'co_registration', 'clinical_placement', 'other']

function AffiliationsSection({ studentId }: { studentId: string }) {
  const { toast } = useToast()
  const q = useAffiliations(studentId)
  const add = useAddAffiliation(studentId)
  const end = useEndAffiliation(studentId)
  const [open, setOpen] = useState(false)
  const [partner, setPartner] = useState('')
  const [kind, setKind] = useState('honorary_contract')
  const [validFrom, setValidFrom] = useState(TODAY)
  const [partnerRef, setPartnerRef] = useState('')
  const [passportExp, setPassportExp] = useState('')
  const [dbsRenewal, setDbsRenewal] = useState('')

  const submit = async () => {
    const compliance: Record<string, string> = {}
    if (passportExp) compliance.nhsResearchPassportExpiresOn = passportExp
    if (dbsRenewal)  compliance.dbsRenewalOn = dbsRenewal
    try {
      await add.mutateAsync({
        partnerName: partner.trim(), affiliationKind: kind, validFrom,
        partnerRef: partnerRef.trim() || undefined,
        compliance: Object.keys(compliance).length > 0 ? compliance : undefined,
      })
      toast({ title: 'Affiliation added' })
      setOpen(false); setPartner(''); setKind('honorary_contract'); setPartnerRef(''); setPassportExp(''); setDbsRenewal('')
    } catch (e) {
      toast({ title: 'Failed', description: (e as ApiError).message, variant: 'destructive' })
    }
  }

  return (
    <PageSection icon={ShieldCheck} title="Partner affiliations (ICR gap 5)" accent="accent"
      description="Royal Marsden honorary contracts, Imperial co-registration, and clinical-placement paperwork with expiry-flag tracking.">
      {q.isLoading ? <Skeleton className="h-16 w-full" /> : (
        <div className="space-y-3">
          {q.data && q.data.affiliations.length > 0 ? (
            <div className="space-y-2">
              {q.data.affiliations.map((a) => (
                <div key={a.id} className="card-elevated p-3 space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={a.active ? 'success' : 'secondary'}>{a.affiliationKind.replace(/_/g,' ')}</Badge>
                    <span className="font-medium">{a.partnerName}</span>
                    {a.partnerRef && <span className="text-helper">{a.partnerRef}</span>}
                    <span className="text-helper ml-auto">{a.validFrom} → {a.validTo ?? '—'}</span>
                    {a.active && (
                      <Button size="sm" variant="ghost"
                        onClick={async () => {
                          try { await end.mutateAsync({ id: a.id, validTo: TODAY }); toast({ title: 'Ended' }) }
                          catch (e) { toast({ title: 'Failed', description: (e as ApiError).message, variant: 'destructive' }) }
                        }}>End</Button>
                    )}
                  </div>
                  {a.complianceFlags.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {a.complianceFlags.map((f) => (
                        <ComplianceBadge key={f.key} k={f.key} status={f.status} date={f.date}
                          daysUntil={f.daysUntil} daysOverdue={f.daysOverdue} />
                      ))}
                    </div>
                  )}
                  {a.compliance && Object.entries(a.compliance)
                    .filter(([k]) => !k.endsWith('ExpiresOn') && !k.endsWith('RenewalOn')).length > 0 && (
                    <div className="text-xs text-muted-foreground">
                      {Object.entries(a.compliance)
                        .filter(([k]) => !k.endsWith('ExpiresOn') && !k.endsWith('RenewalOn'))
                        .map(([k, v]) => <span key={k} className="mr-3">{k}: <span className="font-mono">{v}</span></span>)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-helper">No partner affiliations recorded.</p>
          )}
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button size="sm" variant="outline"><Plus className="h-4 w-4 mr-1" /> Add affiliation</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Add a partner affiliation</DialogTitle></DialogHeader>
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="pn">Partner</Label>
                    <Input id="pn" value={partner} onChange={(e) => setPartner(e.target.value)}
                      placeholder="Royal Marsden NHS Foundation Trust" />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Kind</Label>
                    <Select value={kind} onValueChange={setKind}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {KIND_ALLOWED.map((k) => <SelectItem key={k} value={k}>{k.replace(/_/g,' ')}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="pvf">Valid from</Label>
                    <Input id="pvf" type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="pref">Partner reference (optional)</Label>
                    <Input id="pref" value={partnerRef} onChange={(e) => setPartnerRef(e.target.value)}
                      placeholder="HON-2026-9911" />
                  </div>
                </div>
                <p className="text-label pt-2">Compliance (optional — flagged as expiring / expired)</p>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="pex">NHS Research Passport expires on</Label>
                    <Input id="pex" type="date" value={passportExp} onChange={(e) => setPassportExp(e.target.value)} />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="dbs">DBS renewal on</Label>
                    <Input id="dbs" type="date" value={dbsRenewal} onChange={(e) => setDbsRenewal(e.target.value)} />
                  </div>
                </div>
              </div>
              <DialogFooter>
                <Button disabled={!partner.trim() || add.isPending} onClick={submit}>
                  {add.isPending ? 'Adding…' : 'Add affiliation'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      )}
    </PageSection>
  )
}

function ComplianceBadge({ k, status, date, daysUntil, daysOverdue }: {
  k: string; status: ComplianceStatus; date: string
  daysUntil?: number; daysOverdue?: number
}) {
  const Icon = status === 'expired' ? ShieldOff : status === 'expiring' ? ShieldAlert : ShieldCheck
  const variant = status === 'expired' ? 'destructive' : status === 'expiring' ? 'warning' : 'success'
  const suffix = status === 'expired' ? ` — ${daysOverdue}d overdue`
              : status === 'expiring' ? ` — ${daysUntil}d`
              : ''
  return (
    <Badge variant={variant as 'destructive'|'warning'|'success'} className="inline-flex items-center gap-1">
      <Icon className="h-3 w-3" /> {k} · {date}{suffix}
    </Badge>
  )
}


// ------------------------------------------------------------------ panel

export function IcrStudentPanel({ studentId }: { studentId: string }) {
  return (
    <>
      <ClinicalPlacementSection studentId={studentId} />
      <IndependentTutorSection studentId={studentId} />
      <BenchFeesSection studentId={studentId} />
      <AffiliationsSection studentId={studentId} />
    </>
  )
}
