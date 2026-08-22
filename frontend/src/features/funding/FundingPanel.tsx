'use client'

import { useState } from 'react'
import { Wallet } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { useAwards } from '@/features/research/api'
import { FeeWaiversSection } from './FeeWaiversSection'
import { PaymentsSection } from './PaymentsSection'
import {
  useChangeFunding, useCreateFunding, useEndFunding, useFunding, useFundingSources,
  usePaymentSummary, type FundingStatus, type FundingType,
} from './api'

const STATUS_VARIANT: Record<FundingStatus, 'secondary' | 'success' | 'info' | 'outline'> = {
  planned: 'secondary', active: 'success', changed: 'info', ended: 'outline',
}
const TYPES: FundingType[] = ['research_council', 'university_scholarship', 'external', 'self_funded']

function money(amount: string | null | undefined, currency: string | null | undefined) {
  if (amount === null || amount === undefined || amount === '') return '—'
  return `${currency ?? ''} ${Number(amount).toLocaleString()}`.trim()
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-surface-2 px-3 py-2">
      <p className="text-label">{label}</p>
      <p className="text-sm num font-medium mt-0.5">{value}</p>
    </div>
  )
}

export function FundingPanel({ studentId }: { studentId: string }) {
  const { toast } = useToast()
  const { data, isLoading } = useFunding(studentId)
  const sources = useFundingSources()
  const awards = useAwards()
  const summary = usePaymentSummary(studentId)
  const create = useCreateFunding(studentId)
  const end = useEndFunding(studentId)
  const change = useChangeFunding(studentId)

  const [type, setType] = useState<FundingType>('research_council')
  const [sourceId, setSourceId] = useState('')
  const [amount, setAmount] = useState('')
  const [costCentre, setCostCentre] = useState('')
  const [projectCode, setProjectCode] = useState('')
  const [funderReference, setFunderReference] = useState('')
  const [contributionPct, setContributionPct] = useState('')
  const [awardId, setAwardId] = useState('')

  // Inline "change" editor state (one arrangement at a time).
  const [changingId, setChangingId] = useState<string | null>(null)
  const [changeType, setChangeType] = useState<FundingType>('research_council')
  const [changeAmount, setChangeAmount] = useState('')
  const [changeCostCentre, setChangeCostCentre] = useState('')
  const [changeProjectCode, setChangeProjectCode] = useState('')
  const [changeFunderRef, setChangeFunderRef] = useState('')
  const [changeContribution, setChangeContribution] = useState('')
  const [changeAwardId, setChangeAwardId] = useState('')

  // Which arrangement's payment schedule is expanded.
  const [payingArrangementId, setPayingArrangementId] = useState<string | null>(null)

  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as Error).message, variant: 'destructive' })
  const s = summary.data

  return (
    <PageSection icon={Wallet} title="Funding" accent="accent">
      {/* Payment summary strip */}
      {summary.isLoading ? <Skeleton className="h-16 w-full mb-4" /> : s && (
        <div className="mb-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <Tile label="Instalments" value={String(s.instalments)} />
            <Tile label="Paid" value={money(s.paidTotal, s.currency)} />
            <Tile label="Committed" value={money(s.committedTotal, s.currency)} />
            <Tile label="Outstanding" value={money(s.outstandingTotal, s.currency)} />
          </div>
          {s.overdue.length > 0 && (
            <div className="mt-2">
              <Badge variant="warning">{s.overdue.length} overdue</Badge>
              <span className="text-helper ml-2">
                Earliest due {s.overdue.map((p) => p.dueDate).sort()[0]}.
              </span>
            </div>
          )}
        </div>
      )}

      {isLoading ? <Skeleton className="h-16 w-full" /> : (
        <div className="space-y-2 mb-4">
          {data && data.length > 0 ? data.slice().sort((a, b) => a.validFrom.localeCompare(b.validFrom)).map((a) => (
            <div key={a.id} className="border-b border-border/60 last:border-0 pb-2 last:pb-0">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium">{a.fundingType.replace(/_/g, ' ')}</span>
                  {a.fundingSourceName && <span className="text-sm text-muted-foreground">· {a.fundingSourceName}</span>}
                  <span className="text-sm num">· {money(a.stipendAmount, a.currency)}</span>
                  <Badge variant={STATUS_VARIANT[a.status]}>{a.status}</Badge>
                  <span className="text-helper num">{a.validFrom} → {a.validTo ?? 'current'}</span>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <Button size="sm" variant="ghost"
                    onClick={() => setPayingArrangementId(payingArrangementId === a.id ? null : a.id)}>
                    {payingArrangementId === a.id ? 'Hide payments' : 'Payments'}
                  </Button>
                  {a.validTo === null && (
                    <>
                      <Button size="sm" variant="ghost"
                        onClick={() => {
                          setChangingId(changingId === a.id ? null : a.id)
                          setChangeType(a.fundingType)
                          setChangeAmount(a.stipendAmount ?? '')
                          setChangeCostCentre(a.costCentre ?? '')
                          setChangeProjectCode(a.projectCode ?? '')
                          setChangeFunderRef(a.funderReference ?? '')
                          setChangeContribution(a.contributionPct != null ? String(a.contributionPct) : '')
                          setChangeAwardId(a.researchAwardId ?? '')
                        }}>Change</Button>
                      <Button size="sm" variant="ghost" disabled={end.isPending}
                        onClick={async () => { try { await end.mutateAsync(a.id); toast({ title: 'Funding ended' }) } catch (e) { err(e) } }}>End</Button>
                    </>
                  )}
                </div>
              </div>

              {/* Finance detail (Phase 4B.7) */}
              <p className="text-helper mt-0.5">
                {[
                  a.costCentre ? `cost centre ${a.costCentre}` : null,
                  a.projectCode ? `project ${a.projectCode}` : null,
                  a.funderReference ? `funder ref ${a.funderReference}` : null,
                  a.contributionPct != null ? `${a.contributionPct}% contribution` : null,
                  a.paymentFrequency ? `${a.paymentFrequency.replace(/_/g, ' ')} payments` : null,
                ].filter(Boolean).join(' · ') || 'No finance detail recorded'}
              </p>

              {changingId === a.id && (
                <div className="flex flex-wrap items-end gap-2 mt-2 bg-surface-2 rounded-md p-2">
                  <Select value={changeType} onValueChange={(v) => setChangeType(v as FundingType)}>
                    <SelectTrigger className="w-44 h-8"><SelectValue /></SelectTrigger>
                    <SelectContent>{TYPES.map((t) => <SelectItem key={t} value={t}>{t.replace(/_/g, ' ')}</SelectItem>)}</SelectContent>
                  </Select>
                  <Input type="number" placeholder="New stipend" className="w-36 h-8" value={changeAmount} onChange={(e) => setChangeAmount(e.target.value)} />
                  <Input placeholder="Cost centre" className="w-32 h-8" value={changeCostCentre} onChange={(e) => setChangeCostCentre(e.target.value)} />
                  <Input placeholder="Project code" className="w-32 h-8" value={changeProjectCode} onChange={(e) => setChangeProjectCode(e.target.value)} />
                  <Input placeholder="Funder reference" className="w-40 h-8" value={changeFunderRef} onChange={(e) => setChangeFunderRef(e.target.value)} />
                  <Input type="number" placeholder="Contribution %" className="w-32 h-8" value={changeContribution} onChange={(e) => setChangeContribution(e.target.value)} />
                  {/* Linking the award is what makes the funding chain traceable (Phase 6.3). */}
                  <Select value={changeAwardId} onValueChange={setChangeAwardId}>
                    <SelectTrigger className="w-52 h-8"><SelectValue placeholder="Award (optional)" /></SelectTrigger>
                    <SelectContent>
                      {awards.data?.map((aw) => (
                        <SelectItem key={aw.id} value={aw.id}>{aw.awardRef} — {aw.title}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button size="sm" disabled={change.isPending}
                    onClick={async () => {
                      try {
                        await change.mutateAsync({
                          id: a.id,
                          body: {
                            fundingType: changeType,
                            stipendAmount: changeAmount || undefined,
                            currency: changeAmount ? 'GBP' : undefined,
                            costCentre: changeCostCentre || undefined,
                            projectCode: changeProjectCode || undefined,
                            funderReference: changeFunderRef || undefined,
                            contributionPct: changeContribution ? Number(changeContribution) : undefined,
                            researchAwardId: changeAwardId || undefined,
                          },
                        })
                        toast({ title: 'Funding changed', description: 'Previous arrangement closed, new one opened.' }); setChangingId(null)
                      } catch (e) { err(e) }
                    }}>Apply change</Button>
                  <Button size="sm" variant="ghost" onClick={() => setChangingId(null)}>Cancel</Button>
                </div>
              )}

              {payingArrangementId === a.id && (
                <PaymentsSection studentId={studentId} arrangementId={a.id} />
              )}
            </div>
          )) : <p className="text-helper">No funding arrangements yet.</p>}
        </div>
      )}

      <div className="flex flex-wrap items-end gap-2 pt-2 border-t border-border">
        <Select value={type} onValueChange={(v) => setType(v as FundingType)}>
          <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
          <SelectContent>{TYPES.map((t) => <SelectItem key={t} value={t}>{t.replace(/_/g, ' ')}</SelectItem>)}</SelectContent>
        </Select>
        <Select value={sourceId} onValueChange={setSourceId}>
          <SelectTrigger className="w-48"><SelectValue placeholder="Source (optional)" /></SelectTrigger>
          <SelectContent>{sources.data?.map((s2) => <SelectItem key={s2.id} value={s2.id}>{s2.name}</SelectItem>)}</SelectContent>
        </Select>
        <Input type="number" placeholder="Stipend (GBP)" className="w-40" value={amount} onChange={(e) => setAmount(e.target.value)} />
        <Input placeholder="Cost centre" className="w-32 h-8" value={costCentre} onChange={(e) => setCostCentre(e.target.value)} />
        <Input placeholder="Project code" className="w-32 h-8" value={projectCode} onChange={(e) => setProjectCode(e.target.value)} />
        <Input placeholder="Funder reference" className="w-40 h-8" value={funderReference} onChange={(e) => setFunderReference(e.target.value)} />
        <Input type="number" placeholder="Contribution %" className="w-32 h-8" value={contributionPct} onChange={(e) => setContributionPct(e.target.value)} />
        {/* Optional, but without it the spend cannot be attributed to an award. */}
        <Select value={awardId} onValueChange={setAwardId}>
          <SelectTrigger className="w-56"><SelectValue placeholder="Research award (optional)" /></SelectTrigger>
          <SelectContent>
            {awards.data?.map((aw) => (
              <SelectItem key={aw.id} value={aw.id}>{aw.awardRef} — {aw.title}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button size="sm" disabled={create.isPending}
          onClick={async () => {
            try {
              await create.mutateAsync({
                fundingType: type,
                fundingSourceId: sourceId || undefined,
                stipendAmount: amount || undefined,
                currency: amount ? 'GBP' : undefined,
                costCentre: costCentre || undefined,
                projectCode: projectCode || undefined,
                funderReference: funderReference || undefined,
                contributionPct: contributionPct ? Number(contributionPct) : undefined,
                researchAwardId: awardId || undefined,
              })
              toast({ title: 'Funding arrangement added' })
              setAmount(''); setSourceId(''); setCostCentre(''); setProjectCode('')
              setFunderReference(''); setContributionPct(''); setAwardId('')
            } catch (e) { err(e) }
          }}>Add arrangement</Button>
      </div>

      <FeeWaiversSection studentId={studentId} />
    </PageSection>
  )
}
