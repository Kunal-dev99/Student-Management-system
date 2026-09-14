'use client'

/**
 * Supervision Copilot — review extracted commitments (spec §10).
 *
 * Opens after a meeting's notes exist. Turns shorthand into proposed commitments
 * while preserving human ownership of the record:
 *   - Every proposed row is orange/"proposed" until the reviewer confirms it.
 *   - Null due dates render as "Not specified" — never silently inferred.
 *   - The reviewer can edit text/owner/due date, or drop a row entirely, before
 *     confirming. Nothing persists until "Confirm record".
 *   - Already-persisted commitments for this meeting are shown read-only above
 *     the proposal list so re-opening the drawer doesn't re-propose duplicates.
 */
import { useEffect, useState } from 'react'
import { CheckCircle2, Sparkles, Trash2 } from 'lucide-react'
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { AIStateBanner } from './AIStateBanner'
import { intelligenceApi, type ProposedCommitment, type SupervisionCommitment } from './api'

export interface CommitmentReviewDrawerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  meetingId: string
  studentId: string
  notes: string | null
}

interface DraftRow extends ProposedCommitment {
  include: boolean
}

export function CommitmentReviewDrawer({ open, onOpenChange, meetingId, studentId, notes }: CommitmentReviewDrawerProps) {
  const [existing, setExisting] = useState<SupervisionCommitment[] | null>(null)
  const [drafts, setDrafts] = useState<DraftRow[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  useEffect(() => {
    if (!open) return
    setDone(false)
    setError(null)
    setLoading(true)
    Promise.all([
      intelligenceApi.listCommitments(meetingId),
      notes ? intelligenceApi.proposeCommitments(meetingId, studentId, notes) : Promise.resolve([]),
    ])
      .then(([existingRows, proposed]) => {
        setExisting(existingRows)
        setDrafts(proposed.map((p) => ({ ...p, include: true })))
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [open, meetingId, studentId, notes])

  function updateDraft(i: number, patch: Partial<DraftRow>) {
    setDrafts((rows) => rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
  }
  function removeDraft(i: number) {
    setDrafts((rows) => rows.filter((_, idx) => idx !== i))
  }

  async function confirmRecord() {
    const toPersist = drafts.filter((d) => d.include && d.text.trim())
    if (toPersist.length === 0) { onOpenChange(false); return }
    setSaving(true); setError(null)
    try {
      await intelligenceApi.persistCommitments(
        meetingId, studentId,
        toPersist.map(({ text, ownerPersonOrRole, dueAt }) => ({
          text, ownerPersonOrRole,
          // `due_at` is a timestamptz column — a bare "YYYY-MM-DD" from <input type=date>
          // needs to be a full ISO datetime for the driver, not a date-only string.
          dueAt: dueAt ? `${dueAt}T00:00:00Z` : null,
        })),
      )
      setDone(true)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const activeCount = drafts.filter((d) => d.include).length

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-2xl overflow-y-auto">
        <SheetHeader>
          <SheetTitle>Review meeting record and commitments</SheetTitle>
          <SheetDescription>
            Review extracted commitments before they become part of the record.
          </SheetDescription>
        </SheetHeader>

        {error ? <AIStateBanner state="error" detail={error} className="mt-4" /> : null}

        {done ? (
          <div className="mt-6 flex items-start gap-2 rounded-md border border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/20 px-3 py-2 text-sm text-emerald-900 dark:text-emerald-200">
            <CheckCircle2 className="h-4 w-4 mt-0.5 shrink-0" aria-hidden />
            <span>Commitments confirmed and added to the record.</span>
          </div>
        ) : loading ? (
          <div className="mt-4 space-y-2"><Skeleton className="h-16 w-full" /><Skeleton className="h-16 w-full" /></div>
        ) : (
          <>
            {existing && existing.length > 0 ? (
              <section className="mt-4">
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-2">
                  Already confirmed
                </p>
                <ul className="space-y-1.5">
                  {existing.map((c) => (
                    <li key={c.id} className="rounded-md border p-2 text-sm bg-muted/30">
                      <span className="font-medium">{c.text}</span>
                      <span className="text-xs text-muted-foreground ml-2">
                        {c.ownerPersonOrRole ? `Owner: ${c.ownerPersonOrRole}` : 'Owner: Not specified'}
                        {' · '}
                        {c.dueAt ? `Due: ${new Date(c.dueAt).toLocaleDateString()}` : 'Due: Not specified'}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            <section className="mt-4">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-2 inline-flex items-center gap-1">
                <Sparkles className="h-3 w-3" /> Proposed from meeting notes
              </p>
              {!notes ? (
                <p className="text-sm text-muted-foreground">This meeting has no notes to extract from.</p>
              ) : drafts.length === 0 ? (
                <p className="text-sm text-muted-foreground">No action-shaped lines found in the notes.</p>
              ) : (
                <ul className="space-y-3">
                  {drafts.map((d, i) => (
                    <li key={i} className={`rounded-md border p-2.5 space-y-2 ${
                      d.include ? 'border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/10' : 'opacity-50'
                    }`}>
                      <div className="flex items-start gap-2">
                        <input
                          type="checkbox"
                          className="mt-1"
                          checked={d.include}
                          onChange={(e) => updateDraft(i, { include: e.target.checked })}
                          aria-label={`Include commitment: ${d.text}`}
                        />
                        <div className="flex-1 min-w-0 space-y-1.5">
                          <div className="flex items-center gap-1.5">
                            <Badge variant="warning" className="text-[10px]">Proposed</Badge>
                            <span className="text-[10px] text-muted-foreground">Do not invent — edit if wrong</span>
                          </div>
                          <Input
                            value={d.text}
                            onChange={(e) => updateDraft(i, { text: e.target.value })}
                            className="text-sm h-8"
                          />
                          <div className="flex gap-2">
                            <Input
                              placeholder="Owner (not specified)"
                              value={d.ownerPersonOrRole ?? ''}
                              onChange={(e) => updateDraft(i, { ownerPersonOrRole: e.target.value || null })}
                              className="text-xs h-7 flex-1"
                            />
                            <Input
                              type="date"
                              value={d.dueAt ?? ''}
                              onChange={(e) => updateDraft(i, { dueAt: e.target.value || null })}
                              className="text-xs h-7 w-40"
                              title="Due date — not specified unless the notes said so"
                            />
                          </div>
                        </div>
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => removeDraft(i)}
                                aria-label="Remove this proposed commitment">
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <div className="mt-6 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
              <Button onClick={confirmRecord} disabled={saving}>
                {saving ? 'Confirming…' : `Confirm record${activeCount ? ` (${activeCount})` : ''}`}
              </Button>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}
