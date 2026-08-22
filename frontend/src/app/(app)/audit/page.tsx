'use client'

import { useState } from 'react'
import { ScrollText, ShieldAlert } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useAuth } from '@/shared/auth/AuthContext'
import { useAudit } from '@/features/audit/api'

function statusVariant(code: number | null): 'success' | 'warning' | 'destructive' | 'secondary' {
  if (code == null) return 'secondary'
  if (code >= 500) return 'destructive'
  if (code >= 400) return 'warning'
  if (code >= 200 && code < 300) return 'success'
  return 'secondary'
}

export default function AuditPage() {
  const { hasPermission } = useAuth()
  const [entityType, setEntityType] = useState('')
  const [entityId, setEntityId] = useState('')
  const [actorEmail, setActorEmail] = useState('')

  const { data, isLoading, isError, error } = useAudit({
    entityType: entityType || undefined,
    entityId: entityId || undefined,
    actorEmail: actorEmail || undefined,
    limit: 200,
  })

  if (!hasPermission('audit.read')) {
    return (
      <>
        <PageHeader title="Audit" description="System audit trail." />
        <div className="px-6 pb-6">
          <PageSection icon={ShieldAlert} title="Not authorised" accent="danger">
            <p className="text-sm text-muted-foreground">
              You do not have permission to view the audit trail.
            </p>
          </PageSection>
        </div>
      </>
    )
  }

  return (
    <>
      <PageHeader title="Audit" description="Immutable record of privileged actions and state changes." />
      <div className="px-6 pb-6 space-y-4">
        <PageSection icon={ScrollText} title="Filters" accent="primary">
          <div className="flex flex-wrap items-end gap-2">
            <Input placeholder="Entity type" className="w-44 h-9" value={entityType} onChange={(e) => setEntityType(e.target.value)} />
            <Input placeholder="Entity ID" className="w-64 h-9" value={entityId} onChange={(e) => setEntityId(e.target.value)} />
            <Input placeholder="Actor email" className="w-56 h-9" value={actorEmail} onChange={(e) => setActorEmail(e.target.value)} />
          </div>
        </PageSection>

        <div className="card-elevated overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Method</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Entity</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && <TableRow><TableCell colSpan={6}><Skeleton className="h-5 w-full" /></TableCell></TableRow>}
              {isError && <TableRow><TableCell colSpan={6} className="text-[hsl(var(--destructive))]">{(error as Error)?.message}</TableCell></TableRow>}
              {data?.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="num text-xs text-muted-foreground whitespace-nowrap">{row.createdAt?.replace('T', ' ').slice(0, 19)}</TableCell>
                  <TableCell className="text-sm">{row.actorEmail ?? '—'}</TableCell>
                  <TableCell className="font-mono text-xs">{row.method ?? '—'}</TableCell>
                  <TableCell className="text-sm">{row.action ?? '—'}</TableCell>
                  <TableCell className="text-xs">
                    {row.entityType ? (
                      <span>
                        {row.entityType}
                        {row.entityId && <span className="text-muted-foreground font-mono"> · {row.entityId.slice(0, 8)}</span>}
                      </span>
                    ) : '—'}
                  </TableCell>
                  <TableCell><Badge variant={statusVariant(row.statusCode)}>{row.statusCode ?? '—'}</Badge></TableCell>
                </TableRow>
              ))}
              {data && data.length === 0 && (
                <TableRow><TableCell colSpan={6} className="text-muted-foreground text-center py-8">No audit entries match these filters.</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </div>
        {data && <p className="text-helper">{data.length} entries</p>}
      </div>
    </>
  )
}
