'use client'

/** Effective dating, Phase 7 — the HESA return frozen at sign-off. Each sign-off stores the exact
 *  rows that were attested, taken as at a date and as the data was known at that moment, so later
 *  data changes never alter it. Re-download it here unchanged. */

import { useQuery } from '@tanstack/react-query'
import { Download, Snowflake } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useToast } from '@/components/ui/use-toast'
import { api, downloadFile } from '@/shared/api/client'

export interface ReturnVersion {
  id: string
  versionNo: number
  academicYear: string
  /** Values taken as in force on this date; null = the reporting-year end. */
  asAt: string | null
  /** The data as it was recorded at this moment (the sign-off). */
  knownAt: string | null
  reason: string
  createdAt: string | null
  rowCount: number
  errors: number
  warnings: number
}

export const useReturnVersions = (profileId: string | null) =>
  useQuery({
    queryKey: ['report-profile', profileId, 'versions'],
    queryFn: () => api.get<ReturnVersion[]>(`/report-profiles/${profileId}/versions`),
    enabled: !!profileId,
  })

export function ReturnVersionsPanel({ profileId, code }: { profileId: string; code: string }) {
  const { toast } = useToast()
  const q = useReturnVersions(profileId)
  if (q.isLoading) return <Skeleton className="h-16 w-full" />
  const versions = q.data ?? []
  if (versions.length === 0) return null
  return (
    <div className="rounded-md border border-border p-3 space-y-2">
      <p className="flex items-center gap-1.5 text-sm font-medium">
        <Snowflake className="h-4 w-4 text-[hsl(var(--info))]" /> Frozen returns
      </p>
      <p className="text-helper">
        The exact return attested at each sign-off. Later changes to student data never alter it —
        anything entered afterwards, even back-dated, isn&apos;t in it.
      </p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Version</TableHead>
            <TableHead>As at</TableHead>
            <TableHead>Data as known at</TableHead>
            <TableHead className="text-right">Rows</TableHead>
            <TableHead className="text-right" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {versions.map((v) => (
            <TableRow key={v.id}>
              <TableCell className="num">v{v.versionNo}</TableCell>
              <TableCell className="num">{v.asAt ?? `${v.academicYear} year end`}</TableCell>
              <TableCell className="num">{v.knownAt ? new Date(v.knownAt).toLocaleString() : '—'}</TableCell>
              <TableCell className="num text-right">{v.rowCount}</TableCell>
              <TableCell className="text-right">
                <Button size="sm" variant="ghost" onClick={async () => {
                  try {
                    await downloadFile(`/report-profiles/${profileId}/versions/${v.id}/download`,
                      `${code.toLowerCase()}_${v.academicYear.replace('/', '-')}_v${v.versionNo}.csv`)
                  } catch (e) {
                    toast({ title: 'Download failed', description: (e as Error).message, variant: 'destructive' })
                  }
                }}>
                  <Download className="h-3.5 w-3.5 mr-1" /> CSV
                </Button>
                <Button size="sm" variant="ghost" title="Excel workbook for review (the CSV is the file to submit)"
                  onClick={async () => {
                    try {
                      await downloadFile(`/report-profiles/${profileId}/versions/${v.id}/download?format=xlsx`,
                        `${code.toLowerCase()}_${v.academicYear.replace('/', '-')}_v${v.versionNo}.xlsx`)
                    } catch (e) {
                      toast({ title: 'Download failed', description: (e as Error).message, variant: 'destructive' })
                    }
                  }}>
                  <Download className="h-3.5 w-3.5 mr-1" /> Excel
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
