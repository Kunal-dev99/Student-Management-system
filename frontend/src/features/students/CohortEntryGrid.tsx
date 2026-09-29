'use client'

/**
 * In-app cohort entry — type the cohort row by row instead of preparing a CSV in Excel.
 * Coded fields (programme, funder, mode, status) are dropdowns, so values are always valid
 * and map to real FKs. The dialog turns these rows into the same CSV the importer validates,
 * so the preview/enrol path is unchanged.
 */
import { Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

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

export function CohortEntryGrid({ rows, onChange, programmes, funders }: {
  rows: GridRow[]
  onChange: (rows: GridRow[]) => void
  programmes: ProgrammeOpt[]
  funders: FunderOpt[]
}) {
  const upd = (i: number, k: keyof GridRow, v: string) =>
    onChange(rows.map((r, idx) => (idx === i ? { ...r, [k]: v } : r)))
  const del = (i: number) => onChange(rows.filter((_, idx) => idx !== i))
  const add = () => onChange([...rows, emptyGridRow()])

  const cell = 'h-8'
  return (
    <div className="space-y-2">
      <div className="overflow-x-auto rounded-md border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="min-w-[120px]">Student ref</TableHead>
              <TableHead className="min-w-[110px]">First name</TableHead>
              <TableHead className="min-w-[110px]">Surname</TableHead>
              <TableHead className="min-w-[170px]">Email</TableHead>
              <TableHead className="min-w-[190px]">Programme</TableHead>
              <TableHead className="min-w-[140px]">Start date</TableHead>
              <TableHead className="min-w-[120px]">Mode</TableHead>
              <TableHead className="min-w-[130px]">Status</TableHead>
              <TableHead className="min-w-[170px]">Funder</TableHead>
              <TableHead className="w-8" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r, i) => (
              <TableRow key={i}>
                <TableCell><Input className={cell} value={r.studentRef} onChange={(e) => upd(i, 'studentRef', e.target.value)} /></TableCell>
                <TableCell><Input className={cell} value={r.firstName} onChange={(e) => upd(i, 'firstName', e.target.value)} /></TableCell>
                <TableCell><Input className={cell} value={r.surname} onChange={(e) => upd(i, 'surname', e.target.value)} /></TableCell>
                <TableCell><Input className={cell} type="email" value={r.email} onChange={(e) => upd(i, 'email', e.target.value)} /></TableCell>
                <TableCell>
                  <Select value={r.programme || NONE} onValueChange={(v) => upd(i, 'programme', v === NONE ? '' : v)}>
                    <SelectTrigger className={cell}><SelectValue placeholder="—" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value={NONE}>—</SelectItem>
                      {programmes.map((p) => <SelectItem key={p.id} value={p.code}>{p.code} — {p.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </TableCell>
                <TableCell><Input className={cell} type="date" value={r.startDate} onChange={(e) => upd(i, 'startDate', e.target.value)} /></TableCell>
                <TableCell>
                  <Select value={r.studyMode} onValueChange={(v) => upd(i, 'studyMode', v)}>
                    <SelectTrigger className={cell}><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="full_time">Full time</SelectItem>
                      <SelectItem value="part_time">Part time</SelectItem>
                    </SelectContent>
                  </Select>
                </TableCell>
                <TableCell>
                  <Select value={r.status} onValueChange={(v) => upd(i, 'status', v)}>
                    <SelectTrigger className={cell}><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {STATUS.map((s) => <SelectItem key={s.v} value={s.v}>{s.l}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </TableCell>
                <TableCell>
                  <Select value={r.funder || NONE} onValueChange={(v) => upd(i, 'funder', v === NONE ? '' : v)}>
                    <SelectTrigger className={cell}><SelectValue placeholder="—" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value={NONE}>—</SelectItem>
                      {funders.map((f) => <SelectItem key={f.id} value={f.name}>{f.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </TableCell>
                <TableCell>
                  <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Remove row" onClick={() => del(i)}>
                    <Trash2 className="h-3.5 w-3.5 text-[hsl(var(--destructive))]" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {rows.length === 0 && (
              <TableRow><TableCell colSpan={10} className="py-6 text-center text-sm text-muted-foreground">No rows yet — add one to start.</TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <Button variant="outline" size="sm" onClick={add}><Plus className="mr-1.5 h-4 w-4" />Add row</Button>
    </div>
  )
}
