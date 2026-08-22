'use client'

import { useState } from 'react'
import { FlaskConical, Network, Plus, Trophy, UserSearch } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { ApiError } from '@/shared/api/client'
import { useFundingSources } from '@/features/funding/api'
import {
  DEMAND_NEXT, useAwards, useCreateAward, useCreateDemand, useDemands, useTransitionDemand,
  type DemandStatus,
} from '@/features/research/api'
import { SupervisorMatchPanel } from '@/features/research/SupervisorMatchPanel'
import { RelationshipGraph } from '@/features/research/RelationshipGraph'

const DEMAND_VARIANT: Record<DemandStatus, 'secondary' | 'info' | 'warning' | 'success' | 'destructive'> = {
  identified: 'secondary',
  approved: 'info',
  positioned: 'warning',
  filled: 'success',
  withdrawn: 'destructive',
}

function DemandStatusControl({ id, status }: { id: string; status: DemandStatus }) {
  const { toast } = useToast()
  const transition = useTransitionDemand()
  const next = DEMAND_NEXT[status]
  return (
    <div className="flex items-center gap-2">
      <Badge variant={DEMAND_VARIANT[status]}>{status}</Badge>
      {next.length > 0 && (
        <Select
          value=""
          onValueChange={async (v) => {
            try {
              await transition.mutateAsync({ id, toStatus: v as DemandStatus })
              toast({ title: `Demand moved to ${v}` })
            } catch (e) {
              toast({ title: 'Transition refused', description: (e as ApiError).message, variant: 'destructive' })
            }
          }}
        >
          <SelectTrigger className="w-32 h-7"><SelectValue placeholder="Move to…" /></SelectTrigger>
          <SelectContent>{next.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
        </Select>
      )}
    </div>
  )
}

function RaiseDemandDialog() {
  const { toast } = useToast()
  const create = useCreateDemand()
  const awards = useAwards()
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [awardId, setAwardId] = useState('')
  const [places, setPlaces] = useState('1')
  const [justification, setJustification] = useState('')
  const [targetStart, setTargetStart] = useState('')

  const reset = () => { setTitle(''); setAwardId(''); setPlaces('1'); setJustification(''); setTargetStart('') }

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) reset() }}>
      <DialogTrigger asChild>
        <Button size="sm"><Plus className="h-4 w-4 mr-1" /> Raise demand</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Raise a research demand</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="d-title">Title</Label>
            <Input id="d-title" value={title} onChange={(e) => setTitle(e.target.value)}
              placeholder="Researcher needed for…" />
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
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="d-places">Places requested</Label>
              <Input id="d-places" type="number" min={1} value={places} onChange={(e) => setPlaces(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="d-start">Target start (optional)</Label>
              <Input id="d-start" type="date" value={targetStart} onChange={(e) => setTargetStart(e.target.value)} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="d-just">Justification (optional)</Label>
            <Textarea id="d-just" className="min-h-[72px]" value={justification}
              onChange={(e) => setJustification(e.target.value)} placeholder="Why this place is needed." />
          </div>
        </div>
        <DialogFooter>
          <Button
            disabled={!title.trim() || Number(places) < 1 || create.isPending}
            onClick={async () => {
              try {
                await create.mutateAsync({
                  title: title.trim(),
                  researchAwardId: awardId || undefined,
                  requestedPlaces: Number(places),
                  justification: justification.trim() || undefined,
                  targetStartDate: targetStart || undefined,
                })
                toast({ title: 'Demand raised' })
                setOpen(false); reset()
              } catch (e) {
                toast({ title: 'Could not raise demand', description: (e as ApiError).message, variant: 'destructive' })
              }
            }}
          >
            {create.isPending ? 'Saving…' : 'Raise demand'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function DemandTab() {
  const demands = useDemands()
  const awards = useAwards()
  const awardRef = (id: string | null) =>
    (id && awards.data?.find((a) => a.id === id)?.awardRef) || '—'

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-helper">
          Demand is the recorded <em>need</em> for a researcher. It becomes a recruitable position
          only once it is approved and positioned.
        </p>
        <RaiseDemandDialog />
      </div>
      <div className="card-elevated overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Award</TableHead>
              <TableHead>Places</TableHead>
              <TableHead>Target start</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {demands.isLoading && (
              <TableRow><TableCell colSpan={5}><Skeleton className="h-5 w-full" /></TableCell></TableRow>
            )}
            {demands.data?.map((d) => (
              <TableRow key={d.id}>
                <TableCell className="font-medium" title={d.justification ?? undefined}>{d.title}</TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">{awardRef(d.researchAwardId)}</TableCell>
                <TableCell className="num">{d.requestedPlaces}</TableCell>
                <TableCell className="num text-muted-foreground">{d.targetStartDate ?? '—'}</TableCell>
                <TableCell><DemandStatusControl id={d.id} status={d.status} /></TableCell>
              </TableRow>
            ))}
            {demands.data && demands.data.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-muted-foreground text-center py-8">
                  No research demand has been raised yet.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

function RecordAwardDialog() {
  const { toast } = useToast()
  const create = useCreateAward()
  const funders = useFundingSources()
  const [open, setOpen] = useState(false)
  const [awardRef, setAwardRef] = useState('')
  const [title, setTitle] = useState('')
  const [funderId, setFunderId] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [value, setValue] = useState('')

  const reset = () => {
    setAwardRef(''); setTitle(''); setFunderId(''); setStartDate(''); setEndDate(''); setValue('')
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) reset() }}>
      <DialogTrigger asChild>
        <Button size="sm"><Plus className="h-4 w-4 mr-1" /> Record award</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Record an award reference</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="a-ref">Award reference</Label>
              <Input id="a-ref" value={awardRef} onChange={(e) => setAwardRef(e.target.value)} placeholder="EP/X000000/1" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="a-val">Value (optional)</Label>
              <Input id="a-val" type="number" value={value} onChange={(e) => setValue(e.target.value)} placeholder="450000" />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="a-title">Title</Label>
            <Input id="a-title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Funder (optional)</Label>
            <Select value={funderId} onValueChange={setFunderId}>
              <SelectTrigger><SelectValue placeholder="No funder recorded" /></SelectTrigger>
              <SelectContent>
                {funders.data?.map((f) => <SelectItem key={f.id} value={f.id}>{f.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="a-start">Start (optional)</Label>
              <Input id="a-start" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="a-end">End (optional)</Label>
              <Input id="a-end" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
            </div>
          </div>
          <p className="text-helper">
            Manual fallback only. Where a Research-system integration is live, awards arrive
            through the integration hub and are read-only here.
          </p>
        </div>
        <DialogFooter>
          <Button
            disabled={!awardRef.trim() || !title.trim() || create.isPending}
            onClick={async () => {
              try {
                await create.mutateAsync({
                  awardRef: awardRef.trim(),
                  title: title.trim(),
                  funderId: funderId || undefined,
                  startDate: startDate || undefined,
                  endDate: endDate || undefined,
                  value: value ? Number(value) : undefined,
                  currency: value ? 'GBP' : undefined,
                })
                toast({ title: 'Award recorded' })
                setOpen(false); reset()
              } catch (e) {
                toast({ title: 'Could not record award', description: (e as ApiError).message, variant: 'destructive' })
              }
            }}
          >
            {create.isPending ? 'Saving…' : 'Record award'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function AwardsTab() {
  const awards = useAwards()
  const funders = useFundingSources()
  const funderName = (id: string | null) =>
    (id && funders.data?.find((f) => f.id === id)?.name) || '—'

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-helper">
          The PGR platform holds award <em>references</em>, never the authority. This is not grants
          management.
        </p>
        <RecordAwardDialog />
      </div>
      <div className="card-elevated overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Reference</TableHead>
              <TableHead>Title</TableHead>
              <TableHead>Funder</TableHead>
              <TableHead>Dates</TableHead>
              <TableHead>Value</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {awards.isLoading && (
              <TableRow><TableCell colSpan={6}><Skeleton className="h-5 w-full" /></TableCell></TableRow>
            )}
            {awards.data?.map((a) => (
              <TableRow key={a.id}>
                <TableCell className="font-mono text-xs">{a.awardRef}</TableCell>
                <TableCell className="font-medium">{a.title}</TableCell>
                <TableCell className="text-muted-foreground">{funderName(a.funderId)}</TableCell>
                <TableCell className="num text-muted-foreground whitespace-nowrap">
                  {a.startDate ?? '—'} → {a.endDate ?? '—'}
                </TableCell>
                <TableCell className="num">
                  {a.value ? `${a.currency ?? ''} ${Number(a.value).toLocaleString()}`.trim() : '—'}
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <Badge variant={a.status === 'active' ? 'success' : 'secondary'}>{a.status}</Badge>
                    {/* Mastered elsewhere — deliberately no edit affordance. */}
                    {a.readOnly && (
                      <Badge variant="secondary" className="text-muted-foreground"
                        title={`Maintained in the ${a.sourceSystem} system; changes arrive via the integration hub.`}>
                        Research system
                      </Badge>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {awards.data && awards.data.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-muted-foreground text-center py-8">
                  No awards recorded yet.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

export default function ResearchPage() {
  return (
    <>
      <PageHeader
        title="Research"
        description="Where a PGR position comes from: an award funds a demand, a demand becomes a position."
      />
      <div className="px-6 pb-6">
        <Tabs defaultValue="demand">
          <TabsList>
            <TabsTrigger value="demand"><FlaskConical className="h-4 w-4 mr-1.5" /> Research demand</TabsTrigger>
            <TabsTrigger value="awards"><Trophy className="h-4 w-4 mr-1.5" /> Awards</TabsTrigger>
            <TabsTrigger value="match"><UserSearch className="h-4 w-4 mr-1.5" /> Supervisor match</TabsTrigger>
            <TabsTrigger value="map"><Network className="h-4 w-4 mr-1.5" /> Relationship map</TabsTrigger>
          </TabsList>
          <TabsContent value="demand" className="mt-4"><DemandTab /></TabsContent>
          <TabsContent value="awards" className="mt-4"><AwardsTab /></TabsContent>
          <TabsContent value="match" className="mt-4"><SupervisorMatchPanel /></TabsContent>
          <TabsContent value="map" className="mt-4"><RelationshipGraph limit={25} /></TabsContent>
        </Tabs>
      </div>
    </>
  )
}
