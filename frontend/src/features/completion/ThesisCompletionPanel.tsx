'use client'

import { useState } from 'react'
import { BookOpenCheck, Award as AwardIcon } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import {
  useDeclareIntention, useRecordOutcome, useSubmitThesis, useThesis,
  type ExaminationOutcome,
} from '@/features/thesis/api'
import { useCompletion, useConfirmCompletion, useGraduate } from './api'
import { ExaminersSection } from '@/features/thesis/ExaminersSection'

const OUTCOMES: ExaminationOutcome[] = ['pass', 'pass_with_corrections', 'major_corrections', 'resubmission', 'fail']
const THESIS_VARIANT = (s: string) =>
  s === 'approved' ? 'success' : s === 'failed' ? 'destructive' : s === 'submitted' ? 'info' : 'secondary'

export function ThesisCompletionPanel({ studentId }: { studentId: string }) {
  const { toast } = useToast()
  const thesisQ = useThesis(studentId)
  const completionQ = useCompletion(studentId)
  const declare = useDeclareIntention(studentId)
  const submit = useSubmitThesis(studentId)
  const outcome = useRecordOutcome(studentId)
  const confirm = useConfirmCompletion(studentId)
  const graduate = useGraduate(studentId)
  const [oc, setOc] = useState<ExaminationOutcome | ''>('')

  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as Error).message, variant: 'destructive' })
  const t = thesisQ.data
  const c = completionQ.data
  const thesisApproved = t?.status === 'approved'

  return (
    <PageSection icon={BookOpenCheck} title="Thesis & completion" accent="primary">
      {thesisQ.isLoading ? <Skeleton className="h-16 w-full" /> : (
        <div className="space-y-4">
          {/* Thesis */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-sm font-medium">Thesis</span>
              {t ? <Badge variant={THESIS_VARIANT(t.status)}>{t.status.replace(/_/g, ' ')}</Badge>
                 : <Badge variant="secondary">not started</Badge>}
              {t?.examination?.outcome && <Badge variant="outline">{t.examination.outcome.replace(/_/g, ' ')}</Badge>}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {(!t || t.status === 'preparation') && (
                <Button size="sm" disabled={declare.isPending}
                  onClick={async () => { try { await declare.mutateAsync('Doctoral Thesis'); toast({ title: 'Intention to submit declared' }) } catch (e) { err(e) } }}>
                  Declare intention
                </Button>
              )}
              {t?.status === 'intention_to_submit' && (
                <Button size="sm" disabled={submit.isPending}
                  onClick={async () => { try { await submit.mutateAsync({ id: t.id, documentRef: 'thesis.pdf' }); toast({ title: 'Thesis submitted' }) } catch (e) { err(e) } }}>
                  Submit thesis
                </Button>
              )}
              {t && ['submitted', 'under_examination', 'corrections', 'resubmission'].includes(t.status) && (
                <>
                  <Select value={oc} onValueChange={(v) => setOc(v as ExaminationOutcome)}>
                    <SelectTrigger className="w-56 h-8"><SelectValue placeholder="Examination outcome…" /></SelectTrigger>
                    <SelectContent>{OUTCOMES.map((o) => <SelectItem key={o} value={o}>{o.replace(/_/g, ' ')}</SelectItem>)}</SelectContent>
                  </Select>
                  <Button size="sm" disabled={!oc || outcome.isPending}
                    onClick={async () => { try { await outcome.mutateAsync({ id: t.id, outcome: oc as ExaminationOutcome }); toast({ title: 'Examination outcome recorded' }); setOc('') } catch (e) { err(e) } }}>
                    Record outcome
                  </Button>
                </>
              )}
              {thesisApproved && <span className="text-helper">Thesis approved — ready for completion.</span>}
            </div>
          </div>

          {/* Examiners (once the thesis is submitted) */}
          {t?.submittedAt && <ExaminersSection studentId={studentId} thesisId={t.id} />}

          {/* Completion */}
          <div className="pt-3 border-t border-border">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-sm font-medium">Completion</span>
              {c ? <Badge variant={c.status === 'graduated' ? 'success' : 'info'}>{c.status.replace(/_/g, ' ')}</Badge>
                 : <Badge variant="secondary">pending</Badge>}
            </div>
            {c?.status === 'graduated' ? (
              <div className="flex items-center gap-2 text-sm">
                <AwardIcon className="h-4 w-4 text-[hsl(var(--success))]" />
                🎓 Graduated {c.graduationDate} — <span className="font-medium">{c.award?.title}</span> conferred.
                The person is now <span className="font-medium">alumni</span>.
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                <Button size="sm" variant="secondary" disabled={!thesisApproved || c?.status === 'award_confirmed' || confirm.isPending}
                  onClick={async () => { try { await confirm.mutateAsync(); toast({ title: 'Completion confirmed' }) } catch (e) { err(e) } }}>
                  Confirm completion
                </Button>
                <Button size="sm" disabled={c?.status !== 'award_confirmed' || graduate.isPending}
                  onClick={async () => { try { await graduate.mutateAsync(); toast({ title: 'Graduated 🎓', description: 'Funding closed, student completed, person is now alumni.' }) } catch (e) { err(e) } }}>
                  Graduate
                </Button>
                {!thesisApproved && <span className="text-helper">Thesis must be approved first.</span>}
              </div>
            )}
          </div>
        </div>
      )}
    </PageSection>
  )
}
