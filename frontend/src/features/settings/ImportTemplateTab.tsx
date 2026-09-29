'use client'

/**
 * Settings › Cohort import template.
 *
 * An admin chooses which columns the cohort import expects — the enabled set drives the
 * in-app entry grid, the downloadable CSV template, and the upload instructions. The field
 * set itself is fixed (each maps to a known importer field); the admin toggles visibility,
 * marks which are required, and can relabel a column for their institution's vocabulary.
 */
import { useEffect, useState } from 'react'
import { FileSpreadsheet, RotateCcw } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useToast } from '@/components/ui/use-toast'
import {
  useImportTemplate, useSetImportTemplate, type ImportTemplateColumn,
} from '@/features/students/api'

const DEFAULT_LABELS: Record<string, string> = {
  studentRef: 'Student ref', firstName: 'First name', surname: 'Surname', email: 'Email',
  programme: 'Programme', startDate: 'Start date', studyMode: 'Study mode', status: 'Status', funder: 'Funder',
}

export function ImportTemplateTab() {
  const { toast } = useToast()
  const { data, isLoading } = useImportTemplate()
  const save = useSetImportTemplate()
  const [cols, setCols] = useState<ImportTemplateColumn[]>([])

  useEffect(() => { if (data) setCols(data.columns) }, [data])

  const upd = (field: string, patch: Partial<ImportTemplateColumn>) =>
    setCols((prev) => prev.map((c) => (c.field === field ? { ...c, ...patch } : c)))

  // A required column must stay enabled; toggling required on re-enables it.
  const setRequired = (field: string, required: boolean) =>
    upd(field, required ? { required: true, enabled: true } : { required: false })
  const setEnabled = (field: string, enabled: boolean) =>
    upd(field, enabled ? { enabled: true } : { enabled: false, required: false })

  const resetLabels = () =>
    setCols((prev) => prev.map((c) => ({ ...c, label: DEFAULT_LABELS[c.field] ?? c.label })))

  const onSave = async () => {
    if (!cols.some((c) => c.enabled)) {
      toast({ title: 'Enable at least one column', variant: 'destructive' })
      return
    }
    try {
      await save.mutateAsync(cols)
      toast({ title: 'Import template saved', description: 'The cohort import now uses these columns.' })
    } catch (e) {
      toast({ title: 'Save failed', description: (e as Error).message, variant: 'destructive' })
    }
  }

  const enabledCount = cols.filter((c) => c.enabled).length

  return (
    <PageSection icon={FileSpreadsheet} title="Cohort import template" accent="primary">
      <p className="text-helper mb-4 max-w-2xl">
        Choose which columns your cohort import uses. Enabled columns appear in the in-app entry
        grid, the downloadable CSV template and the upload instructions. Required columns must be
        filled for every student (unless a whole-cohort default is supplied at import time).
      </p>

      {isLoading ? <Skeleton className="h-64 w-full" /> : (
        <div className="space-y-4">
          <div className="rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-20 text-center">Include</TableHead>
                  <TableHead className="min-w-[220px]">Column label</TableHead>
                  <TableHead className="w-24 text-center">Required</TableHead>
                  <TableHead className="text-muted-foreground">Maps to</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cols.map((c) => (
                  <TableRow key={c.field} className={c.enabled ? '' : 'opacity-60'}>
                    <TableCell className="text-center">
                      <Checkbox
                        checked={c.enabled}
                        onCheckedChange={(v) => setEnabled(c.field, v === true)}
                        aria-label={`Include ${c.label}`}
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        value={c.label}
                        onChange={(e) => upd(c.field, { label: e.target.value })}
                        className="h-8"
                        disabled={!c.enabled}
                      />
                    </TableCell>
                    <TableCell className="text-center">
                      <Checkbox
                        checked={c.required}
                        onCheckedChange={(v) => setRequired(c.field, v === true)}
                        aria-label={`${c.label} required`}
                      />
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{c.field}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center gap-3 border-t border-border pt-3">
            <Button size="sm" onClick={onSave} disabled={save.isPending}>
              {save.isPending ? 'Saving…' : 'Save template'}
            </Button>
            <Button size="sm" variant="ghost" onClick={resetLabels}>
              <RotateCcw className="mr-1.5 h-3.5 w-3.5" />Reset labels
            </Button>
            <span className="ml-auto text-xs text-muted-foreground">{enabledCount} column(s) enabled</span>
          </div>
        </div>
      )}
    </PageSection>
  )
}
