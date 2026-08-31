'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { ArrowLeft, ClipboardCheck, GitBranch, Mail } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Button } from '@/components/ui/button'
import { useCan } from '@/shared/auth/Can'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import {
  useAcceptOffer, useAdvance, useApplication, useAssess, useCreateOffer,
  useDeclineOffer, useIssueOffer, useOfferForApplication, type CandidateStage,
} from '@/features/recruitment/api'
import { OfferPill, StagePill } from '@/features/recruitment/StatusPills'
import { usePerson } from '@/features/persons/api'

const STAGES: CandidateStage[] = [
  'under_assessment', 'shortlisted', 'interview', 'selected', 'offer_made',
  'rejected', 'withdrawn',
]

export default function ApplicationDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { toast } = useToast()
  const appQ = useApplication(id)
  const offerQ = useOfferForApplication(id)
  const app = appQ.data
  const person = usePerson(app?.personId ?? '')

  // Stage/assessment/offer controls are recruitment.write server-side; accepting
  // an offer creates the student record, so that one is student.write.
  const canRecruit = useCan('recruitment.write')
  const canCreateStudent = useCan('student.write')
  const advance = useAdvance(id)
  const assess = useAssess(id)
  const createOffer = useCreateOffer(id)
  const issueOffer = useIssueOffer(id)
  const acceptOffer = useAcceptOffer(id)
  const declineOffer = useDeclineOffer(id)

  const [stage, setStage] = useState<string>('')
  const [reason, setReason] = useState('')
  const [decision, setDecision] = useState('recommended')
  const [rationale, setRationale] = useState('')

  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as Error).message, variant: 'destructive' })

  const offer = offerQ.data
  const name = person.data ? `${person.data.givenName} ${person.data.familyName}` : '…'

  return (
    <>
      <PageHeader title="Application" description="Assess, advance, and make an offer." />
      <div className="px-6 pb-6 space-y-4">
        <Link href="/recruitment" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> Back to recruitment
        </Link>

        <PageSection icon={ClipboardCheck} title="Overview" accent="primary">
          {appQ.isLoading ? <Skeleton className="h-16 w-full" /> : (
            <div className="flex flex-wrap items-center gap-x-8 gap-y-2 text-sm">
              <span>Applicant: <Link href={`/persons/${app?.personId}`} className="font-medium hover:text-primary">{name}</Link></span>
              <span>Route: <span className="text-muted-foreground">{app?.route.replace(/_/g, ' ')}</span></span>
              <span className="flex items-center gap-2">Stage {app && <StagePill stage={app.currentStage} />}</span>
            </div>
          )}
        </PageSection>

        {canRecruit && <div className="grid gap-4 md:grid-cols-2">
          <PageSection icon={GitBranch} title="Advance stage" accent="primary">
            <div className="space-y-2">
              <Select value={stage} onValueChange={setStage}>
                <SelectTrigger><SelectValue placeholder="Target stage" /></SelectTrigger>
                <SelectContent>
                  {STAGES.map((s) => <SelectItem key={s} value={s}>{s.replace(/_/g, ' ')}</SelectItem>)}
                </SelectContent>
              </Select>
              <Input placeholder="Reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} />
              <Button size="sm" disabled={!stage || advance.isPending}
                onClick={async () => {
                  try { await advance.mutateAsync({ toStage: stage as CandidateStage, reason: reason || undefined }); toast({ title: `Advanced to ${stage.replace(/_/g, ' ')}` }); setStage(''); setReason('') }
                  catch (e) { err(e) }
                }}>Advance</Button>
            </div>
          </PageSection>

          <PageSection icon={ClipboardCheck} title="Record assessment" accent="accent">
            <div className="space-y-2">
              <div className="space-y-1"><Label>Decision</Label>
                <Select value={decision} onValueChange={setDecision}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="recommended">recommended</SelectItem>
                    <SelectItem value="conditionally_recommended">conditionally recommended</SelectItem>
                    <SelectItem value="rejected">rejected</SelectItem>
                    <SelectItem value="request_info">request info</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Input placeholder="Rationale" value={rationale} onChange={(e) => setRationale(e.target.value)} />
              <Button size="sm" variant="secondary" disabled={assess.isPending}
                onClick={async () => {
                  try { await assess.mutateAsync({ decision, rationale: rationale || undefined }); toast({ title: 'Assessment recorded' }); setRationale('') }
                  catch (e) { err(e) }
                }}>Record</Button>
            </div>
          </PageSection>
        </div>}

        <PageSection icon={Mail} title="Offer" accent="primary">
          {offerQ.isLoading ? <Skeleton className="h-10 w-40" /> : !offer ? (
            <div className="flex items-center gap-3">
              <span className="text-helper">No offer yet.</span>
              {canRecruit && <Button size="sm" disabled={createOffer.isPending}
                onClick={async () => { try { await createOffer.mutateAsync(); toast({ title: 'Offer created (draft)' }) } catch (e) { err(e) } }}>
                Create offer
              </Button>}
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-3">
              <OfferPill status={offer.status} />
              {canRecruit && offer.status === 'draft' && (
                <Button size="sm" disabled={issueOffer.isPending}
                  onClick={async () => { try { await issueOffer.mutateAsync(offer.id); toast({ title: 'Offer issued' }) } catch (e) { err(e) } }}>Issue</Button>
              )}
              {offer.status === 'issued' && (
                <>
                  {canCreateStudent && <Button size="sm" disabled={acceptOffer.isPending}
                    onClick={async () => {
                      try { const s = await acceptOffer.mutateAsync(offer.id); toast({ title: 'Offer accepted', description: `Student ${s.studentRef} created (same person).` }) }
                      catch (e) { err(e) }
                    }}>Accept → create student</Button>}
                  {canRecruit && <Button size="sm" variant="outline" disabled={declineOffer.isPending}
                    onClick={async () => { try { await declineOffer.mutateAsync(offer.id); toast({ title: 'Offer declined' }) } catch (e) { err(e) } }}>Decline</Button>}
                </>
              )}
              {offer.status === 'accepted' && (
                <span className="text-helper">Accepted — <Link href="/students" className="text-primary hover:underline">view students</Link></span>
              )}
            </div>
          )}
        </PageSection>

        <PageSection icon={GitBranch} title="Stage history" accent="primary">
          {app?.history.length ? (
            <ol className="relative border-l border-border ml-2 space-y-3">
              {app.history.slice().sort((a, b) => a.movedAt.localeCompare(b.movedAt)).map((h) => (
                <li key={h.id} className="ml-4">
                  <span className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full bg-primary" />
                  <p className="text-sm">{h.fromStage ? `${h.fromStage.replace(/_/g, ' ')} → ` : ''}<span className="font-medium">{h.toStage.replace(/_/g, ' ')}</span></p>
                  <p className="text-helper num">{h.movedAt.slice(0, 19).replace('T', ' ')}{h.reason ? ` · ${h.reason}` : ''}</p>
                </li>
              ))}
            </ol>
          ) : <p className="text-helper">No history.</p>}
        </PageSection>
      </div>
    </>
  )
}
