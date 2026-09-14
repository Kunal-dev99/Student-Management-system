'use client'

/**
 * Digital Twin timeline (spec §5).
 *
 * A read-model timeline of longitudinal, cross-domain events for one student —
 * lifecycle changes, supervision engagement, funding integrity, model score change,
 * interventions, missing sources — plus predicted pressure points at the near-future
 * edge. Deterministic-first: every event is derived from an authoritative row and
 * carries its source reference so the user can jump to the record.
 *
 * The endpoint story: rather than one aggregate "twin events" endpoint, we compose
 * from the surfaces the platform already exposes (twin snapshot for pressure,
 * engagement events, milestones, supervision meetings). If a future backend adds
 * `/intelligence/twin/{id}/events` this component's shape is the target.
 */
import { useMemo } from 'react'
import {
  BadgeAlert, CircleDot, Coins, GraduationCap,
  MessageSquare, Sparkles, Wand2, Waypoints,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { AIStateBanner } from './AIStateBanner'
import { intelligenceApi, type EngagementTrajectory, type StudentTwinSnapshot } from './api'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/shared/api/client'
import type { Milestone } from '@/features/progression/api'
import type { SupervisionMeeting } from '@/features/supervision-meetings/api'

// ---- Timeline event types --------------------------------------------------

type EventKind =
  | 'lifecycle'    // registered, decided milestone, mode change, etc.
  | 'model'        // model score movement
  | 'funding'      // funding integrity state change
  | 'supervision'  // meeting logged, interval missed
  | 'intervention' // action taken / scheduled
  | 'missing'      // source unavailable — conclusion limited

export interface TimelineEvent {
  id: string
  kind: EventKind
  at: string             // ISO date/datetime
  title: string
  detail?: string
  reasonCode?: string    // for supervision events
  source?: { kind: string; id?: string; label?: string }
}

const KIND_META: Record<EventKind, {
  icon: typeof CircleDot; label: string
  ring: string           // ring color for the dot
  chip: 'success' | 'warning' | 'destructive' | 'secondary' | 'outline'
}> = {
  lifecycle:    { icon: GraduationCap,  label: 'Lifecycle',    ring: 'ring-emerald-500',                         chip: 'success' },
  model:        { icon: Waypoints,      label: 'Model signal', ring: 'ring-purple-500',                          chip: 'secondary' },
  funding:      { icon: Coins,          label: 'Funding',      ring: 'ring-destructive',                         chip: 'destructive' },
  supervision:  { icon: MessageSquare,  label: 'Supervision',  ring: 'ring-muted-foreground/60',                 chip: 'secondary' },
  intervention: { icon: Wand2,          label: 'Intervention', ring: 'ring-primary',                             chip: 'outline' },
  missing:      { icon: BadgeAlert,     label: 'Missing',      ring: 'ring-orange-500 [background:transparent]', chip: 'warning' },
}

// ---- Composition -----------------------------------------------------------

function composeEvents({
  twin, engagement, milestones, meetings,
}: {
  twin?: StudentTwinSnapshot | null
  engagement?: EngagementTrajectory | null
  milestones?: Milestone[]
  meetings?: SupervisionMeeting[]
}): TimelineEvent[] {
  const out: TimelineEvent[] = []

  // Lifecycle: milestone decisions. Decided milestones without a recorded decidedAt
  // (older seed rows, historical imports) still deserve to appear — anchor them to
  // the due date so the sequence still reads correctly.
  milestones?.forEach((m) => {
    if (m.status === 'decided') {
      const at = m.review?.decidedAt ?? m.dueDate
      if (!at) return
      out.push({
        id: `ms-dec-${m.id}`, kind: 'lifecycle', at,
        title: `${m.name} decided`,
        detail: m.review?.panelDecision?.replace(/_/g, ' ')
              ?? (m.review?.decidedAt ? undefined : 'decision date not recorded'),
        source: { kind: 'milestone', id: m.id, label: m.name },
      })
    } else if (m.status === 'overdue' && m.dueDate) {
      out.push({
        id: `ms-over-${m.id}`, kind: 'lifecycle', at: m.dueDate,
        title: `${m.name} overdue`,
        detail: `due ${m.dueDate}`,
        source: { kind: 'milestone', id: m.id, label: m.name },
      })
    } else if ((m.status === 'due' || m.status === 'submitted' || m.status === 'under_review') && m.dueDate) {
      out.push({
        id: `ms-${m.status}-${m.id}`, kind: 'lifecycle', at: m.dueDate,
        title: `${m.name} — ${m.status.replace('_', ' ')}`,
        source: { kind: 'milestone', id: m.id, label: m.name },
      })
    }
  })

  // Supervision meetings — deterministic contact markers
  meetings?.forEach((mtg) => {
    out.push({
      id: `mtg-${mtg.id}`, kind: 'supervision', at: mtg.metOn,
      title: 'Supervision meeting',
      detail: [mtg.supervisorName ?? 'Supervisor', mtg.format.replace('_', ' ')].join(' · '),
      reasonCode: 'meeting_logged',
      source: { kind: 'supervision_meeting', id: mtg.id },
    })
  })

  // Engagement events (interval_missed, commitment_completed, etc.)
  engagement?.recentEvents.forEach((e, i) => {
    if (e.kind === 'meeting_logged') return  // already covered above
    out.push({
      id: `eng-${i}-${e.occurredAt}`, kind: 'supervision', at: e.occurredAt,
      title: e.kind.replace(/_/g, ' '),
      detail: e.reasonCode ?? undefined,
      reasonCode: e.kind,
    })
  })

  // Model signals — one marker per target for the current snapshot
  twin?.modelSignals?.forEach((m) => {
    out.push({
      id: `mdl-${m.target}`, kind: 'model', at: twin.asOf,
      title: `${m.target.replace(/_/g, ' ')} · ${(m.probability * 100).toFixed(0)}%`,
      detail: `Model health: ${m.modelHealth}`,
      source: { kind: 'model_version', id: m.modelVersionId ?? undefined },
    })
  })

  // Missing sources — hollow orange markers keyed to today so they show up "now"
  twin?.blockers?.forEach((b) => {
    out.push({
      id: `missing-${b}`, kind: 'missing', at: twin.asOf,
      title: b,
      detail: 'Conclusion limited by this gap',
    })
  })

  // Sort oldest → newest so the timeline reads left-to-right / top-to-bottom in
  // chronological order like a story. Pressure points are rendered separately
  // as the "predicted" edge on the right.
  return out.sort((a, b) => a.at.localeCompare(b.at))
}

// ---- Component -------------------------------------------------------------

export interface TwinTimelineProps {
  studentId: string
  className?: string
}

export function TwinTimeline({ studentId, className }: TwinTimelineProps) {
  const twinQ = useQuery({
    queryKey: ['intel', 'twin', studentId],
    queryFn: () => intelligenceApi.twin(studentId, { enableLlm: false }),
  })
  const engagementQ = useQuery({
    queryKey: ['intel', 'engagement', studentId],
    queryFn: () => intelligenceApi.engagement(studentId),
    retry: false,
  })
  const milestonesQ = useQuery({
    queryKey: ['milestones', studentId],
    queryFn: () => api.get<Milestone[]>(`/students/${studentId}/milestones`),
    retry: false,
  })
  const meetingsQ = useQuery({
    queryKey: ['supervision-meetings', studentId],
    queryFn: () => api.get<SupervisionMeeting[]>(`/students/${studentId}/supervision-meetings`),
    retry: false,
  })

  const events = useMemo(() => composeEvents({
    twin: twinQ.data,
    engagement: engagementQ.data,
    milestones: milestonesQ.data,
    meetings: meetingsQ.data,
  }), [twinQ.data, engagementQ.data, milestonesQ.data, meetingsQ.data])

  const loading = twinQ.isLoading
  const error = twinQ.error as Error | undefined
  const pressureAhead = twinQ.data?.pressurePoints ?? []

  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles className="h-4 w-4 text-primary" />
              Student journey — what happened, what's next
            </CardTitle>
            <p className="text-xs text-muted-foreground mt-1 max-w-xl">
              Everything that has happened to this student across programme, supervision,
              funding — plus what we think will need attention next.
            </p>
          </div>
          {/* Legend sits with the title so the marker colours read as a KEY, not a
              footnote you find only after trying to decode the dots yourself. */}
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-muted-foreground max-w-sm justify-end">
            {(Object.keys(KIND_META) as EventKind[]).map((k) => {
              const meta = KIND_META[k]
              const Icon = meta.icon
              return (
                <span key={k} className="inline-flex items-center gap-1 whitespace-nowrap">
                  <span className={cn('inline-block h-2 w-2 rounded-full ring-2 bg-background', meta.ring)} />
                  <Icon className="h-3 w-3" aria-hidden /> {meta.label}
                </span>
              )
            })}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading ? (
          <div className="space-y-2"><Skeleton className="h-6 w-1/2" /><Skeleton className="h-24 w-full" /></div>
        ) : error ? (
          <AIStateBanner state="error" detail={error.message} />
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_16rem] gap-6">
            <div>
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-2">
                What has happened
              </p>
              <TimelineRail events={events} />
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-2">
                What we think will need attention next
              </p>
              <PressureAhead pressure={pressureAhead} asOf={twinQ.data?.asOf} />
              <p className="text-[10px] text-muted-foreground mt-2 leading-snug">
                This is the same signal the "PGR Intelligence" strip uses at the top of
                the page — plotted here over time.
              </p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ---- Sub-parts -------------------------------------------------------------

function TimelineRail({ events }: { events: TimelineEvent[] }) {
  if (events.length === 0) {
    return <p className="text-sm text-muted-foreground py-6">No timeline events yet — engagement, milestones and supervision meetings appear here as they land.</p>
  }
  return (
    <ol className="relative border-l border-border pl-6 space-y-4">
      {events.map((e) => {
        const meta = KIND_META[e.kind]
        const Icon = meta.icon
        return (
          <li key={e.id} className="relative">
            <span
              className={cn(
                'absolute -left-[1.85rem] top-1 h-3 w-3 rounded-full ring-2 bg-background',
                meta.ring,
              )}
              aria-hidden
            />
            <div className="flex items-baseline gap-2 flex-wrap">
              <time className="text-[11px] font-mono text-muted-foreground tabular-nums">
                {formatWhen(e.at)}
              </time>
              <Badge variant={meta.chip} className="gap-1 py-0 h-5">
                <Icon className="h-3 w-3" aria-hidden />
                {meta.label}
              </Badge>
              <p className="text-sm font-medium">{e.title}</p>
            </div>
            {e.detail ? <p className="text-xs text-muted-foreground pl-1 mt-0.5">{e.detail}</p> : null}
            {e.reasonCode && e.reasonCode !== e.detail ? (
              <p className="text-[10px] font-mono text-muted-foreground/70 pl-1">{e.reasonCode}</p>
            ) : null}
          </li>
        )
      })}
    </ol>
  )
}

function PressureAhead({ pressure, asOf }: { pressure: NonNullable<StudentTwinSnapshot['pressurePoints']>; asOf?: string }) {
  if (pressure.length === 0) {
    return (
      <aside className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
        No predicted pressure ahead.
      </aside>
    )
  }
  const top = pressure[0]
  const now = asOf ? new Date(asOf) : new Date()
  const daysAhead = top.when ? Math.max(0, Math.round((new Date(top.when).getTime() - now.getTime()) / 86_400_000)) : null
  return (
    <aside className="rounded-md border p-3 space-y-2 bg-primary/5">
      <p className="text-[10px] uppercase tracking-wide text-primary font-semibold flex items-center gap-1">
        <Sparkles className="h-3 w-3" /> Predicted pressure ahead
      </p>
      <p className="text-sm font-medium">{top.label}</p>
      <p className="text-xs text-muted-foreground">
        {top.kind.replace(/_/g, ' ')}
        {daysAhead !== null ? <> · {daysAhead} day{daysAhead === 1 ? '' : 's'} away</> : null}
        {top.when ? <> · {formatWhen(top.when)}</> : null}
      </p>
      {pressure.length > 1 ? (
        <ul className="pt-2 border-t space-y-1 text-xs">
          {pressure.slice(1, 5).map((p, i) => (
            <li key={i} className="flex items-baseline gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 mt-1 shrink-0" />
              <span className="flex-1 min-w-0 truncate">{p.label}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </aside>
  )
}

function formatWhen(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const now = new Date()
  const sameYear = d.getFullYear() === now.getFullYear()
  return sameYear
    ? d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
    : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}
