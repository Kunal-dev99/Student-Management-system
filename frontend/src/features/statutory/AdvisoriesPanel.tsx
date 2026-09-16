'use client'

/**
 * ICR G5 — statutory advisory ingestion review surface.
 *
 * The Registry pastes a published HESA advisory; the platform parses it into a deterministic diff
 * against the current spec pack, shown here for review. Only a Registry owner (reports.signoff)
 * accepting an advisory makes its proposed pack the active version — the same trust boundary as
 * signing off a return. Nothing here scrapes anything.
 */
import { useState, type ReactNode } from 'react'
import { CheckCircle2, FileUp, ListTree, ShieldCheck, XCircle } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { useToast } from '@/components/ui/use-toast'
import { ApiError } from '@/shared/api/client'
import {
  useAcceptAdvisory, useAdvisories, useIngestAdvisory, useRejectAdvisory,
  type Advisory, type AdvisoryChange, type ChangeType,
} from '@/features/statutory/api'

const CHANGE_LABEL: Record<ChangeType, string> = {
  field_added: 'Field added',
  field_removed: 'Field removed',
  coding_changed: 'Coding changed',
  description_changed: 'Description',
  rule_added: 'Rule added',
  rule_removed: 'Rule removed',
}

const CHANGE_VARIANT: Record<ChangeType, 'success' | 'destructive' | 'warning' | 'info' | 'secondary'> = {
  field_added: 'success',
  field_removed: 'destructive',
  coding_changed: 'warning',
  description_changed: 'info',
  rule_added: 'success',
  rule_removed: 'destructive',
}

const STATUS_VARIANT: Record<Advisory['status'], 'secondary' | 'success' | 'destructive'> = {
  ingested: 'secondary',
  accepted: 'success',
  rejected: 'destructive',
}

/** A coding frame (list of codes) as a compact string, or '—'. */
function codes(v: unknown): string {
  if (Array.isArray(v)) return v.length ? v.join(', ') : '—'
  return '—'
}

function ChangeRow({ c }: { c: AdvisoryChange }) {
  const before = c.before as Record<string, unknown> | unknown[] | string | null
  const after = c.after as Record<string, unknown> | unknown[] | string | null

  let detail: ReactNode = null
  if (c.type === 'coding_changed') {
    detail = <span className="num">{codes(before)} → {codes(after)}</span>
  } else if (c.type === 'description_changed') {
    detail = <span>“{String(before ?? '')}” → “{String(after ?? '')}”</span>
  } else if (c.type === 'field_added' && after && typeof after === 'object' && !Array.isArray(after)) {
    const a = after as Record<string, unknown>
    detail = (
      <span>
        {String(a.description ?? '')}
        {Array.isArray(a.allowed) && a.allowed.length > 0 && (
          <span className="text-helper num"> · coding {a.allowed.join(', ')}</span>
        )}
      </span>
    )
  } else if ((c.type === 'rule_added' || c.type === 'rule_removed')) {
    const r = (c.type === 'rule_added' ? after : before) as Record<string, unknown> | null
    detail = r ? <span className="num">{String(r.kind)} {Array.isArray(r.fields) ? r.fields.join(' ') : ''}</span> : null
  }

  return (
    <div className="flex flex-wrap items-baseline gap-2 py-1.5 border-b border-border/50 last:border-0">
      <Badge variant={CHANGE_VARIANT[c.type]}>{CHANGE_LABEL[c.type]}</Badge>
      {c.field && <span className="font-mono text-xs font-medium">{c.field}</span>}
      <span className="text-sm">{detail}</span>
      <span className="text-helper ml-auto">{c.note}</span>
    </div>
  )
}

const SAMPLE = `YEAR: 2027/28
ADD FIELD SEXORT "Sexual orientation" coding=[10,11,12,13,98] keyed_at="Person › sexual orientation"
CODING MODE = [01,02,03,31,99]
DESC STULOAD "Student instance load (FTE, revised 2027/28)"`

