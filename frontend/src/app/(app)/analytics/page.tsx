'use client'

import { useMemo, useState } from 'react'
import { AlertTriangle, Globe, TrendingUp } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { SearchInput } from '@/components/common/SearchInput'
import { FilterChips } from '@/components/common/FilterChips'
import { Pagination } from '@/components/common/Pagination'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useAnalytics, useEnterprise360, type Enterprise360Row } from '@/features/analytics/api'

const E360_PAGE_SIZE = 50

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="card-elevated p-4">
      <p className="text-label">{label}</p>
      <p className="mt-1 text-2xl font-semibold tracking-tight num">{value}</p>
      {hint && <p className="text-helper mt-0.5">{hint}</p>}
    </div>
  )
}

const LENSES: { key: string; label: string; cols: string[]; row: (r: Enterprise360Row) => (string | JSX.Element)[] }[] = [
  { key: 'student', label: 'Student', cols: ['Student', 'Status', 'Mode', 'Start'],
    row: (r) => [`${r.personName} · ${r.studentRef}`, r.student.status, r.student.studyMode.replace(/_/g, ' '), r.student.startDate ?? '—'] },
  { key: 'research', label: 'Research', cols: ['Student', 'Area', 'Topic', 'Group'],
    row: (r) => [r.personName, r.research.area ?? '—', r.research.topic ?? '—', r.research.group ?? '—'] },
  { key: 'funding', label: 'Funding', cols: ['Student', 'Type', 'Source', 'Amount'],
    row: (r) => [r.personName, r.funding?.type.replace(/_/g, ' ') ?? '—', r.funding?.source ?? '—',
      r.funding ? `${r.funding.currency ?? ''} ${r.funding.amount ? Number(r.funding.amount).toLocaleString() : ''}`.trim() : '—'] },
  { key: 'workforce', label: 'Workforce', cols: ['Student', 'Also an employee?'],
    row: (r) => [r.personName, r.workforce.isEmployee ? 'yes' : 'no'] },
  { key: 'statutory', label: 'Statutory', cols: ['Student', 'Nationality', 'Programme', 'Expected end'],
    row: (r) => [r.personName, r.statutory.nationality ?? '—', r.statutory.programme ?? '—', r.statutory.expectedEnd ?? '—'] },
]

export default function AnalyticsPage() {
  const analytics = useAnalytics()
  const e360 = useEnterprise360()
  const a = analytics.data

  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [offset, setOffset] = useState(0)

  const statusOptions = useMemo(() => {
    const statuses = Array.from(new Set((e360.data?.population ?? []).map((r) => r.student.status))).sort()
    return [{ value: 'all', label: 'All' }, ...statuses.map((s) => ({ value: s, label: s.replace(/_/g, ' ') }))]
  }, [e360.data])

  const filteredPopulation = useMemo(() => {
    const rows = e360.data?.population ?? []
    const q = search.trim().toLowerCase()
    return rows.filter((r) => {
      if (statusFilter !== 'all' && r.student.status !== statusFilter) return false
      if (!q) return true
      return r.personName.toLowerCase().includes(q) || r.studentRef.toLowerCase().includes(q)
    })
  }, [e360.data, search, statusFilter])

  const pagedPopulation = filteredPopulation.slice(offset, offset + E360_PAGE_SIZE)

  const handleSearch = (v: string) => { setSearch(v); setOffset(0) }
  const handleStatus = (v: string) => { setStatusFilter(v); setOffset(0) }

  return (
    <>
      <PageHeader title="Analytics" />
      <div className="px-6 pb-6 space-y-4">
        <PageSection icon={AlertTriangle} title="Risk & completion" accent="accent">
          {analytics.isLoading ? <Skeleton className="h-20 w-full" /> : (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <Tile label="Students at risk" value={String(a?.risk.atRiskCount ?? '—')} hint={`${a?.risk.atRiskRatePct ?? 0}% of active`} />
              <Tile label="On track" value={String(a?.forecast.onTrack ?? '—')} hint="active, no risk flag" />
              <Tile label="Completions" value={String(a?.completion.completed ?? '—')} hint={`${a?.completion.completionRatePct ?? 0}% rate`} />
              <Tile label="Avg time to completion" value={a?.completion.avgTimeToCompletionDays ? `${a.completion.avgTimeToCompletionDays}d` : '—'} hint="graduated students" />
              <Tile label="Active researchers" value={String(a?.risk.activeStudents ?? '—')} hint="registered / active" />
            </div>
          )}
          {a && a.risk.students.length > 0 && (
            <div className="mt-4">
              <p className="text-label mb-2">At-risk students</p>
              <div className="space-y-1.5">
                {a.risk.students.map((s) => (
                  <div key={s.studentRef} className="flex items-center gap-2 text-sm">
                    <AlertTriangle className="h-4 w-4 text-[hsl(var(--warning))]" />
                    <span className="font-medium">{s.personName}</span>
                    <span className="text-helper font-mono">{s.studentRef}</span>
                    {s.reasons.map((r) => <Badge key={r} variant="warning">{r}</Badge>)}
                  </div>
                ))}
              </div>
            </div>
          )}
          {a && <p className="text-helper mt-3"><TrendingUp className="inline h-3.5 w-3.5 mr-1" />{a.forecast.note}</p>}
        </PageSection>

        <PageSection icon={Globe} title="PGR Enterprise 360" accent="primary">
          {e360.isLoading ? <Skeleton className="h-40 w-full" /> : (
            <>
              <div className="flex flex-wrap gap-2 mb-3 text-sm">
                <Badge variant="info">{e360.data?.summary.population ?? 0} population</Badge>
                <Badge variant="success">{e360.data?.summary.funded ?? 0} funded</Badge>
                <Badge variant="secondary">{e360.data?.summary.employees ?? 0} also employees</Badge>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                <SearchInput value={search} onChange={handleSearch} placeholder="Search by name or student ref…" />
                <FilterChips label="Status:" options={statusOptions} value={statusFilter} onChange={handleStatus} />
              </div>
              <Tabs defaultValue="student">
                <TabsList>
                  {LENSES.map((l) => <TabsTrigger key={l.key} value={l.key}>{l.label}</TabsTrigger>)}
                </TabsList>
                {LENSES.map((l) => (
                  <TabsContent key={l.key} value={l.key} className="mt-3 space-y-3">
                    <div className="card-elevated overflow-x-auto">
                      <Table>
                        <TableHeader><TableRow>{l.cols.map((c) => <TableHead key={c}>{c}</TableHead>)}</TableRow></TableHeader>
                        <TableBody>
                          {pagedPopulation.map((r) => (
                            <TableRow key={r.studentRef}>
                              {l.row(r).map((cell, i) => <TableCell key={i} className={i === 0 ? 'font-medium' : 'text-muted-foreground'}>{cell}</TableCell>)}
                            </TableRow>
                          ))}
                          {e360.data && filteredPopulation.length === 0 && (
                            <TableRow><TableCell colSpan={l.cols.length} className="text-muted-foreground text-center py-6">
                              {search || statusFilter !== 'all' ? 'No students match this search/filter.' : 'No students.'}
                            </TableCell></TableRow>
                          )}
                        </TableBody>
                      </Table>
                    </div>
                    <Pagination
                      offset={offset}
                      limit={E360_PAGE_SIZE}
                      total={filteredPopulation.length}
                      onOffsetChange={setOffset}
                    />
                  </TabsContent>
                ))}
              </Tabs>
            </>
          )}
        </PageSection>
      </div>
    </>
  )
}
