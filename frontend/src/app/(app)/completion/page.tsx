'use client'

import { useState } from 'react'
import Link from 'next/link'
import { ArrowUpRight, Award, FileCheck2, GraduationCap, Sparkles } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { api } from '@/shared/api/client'

const SECTION_CAP = 12

function ShowMoreButton({ total, expanded, onToggle }: { total: number; expanded: boolean; onToggle: () => void }) {
  if (total <= SECTION_CAP) return null
  return (
    <Button size="sm" variant="ghost" className="mt-1.5" onClick={onToggle}>
      {expanded ? 'Show fewer' : `Show all ${total}`}
    </Button>
  )
}

interface ReadyRow { studentId: string; studentRef: string; personName: string; classification: string | null; publishedAt: string | null; hasCertificate: boolean; link: string }
interface PendingRow { studentId: string; studentRef: string; personName: string; classificationState: string; proposedClassification: string | null; link: string }
interface RecentRow { studentId: string; studentRef: string; personName: string; graduationDate: string; classification: string | null; link: string }
interface ClassCount { classification: string; count: number }

interface Pipeline {
  totals: {
    inPipeline: number
    readyToGraduate: number
    classificationPending: number
    recentlyGraduated: number
    certificatesPending: number
    recentWindowDays: number
  }
  byStatus: Record<string, number>
  byClassificationState: Record<string, number>
  byClassification: ClassCount[]
  readyToGraduate: ReadyRow[]
  classificationPending: PendingRow[]
  recentlyGraduated: RecentRow[]
}

function Tile({ label, value, tone }: { label: string; value: number | string; tone?: 'error' | 'warning' | 'success' }) {
  const toneCls =
    tone === 'error' ? 'text-[hsl(var(--destructive))]'
      : tone === 'warning' ? 'text-[hsl(var(--warning))]'
        : tone === 'success' ? 'text-[hsl(var(--success))]'
          : 'text-foreground'
  return (
    <div className="flex h-[70px] flex-col justify-between rounded-md bg-surface-2 px-3 py-2">
      <p className="truncate text-[10px] font-medium uppercase tracking-wide text-muted-foreground" title={label}>
        {label}
      </p>
      <p className={`text-lg num font-semibold leading-none ${toneCls}`}>{value}</p>
    </div>
  )
}

function PersonLink({ href, name, sub }: { href: string; name: string; sub?: string }) {
  return (
    <Link href={href}
      className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline">
      {name}
      <ArrowUpRight className="h-3.5 w-3.5" />
      {sub && <span className="text-helper ml-1 font-mono">{sub}</span>}
    </Link>
  )
}

const STATE_LABEL: Record<string, string> = {
  draft: 'Draft', proposed: 'Proposed', confirmed: 'Confirmed', published: 'Published',
}
const STATE_TONE: Record<string, 'secondary' | 'warning' | 'success'> = {
  draft: 'secondary', proposed: 'warning', confirmed: 'warning', published: 'success',
}

