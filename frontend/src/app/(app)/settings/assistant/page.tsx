'use client'

/**
 * CB-C — Assistant vocab review.
 *
 * Every query that Ask PGR flagged as clarify or not_understood (with names/emails/refs
 * scrubbed) is listed here. An admin either assigns the phrasing to an existing intent
 * (a note explains what synonym to add) or marks it "reviewed — not worth adding".
 */

import { useState } from 'react'
import { CheckCircle2, MessageSquareWarning } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { useToast } from '@/components/ui/use-toast'
import {
  useAssignTelemetry,
  useAssistantHelp,
  useAssistantTelemetry,
  type TelemetryEntry,
} from '@/features/assistant/api'

function EntryRow({ entry, intentNames }: { entry: TelemetryEntry; intentNames: string[] }) {
  const { toast } = useToast()
  const assign = useAssignTelemetry()
  const [intent, setIntent] = useState<string>(entry.assignedIntent ?? '')
  const [note, setNote] = useState<string>(entry.synonymNote ?? '')

  const save = async (assigned: string | null) => {
    try {
      await assign.mutateAsync({ id: entry.id, assignedIntent: assigned, synonymNote: note || null })
      toast({ title: assigned ? `Assigned to ${assigned}` : 'Marked reviewed' })
    } catch (e) {
      toast({ title: 'Save failed', description: (e as Error).message, variant: 'destructive' })
    }
  }

  return (
    <div className="border-b border-border/60 last:border-0 py-3 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm">{entry.queryRedacted}</span>
        {entry.sessionRole && <Badge variant="outline">{entry.sessionRole}</Badge>}
        <span className="text-helper">{entry.createdAt}</span>
      </div>
      {entry.suggestedIntents && entry.suggestedIntents.length > 0 && (
        <p className="text-helper">
          closest: {entry.suggestedIntents.map((s) => `${s.name}(${s.score.toFixed(2)})`).join(' · ')}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Input
          list={`intents-${entry.id}`}
          value={intent}
          onChange={(e) => setIntent(e.target.value)}
          placeholder="assign to intent (or leave blank to skip)"
          className="h-8 w-64 text-sm"
        />
        <datalist id={`intents-${entry.id}`}>
          {intentNames.map((n) => <option key={n} value={n} />)}
        </datalist>
        <Textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="synonym note (e.g. add 'chase up' to overdue_payments)"
          className="min-h-[36px] flex-1 text-sm"
        />
        <Button size="sm" onClick={() => save(intent || null)} disabled={assign.isPending}>
          {assign.isPending ? 'Saving…' : intent ? 'Assign' : 'Mark reviewed'}
        </Button>
      </div>
    </div>
  )
}

export default function AssistantVocabReviewPage() {
  const [unreviewedOnly, setUnreviewedOnly] = useState(true)
  const q = useAssistantTelemetry(unreviewedOnly)
  const help = useAssistantHelp()
  const intentNames = (help.data?.groups ?? []).flatMap((g) => g.intents.map((i) => i.name))

  return (
    <>
      <PageHeader
        title="Assistant vocab review"
        description="CB-C — every query Ask PGR flagged as clarify or not_understood. Grow the vocabulary from real user phrasings, or mark reviewed if there's no fit."
      />
      <div className="px-6 pb-6 space-y-4">
        <div className="flex items-center gap-2">
          <Button size="sm" variant={unreviewedOnly ? 'default' : 'outline'}
            onClick={() => setUnreviewedOnly(true)}>
            Unreviewed
          </Button>
          <Button size="sm" variant={unreviewedOnly ? 'outline' : 'default'}
            onClick={() => setUnreviewedOnly(false)}>
            All
          </Button>
        </div>

        <PageSection
          icon={unreviewedOnly ? MessageSquareWarning : CheckCircle2}
          title={`Queries (${q.data?.entries.length ?? 0})`}
          accent={q.data?.entries.length ? 'warning' : 'primary'}
          description="Redacted before write — no names, emails, IDs, or student refs are stored."
        >
          {q.isLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : q.data?.entries.length === 0 ? (
            <p className="text-helper">
              {unreviewedOnly
                ? 'Nothing new to review — every recent gap has been handled.'
                : 'No telemetry yet.'}
            </p>
          ) : (
            q.data?.entries.map((e) => (
              <EntryRow key={e.id} entry={e} intentNames={intentNames} />
            ))
          )}
        </PageSection>
      </div>
    </>
  )
}
