'use client'

/**
 * ICR G2 (slice B) — cohort CSV import.
 *
 * ICR exports an accepted cohort from its own recruitment system. Upload the CSV, see a
 * per-row validation preview (nothing is written yet), then commit to enrol everyone who is
 * OK. Re-uploading the same file is safe — rows with an existing student ref skip.
 */
import { useRef, useState } from 'react'
import { Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from '@/components/ui/dialog'
import { Badge, type BadgeProps } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useToast } from '@/components/ui/use-toast'
import {
  useImportPreview, useImportCommit, type ImportAction, type ImportResult,
} from '@/features/students/api'

const ACTION_TONE: Record<ImportAction, BadgeProps['variant']> = {
  create: 'success',
  attach: 'info',
  skip: 'secondary',
  error: 'destructive',
}
const ACTION_LABEL: Record<ImportAction, string> = {
  create: 'New', attach: 'Attach', skip: 'Skip', error: 'Error',
}

export function CohortImportDialog() {
  const [open, setOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportResult | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const previewMut = useImportPreview()
  const commitMut = useImportCommit()
  const { toast } = useToast()

  const reset = () => { setFile(null); setPreview(null); if (fileInput.current) fileInput.current.value = '' }

  const onPick = (f: File | null) => {
    setFile(f)
    setPreview(null)
    if (!f) return
    previewMut.mutate(f, {
      onSuccess: setPreview,
      onError: (e) => toast({
        title: 'Could not read the file',
        description: (e as Error)?.message ?? 'Check it is a CSV with a programme column.',
        variant: 'destructive',
      }),
    })
  }

  const onCommit = () => {
    if (!file) return
    commitMut.mutate(file, {
      onSuccess: (res) => {
        toast({
          title: 'Cohort imported',
          description: `${res.toCreate} enrolled, ${res.skipped} skipped, ${res.errors} error(s).`,
        })
        reset()
        setOpen(false)
      },
      onError: (e) => toast({
        title: 'Import failed',
        description: (e as Error)?.message ?? 'Please try again.',
        variant: 'destructive',
      }),
    })
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) reset() }}>
      <DialogTrigger asChild>
        <Button variant="outline"><Upload className="mr-2 h-4 w-4" />Import cohort</Button>
      </DialogTrigger>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Import a cohort</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground -mt-1">
          Upload a CSV of accepted students. Columns: <span className="font-mono text-xs">student ref, name,
          email, programme code, start date, mode</span> (funder optional). You will see a preview before anything is saved.
        </p>

        <div className="py-2">
          <input
            ref={fileInput}
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => onPick(e.target.files?.[0] ?? null)}
            className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-1.5 file:text-primary-foreground hover:file:opacity-90"
          />
        </div>

        {previewMut.isPending && (
          <p className="text-sm text-muted-foreground">Validating…</p>
        )}

        {preview && (
          <>
            <div className="flex flex-wrap gap-2 text-sm">
              <Badge variant="success">{preview.toCreate} to enrol</Badge>
              <Badge variant="secondary">{preview.skipped} skip</Badge>
              <Badge variant={preview.errors ? 'destructive' : 'outline'}>{preview.errors} error(s)</Badge>
              <span className="text-muted-foreground self-center">of {preview.total} rows</span>
            </div>

            <div className="mt-3 max-h-[45vh] overflow-auto rounded-md border border-border">
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
                      <TableCell><Badge variant={ACTION_TONE[r.action]}>{ACTION_LABEL[r.action]}</Badge></TableCell>
                      <TableCell className="text-xs text-muted-foreground">{r.messages.join('; ')}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => { setOpen(false); reset() }}>Cancel</Button>
          <Button
            onClick={onCommit}
            disabled={!preview || preview.toCreate === 0 || commitMut.isPending}
          >
            {commitMut.isPending ? 'Enrolling…' : preview ? `Enrol ${preview.toCreate} student(s)` : 'Enrol'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
