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
import {
  useChangeFunding, useCreateFunding, useEndFunding, useFunding, useFundingSources,
  type FundingStatus, type FundingType,
} from './api'

const STATUS_VARIANT: Record<FundingStatus, 'secondary' | 'success' | 'info' | 'outline'> = {
  planned: 'secondary', active: 'success', changed: 'info', ended: 'outline',
}
const TYPES: FundingType[] = ['research_council', 'university_scholarship', 'external', 'self_funded']

function money(amount: string | null, currency: string | null) {
  if (!amount) return '—'
  return `${currency ?? ''} ${Number(amount).toLocaleString()}`.trim()
}

export function FundingPanel({ studentId }: { studentId: string }) {
  const { toast } = useToast()
  const { data, isLoading } = useFunding(studentId)
  const sources = useFundingSources()
  const create = useCreateFunding(studentId)
  const end = useEndFunding(studentId)
  const change = useChangeFunding(studentId)

  const [type, setType] = useState<FundingType>('research_council')
  const [sourceId, setSourceId] = useState('')
  const [amount, setAmount] = useState('')

  // Inline "change" editor state (one arrangement at a time).
  const [changingId, setChangingId] = useState<string | null>(null)
  const [changeType, setChangeType] = useState<FundingType>('research_council')
  const [changeAmount, setChangeAmount] = useState('')

  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as Error).message, variant: 'destructive' })

  return (
    <PageSection icon={Wallet} title="Funding" accent="accent">
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
                {a.validTo === null && (
                  <div className="flex items-center gap-1 shrink-0">
                    <Button size="sm" variant="ghost"
                      onClick={() => { setChangingId(changingId === a.id ? null : a.id); setChangeType(a.fundingType); setChangeAmount(a.stipendAmount ?? '') }}>Change</Button>
                    <Button size="sm" variant="ghost" disabled={end.isPending}
                      onClick={async () => { try { await end.mutateAsync(a.id); toast({ title: 'Funding ended' }) } catch (e) { err(e) } }}>End</Button>
                  </div>
                )}
              </div>
              {changingId === a.id && (
                <div className="flex flex-wrap items-end gap-2 mt-2 bg-surface-2 rounded-md p-2">
                  <Select value={changeType} onValueChange={(v) => setChangeType(v as FundingType)}>
                    <SelectTrigger className="w-44 h-8"><SelectValue /></SelectTrigger>
                    <SelectContent>{TYPES.map((t) => <SelectItem key={t} value={t}>{t.replace(/_/g, ' ')}</SelectItem>)}</SelectContent>
                  </Select>
                  <Input type="number" placeholder="New stipend" className="w-36 h-8" value={changeAmount} onChange={(e) => setChangeAmount(e.target.value)} />
                  <Button size="sm" disabled={change.isPending}
                    onClick={async () => {
                      try {
                        await change.mutateAsync({ id: a.id, body: { fundingType: changeType, stipendAmount: changeAmount || undefined, currency: changeAmount ? 'GBP' : undefined } })
                        toast({ title: 'Funding changed', description: 'Previous arrangement closed, new one opened.' }); setChangingId(null)
                      } catch (e) { err(e) }
                    }}>Apply change</Button>
                  <Button size="sm" variant="ghost" onClick={() => setChangingId(null)}>Cancel</Button>
                </div>
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
          <SelectContent>{sources.data?.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent>
        </Select>
        <Input type="number" placeholder="Stipend (GBP)" className="w-40" value={amount} onChange={(e) => setAmount(e.target.value)} />
        <Button size="sm" disabled={create.isPending}
          onClick={async () => {
            try {
              await create.mutateAsync({
                fundingType: type,
                fundingSourceId: sourceId || undefined,
                stipendAmount: amount || undefined,
                currency: amount ? 'GBP' : undefined,
              })
              toast({ title: 'Funding arrangement added' }); setAmount(''); setSourceId('')
            } catch (e) { err(e) }
          }}>Add arrangement</Button>
      </div>
    </PageSection>
  )
}
