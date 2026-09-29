'use client'

/**
 * In-app cohort entry — type the cohort row by row instead of preparing a CSV in Excel.
 * Coded fields (programme, funder, mode, status) are dropdowns, so values are always valid
 * and map to real FKs. The dialog turns these rows into the same CSV the importer validates,
 * so the preview/enrol path is unchanged.
 *
 * Which columns appear is driven by the Settings › Cohort import template: an admin enables
 * only the columns their institution captures, so the grid shows just those (the underlying
 * CSV still carries the full field set, blank for hidden columns).
 */
import { Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import type { ImportTemplateColumn, ImportTemplateField } from '@/features/students/api'

export type GridRow = {
  studentRef: string; firstName: string; surname: string; email: string
  programme: string; startDate: string; studyMode: string; status: string; funder: string
}
export const emptyGridRow = (): GridRow => ({
  studentRef: '', firstName: '', surname: '', email: '',
  programme: '', startDate: '', studyMode: 'full_time', status: 'registered', funder: '',
})
export const rowIsBlank = (r: GridRow) =>
  !r.studentRef && !r.firstName && !r.surname && !r.email && !r.programme && !r.funder

const NONE = '__none'
const STATUS = [
  { v: 'registered', l: 'Registered' },
  { v: 'prospective', l: 'Prospective' },
  { v: 'active', l: 'Active' },
]

type ProgrammeOpt = { id: string; code: string; name: string }
type FunderOpt = { id: string; name: string }

// Each template field maps to a GridRow key and a render kind + column min-width.
const FIELD_META: Record<ImportTemplateField, { key: keyof GridRow; kind: 'text' | 'email' | 'date' | 'programme' | 'funder' | 'mode' | 'status'; min: string }> = {
  studentRef: { key: 'studentRef', kind: 'text', min: 'min-w-[120px]' },
  firstName: { key: 'firstName', kind: 'text', min: 'min-w-[110px]' },
  surname: { key: 'surname', kind: 'text', min: 'min-w-[110px]' },
  email: { key: 'email', kind: 'email', min: 'min-w-[170px]' },
  programme: { key: 'programme', kind: 'programme', min: 'min-w-[190px]' },
  startDate: { key: 'startDate', kind: 'date', min: 'min-w-[140px]' },
  studyMode: { key: 'studyMode', kind: 'mode', min: 'min-w-[120px]' },
  status: { key: 'status', kind: 'status', min: 'min-w-[130px]' },
  funder: { key: 'funder', kind: 'funder', min: 'min-w-[170px]' },
}

export function CohortEntryGrid({ rows, onChange, programmes, funders, columns }: {
  rows: GridRow[]
  onChange: (rows: GridRow[]) => void
  programmes: ProgrammeOpt[]
  funders: FunderOpt[]
  /** Enabled columns from the import template, in display order. */
  columns: ImportTemplateColumn[]
}) {
  const upd = (i: number, k: keyof GridRow, v: string) =>
    onChange(rows.map((r, idx) => (idx === i ? { ...r, [k]: v } : r)))
  const del = (i: number) => onChange(rows.filter((_, idx) => idx !== i))
  const add = () => onChange([...rows, emptyGridRow()])

  const cell = 'h-8'
  const cols = columns.filter((c) => c.enabled)

  const renderCell = (col: ImportTemplateColumn, r: GridRow, i: number) => {
    const meta = FIELD_META[col.field]
    const val = r[meta.key]
    switch (meta.kind) {
      case 'programme':
        return (
          <Select value={val || NONE} onValueChange={(v) => upd(i, meta.key, v === NONE ? '' : v)}>
            <SelectTrigger className={cell}><SelectValue placeholder="—" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>—</SelectItem>
              {programmes.map((p) => <SelectItem key={p.id} value={p.code}>{p.code} — {p.name}</SelectItem>)}
            </SelectContent>
          </Select>
        )
      case 'funder':
        return (
          <Select value={val || NONE} onValueChange={(v) => upd(i, meta.key, v === NONE ? '' : v)}>
            <SelectTrigger className={cell}><SelectValue placeholder="—" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>—</SelectItem>
              {funders.map((f) => <SelectItem key={f.id} value={f.name}>{f.name}</SelectItem>)}
            </SelectContent>
          </Select>
        )
      case 'mode':
        return (
          <Select value={val} onValueChange={(v) => upd(i, meta.key, v)}>
            <SelectTrigger className={cell}><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="full_time">Full time</SelectItem>
              <SelectItem value="part_time">Part time</SelectItem>
            </SelectContent>
          </Select>
        )
      case 'status':
        return (
          <Select value={val} onValueChange={(v) => upd(i, meta.key, v)}>
            <SelectTrigger className={cell}><SelectValue /></SelectTrigger>
            <SelectContent>
              {STATUS.map((s) => <SelectItem key={s.v} value={s.v}>{s.l}</SelectItem>)}
            </SelectContent>
          </Select>
        )
      case 'date':
        return <Input className={cell} type="date" value={val} onChange={(e) => upd(i, meta.key, e.target.value)} />
      case 'email':
        return <Input className={cell} type="email" value={val} onChange={(e) => upd(i, meta.key, e.target.value)} />
      default:
        return <Input className={cell} value={val} onChange={(e) => upd(i, meta.key, e.target.value)} />
    }
  }

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto rounded-md border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              {cols.map((c) => (
                <TableHead key={c.field} className={FIELD_META[c.field].min}>
                  {c.label}{c.required && <span className="text-[hsl(var(--destructive))]"> *</span>}
                </TableHead>
              ))}
              <TableHead className="w-8" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r, i) => (
              <TableRow key={i}>
                {cols.map((c) => (
                  <TableCell key={c.field}>{renderCell(c, r, i)}</TableCell>
                ))}
                <TableCell>
                  <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Remove row" onClick={() => del(i)}>
                    <Trash2 className="h-3.5 w-3.5 text-[hsl(var(--destructive))]" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {rows.length === 0 && (
              <TableRow><TableCell colSpan={cols.length + 1} className="py-6 text-center text-sm text-muted-foreground">No rows yet — add one to start.</TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <Button variant="outline" size="sm" onClick={add}><Plus className="mr-1.5 h-4 w-4" />Add row</Button>
    </div>
  )
}
