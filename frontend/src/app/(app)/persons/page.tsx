'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Search } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { usePersons } from '@/features/persons/api'
import { RelationshipBadge } from '@/features/persons/RelationshipBadge'

export default function PersonsPage() {
  const [search, setSearch] = useState('')
  const { data, isLoading, isError, error } = usePersons(search)

  return (
    <>
      <PageHeader title="Persons" description="One person across every identity over time." />
      <div className="px-6 pb-6 space-y-4">
        <div className="relative max-w-sm">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by name or email…"
            className="pl-8"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="card-elevated overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Nationality</TableHead>
                <TableHead>Current identities</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading &&
                Array.from({ length: 3 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={4}><Skeleton className="h-5 w-full" /></TableCell>
                  </TableRow>
                ))}

              {isError && (
                <TableRow>
                  <TableCell colSpan={4} className="text-[hsl(var(--destructive))]">
                    {(error as Error)?.message ?? 'Failed to load persons'}
                  </TableCell>
                </TableRow>
              )}

              {data?.data.map((p) => {
                const current = p.relationships.filter((r) => r.validTo === null)
                return (
                  <TableRow key={p.id} className="cursor-pointer">
                    <TableCell className="font-medium">
                      <Link href={`/persons/${p.id}`} className="hover:text-primary">
                        {p.givenName} {p.familyName}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{p.email ?? '—'}</TableCell>
                    <TableCell className="text-muted-foreground">{p.nationality ?? '—'}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {current.length ? (
                          current.map((r) => (
                            <RelationshipBadge key={r.id} type={r.relationshipType} current />
                          ))
                        ) : (
                          <span className="text-muted-foreground text-sm">none</span>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}

              {data && data.data.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4} className="text-muted-foreground text-center py-8">
                    No persons match “{search}”.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
        {data?.page.total != null && (
          <p className="text-helper">{data.page.total} total</p>
        )}
      </div>
    </>
  )
}
