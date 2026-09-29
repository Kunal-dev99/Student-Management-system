'use client'

/**
 * ICR G2 (slice B) — cohort CSV import.
 *
 * Upload a CSV of an accepted cohort, see a per-row validation preview (nothing is written
 * yet), then commit to enrol everyone who is OK. Re-uploading the same file is safe — rows
 * with an existing student ref skip. Per-import defaults fill blank cells for the whole
 * cohort (one programme / start date / funder), so a tidy export needs no per-row editing.
 */
import { useCallback, useRef, useState } from 'react'
import { Upload, Download, FileDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from '@/components/ui/dialog'
import { Badge, type BadgeProps } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { useProgrammes } from '@/features/progression/api'
import {
  useImportPreview, useImportCommit, type ImportAction, type ImportResult, type ImportDefaults,
} from '@/features/students/api'

const ACTION_TONE: Record<ImportAction, BadgeProps['variant']> = {
  create: 'success', attach: 'info', skip: 'secondary', error: 'destructive',
}
const ACTION_LABEL: Record<ImportAction, string> = {
  create: 'New', attach: 'Attach', skip: 'Skip', error: 'Error',
}
const ACTION_HELP: Record<ImportAction, string> = {
  create: 'a new student will be enrolled',
  attach: 'links to an existing person with this email',
  skip: 'already imported (matching student ref) — left untouched',
  error: 'will not be imported — see the note',
}

const NONE = '__none'

function downloadCsv(name: string, rows: string[][]) {
  const csv = rows.map((r) => r.map((c) => `"${(c ?? '').replace(/"/g, '""')}"`).join(',')).join('\r\n')
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  const a = document.createElement('a')
  a.href = url; a.download = name; a.click()
  URL.revokeObjectURL(url)
}

export function CohortImportDialog() {
  const [open, setOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportResult | null>(null)
  const [defProgramme, setDefProgramme] = useState('')
  const [defStart, setDefStart] = useState('')
  const [defFunder, setDefFunder] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)
  const previewMut = useImportPreview()
  const commitMut = useImportCommit()
  const { toast } = useToast()
  const { data: programmes } = useProgrammes()

  const defaults = useCallback((): ImportDefaults => ({
    programme: defProgramme || undefined,
    startDate: defStart || undefined,
    funder: defFunder || undefined,
  }), [defProgramme, defStart, defFunder])

  const reset = () => {
    setFile(null); setPreview(null); setDefProgramme(''); setDefStart(''); setDefFunder('')
    if (fileInput.current) fileInput.current.value = ''
  }

  const runPreview = useCallback((f: File) => {
    previewMut.mutate({ file: f, defaults: defaults() }, {
      onSuccess: setPreview,
      onError: (e) => toast({
        title: 'Could not read the file',
        description: (e as Error)?.message ?? 'Check it is a CSV with a programme column.',
        variant: 'destructive',
      }),
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaults])

  const onPick = (f: File | null) => {
    setFile(f); setPreview(null)
    if (f) runPreview(f)
  }

  const onCommit = () => {
    if (!file) return
    commitMut.mutate({ file, defaults: defaults() }, {
      onSuccess: (res) => {
        toast({ title: 'Cohort imported', description: `${res.toCreate} enrolled, ${res.skipped} skipped, ${res.errors} error(s).` })
        reset(); setOpen(false)
      },
      onError: (e) => toast({
        title: 'Import failed', description: (e as Error)?.message ?? 'Please try again.', variant: 'destructive',
      }),
    })
  }

  const downloadTemplate = () => downloadCsv('cohort_template.csv', [
    ['Student Ref', 'First Name', 'Surname', 'Email', 'Course', 'Start Date', 'Attendance', 'Status', 'Funder'],
    ['ICR-2026-001', 'Ada', 'Lovelace', 'ada@example.ac.uk', 'MSC-ONC', '29/09/2026', 'full time', 'registered', ''],
  ])

  const downloadErrors = () => {
    if (!preview) return
    const bad = preview.rows.filter((r) => r.action === 'error')
    downloadCsv('cohort_failed_rows.csv', [
      ['Line', 'Name', 'Student Ref', 'Programme', 'Email', 'Problem'],
      ...bad.map((r) => [String(r.line), r.name, r.studentRef ?? '', r.programmeCode ?? '', r.email ?? '', r.messages.join('; ')]),
    ])
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) reset() }}>
      <DialogTrigger asChild>
        <Button variant="outline"><Upload className="mr-2 h-4 w-4" />Import cohort</Button>
      </DialogTrigger>
      <DialogContent className="flex max-h-[88vh] max-w-3xl flex-col overflow-hidden">
        <DialogHeader className="flex-none">
          <DialogTitle>Import a cohort</DialogTitle>
        </DialogHeader>

        <div className="-mr-2 flex-1 space-y-3 overflow-y-auto pr-2">
          <div className="flex items-start justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              Upload a CSV of accepted students. Columns: <span className="font-mono text-xs">student ref, name,
              email, programme code, start date, mode, status</span> (funder optional). You will see a preview
              before anything is saved.
            </p>
            <Button variant="ghost" size="sm" className="shrink-0" onClick={downloadTemplate}>
              <FileDown className="mr-1.5 h-4 w-4" />Template
            </Button>
          </div>

          <input
            ref={fileInput}
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => onPick(e.target.files?.[0] ?? null)}
            className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-1.5 file:text-primary-foreground hover:file:opacity-90"
          />

          {/* Per-import defaults — fill blank cells for the whole cohort. */}
          <div className="rounded-md border border-border bg-muted/30 p-3">
            <p className="mb-2 text-xs font-medium text-muted-foreground">
              Defaults for blank cells (optional — applied to any row that leaves these empty)
            </p>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="space-y-1">
                <Label className="text-xs">Programme</Label>
                <Select
                  value={defProgramme || NONE}
                  onValueChange={(v) => { const nv = v === NONE ? '' : v; setDefProgramme(nv); if (file) runPreview(file) }}
                >
                  <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>None</SelectItem>
                    {(programmes ?? []).map((p) => (
                      <SelectItem key={p.id} value={p.code}>{p.code} — {p.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Start date</Label>
                <Input type="date" value={defStart}
                  onChange={(e) => setDefStart(e.target.value)}
                  onBlur={() => { if (file) runPreview(file) }} />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Funder</Label>
                <Input value={defFunder} placeholder="e.g. CRUK"
                  onChange={(e) => setDefFunder(e.target.value)}
                  onBlur={() => { if (file) runPreview(file) }} />
              </div>
            </div>
          </div>

          {previewMut.isPending && <p className="text-sm text-muted-foreground">Validating…</p>}

          {preview && preview.total === 0 && (
            <p className="text-sm text-muted-foreground">No data rows found in the file — only a header, or an empty file.</p>
          )}

          {preview && preview.total > 0 && (
            <>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <Badge variant="success">{preview.toCreate} to enrol</Badge>
                <Badge variant="secondary">{preview.skipped} skip</Badge>
                <Badge variant={preview.errors ? 'destructive' : 'outline'}>{preview.errors} error(s)</Badge>
                <span className="text-muted-foreground">of {preview.total} rows</span>
                {preview.errors > 0 && (
                  <Button variant="ghost" size="sm" className="ml-auto" onClick={downloadErrors}>
                    <Download className="mr-1.5 h-4 w-4" />Failed rows
                  </Button>
                )}
              </div>

              <div className="max-h-[38vh] overflow-auto rounded-md border border-border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-10">#</TableHead>
                      <TableHead>Name</TableHead>
                      <TableHead>Programme</TableHead>
                      <TableHead>Ref</TableHead>
                      <TableHead>Action</TableHead>
                      <TableHead>Notes</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {preview.rows.map((r) => (
                      <TableRow key={r.line}>
                        <TableCell className="text-muted-foreground num">{r.line}</TableCell>
                        <TableCell className="font-medium">{r.name || '—'}</TableCell>
                        <TableCell className="text-muted-foreground">{r.programmeName ?? r.programmeCode ?? '—'}</TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">{r.studentRef ?? '—'}</TableCell>
                        <TableCell><Badge variant={ACTION_TONE[r.action]} title={ACTION_HELP[r.action]}>{ACTION_LABEL[r.action]}</Badge></TableCell>
                        <TableCell className="text-xs text-muted-foreground">{r.messages.join('; ')}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              <p className="text-xs text-muted-foreground">
                <span className="font-medium">New</span> {ACTION_HELP.create} · <span className="font-medium">Attach</span> {ACTION_HELP.attach} · <span className="font-medium">Skip</span> {ACTION_HELP.skip} · <span className="font-medium">Error</span> {ACTION_HELP.error}.
              </p>
            </>
          )}
        </div>

        <DialogFooter className="flex-none">
          <Button variant="outline" onClick={() => { setOpen(false); reset() }}>Cancel</Button>
          <Button onClick={onCommit} disabled={!preview || preview.toCreate === 0 || commitMut.isPending}>
            {commitMut.isPending ? 'Enrolling…' : preview ? `Enrol ${preview.toCreate} student(s)` : 'Enrol'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