export default function CompletionPage() {
  const q = useQuery({
    queryKey: ['completion-pipeline'],
    queryFn: () => api.get<Pipeline>('/reports/completion-pipeline'),
  })
  const data = q.data
  const t = data?.totals
  const [expandReady, setExpandReady] = useState(false)
  const [expandPending, setExpandPending] = useState(false)
  const [expandRecent, setExpandRecent] = useState(false)

  return (
    <>
      <PageHeader title="Completion" />
      <div className="px-6 pb-6 space-y-4">
        {q.isLoading || !data ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <>
            {/* Actionable tiles */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
              <Tile label="In pipeline" value={t!.inPipeline} />
              <Tile label="Ready to graduate" value={t!.readyToGraduate}
                    tone={t!.readyToGraduate > 0 ? 'success' : undefined} />
              <Tile label="Classification pending" value={t!.classificationPending}
                    tone={t!.classificationPending > 0 ? 'warning' : undefined} />
              <Tile label={`Graduated · ${t!.recentWindowDays}d`} value={t!.recentlyGraduated} />
              <Tile label="Certificates pending" value={t!.certificatesPending}
                    tone={t!.certificatesPending > 0 ? 'warning' : undefined} />
            </div>

            {/* Ready to graduate */}
            <PageSection
              icon={GraduationCap}
              title={`Ready to graduate (${data.readyToGraduate.length})`}
              accent={data.readyToGraduate.length ? 'primary' : 'primary'}
              attention={data.readyToGraduate.length > 0}
              description="Classification is published; waiting on the graduation date."
            >
              {data.readyToGraduate.length === 0 ? (
                <p className="text-helper">Nobody waiting to graduate.</p>
              ) : (
                <ul className="divide-y divide-border/40 rounded-md border border-border/40">
                  {data.readyToGraduate.slice(0, expandReady ? undefined : SECTION_CAP).map((r) => (
                    <li key={r.studentId} className="flex items-center justify-between gap-3 px-3 py-2">
                      <div>
                        <PersonLink href={r.link} name={r.personName} sub={r.studentRef} />
                        <p className="text-helper">
                          {r.classification && <Badge variant="secondary" className="mr-2">{r.classification}</Badge>}
                          published {r.publishedAt?.slice(0, 10) ?? '—'}
                        </p>
                      </div>
                      {r.hasCertificate
                        ? <Badge variant="success">certificate ready</Badge>
                        : <Badge variant="warning">certificate pending</Badge>}
                    </li>
                  ))}
                </ul>
              )}
              <ShowMoreButton total={data.readyToGraduate.length} expanded={expandReady}
                onToggle={() => setExpandReady((v) => !v)} />
            </PageSection>

            {/* Classification pending */}
            <PageSection
              icon={FileCheck2}
              title={`Classification pending (${data.classificationPending.length})`}
              accent={data.classificationPending.length ? 'warning' : 'primary'}
              attention={data.classificationPending.length > 0}
              description="Thesis approved but classification not yet published — draft, proposed, or awaiting confirmation."
            >
              {data.classificationPending.length === 0 ? (
                <p className="text-helper">No thesis stuck at classification.</p>
              ) : (
                <ul className="divide-y divide-border/40 rounded-md border border-border/40">
                  {data.classificationPending.slice(0, expandPending ? undefined : SECTION_CAP).map((r) => (
                    <li key={r.studentId} className="flex items-center justify-between gap-3 px-3 py-2">
                      <div>
                        <PersonLink href={r.link} name={r.personName} sub={r.studentRef} />
                        {r.proposedClassification && (
                          <p className="text-helper">proposed: {r.proposedClassification}</p>
                        )}
                      </div>
                      <Badge variant={STATE_TONE[r.classificationState] ?? 'secondary'}>
                        {STATE_LABEL[r.classificationState] ?? r.classificationState}
                      </Badge>
                    </li>
                  ))}
                </ul>
              )}
              <ShowMoreButton total={data.classificationPending.length} expanded={expandPending}
                onToggle={() => setExpandPending((v) => !v)} />
            </PageSection>

            {/* Recently graduated */}
            <PageSection
              icon={Sparkles}
              title={`Recently graduated (${data.recentlyGraduated.length})`}
              accent="primary"
              description={`Graduations in the last ${t!.recentWindowDays} days — alumni handover.`}
            >
              {data.recentlyGraduated.length === 0 ? (
                <p className="text-helper">No recent graduations.</p>
              ) : (
                <ul className="divide-y divide-border/40 rounded-md border border-border/40">
                  {data.recentlyGraduated.slice(0, expandRecent ? undefined : SECTION_CAP).map((r) => (
                    <li key={r.studentId} className="flex items-center justify-between gap-3 px-3 py-2">
                      <div>
                        <PersonLink href={r.link} name={r.personName} sub={r.studentRef} />
                        {r.classification && <p className="text-helper">{r.classification}</p>}
                      </div>
                      <span className="text-sm num text-muted-foreground">{r.graduationDate}</span>
                    </li>
                  ))}
                </ul>
              )}
              <ShowMoreButton total={data.recentlyGraduated.length} expanded={expandRecent}
                onToggle={() => setExpandRecent((v) => !v)} />
            </PageSection>

            {/* Award distribution */}
            <PageSection
              icon={Award}
              title="Award distribution"
              accent="primary"
              description="Awards published so far, grouped by classification."
            >
              {data.byClassification.length === 0 ? (
                <p className="text-helper">Nothing published yet.</p>
              ) : (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  {data.byClassification.map((c) => (
                    <div key={c.classification}
                         className="flex items-center justify-between rounded-md bg-surface-2 px-3 py-2">
                      <span className="text-sm">{c.classification}</span>
                      <span className="num text-sm font-semibold">{c.count}</span>
                    </div>
                  ))}
                </div>
              )}
            </PageSection>
          </>
        )}
      </div>
    </>
  )
}