function IngestDialog() {
  const { toast } = useToast()
  const ingest = useIngestAdvisory()
  const [open, setOpen] = useState(false)
  const [packCode, setPackCode] = useState('HESA_STUDENT')
  const [academicYear, setAcademicYear] = useState('')
  const [title, setTitle] = useState('')
  const [rawText, setRawText] = useState('')

  const reset = () => { setPackCode('HESA_STUDENT'); setAcademicYear(''); setTitle(''); setRawText('') }

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) reset() }}>
      <DialogTrigger asChild>
        <Button size="sm"><FileUp className="h-4 w-4 mr-1" /> Ingest advisory</Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader><DialogTitle>Ingest a published statutory advisory</DialogTitle></DialogHeader>
        <p className="text-helper -mt-1">
          Paste the advisory as change directives. It is parsed into a diff against the current pack
          for review — nothing takes effect until a Registry owner accepts it.
        </p>
        <div className="grid grid-cols-2 gap-3 py-1">
          <div className="space-y-1.5">
            <Label htmlFor="a-code">Return code</Label>
            <Input id="a-code" value={packCode} onChange={(e) => setPackCode(e.target.value)} placeholder="HESA_STUDENT" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="a-year">Academic year (optional)</Label>
            <Input id="a-year" value={academicYear} onChange={(e) => setAcademicYear(e.target.value)}
              placeholder="from a YEAR: line, or set here" />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="a-title">Title (optional)</Label>
          <Input id="a-title" value={title} onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. HESA Student 2027/28 coding manual changes" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="a-text">Advisory directives</Label>
          <Textarea id="a-text" className="min-h-[160px] font-mono text-xs" value={rawText}
            onChange={(e) => setRawText(e.target.value)} placeholder={SAMPLE} />
          <p className="text-helper">
            Grammar: <span className="font-mono">ADD FIELD NAME &quot;desc&quot; coding=[a,b]</span>,{' '}
            <span className="font-mono">REMOVE FIELD NAME</span>,{' '}
            <span className="font-mono">CODING NAME = [a,b]</span>,{' '}
            <span className="font-mono">DESC NAME &quot;desc&quot;</span>,{' '}
            <span className="font-mono">RULE order F1 F2 &quot;message&quot;</span>. Lines that don&apos;t
            match become warnings, never silent changes.
          </p>
        </div>
        <DialogFooter>
          <Button
            disabled={!packCode.trim() || !rawText.trim() || ingest.isPending}
            onClick={async () => {
              try {
                const adv = await ingest.mutateAsync({
                  packCode: packCode.trim(),
                  academicYear: academicYear.trim() || undefined,
                  title: title.trim() || undefined,
                  rawText,
                })
                const warned = adv.parseWarnings?.length
                  ? ` (${adv.parseWarnings.length} warning${adv.parseWarnings.length === 1 ? '' : 's'})`
                  : ''
                toast({
                  title: `Parsed ${adv.changes.length} change${adv.changes.length === 1 ? '' : 's'}${warned}`,
                  description: `${adv.packCode} ${adv.academicYear} — review and accept below.`,
                })
                setOpen(false); reset()
              } catch (e) {
                toast({ title: 'Could not ingest advisory', description: (e as ApiError).message, variant: 'destructive' })
              }
            }}>
            {ingest.isPending ? 'Parsing…' : 'Parse advisory'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function AdvisoryCard({ advisory, canSignOff }: { advisory: Advisory; canSignOff: boolean }) {
  const { toast } = useToast()
  const accept = useAcceptAdvisory()
  const reject = useRejectAdvisory()
  const [open, setOpen] = useState(false)

  const pending = advisory.status === 'ingested'

  return (
    <div className="rounded-md border border-border/60 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="flex items-center gap-2 text-left"
          onClick={() => setOpen((v) => !v)}>
          <ListTree className="h-4 w-4 text-muted-foreground" />
          <span className="font-medium">{advisory.title}</span>
        </button>
        <span className="font-mono text-xs text-muted-foreground">{advisory.packCode}</span>
        <Badge variant="outline" className="num">{advisory.academicYear}</Badge>
        <Badge variant={STATUS_VARIANT[advisory.status]}>{advisory.status}</Badge>
        <span className="text-helper num">
          {advisory.changes.length} change{advisory.changes.length === 1 ? '' : 's'}
        </span>
        {advisory.parseSource === 'model' && <Badge variant="info">AI-extracted</Badge>}
        {pending && canSignOff && (
          <div className="ml-auto flex items-center gap-2">
            <Button size="sm" variant="outline"
              disabled={reject.isPending}
              onClick={async () => {
                try {
                  await reject.mutateAsync({ id: advisory.id })
                  toast({ title: 'Advisory rejected' })
                } catch (e) { toast({ title: 'Could not reject', description: (e as ApiError).message, variant: 'destructive' }) }
              }}>
              <XCircle className="h-4 w-4 mr-1" /> Reject
            </Button>
            <Button size="sm"
              disabled={accept.isPending || advisory.changes.length === 0}
              onClick={async () => {
                try {
                  const v = await accept.mutateAsync({ id: advisory.id })
                  toast({ title: `Accepted — now active v${v.version}`, description: `${advisory.packCode} ${v.academicYear}` })
                } catch (e) { toast({ title: 'Could not accept', description: (e as ApiError).message, variant: 'destructive' }) }
              }}>
              <ShieldCheck className="h-4 w-4 mr-1" /> Accept
            </Button>
          </div>
        )}
        {!pending && advisory.decidedAt && (
          <span className="text-helper ml-auto">
            {advisory.status} {new Date(advisory.decidedAt).toLocaleDateString()}
            {advisory.decisionNote ? ` — ${advisory.decisionNote}` : ''}
          </span>
        )}
      </div>

      {open && (
        <div className="mt-3 pl-6">
          {advisory.changes.length === 0 ? (
            <p className="text-helper">No changes were recognised in this advisory.</p>
          ) : (
            <div>{advisory.changes.map((c, i) => <ChangeRow key={i} c={c} />)}</div>
          )}
          {advisory.parseWarnings && advisory.parseWarnings.length > 0 && (
            <div className="mt-2 text-xs text-[hsl(var(--warning))]">
              {advisory.parseWarnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function AdvisoriesPanel({ canConfigure, canSignOff }: {
  canConfigure: boolean
  canSignOff: boolean
}) {
  const advisories = useAdvisories()
  const rows = advisories.data?.advisories ?? []

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-helper max-w-2xl">
          Ingest a published advisory to see exactly what it changes for a return, then a Registry
          owner accepts it — acceptance makes the proposed pack the active spec version everywhere
          (the from-spec picker, validation and the sign-off gate).
        </p>
        {canConfigure && <IngestDialog />}
      </div>

      {advisories.isLoading ? (
        <Skeleton className="h-20 w-full" />
      ) : advisories.isError ? (
        <p className="text-sm text-[hsl(var(--destructive))]">{(advisories.error as ApiError)?.message}</p>
      ) : rows.length === 0 ? (
        <p className="text-helper inline-flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4" /> No advisories ingested yet.
        </p>
      ) : (
        <div className="space-y-2">
          {rows.map((a) => <AdvisoryCard key={a.id} advisory={a} canSignOff={canSignOff} />)}
        </div>
      )}
    </div>
  )
}
