'use client'

import { useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, Check, GitBranch, Megaphone, Pencil, Plus, X } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { Can, useCan } from '@/shared/auth/Can'
import {
  useApplications, useCreateApplication, useCreateOpportunity, useCreatePersonQuick,
  useOpportunities, usePipeline, useUpdateOpportunity,
  useTransitionOpportunity, type OpportunityStatus,
} from '@/features/recruitment/api'
import { OpportunityPill, StagePill } from '@/features/recruitment/StatusPills'
import { useAwards, useDemands, usePositionLineage } from '@/features/research/api'
import { ApiError } from '@/shared/api/client'
import { usePersons } from '@/features/persons/api'

// Allowed opportunity transitions (mirrors the backend FSM, arch §8.4).
// W1.3 — 'paused' is bidirectional with open, and also reachable from recruiting.
const OPP_NEXT: Record<OpportunityStatus, OpportunityStatus[]> = {
  draft: ['approved', 'closed'],
  approved: ['open', 'closed'],
  open: ['recruiting', 'paused', 'closed'],
  recruiting: ['filled', 'paused', 'closed'],
  paused: ['open', 'closed'],
  filled: ['closed'],
  closed: [],
}

function OpportunityStatusControl({ id, status }: { id: string; status: OpportunityStatus }) {
  const { toast } = useToast()
  const transition = useTransitionOpportunity()
  // Opportunity transitions are recruitment.write server-side.
  const canWrite = useCan('recruitment.write')
  const next = OPP_NEXT[status]
  return (
    <div className="flex items-center gap-2">
      <OpportunityPill status={status} />
      {canWrite && next.length > 0 && (
        <Select
          value=""
          onValueChange={async (v) => {
            try { await transition.mutateAsync({ id, toStatus: v as OpportunityStatus }); toast({ title: `Moved to ${v}` }) }
            catch (e) { toast({ title: 'Transition failed', description: (e as Error).message, variant: 'destructive' }) }
          }}
        >
          <SelectTrigger className="w-32 h-7"><SelectValue placeholder="Move to…" /></SelectTrigger>
          <SelectContent>{next.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
        </Select>
      )}
    </div>
  )
}

const STAGE_ORDER = [
  'applicant', 'under_assessment', 'shortlisted', 'interview', 'selected',
  'offer_made', 'offer_accepted', 'converted', 'rejected', 'withdrawn',
]

function NewOpportunityDialog() {
  const { toast } = useToast()
  const create = useCreateOpportunity()
  const demands = useDemands()
  const awards = useAwards()
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [stipend, setStipend] = useState('')
  const [eligibility, setEligibility] = useState('')
  const [demandId, setDemandId] = useState('')
  const [awardId, setAwardId] = useState('')

  const submit = async () => {
    try {
      await create.mutateAsync({
        title,
        stipendAmount: stipend ? Number(stipend) : undefined,
        currency: stipend ? 'GBP' : undefined,
        eligibility: eligibility || undefined,
        researchDemandId: demandId || undefined,
        researchAwardId: awardId || undefined,
      })
      toast({ title: 'Opportunity created' })
      setOpen(false); setTitle(''); setStipend(''); setEligibility(''); setDemandId(''); setAwardId('')
    } catch (e) {
      toast({ title: 'Could not create', description: (e as Error).message, variant: 'destructive' })
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm"><Plus className="h-4 w-4 mr-1" /> New opportunity</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>New research opportunity</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="t">Title</Label>
            <Input id="t" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="PhD in …" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="s">Stipend (GBP, optional)</Label>
            <Input id="s" type="number" value={stipend} onChange={(e) => setStipend(e.target.value)} placeholder="19000" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="e">Eligibility (optional)</Label>
            <Input id="e" value={eligibility} onChange={(e) => setEligibility(e.target.value)} placeholder="2:1 or higher…" />
          </div>
          {/* Provenance (Phase 6.1) — link the position back to the need and the money. */}
          <div className="space-y-1.5">
            <Label>Research demand (optional)</Label>
            <Select value={demandId} onValueChange={setDemandId}>
              <SelectTrigger><SelectValue placeholder="Not linked to a demand" /></SelectTrigger>
              <SelectContent>
                {demands.data?.map((d) => (
                  <SelectItem key={d.id} value={d.id}>{d.title} ({d.status})</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Research award (optional)</Label>
            <Select value={awardId} onValueChange={setAwardId}>
              <SelectTrigger><SelectValue placeholder="Not linked to an award" /></SelectTrigger>
              <SelectContent>
                {awards.data?.map((a) => (
                  <SelectItem key={a.id} value={a.id}>{a.awardRef} — {a.title}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button onClick={submit} disabled={!title || create.isPending}>
            {create.isPending ? 'Creating…' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** One hop in the provenance chain. A missing hop is shown, not hidden. */
function LineageHop({ label, value, detail }: { label: string; value: string | null; detail?: string }) {
  return (
    <div className="flex items-baseline gap-3 py-1.5 border-b border-border last:border-0">
      <span className="text-label w-28 shrink-0">{label}</span>
      {value ? (
        <span className="text-sm">
          {value}
          {detail && <span className="text-muted-foreground"> — {detail}</span>}
        </span>
      ) : (
        <span className="text-sm text-muted-foreground italic">not linked</span>
      )}
    </div>
  )
}

function LineageDialog({ opportunityId, title }: { opportunityId: string; title: string }) {
  const [open, setOpen] = useState(false)
  // Only fetch while the dialog is open; the query is disabled otherwise.
  const lineage = usePositionLineage(open ? opportunityId : null)
  const l = lineage.data

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="ghost"><GitBranch className="h-4 w-4 mr-1" /> Lineage</Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader><DialogTitle>Provenance — {title}</DialogTitle></DialogHeader>
        {lineage.isLoading && <Skeleton className="h-40 w-full" />}
        {lineage.isError && (
          <p className="text-sm text-destructive">{(lineage.error as Error).message}</p>
        )}
        {l && (
          <div className="space-y-4">
            <div>
              <LineageHop label="Award" value={l.award ? l.award.awardRef : null} detail={l.award?.title} />
              <LineageHop label="Funder" value={l.funder?.name ?? null} />
              <LineageHop label="Demand" value={l.demand?.title ?? null}
                detail={l.demand ? `${l.demand.requestedPlaces} place(s), ${l.demand.status}` : undefined} />
              <LineageHop label="Position" value={l.position.title}
                detail={`${l.position.positionsFilled}/${l.position.positionsAvailable} filled, ${l.position.positionsRemaining} remaining`} />
            </div>

            <div>
              <p className="text-label mb-1.5">
                Students produced <span className="num">({l.studentsProduced})</span>
              </p>
              {l.applications.length === 0 ? (
                <p className="text-helper">No applications have been made against this position.</p>
              ) : (
                <ul className="space-y-1">
                  {l.applications.map((a) => (
                    <li key={a.applicationId} className="text-sm flex items-center gap-2">
                      <Badge variant="secondary">{a.stage.replace(/_/g, ' ')}</Badge>
                      {a.student ? (
                        <Link
                          href={a.student.link}
                          // Close first: a mounted Radix dialog would otherwise sit over the new page.
                          onClick={() => setOpen(false)}
                          className="font-medium text-primary hover:underline"
                        >
                          {a.student.personName}
                          <span className="font-mono text-xs text-muted-foreground"> {a.student.studentRef}</span>
                        </Link>
                      ) : (
                        <span className="text-muted-foreground">
                          application {a.applicationId.slice(0, 8)}… — no student record yet
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {l.gaps.length > 0 && (
              <div className="rounded-md border border-[hsl(var(--warning)/0.3)] bg-[hsl(var(--warning)/0.1)] p-3 space-y-1">
                {l.gaps.map((g) => (
                  <p key={g} className="text-sm text-[hsl(var(--warning))] flex items-start gap-2">
                    <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" /> {g}
                  </p>
                ))}
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

/** Inline "positions_available" editor on the Places cell. Click the pencil,
 *  type the new cap, save. Read-only for anyone without recruitment.write. */
function CapacityCell({ id, filled, available }: { id: string; filled: number; available: number }) {
  const { toast } = useToast()
  const canWrite = useCan('recruitment.write')
  const update = useUpdateOpportunity()
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(String(available))
  const over = filled >= available

  const save = async () => {
    const n = parseInt(val, 10)
    if (!Number.isFinite(n) || n < 1) {
      toast({ title: 'Enter a positive number', variant: 'destructive' }); return
    }
    try {
      await update.mutateAsync({ id, body: { positionsAvailable: n } })
      toast({ title: `Capacity updated to ${n}` })
      setEditing(false)
    } catch (e) {
      toast({ title: 'Update failed', description: (e as Error).message, variant: 'destructive' })
    }
  }

  if (editing) {
    return (
      <div className="flex items-center gap-1">
        <span className="num text-muted-foreground">{filled} /</span>
        <Input value={val} onChange={(e) => setVal(e.target.value)} className="h-7 w-16 num" />
        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={save} disabled={update.isPending}>
          <Check className="h-3.5 w-3.5 text-success" />
        </Button>
        <Button size="sm" variant="ghost" className="h-7 w-7 p-0"
                onClick={() => { setEditing(false); setVal(String(available)) }}>
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>
    )
  }
  return (
    <div className="flex items-center gap-2">
      <span className="num">{filled} / {available}</span>
      {over && <Badge variant="warning">full</Badge>}
      {canWrite && (
        <Button size="sm" variant="ghost" className="h-6 w-6 p-0" title="Edit capacity"
                onClick={() => { setVal(String(available)); setEditing(true) }}>
          <Pencil className="h-3 w-3 text-muted-foreground" />
        </Button>
      )}
    </div>
  )
}

function OpportunitiesTab() {
  const { data, isLoading } = useOpportunities()
  // W1.8 — opportunity_type filter chip
  const [typeFilter, setTypeFilter] = useState<'all' | 'funded' | 'partially_funded' | 'unfunded'>('all')
  const filtered = (data?.data ?? []).filter(
    (o) => typeFilter === 'all' || o.opportunityType === typeFilter,
  )
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-label mr-1">Funding:</span>
        {(['all', 'funded', 'partially_funded', 'unfunded'] as const).map((f) => (
          <button
            key={f}
            onClick={() => setTypeFilter(f)}
            className={`px-2.5 py-1 rounded-full text-xs border transition ${
              typeFilter === f
                ? 'bg-primary text-primary-foreground border-primary'
                : 'bg-transparent text-muted-foreground border-border hover:text-foreground'
            }`}
          >
            {f === 'all' ? 'All' : f.replace(/_/g, ' ')}
          </button>
        ))}
        <span className="text-helper ml-2">Showing {filtered.length} of {data?.data.length ?? 0}</span>
        <div className="ml-auto"><Can perm="recruitment.write"><NewOpportunityDialog /></Can></div>
      </div>
      <div className="card-elevated overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Funding</TableHead>
              <TableHead>Stipend</TableHead>
              <TableHead>Places</TableHead><TableHead>Status</TableHead>
              <TableHead className="text-right">Provenance</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow><TableCell colSpan={6}><Skeleton className="h-5 w-full" /></TableCell></TableRow>
            )}
            {filtered.map((o) => (
              <TableRow key={o.id}>
                <TableCell className="font-medium">{o.title}</TableCell>
                <TableCell>
                  <Badge variant={o.opportunityType === 'funded' ? 'success'
                                : o.opportunityType === 'partially_funded' ? 'warning' : 'secondary'}>
                    {o.opportunityType.replace(/_/g, ' ')}
                  </Badge>
                </TableCell>
                <TableCell className="num text-muted-foreground">
                  {o.stipendAmount ? `${o.currency ?? ''} ${Number(o.stipendAmount).toLocaleString()}` : '—'}
                </TableCell>
                <TableCell>
                  <CapacityCell
                    id={o.id}
                    filled={o.positionsFilled ?? 0}
                    available={o.positionsAvailable}
                  />
                </TableCell>
                <TableCell><OpportunityStatusControl id={o.id} status={o.status} /></TableCell>
                <TableCell className="text-right">
                  <LineageDialog opportunityId={o.id} title={o.title} />
                </TableCell>
              </TableRow>
            ))}
            {data && filtered.length === 0 && (
              <TableRow><TableCell colSpan={6} className="text-muted-foreground text-center py-8">
                {data.data.length === 0 ? 'No opportunities yet.' : 'No opportunities match this funding filter.'}
              </TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

/** New Application dialog — Route A (opportunity-led) or Route B (student-led).
 *  Handles the person side too: pick an existing Person, or create a new one
 *  inline. Backend requires an existing person_id, so a new person is created
 *  first and the application POST follows. */
function NewApplicationDialog() {
  const { toast } = useToast()
  const [open, setOpen] = useState(false)
  const [route, setRoute] = useState<'opportunity_led' | 'student_led'>('opportunity_led')
  const [personMode, setPersonMode] = useState<'existing' | 'new'>('new')
  const [personId, setPersonId] = useState('')
  const [personSearch, setPersonSearch] = useState('')
  const [givenName, setGivenName] = useState('')
  const [familyName, setFamilyName] = useState('')
  const [email, setEmail] = useState('')
  const [opportunityId, setOpportunityId] = useState('')
  const [proposalRef, setProposalRef] = useState('')

  const opps = useOpportunities()
  const persons = usePersons(personSearch, { enabled: personMode === 'existing' })
  const createPerson = useCreatePersonQuick()
  const createApp = useCreateApplication()

  const reset = () => {
    setRoute('opportunity_led')
    setPersonMode('new')
    setPersonId(''); setPersonSearch('')
    setGivenName(''); setFamilyName(''); setEmail('')
    setOpportunityId(''); setProposalRef('')
  }

  const ACCEPTS_APPLICATIONS = new Set(['open', 'recruiting', 'approved'])
  const allOpps = opps.data?.data ?? []
  // Show every opportunity so a newly-created one is visible, but only the ones whose
  // status accepts applications are selectable. The rest render as disabled rows with
  // their current status so the user understands what to do next (e.g. approve a draft).
  const sortedOpps = [...allOpps].sort((a, b) => {
    const ai = ACCEPTS_APPLICATIONS.has(a.status) ? 0 : 1
    const bi = ACCEPTS_APPLICATIONS.has(b.status) ? 0 : 1
    return ai - bi || a.title.localeCompare(b.title)
  })
  const hiddenBecauseStatus = allOpps.filter((o) => !ACCEPTS_APPLICATIONS.has(o.status))

  const personValid = personMode === 'existing'
    ? !!personId
    : !!givenName.trim() && !!familyName.trim()
  const routeValid = route === 'opportunity_led' ? !!opportunityId : true
  const canSubmit = personValid && routeValid && !createPerson.isPending && !createApp.isPending

  const submit = async () => {
    try {
      let pid = personId
      if (personMode === 'new') {
        const p = await createPerson.mutateAsync({
          givenName: givenName.trim(),
          familyName: familyName.trim(),
          email: email.trim() || null,
        })
        pid = p.id
      }
      const app = await createApp.mutateAsync({
        personId: pid,
        route,
        researchOpportunityId: route === 'opportunity_led' ? opportunityId : null,
        proposalDocumentRef: route === 'student_led' ? (proposalRef.trim() || null) : null,
      })
      toast({ title: 'Application created', description: `${route.replace('_', ' ')} · id ${app.id.slice(0, 8)}…` })
      setOpen(false)
      reset()
    } catch (e) {
      toast({ title: 'Could not create application', description: (e as ApiError).message, variant: 'destructive' })
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) reset() }}>
      <DialogTrigger asChild>
        <Button size="sm"><Plus className="h-4 w-4 mr-1" /> New application</Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>New application</DialogTitle></DialogHeader>
        <div className="space-y-4">
          {/* Route selector */}
          <div className="space-y-1.5">
            <Label>Route</Label>
            <Select value={route} onValueChange={(v) => setRoute(v as typeof route)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="opportunity_led">Route A · opportunity-led (advertised position)</SelectItem>
                <SelectItem value="student_led">Route B · student-led (unsolicited proposal)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Person: existing or new */}
          <div className="space-y-1.5">
            <Label>Applicant</Label>
            <div className="flex gap-1.5 mb-1">
              <button type="button"
                onClick={() => setPersonMode('new')}
                className={`px-2.5 py-1 rounded-full text-xs border transition ${
                  personMode === 'new' ? 'bg-primary text-primary-foreground border-primary'
                  : 'text-muted-foreground border-border hover:text-foreground'}`}>
                New person
              </button>
              <button type="button"
                onClick={() => setPersonMode('existing')}
                className={`px-2.5 py-1 rounded-full text-xs border transition ${
                  personMode === 'existing' ? 'bg-primary text-primary-foreground border-primary'
                  : 'text-muted-foreground border-border hover:text-foreground'}`}>
                Existing person
              </button>
            </div>
            {personMode === 'new' ? (
              <div className="grid grid-cols-2 gap-2">
                <Input placeholder="Given name *" value={givenName} onChange={(e) => setGivenName(e.target.value)} />
                <Input placeholder="Family name *" value={familyName} onChange={(e) => setFamilyName(e.target.value)} />
                <Input className="col-span-2" placeholder="Email (optional)" type="email"
                       value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
            ) : (
              <div className="space-y-1.5">
                <Input placeholder="Search by name…" value={personSearch}
                       onChange={(e) => setPersonSearch(e.target.value)} />
                <Select value={personId} onValueChange={setPersonId}>
                  <SelectTrigger><SelectValue placeholder="Pick a person" /></SelectTrigger>
                  <SelectContent>
                    {persons.data?.data?.map((p) => (
                      <SelectItem key={p.id} value={p.id}>
                        {p.givenName} {p.familyName}
                        {p.email ? ` (${p.email})` : ''}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          {/* Route-specific fields */}
          {route === 'opportunity_led' ? (
            <div className="space-y-1.5">
              <Label>Research opportunity *</Label>
              <Select value={opportunityId} onValueChange={setOpportunityId}>
                <SelectTrigger><SelectValue placeholder="Pick an opportunity" /></SelectTrigger>
                <SelectContent>
                  {sortedOpps.length === 0 ? (
                    <SelectItem value="_none" disabled>No opportunities yet</SelectItem>
                  ) : sortedOpps.map((o) => {
                    const takesApps = ACCEPTS_APPLICATIONS.has(o.status)
                    return (
                      <SelectItem key={o.id} value={o.id} disabled={!takesApps}>
                        <span className="flex items-center gap-2">
                          <span>{o.title}</span>
                          <span className={`text-[10px] uppercase tracking-wider rounded-sm px-1.5 py-0.5 border ${
                            takesApps
                              ? 'border-[hsl(var(--success)/0.3)] bg-[hsl(var(--success)/0.1)] text-[hsl(var(--success))]'
                              : 'border-border bg-surface-2 text-muted-foreground'
                          }`}>{o.status}</span>
                        </span>
                      </SelectItem>
                    )
                  })}
                </SelectContent>
              </Select>
              {hiddenBecauseStatus.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  {hiddenBecauseStatus.length} opportunit{hiddenBecauseStatus.length === 1 ? 'y is' : 'ies are'} listed
                  but not selectable — only <span className="font-mono">approved</span>, <span className="font-mono">open</span>{' '}
                  or <span className="font-mono">recruiting</span> statuses accept applications.
                  Approve a draft from the Opportunities tab first.
                </p>
              )}
              {sortedOpps.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  No opportunities yet. Create one on the Opportunities tab first.
                </p>
              )}
            </div>
          ) : (
            <div className="space-y-1.5">
              <Label>Proposal document reference</Label>
              <Input placeholder="e.g. proposal-2026-aisha-rahman.pdf" value={proposalRef}
                     onChange={(e) => setProposalRef(e.target.value)} />
              <p className="text-xs text-muted-foreground">
                Optional but recommended — the reference to the applicant&apos;s uploaded proposal.
              </p>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
          <Button onClick={submit} disabled={!canSubmit}>
            {(createPerson.isPending || createApp.isPending) ? 'Creating…' : 'Create application'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ApplicationsTab() {
  const pipeline = usePipeline()
  const { data, isLoading } = useApplications()
  const counts = pipeline.data?.counts ?? {}
  // F3 — route filter chip. Server does not filter by route yet; client-side is enough at
  // this scale (a few hundred applications per year).
  const [routeFilter, setRouteFilter] = useState<'all' | 'opportunity_led' | 'student_led'>('all')
  const filteredRows = (data?.data ?? []).filter(
    (a) => routeFilter === 'all' || a.route === routeFilter,
  )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {STAGE_ORDER.filter((s) => counts[s]).map((s) => (
          <div key={s} className="card-elevated px-3 py-2">
            <div className="text-label">{s.replace(/_/g, ' ')}</div>
            <div className="text-lg font-semibold num">{counts[s]}</div>
          </div>
        ))}
        {pipeline.data && pipeline.data.total === 0 && (
          <p className="text-helper">No applications in the pipeline yet.</p>
        )}
      </div>

      <div className="flex items-center justify-end">
        <Can perm="recruitment.write"><NewApplicationDialog /></Can>
      </div>

      <div className="flex flex-wrap gap-1.5 items-center">
        <span className="text-label mr-1">Route:</span>
        {(['all', 'opportunity_led', 'student_led'] as const).map((r) => (
          <button
            key={r}
            onClick={() => setRouteFilter(r)}
            className={`px-2.5 py-1 rounded-full text-xs border transition ${
              routeFilter === r
                ? 'bg-primary text-primary-foreground border-primary'
                : 'bg-transparent text-muted-foreground border-border hover:text-foreground'
            }`}
          >
            {r === 'all' ? 'All' : r === 'opportunity_led' ? 'Route A · opportunity' : 'Route B · student proposal'}
          </button>
        ))}
        <span className="text-helper ml-2">
          Showing {filteredRows.length} of {data?.data.length ?? 0}
        </span>
      </div>

      <div className="card-elevated overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Application</TableHead><TableHead>Route</TableHead>
              <TableHead>Stage</TableHead><TableHead>Submitted</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow><TableCell colSpan={4}><Skeleton className="h-5 w-full" /></TableCell></TableRow>
            )}
            {filteredRows.map((a) => (
              <TableRow key={a.id}>
                <TableCell className="font-medium">
                  <Link href={`/recruitment/applications/${a.id}`} className="hover:text-primary">
                    {a.personName ?? `${a.id.slice(0, 8)}…`}
                  </Link>
                </TableCell>
                <TableCell>
                  <Badge variant={a.route === 'opportunity_led' ? 'secondary' : 'warning'}>
                    {a.route === 'opportunity_led' ? 'Route A' : 'Route B'}
                  </Badge>
                </TableCell>
                <TableCell><StagePill stage={a.currentStage} /></TableCell>
                <TableCell className="text-muted-foreground num">{a.submittedAt?.slice(0, 10) ?? '—'}</TableCell>
              </TableRow>
            ))}
            {data && filteredRows.length === 0 && (
              <TableRow><TableCell colSpan={4} className="text-muted-foreground text-center py-8">
                No applications match this route filter.
              </TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

export default function RecruitmentPage() {
  return (
    <>
      <PageHeader title="Recruitment" />
      <div className="px-6 pb-6">
        <Tabs defaultValue="opportunities">
          <TabsList>
            <TabsTrigger value="opportunities"><Megaphone className="h-4 w-4 mr-1.5" /> Opportunities</TabsTrigger>
            <TabsTrigger value="applications">Applications</TabsTrigger>
          </TabsList>
          <TabsContent value="opportunities" className="mt-4"><OpportunitiesTab /></TabsContent>
          <TabsContent value="applications" className="mt-4"><ApplicationsTab /></TabsContent>
        </Tabs>
      </div>
    </>
  )
}
