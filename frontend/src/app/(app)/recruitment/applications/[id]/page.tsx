'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useParams, useSearchParams } from 'next/navigation'
import { AlertTriangle, ArrowLeft, ArrowRight, ArrowUpRight, CheckCircle2, ClipboardCheck, GitBranch, Mail, ShieldCheck } from 'lucide-react'
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
  useDeclineOffer, useIssueOffer, useOfferForApplication, useVisaCheck,
  type Application, type CandidateStage,
} from '@/features/recruitment/api'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { OfferPill, StagePill } from '@/features/recruitment/StatusPills'
import { usePerson } from '@/features/persons/api'

const STAGES: CandidateStage[] = [
  'under_assessment', 'shortlisted', 'interview', 'selected', 'offer_made',
  'rejected', 'withdrawn',
]

const TERMINAL: CandidateStage[] = ['converted', 'rejected', 'withdrawn']

// Stages where an offer is "conventional". Anything below (applicant, under_assessment)
// gets a soft warning because it's unusual to jump straight to offer from there.
const ADVANCED_ENOUGH = new Set<CandidateStage>([
  'shortlisted', 'interview', 'selected', 'offer_made', 'offer_accepted',
])

/** Small visual guide showing how the three cards on this page relate. */
function FlowStrip({
  currentStage, assessmentCount, hasOffer,
}: {
  currentStage: CandidateStage
  assessmentCount: number
  hasOffer: boolean
}) {
  const stageDone = currentStage !== 'applicant'
  const assessDone = assessmentCount > 0
  const offerDone = hasOffer

  const step = (
    n: number,
    Icon: React.ComponentType<{ className?: string }>,
    label: string,
    sub: string,
    done: boolean,
    active: boolean,
  ) => {
    const tone = done
      ? 'border-[hsl(var(--success)/0.5)] bg-[hsl(var(--success)/0.06)]'
      : active
        ? 'border-primary/50 bg-primary/5'
        : 'border-border/60 bg-surface-2/40'
    const num = done ? '✓' : String(n)
    return (
      <div className={`flex flex-1 items-start gap-3 rounded-lg border ${tone} px-3 py-2`}>
        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-current text-xs font-medium text-muted-foreground">
          {num}
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-1 text-sm font-medium">
            <Icon className="h-3.5 w-3.5" />
            {label}
          </div>
          <p className="text-helper mt-0.5">{sub}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-lg bg-surface-2/40 p-3">
      <div className="flex flex-col items-stretch gap-2 md:flex-row md:items-center">
        {step(1, GitBranch, 'Advance stage',
              'audit spine · everyone sees the badge',
              stageDone, !stageDone)}
        <ArrowRight className="hidden h-4 w-4 shrink-0 text-muted-foreground md:block" />
        {step(2, ClipboardCheck, 'Record assessment',
              `evidence trail · ${assessmentCount} on file`,
              assessDone, stageDone && !assessDone)}
        <ArrowRight className="hidden h-4 w-4 shrink-0 text-muted-foreground md:block" />
        {step(3, Mail, 'Offer',
              hasOffer ? 'contractual step · offer exists' : 'contractual step · creates the student',
              offerDone, assessDone && !offerDone)}
      </div>
      <p className="text-helper mt-2">
        Loose sequence. Only <span className="font-medium">Accept offer</span> creates the student.
      </p>
    </div>
  )
}

function TerminalBanner({ stage, personId, personName }: {
  stage: CandidateStage
  personId: string
  personName: string
}) {
  if (stage === 'converted') {
    return (
      <div className="rounded-lg border border-[hsl(var(--success)/0.4)] bg-[hsl(var(--success)/0.06)] px-4 py-3">
        <div className="flex items-start gap-2">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[hsl(var(--success))]" />
          <div className="flex-1">
            <p className="text-sm font-medium">Became a student</p>
            <p className="text-helper mt-0.5">The record lives on the Students page.</p>
          </div>
          <Link href={`/persons/${personId}`}>
            <Button size="sm" variant="secondary">
              Open student record <ArrowUpRight className="ml-1 h-3 w-3" />
            </Button>
          </Link>
        </div>
      </div>
    )
  }
  const closedText = stage === 'rejected'
    ? 'This application was rejected and is closed.'
    : 'This application was withdrawn by the applicant and is closed.'
  return (
    <div className="rounded-lg border border-border bg-surface-2/60 px-4 py-3">
      <p className="text-sm font-medium">{closedText}</p>
      <p className="text-helper mt-0.5">
        If {personName || 'the applicant'} re-applies, start a new application from Recruitment.
      </p>
    </div>
  )
}

/** F3 — Fee status + visa gate. If visa_required is true and the check has not
 *  been completed, the backend refuses to issue the offer. This panel is where
 *  Compliance ticks the boxes that unlock the offer flow. */
function CompliancePanel({ app, canWrite }: { app: Application; canWrite: boolean }) {
  const { toast } = useToast()
  const patch = useVisaCheck(app.id)
  // Values MUST match the backend fee_status enum
  // (home / overseas / channel_islands / unknown) — anything else 500s.
  const feeStatuses: { value: string; label: string }[] = [
    { value: 'unknown',         label: 'Unknown' },
    { value: 'home',            label: 'Home' },
    { value: 'overseas',        label: 'Overseas' },
    { value: 'channel_islands', label: 'Channel Islands' },
  ]
  const cleared = !app.visaRequired || !!app.visaCheckCompletedAt

  const err = (e: unknown) =>
    toast({ title: 'Failed', description: (e as Error).message, variant: 'destructive' })

  return (
    <PageSection
      icon={ShieldCheck}
      title="Compliance — fee status & visa"
      accent="accent"
      description="An offer cannot be issued to a visa-required applicant until the visa check is complete."
    >
      <div className="grid gap-4 md:grid-cols-3">
        {/* Fee status */}
        <div className="space-y-1.5">
          <Label>Fee status</Label>
          <Select
            value={app.feeStatus ?? 'unknown'}
            onValueChange={async (v) => {
              try { await patch.mutateAsync({ feeStatus: v }); toast({ title: `Fee status: ${v}` }) }
              catch (e) { err(e) }
            }}
            disabled={!canWrite || patch.isPending}
          >
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {feeStatuses.map((f) => (
                <SelectItem key={f.value} value={f.value}>{f.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            Overseas fee status usually implies visa-required.
          </p>
        </div>

        {/* Visa required */}
        <div className="space-y-1.5">
          <Label>Visa</Label>
          <div className="flex items-center gap-2 h-10">
            <Checkbox
              id="visa-required"
              checked={!!app.visaRequired}
              disabled={!canWrite || patch.isPending}
              onCheckedChange={async (v) => {
                try {
                  await patch.mutateAsync({ visaRequired: v === true })
                  toast({ title: v === true ? 'Marked visa-required' : 'Marked visa-not-required' })
                } catch (e) { err(e) }
              }}
            />
            <Label htmlFor="visa-required" className="font-normal cursor-pointer">
              Applicant requires a visa
            </Label>
          </div>
          {app.visaRequired && !app.visaCheckCompletedAt && (
            <p className="text-xs text-[hsl(var(--warning))]">
              Offer issue is blocked until the check is complete.
            </p>
          )}
        </div>

        {/* Visa check */}
        <div className="space-y-1.5">
          <Label>Visa check</Label>
          <div className="space-y-1.5">
            {app.visaCheckCompletedAt ? (
              <>
                <Badge variant="success" className="w-fit">
                  <CheckCircle2 className="h-3 w-3 mr-1" />
                  Completed {new Date(app.visaCheckCompletedAt).toLocaleDateString()}
                </Badge>
                {canWrite && (
                  <Button
                    size="sm" variant="ghost" className="h-7 text-xs"
                    disabled={patch.isPending}
                    onClick={async () => {
                      try { await patch.mutateAsync({ completeVisaCheck: false }); toast({ title: 'Visa check cleared' }) }
                      catch (e) { err(e) }
                    }}
                  >Undo</Button>
                )}
              </>
            ) : app.visaRequired ? (
              <Button
                size="sm" variant="secondary"
                disabled={!canWrite || patch.isPending}
                onClick={async () => {
                  try {
                    await patch.mutateAsync({ completeVisaCheck: true })
                    toast({ title: 'Visa check completed' })
                  } catch (e) { err(e) }
                }}
              >
                Mark visa check complete
              </Button>
            ) : (
              <Badge variant="secondary" className="w-fit text-muted-foreground">
                Not required
              </Badge>
            )}
          </div>
        </div>
      </div>

      {/* Overall status ribbon */}
      <div className="mt-4 flex items-center gap-2 text-sm border-t border-border/60 pt-3">
        <span className="text-muted-foreground">Compliance state:</span>
        {cleared ? (
          <Badge variant="success">Cleared to offer</Badge>
        ) : (
          <Badge variant="warning">Blocking offer — visa check outstanding</Badge>
        )}
      </div>
    </PageSection>
  )
}

export default function ApplicationDetailPage() {
  const { id } = useParams<{ id: string }>()
  const searchParams = useSearchParams()
  const cameFrom = searchParams.get('from')       // 'admissions' when opened from that queue
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
      <PageHeader
        title={person.data ? name : 'Application'}
        description={person.data
          ? `Application · assess, advance, and make an offer.`
          : 'Assess, advance, and make an offer.'}
      />
      <div className="px-6 pb-6 space-y-4">
        {cameFrom === 'admissions' ? (
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <Link href="/admissions"
                  className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground">
              <ArrowLeft className="h-4 w-4" /> Back to Admissions
            </Link>
            <span className="text-muted-foreground/60">·</span>
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <Link href="/admissions" className="hover:text-foreground">Admissions</Link>
              <span className="opacity-60">›</span>
              <span className="opacity-60">Recruitment</span>
              <span className="opacity-60">›</span>
              <span className="text-foreground">Application</span>
            </span>
            <span
              className="rounded-full border border-border/60 bg-surface-2 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground"
              title="Application records live in the Recruitment module; Admissions is a queue over the offer lifecycle."
            >
              opened from admissions
            </span>
          </div>
        ) : (
          <Link href="/recruitment" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-4 w-4" /> Back to recruitment
          </Link>
        )}

        <PageSection icon={ClipboardCheck} title="Overview" accent="primary">
          {appQ.isLoading ? <Skeleton className="h-16 w-full" /> : (
            <div className="flex flex-wrap items-center gap-x-8 gap-y-2 text-sm">
              <span>Applicant: <Link href={`/persons/${app?.personId}`} className="font-medium hover:text-primary">{name}</Link></span>
              <span>Route: <span className="text-muted-foreground capitalize">{app?.route.replace(/_/g, ' ')}</span></span>
              <span className="flex items-center gap-2">Stage {app && <StagePill stage={app.currentStage} />}</span>
            </div>
          )}
        </PageSection>

        {app && !TERMINAL.includes(app.currentStage) && (
          <CompliancePanel app={app} canWrite={canRecruit} />
        )}

        {app && TERMINAL.includes(app.currentStage) && (
          <TerminalBanner
            stage={app.currentStage}
            personId={app.personId}
            personName={person.data ? name : ''}
          />
        )}

        {canRecruit && app && !TERMINAL.includes(app.currentStage) && (
          <FlowStrip
            currentStage={app.currentStage}
            assessmentCount={app.assessments?.length ?? 0}
            hasOffer={!!offer}
          />
        )}

        {canRecruit && app && !TERMINAL.includes(app.currentStage) && <div className="grid gap-4 md:grid-cols-2">
          <PageSection
            icon={GitBranch}
            title="1 · Advance stage"
            accent="primary"
            description="Audit spine — one row per move."
          >
            <div className="space-y-2">
              <Select value={stage} onValueChange={setStage}>
                <SelectTrigger><SelectValue placeholder="Target stage" /></SelectTrigger>
                <SelectContent>
                  {STAGES.map((s) => <SelectItem key={s} value={s} className="capitalize">{s.replace(/_/g, ' ')}</SelectItem>)}
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

          <PageSection
            icon={ClipboardCheck}
            title="2 · Record assessment"
            accent="accent"
            description="Evidence trail — multiple reviewers welcome."
          >
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

        <PageSection
          icon={Mail}
          title="3 · Offer"
          accent="primary"
          description="Contractual step — Accept creates the student."
        >
          {/* Soft warning — the offer path doesn't wait for stage/assessments to advance, but
              usually you'd have both done first. Non-blocking, just a nudge. */}
          {app && !offer && !ADVANCED_ENOUGH.has(app.currentStage)
            && (app.assessments?.length ?? 0) === 0 && (
            <div className="mb-3 flex items-start gap-2 rounded-md border border-[hsl(var(--warning)/0.4)] bg-[hsl(var(--warning)/0.06)] px-3 py-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[hsl(var(--warning))]" />
              <div className="text-xs">
                <p className="font-medium">
                  Still at <span className="font-mono">{app.currentStage.replace(/_/g, ' ')}</span>,
                  no assessment yet.
                </p>
                <p className="text-muted-foreground mt-0.5">
                  Usually advance and record an assessment first — nudge, not a block.
                </p>
              </div>
            </div>
          )}
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
                  <p className="text-sm capitalize">{h.fromStage ? `${h.fromStage.replace(/_/g, ' ')} → ` : ''}<span className="font-medium">{h.toStage.replace(/_/g, ' ')}</span></p>
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
