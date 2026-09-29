'use client'

/**
 * Import a FULL statutory spec pack from a file — the Cloudflare-free path to the real HESA spec.
 * The Registry downloads HESA's data-model export once (as CSV or JSON), uploads it here, and it
 * becomes the active spec version for that return + year — pre-mapping every profile created from it.
 *
 * This is the whole field set at once (not an advisory diff), so it supersedes the current pack. A
 * person always chooses to do it.
 */
import { useState } from 'react'
import { FileSpreadsheet, FileDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useToast } from '@/components/ui/use-toast'
import { ApiError } from '@/shared/api/client'
import { useImportSpec } from '@/features/statutory/api'

const TEMPLATE_CSV = [
  'field,description,allowed,source,transform,default,required,keyed_at',
  'OWNSTU,Institution’s own student identifier,,student.ref,,,true,Student record › reference',
  'SEXID,Sex identifier,10|11|12|13,,,,true,Person › sex',
  'SURNAME,Family name,,person.familyName,upper,,true,Person › family name',
  'BIRTHDTE,Date of birth (YYYYMMDD),,person.dateOfBirth,date_compact,,true,Person › date of birth',
].join('\r\n')

function downloadTemplate() {
  const url = URL.createObjectURL(new Blob([TEMPLATE_CSV], { type: 'text/csv;charset=utf-8' }))
  const a = document.createElement('a')
  a.href = url; a.download = 'hesa_spec_template.csv'; a.click()
  URL.revokeObjectURL(url)
}

export function ImportSpecDialog() {
  const { toast } = useToast()
  const importSpec = useImportSpec()
  const [open, setOpen] = useState(false)
  const [packCode, setPackCode] = useState('HESA_STUDENT')
  const [academicYear, setAcademicYear] = useState('')
  const [name, setName] = useState('')
  const [file, setFile] = useState<File | null>(null)

  const reset = () => { setPackCode('HESA_STUDENT'); setAcademicYear(''); setName(''); setFile(null) }
  const canSubmit = !!file && !!packCode.trim() && !!academicYear.trim()

  const submit = async () => {
    if (!file) return
    const form = new FormData()
    form.append('file', file)
    form.append('packCode', packCode.trim())
    form.append('academicYear', academicYear.trim())
    if (name.trim()) form.append('name', name.trim())
    try {
      const res = await importSpec.mutateAsync(form)
      toast({
        title: `Imported ${res.name}`,
        description: `${res.fieldCount} fields${res.ruleCount ? `, ${res.ruleCount} rules` : ''} — now the active ${res.packCode} ${res.academicYear} spec (v${res.version}).`,
      })
      reset(); setOpen(false)
    } catch (e) {
      toast({ title: 'Could not import spec', description: (e as ApiError).message, variant: 'destructive' })
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) reset() }}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline"><FileSpreadsheet className="h-4 w-4 mr-1" /> Import spec file</Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>Import a full spec from a file</DialogTitle></DialogHeader>
        <p className="text-helper -mt-1">
          Upload HESA&apos;s data-model export (CSV or JSON) once and it becomes the active spec for
          that return &amp; year — no scraping, no code release. This replaces the current pack for
          that year and pre-maps every profile created from it.
        </p>

        <div className="grid grid-cols-2 gap-3 py-1">
          <div className="space-y-1.5">
            <Label htmlFor="is-code">Return code</Label>
            <Input id="is-code" value={packCode} onChange={(e) => setPackCode(e.target.value)} placeholder="HESA_STUDENT" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="is-year">Academic year</Label>
            <Input id="is-year" value={academicYear} onChange={(e) => setAcademicYear(e.target.value)} placeholder="e.g. 2025/26" />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="is-name">Name (optional)</Label>
          <Input id="is-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. HESA Student record 2025/26" />
        </div>
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label htmlFor="is-file">Spec file (CSV or JSON)</Label>
            <Button variant="ghost" size="sm" className="h-7" onClick={downloadTemplate}>
              <FileDown className="h-3.5 w-3.5 mr-1" /> CSV template
            </Button>
          </div>
          <Input id="is-file" type="file" accept=".csv,.json,text/csv,application/json,text/plain"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <p className="text-helper">
            CSV: one row per field with a <span className="font-mono text-xs">field</span> (or{' '}
            <span className="font-mono text-xs">code</span>) column; list allowed codes with{' '}
            <span className="font-mono text-xs">|</span>. JSON:{' '}
            <span className="font-mono text-xs">{'{ "fields": [...], "rules": [...] }'}</span> for
            cross-field rules too.
          </p>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => { setOpen(false); reset() }}>Cancel</Button>
          <Button onClick={submit} disabled={!canSubmit || importSpec.isPending}>
            {importSpec.isPending ? 'Importing…' : 'Import spec'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
