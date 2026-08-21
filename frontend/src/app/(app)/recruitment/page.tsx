'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Megaphone, Plus } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
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
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [stipend, setStipend] = useState('')
  const [eligibility, setEligibility] = useState('')

  const submit = async () => {
    try {
      await create.mutateAsync({
        title,
        stipendAmount: stipend ? Number(stipend) : undefined,
        currency: stipend ? 'GBP' : undefined,
        eligibility: eligibility || undefined,
      })
      toast({ title: 'Opportunity created' })
      setOpen(false); setTitle(''); setStipend(''); setEligibility('')
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
              <TableHead>Positions</TableHead><TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow><TableCell colSpan={4}><Skeleton className="h-5 w-full" /></TableCell></TableRow>
            )}
            {data?.data.map((o) => (
              <TableRow key={o.id}>
                <TableCell className="font-medium">{o.title}</TableCell>
                <TableCell className="num text-muted-foreground">
                  {o.stipendAmount ? `${o.currency ?? ''} ${Number(o.stipendAmount).toLocaleString()}` : '—'}
                </TableCell>
                <TableCell className="num">{o.positionsAvailable}</TableCell>
                <TableCell><OpportunityStatusControl id={o.id} status={o.status} /></TableCell>
              </TableRow>
            ))}
            {data && data.data.length === 0 && (
              <TableRow><TableCell colSpan={4} className="text-muted-foreground text-center py-8">No opportunities yet.</TableCell></TableRow>
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
