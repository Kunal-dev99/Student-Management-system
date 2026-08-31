'use client'

/**
 * W2 — Supervisor assignment requests card, mounted on the student detail page.
 *
 * Shows the recommend panel, existing requests, and the review/approve/reject actions.
 */

import { useState } from 'react'
import {
  CheckCircle2, ClipboardCheck, Sparkles, UserPlus, XCircle,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { PageSection } from '@/components/common/PageSection'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { ApiError } from '@/shared/api/client'
import {
  useApproveRequest, useCreateAssignmentRequest, useRecommend, useRejectRequest,
  useReviewRequest, useStudentSupervisorRequests, useWithdrawRequest,
  type AssignmentRequestState, type Recommendation,
} from '@/features/supervision/w2_api'


const STATE_VARIANT: Record<AssignmentRequestState, 'secondary'|'warning'|'success'|'destructive'|'outline'> = {
  recommended: 'secondary', requested: 'warning', academic_review: 'warning',
  approved: 'success', rejected: 'destructive', withdrawn: 'outline',
}

export function SupervisorRequestsCard({ studentId }: { studentId: string }) {
  const { toast } = useToast()
  const q = useStudentSupervisorRequests(studentId)
  const create = useCreateAssignmentRequest(studentId)
  const review = useReviewRequest()
  const approve = useApproveRequest()
  const reject = useRejectRequest()
  const withdraw = useWithdrawRequest()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [sid, setSid] = useState('')
  const [role, setRole] = useState<'primary'|'co_supervisor'>('primary')
  const [note, setNote] = useState('')
  const [rejectingId, setRejectingId] = useState<string | null>(null)
  const [rejectReason, setRejectReason] = useState('')

  return (
    <PageSection icon={UserPlus} title="Supervisor assignment (W2)" accent="primary"
      description="Recommend → request → academic review → approve. Every decision is on the record.">
      {q.isLoading ? <Skeleton className="h-16 w-full" /> : (
        <div className="space-y-3">
          <RecommendPanel studentId={studentId}
            onPick={(person, score, reasons) => {
              setSid(person.personId)
              // pre-fill the dialog
              setDialogOpen(true)
              // note reflects the match
              setNote(`Matched score ${score}%: ${reasons.slice(0,2).map(r=>r.factor).join(', ')}`)
            }} />

          {q.data && q.data.requests.length > 0 ? (
            <div className="space-y-2">
              {q.data.requests.map((r) => (
                <div key={r.id} className="card-elevated p-3 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={STATE_VARIANT[r.state]}>{r.state.replace(/_/g,' ')}</Badge>
                    <Badge variant="secondary">{r.proposedRole}</Badge>
                    <span className="text-sm font-mono">{r.proposedSupervisorPersonId.slice(0,8)}…</span>
                    {r.matchScore !== null && (
                      <span className="text-helper">match {r.matchScore}%</span>
                    )}
                    <span className="text-helper ml-auto">{new Date(r.createdAt).toLocaleDateString()}</span>
                  </div>
                  {r.note && <p className="text-sm text-muted-foreground">{r.note}</p>}
                  {r.rejectionReason && (
                    <p className="text-sm text-[hsl(var(--destructive))]">Rejected: {r.rejectionReason}</p>
                  )}
                  <div className="flex flex-wrap gap-2 pt-1">
                    {r.state === 'requested' && (
                      <Button size="sm" variant="secondary"
                        onClick={async () => {
                          try { await review.mutateAsync(r.id); toast({ title: 'Moved to review' }) }
                          catch (e) { toast({ title: 'Failed', description: (e as ApiError).message, variant: 'destructive' }) }
                        }}>
                        <ClipboardCheck className="h-4 w-4 mr-1" /> Send to review
                      </Button>
                    )}
                    {(r.state === 'requested' || r.state === 'academic_review') && (
                      <>
                        <Button size="sm"
                          onClick={async () => {
                            try {
                              const res = await approve.mutateAsync(r.id)
                              toast({ title: 'Approved', description: `Relationship ${res.relationshipId.slice(0,8)}…` })
                            } catch (e) {
                              toast({ title: 'Approve refused', description: (e as ApiError).message, variant: 'destructive' })
                            }
                          }}>
                          <CheckCircle2 className="h-4 w-4 mr-1" /> Approve
                        </Button>
                        <Dialog open={rejectingId === r.id} onOpenChange={(o) => { setRejectingId(o ? r.id : null); if (!o) setRejectReason('') }}>
                          <DialogTrigger asChild>
                            <Button size="sm" variant="destructive">
                              <XCircle className="h-4 w-4 mr-1" /> Reject
                            </Button>
                          </DialogTrigger>
                          <DialogContent>
                            <DialogHeader><DialogTitle>Reject this assignment</DialogTitle></DialogHeader>
                            <div className="space-y-3">
                              <p className="text-helper">A rejection reason is required and shown on the request record.</p>
                              <div className="space-y-1.5">
                                <Label htmlFor="rej">Reason</Label>
                                <Textarea id="rej" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} />
                              </div>
                            </div>
                            <DialogFooter>
                              <Button variant="destructive" disabled={!rejectReason.trim() || reject.isPending}
                                onClick={async () => {
                                  try {
                                    await reject.mutateAsync({ id: r.id, reason: rejectReason.trim() })
                                    toast({ title: 'Rejected' })
                                    setRejectingId(null); setRejectReason('')
                                  } catch (e) { toast({ title: 'Failed', description: (e as ApiError).message, variant: 'destructive' }) }
                                }}>Reject</Button>
                            </DialogFooter>
                          </DialogContent>
                        </Dialog>
                        <Button size="sm" variant="ghost"
                          onClick={async () => {
                            try { await withdraw.mutateAsync(r.id); toast({ title: 'Withdrawn' }) }
                            catch (e) { toast({ title: 'Failed', description: (e as ApiError).message, variant: 'destructive' }) }
                          }}>Withdraw</Button>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-helper">No assignment requests yet.</p>
          )}

          <Dialog open={dialogOpen} onOpenChange={(o) => { setDialogOpen(o); if (!o) { setSid(''); setNote('') } }}>
            <DialogTrigger asChild>
              <Button size="sm" variant="outline"><UserPlus className="h-4 w-4 mr-1" /> Request supervisor manually</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Request a supervisor</DialogTitle></DialogHeader>
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label htmlFor="sid">Supervisor person id</Label>
                  <Input id="sid" className="font-mono text-xs" value={sid} onChange={(e) => setSid(e.target.value)} placeholder="uuid" />
                </div>
                <div className="space-y-1.5">
                  <Label>Role</Label>
                  <Select value={role} onValueChange={(v) => setRole(v as 'primary'|'co_supervisor')}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="primary">Primary</SelectItem>
                      <SelectItem value="co_supervisor">Co-supervisor</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="note">Note (optional)</Label>
                  <Textarea id="note" value={note} onChange={(e) => setNote(e.target.value)} />
                </div>
              </div>
              <DialogFooter>
                <Button disabled={!sid.trim() || create.isPending}
                  onClick={async () => {
                    try {
                      await create.mutateAsync({
                        supervisorPersonId: sid.trim(), role,
                        note: note.trim() || undefined,
                      })
                      toast({ title: 'Request created' })
                      setDialogOpen(false); setSid(''); setNote('')
                    } catch (e) { toast({ title: 'Failed', description: (e as ApiError).message, variant: 'destructive' }) }
                  }}>
                  Request
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      )}
    </PageSection>
  )
}


function RecommendPanel({ studentId, onPick }: {
  studentId: string
  onPick: (r: Recommendation, score: number, reasons: { factor: string; points: number }[]) => void
}) {
  const q = useRecommend(studentId)
  if (q.isLoading) return <Skeleton className="h-12 w-full" />
  if (!q.data || !q.data.suggestions || q.data.suggestions.length === 0) return null
  const top = q.data.suggestions.slice(0, 5)
  return (
    <div className="rounded-md border border-border p-3 space-y-2">
      <p className="text-label inline-flex items-center gap-1">
        <Sparkles className="h-3 w-3" /> Recommended supervisors
      </p>
      <div className="space-y-1.5">
        {top.map((s) => (
          <div key={s.personId} className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary">{s.score}%</Badge>
            <span className="text-sm font-medium">{s.name ?? s.personId.slice(0,8)+'…'}</span>
            {s.available === false && <Badge variant="destructive">unavailable</Badge>}
            {s.reasons && s.reasons.length > 0 && (
              <span className="text-helper">
                {s.reasons.slice(0,3).map((r) => `${r.factor} +${r.points}`).join(' · ')}
              </span>
            )}
            <Button size="sm" variant="ghost" className="ml-auto"
              onClick={() => onPick(s, s.score, s.reasons)}>Request</Button>
          </div>
        ))}
      </div>
    </div>
  )
}
