'use client'

/**
 * F4 — Classification workflow card on the student detail page.
 *
 * Chair proposes → exam board confirms (approver separation enforced server-side) → Registry
 * publishes. Publishing renders the certificate PDF; from that point graduation is unlocked.
 */

import { useState } from 'react'
import { Award as AwardIcon, CheckCircle2, Download, GraduationCap, Lock, ShieldCheck, Sparkles } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { PageSection } from '@/components/common/PageSection'
import { ErrorState } from '@/components/common/ErrorState'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { ApiError } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import {
  certificateUrl,
  useClassification, useConfirmClassification, useProposeClassification, usePublishClassification,
  type ClassificationState,
} from '@/features/completion/api'

const STATE_TONES: Record<ClassificationState, { variant: 'secondary' | 'warning' | 'success'; label: string }> = {
  none:      { variant: 'secondary', label: 'Not started' },
  draft:     { variant: 'secondary', label: 'Draft' },
  proposed:  { variant: 'warning',   label: 'Proposed — awaiting exam board' },
  confirmed: { variant: 'warning',   label: 'Confirmed — awaiting Registry publish' },
  published: { variant: 'success',   label: 'Published — certificate available' },
}


export function ClassificationCard({ studentId }: { studentId: string }) {
  const { toast } = useToast()
  const { hasPermission } = useAuth()
  const canPropose = hasPermission('student.write')
  const canConfirm = hasPermission('progression.decide')
  const canPublish = hasPermission('reports.signoff')

  const q = useClassification(studentId)
  const propose = useProposeClassification(studentId)
  const confirm = useConfirmClassification(studentId)
  const publish = usePublishClassification(studentId)
  const [choice, setChoice] = useState('PhD')

  return (
    <PageSection icon={AwardIcon} title="Award classification (F4)" accent="primary"
      description="Chair proposes → exam board confirms → Registry publishes. Only a published award can graduate.">
      {q.isLoading ? <Skeleton className="h-16 w-full" /> : q.isError ? (
        <ErrorState error={q.error} />
      ) : q.data ? (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={STATE_TONES[q.data.classificationState].variant}>
              {STATE_TONES[q.data.classificationState].label}
            </Badge>
            {q.data.classification && (
              <span className="text-sm font-medium">
                {q.data.classificationTitle ?? q.data.classification}
              </span>
            )}
            {q.data.publishedAt && (
              <span className="text-helper">
                published {new Date(q.data.publishedAt).toLocaleString()}
              </span>
            )}
          </div>

          {q.data.classificationState === 'none' || q.data.classificationState === 'draft' ? (
            <div className="flex flex-wrap items-center gap-2">
              <div className="w-56">
                <Select value={choice} onValueChange={setChoice}>
                  <SelectTrigger><SelectValue placeholder="Choose classification" /></SelectTrigger>
                  <SelectContent>
                    {q.data.options.map((o) => (
                      <SelectItem key={o} value={o}>{o}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {canPropose ? (
                <Button size="sm" disabled={propose.isPending}
                  onClick={async () => {
                    try {
                      await propose.mutateAsync(choice)
                      toast({ title: `Proposed ${choice}` })
                    } catch (e) { toast({ title: 'Propose failed', description: (e as ApiError).message, variant: 'destructive' }) }
                  }}>
                  <Sparkles className="h-4 w-4 mr-1" />
                  {propose.isPending ? 'Proposing…' : 'Propose'}
                </Button>
              ) : (
                <span className="text-helper">Ask a chair with <span className="font-mono">student.write</span> to propose.</span>
              )}
            </div>
          ) : q.data.classificationState === 'proposed' ? (
            canConfirm ? (
              <Button size="sm" disabled={confirm.isPending}
                onClick={async () => {
                  try {
                    await confirm.mutateAsync()
                    toast({ title: 'Classification confirmed' })
                  } catch (e) { toast({ title: 'Confirm refused', description: (e as ApiError).message, variant: 'destructive' }) }
                }}>
                <CheckCircle2 className="h-4 w-4 mr-1" />
                {confirm.isPending ? 'Confirming…' : 'Confirm (exam board)'}
              </Button>
            ) : (
              <p className="text-helper">
                Awaiting exam board confirmation. Approver separation is enforced — the confirmer
                must differ from the proposer.
              </p>
            )
          ) : q.data.classificationState === 'confirmed' ? (
            canPublish ? (
              <Button size="sm" disabled={publish.isPending}
                onClick={async () => {
                  try {
                    await publish.mutateAsync()
                    toast({ title: 'Published — certificate rendered' })
                  } catch (e) { toast({ title: 'Publish failed', description: (e as ApiError).message, variant: 'destructive' }) }
                }}>
                <ShieldCheck className="h-4 w-4 mr-1" />
                {publish.isPending ? 'Publishing…' : 'Publish (Registry)'}
              </Button>
            ) : (
              <p className="text-helper">
                Awaiting Registry publish (<span className="font-mono">reports.signoff</span>).
              </p>
            )
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <Lock className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm">Classification is locked. Graduation is unlocked.</span>
              {q.data.certificateDocumentId && (
                <a
                  className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
                  href={certificateUrl(studentId)} target="_blank" rel="noreferrer"
                >
                  <Download className="h-4 w-4" /> Download certificate
                </a>
              )}
              <GraduationCap className="h-4 w-4 text-muted-foreground ml-2" />
            </div>
          )}
        </div>
      ) : null}
    </PageSection>
  )
}
