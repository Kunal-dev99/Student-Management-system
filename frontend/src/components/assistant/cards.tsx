'use client'

/**
 * Card renderers per `answer.card.spec`. Each intent binds to a spec id at classification
 * time and the assistant emits the tool payload as `card.data`. This file keeps the palette
 * itself readable by moving spec dispatch out of the message loop.
 *
 * The generic fallback still renders a compact summary when no dedicated renderer exists,
 * so a brand-new intent never lands with a blank card.
 */
import Link from 'next/link'
import {
  ArrowUpRight,
  Banknote,
  Ban,
  Building2,
  Clock,
  FileWarning,
  MessagesSquare,
  UsersRound,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import type { AssistantAnswer } from '@/features/assistant/api'

type CardData = Record<string, unknown>

function money(v: unknown, currency: unknown): string {
  const n = typeof v === 'string' ? Number(v) : typeof v === 'number' ? v : NaN
  if (Number.isNaN(n)) return String(v ?? '—')
  const c = typeof currency === 'string' ? currency : 'GBP'
  return `${c} ${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function Tile({ label, value, tone }: { label: string; value: string | number; tone?: 'error' | 'warning' | 'success' }) {
  const toneCls =
    tone === 'error' ? 'text-[hsl(var(--destructive))]'
      : tone === 'warning' ? 'text-[hsl(var(--warning))]'
        : tone === 'success' ? 'text-[hsl(var(--success))]'
          : 'text-foreground'
  return (
    <div className="rounded-md bg-surface-2 px-3 py-2">
      <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={`text-base num font-semibold ${toneCls}`}>{value}</p>
    </div>
  )
}

function PersonLink({ href, name, sub, onNavigate }:
  { href: string; name: string; sub?: string; onNavigate: () => void }) {
  return (
    <Link
      href={href}
      onClick={onNavigate}
      className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
    >
      {name}
      <ArrowUpRight className="h-3.5 w-3.5" />
      {sub && <span className="text-helper ml-1">{sub}</span>}
    </Link>
  )
}

// ---------- Finance lens ----------

interface FinanceRow {
  paymentId: string; personName: string; studentRef?: string; amount: string; currency?: string
  dueDate?: string | null; paidOn?: string | null; note?: string | null; daysOverdue?: number
  link: string
}

function FinancePaymentList({
  rows, tone, emptyMsg, onNavigate,
}: { rows: FinanceRow[]; tone?: 'error' | 'warning'; emptyMsg: string; onNavigate: () => void }) {
  if (!rows || rows.length === 0) {
    return <p className="text-helper">{emptyMsg}</p>
  }
  return (
    <ul className="mt-2 divide-y divide-border/40 rounded-lg bg-surface-2/40 border border-border/40">
      {rows.slice(0, 8).map((r) => (
        <li key={r.paymentId} className="flex items-center justify-between gap-3 px-3 py-2">
          <div className="min-w-0 space-y-0.5">
            <PersonLink href={r.link} name={r.personName} sub={r.studentRef} onNavigate={onNavigate} />
            {r.note && <p className="text-helper truncate">{r.note}</p>}
            {r.daysOverdue != null && (
              <Badge variant={tone === 'error' ? 'destructive' : 'warning'}>{r.daysOverdue} days overdue</Badge>
            )}
          </div>
          <div className="shrink-0 text-right">
            <p className="text-sm num font-medium">{money(r.amount, r.currency)}</p>
            <p className="text-helper num">{r.dueDate ? `due ${r.dueDate}` : r.paidOn ? `paid ${r.paidOn}` : '—'}</p>
          </div>
        </li>
      ))}
    </ul>
  )
}

function FinanceLensTotals({ data }: { data: CardData }) {
  const totals = (data.totals ?? {}) as Record<string, string>
  const w = (data.window ?? {}) as { from?: string; to?: string }
  return (
    <div className="mt-2 space-y-2">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Tile label="Paid" value={money(totals.paid, 'GBP')} tone="success" />
        <Tile label="Approved" value={money(totals.approved, 'GBP')} />
        <Tile label="Held" value={money(totals.held, 'GBP')} tone="error" />
        <Tile label="Scheduled" value={money(totals.scheduled, 'GBP')} />
      </div>
      <p className="text-helper num">{w.from} → {w.to}</p>
    </div>
  )
}

// ---------- Workforce ----------

function WorkforceStrip({ data, onNavigate }: { data: CardData; onNavigate: () => void }) {
  const t = (data.totals ?? {}) as Record<string, number>
  const rows = (data.supervisors as Array<{
    personId: string; personName: string; caseload: number; maxStudents: number;
    overCapacity: boolean; pendingRequests: number; link: string
  }>) ?? []
  return (
    <div className="mt-2 space-y-2">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Tile label="Supervisors" value={t.supervisors ?? 0} />
        <Tile label="Over cap" value={t.overCapacity ?? 0} tone={t.overCapacity ? 'error' : undefined} />
        <Tile label="Pending" value={t.pendingRequests ?? 0} tone={t.pendingRequests ? 'warning' : undefined} />
        <Tile label="Utilisation" value={`${t.utilisationPct ?? 0}%`} />
      </div>
      {rows.length > 0 && (
        <ul className="divide-y divide-border/40 rounded-lg bg-surface-2/40 border border-border/40">
          {rows.slice(0, 6).map((r) => (
            <li key={r.personId} className="flex items-center justify-between px-3 py-1.5">
              <PersonLink href={r.link} name={r.personName} onNavigate={onNavigate} />
              <div className="flex items-center gap-2">
                {r.overCapacity && <Badge variant="destructive">over cap</Badge>}
                {r.pendingRequests > 0 && (
                  <Badge variant="secondary">{r.pendingRequests} pending</Badge>
                )}
                <span className="text-sm num text-muted-foreground">{r.caseload}/{r.maxStudents}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ---------- Task list ----------

function TaskList({ data, onNavigate }: { data: CardData; onNavigate: () => void }) {
  const tasks = (data.tasks as Array<{ id: string; title: string; link?: string }>) ?? []
  if (tasks.length === 0) return <p className="text-helper mt-2">Nothing on your plate.</p>
  return (
    <ul className="mt-2 divide-y divide-border/40 rounded-lg bg-surface-2/40 border border-border/40">
      {tasks.slice(0, 8).map((t) => (
        <li key={t.id} className="flex items-center justify-between px-3 py-1.5">
          <span className="text-sm">{t.title}</span>
          {t.link && (
            <Link href={t.link} onClick={onNavigate}
              className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
              open <ArrowUpRight className="h-3 w-3" />
            </Link>
          )}
        </li>
      ))}
    </ul>
  )
}

// ---------- Analytics tiles ----------

function AnalyticsTiles({ data }: { data: CardData }) {
  const risk = (data.risk ?? {}) as Record<string, number>
  const comp = (data.completion ?? {}) as Record<string, number>
  return (
    <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2">
      <Tile label="At risk" value={risk.atRiskCount ?? 0}
            tone={(risk.atRiskCount ?? 0) > 0 ? 'warning' : 'success'} />
      <Tile label="Active" value={risk.activeStudents ?? 0} />
      <Tile label="Completion" value={`${comp.completionRatePct ?? 0}%`} />
      <Tile label="Cohort" value={comp.cohortSize ?? 0} />
    </div>
  )
}

// ---------- Student summary ----------

function StudentSummary({ data, onNavigate }: { data: CardData; onNavigate: () => void }) {
  const st = (data.student ?? {}) as Record<string, unknown>
  const comp = (data.supervisionCompliance ?? {}) as Record<string, unknown>
  const link = typeof st.link === 'string' ? st.link : '#'
  return (
    <div className="mt-2 rounded-lg bg-surface-2/40 p-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <PersonLink href={link} name={String(st.personName ?? 'Unknown')} sub={String(st.studentRef ?? '')} onNavigate={onNavigate} />
        <Badge variant="secondary">{String(st.status ?? '').replace(/_/g, ' ')}</Badge>
      </div>
      {Array.isArray(st.supervisors) && (
        <p className="text-helper">
          {st.supervisors.length} supervisor{st.supervisors.length === 1 ? '' : 's'}
        </p>
      )}
      {comp.overdue ? (
        <Badge variant="warning">supervision overdue (last: {String(comp.lastMeetingOn ?? 'never')})</Badge>
      ) : null}
    </div>
  )
}

// ---------- Help surface ----------

function HelpSurface({ data, onSuggest }: { data: CardData; onSuggest: (q: string) => void }) {
  const groups = (data.groups as Array<{ name: string; intents: Array<{ name: string; description: string; examples: string[] }> }>) ?? []
  return (
    <div className="mt-2 space-y-3">
      {groups.map((g) => (
        <div key={g.name}>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{g.name}</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {g.intents.flatMap((i) =>
              i.examples.slice(0, 1).map((ex) => (
                <button
                  key={`${i.name}-${ex}`}
                  type="button"
                  onClick={() => onSuggest(ex)}
                  className="rounded-md border border-border bg-surface-2 px-2 py-0.5 text-xs transition-colors hover:border-foreground/30"
                  title={i.description}
                >
                  {ex}
                </button>
              )),
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

// ---------- Nav target ----------

function NavTargetCard({ data }: { data: CardData }) {
  const label = String(data.label ?? 'that page')
  const href = typeof data.link === 'string' ? data.link : String(data.target ?? '#')
  return (
    <p className="text-helper mt-1">
      Opening <span className="font-mono">{label}</span> at <span className="font-mono">{href}</span>.
    </p>
  )
}

// ---------- Dispatcher ----------

/** Card icon by spec — pretty header for each specialised renderer. */
const CARD_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  finance_lens_held: Ban,
  finance_lens_overdue: Clock,
  finance_lens_drift: FileWarning,
  finance_lens_totals: Banknote,
  workforce_strip: UsersRound,
  task_list: MessagesSquare,
  student_summary: Building2,
}

export function AssistantCard({
  answer, onNavigate, onSuggest,
}: {
  answer: AssistantAnswer
  onNavigate: () => void
  onSuggest: (q: string) => void
}) {
  const card = answer.card
  if (!card) return null
  const data = (card.data ?? {}) as CardData
  const Icon = CARD_ICON[card.spec]

  // Special spec dispatch.
  let body: React.ReactNode = null
  switch (card.spec) {
    case 'finance_lens_held':
      body = <FinancePaymentList rows={(data.held as FinanceRow[]) ?? []}
                                  tone="error" emptyMsg="Nothing held."
                                  onNavigate={onNavigate} />
      break
    case 'finance_lens_overdue':
      body = <FinancePaymentList rows={(data.overdueApproved as FinanceRow[]) ?? []}
                                  tone="warning" emptyMsg="Nothing overdue."
                                  onNavigate={onNavigate} />
      break
    case 'finance_lens_drift':
      body = <FinancePaymentList rows={(data.paidWithoutFinanceReference as FinanceRow[]) ?? []}
                                  emptyMsg="No drift — every paid instalment has a reference."
                                  onNavigate={onNavigate} />
      break
    case 'finance_lens_totals':
      body = <FinanceLensTotals data={data} />
      break
    case 'workforce_strip':
      body = <WorkforceStrip data={data} onNavigate={onNavigate} />
      break
    case 'task_list':
      body = <TaskList data={data} onNavigate={onNavigate} />
      break
    case 'analytics_tiles':
      body = <AnalyticsTiles data={data} />
      break
    case 'student_summary':
      body = <StudentSummary data={data} onNavigate={onNavigate} />
      break
    case 'help_surface':
      body = <HelpSurface data={data} onSuggest={onSuggest} />
      break
    case 'nav_target':
      body = <NavTargetCard data={data} />
      break
  }

  if (!body) return null
  return (
    <div className="mt-2">
      {Icon && (
        <div className="mb-1 inline-flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          <Icon className="h-3 w-3" />
          {card.spec.replace(/_/g, ' ')}
        </div>
      )}
      {body}
    </div>
  )
}
