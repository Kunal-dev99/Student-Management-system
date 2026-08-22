'use client'

import { useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, GitBranch, Megaphone, Plus } from 'lucide-react'
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
import {
  useApplications, useCreateOpportunity, useOpportunities, usePipeline,
  useTransitionOpportunity, type OpportunityStatus,
} from '@/features/recruitment/api'
import { OpportunityPill, StagePill } from '@/features/recruitment/StatusPills'
import { useAwards, useDemands, usePositionLineage } from '@/features/research/api'

// Allowed opportunity transitions (mirrors the backend FSM, arch §8.4).
const OPP_NEXT: Record<OpportunityStatus, OpportunityStatus[]> = {
  draft: ['approved', 'closed'],
  approved: ['open', 'closed'],
  open: ['recruiting', 'closed'],
  recruiting: ['filled', 'closed'],
  filled: ['closed'],
  closed: [],
}

function OpportunityStatusControl({ id, status }: { id: string; status: OpportunityStatus }) {
  const { toast } = useToast()
  const transition = useTransitionOpportunity()
  const next = OPP_NEXT[status]
  return (
    <div className="flex items-center gap-2">
      <OpportunityPill status={status} />
      {next.length > 0 && (
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

function OpportunitiesTab() {
  const { data, isLoading } = useOpportunities()
  return (
    <div className="space-y-3">
      <div className="flex justify-end"><NewOpportunityDialog /></div>
      <div className="card-elevated overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead><TableHead>Stipend</TableHead>
              <TableHead>Places</TableHead><TableHead>Status</TableHead>
              <TableHead className="text-right">Provenance</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow><TableCell colSpan={5}><Skeleton className="h-5 w-full" /></TableCell></TableRow>
            )}
            {data?.data.map((o) => (
              <TableRow key={o.id}>
                <TableCell className="font-medium">{o.title}</TableCell>
                <TableCell className="num text-muted-foreground">
                  {o.stipendAmount ? `${o.currency ?? ''} ${Number(o.stipendAmount).toLocaleString()}` : '—'}
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <span className="num">{o.positionsFilled ?? 0} / {o.positionsAvailable}</span>
                    {(o.positionsFilled ?? 0) >= o.positionsAvailable && <Badge variant="warning">full</Badge>}
                  </div>
                </TableCell>
                <TableCell><OpportunityStatusControl id={o.id} status={o.status} /></TableCell>
                <TableCell className="text-right">
                  <LineageDialog opportunityId={o.id} title={o.title} />
                </TableCell>
              </TableRow>
            ))}
            {data && data.data.length === 0 && (
              <TableRow><TableCell colSpan={5} className="text-muted-foreground text-center py-8">No opportunities yet.</TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

function ApplicationsTab() {
  const pipeline = usePipeline()
  const { data, isLoading } = useApplications()
  const counts = pipeline.data?.counts ?? {}

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
            {data?.data.map((a) => (
              <TableRow key={a.id}>
                <TableCell className="font-medium">
                  <Link href={`/recruitment/applications/${a.id}`} className="hover:text-primary">
                    {a.id.slice(0, 8)}…
                  </Link>
                </TableCell>
                <TableCell className="text-muted-foreground">{a.route.replace(/_/g, ' ')}</TableCell>
                <TableCell><StagePill stage={a.currentStage} /></TableCell>
                <TableCell className="text-muted-foreground num">{a.submittedAt?.slice(0, 10) ?? '—'}</TableCell>
              </TableRow>
            ))}
            {data && data.data.length === 0 && (
              <TableRow><TableCell colSpan={4} className="text-muted-foreground text-center py-8">No applications yet.</TableCell></TableRow>
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
      <PageHeader title="Recruitment" description="Opportunities and the application pipeline." />
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
