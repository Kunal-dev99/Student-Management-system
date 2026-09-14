'use client'

/**
 * Institutional Memory — comparable case explorer (spec §19).
 *
 * Rules from the spec, followed deliberately:
 *   - This is a case EXPLORER, not a "recommend outcome" button. The primary CTA
 *     is "Use as context / open case" — never "copy outcome".
 *   - Similarity summary states WHAT was matched on (case class, study mode,
 *     funding, stage) so the reader can judge the match themselves.
 *   - A permanent bias warning: historical frequency is not a rule.
 *   - No persuasive colour coding on outcomes — score renders as a plain number,
 *     not a red/green gradient implying "good" or "bad".
 */
import { useState } from 'react'
import { AlertTriangle, ExternalLink, Search } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { AIStateBanner } from './AIStateBanner'
import { intelligenceApi, type SimilarCasesResult } from './api'

const CASE_CLASSES: Record<string, string> = {
  extension: 'Extension request',
  suspension: 'Suspension request',
  mode_change: 'Study mode change',
  supervisor_change: 'Supervisor change',
  withdrawal: 'Withdrawal',
}

const STUDY_MODES = ['full_time', 'part_time']
const STAGES = ['registered', 'confirmed', 'thesis']

export function CaseExplorer() {
  const [caseClass, setCaseClass] = useState('extension')
  const [studyMode, setStudyMode] = useState<string>('full_time')
  const [stage, setStage] = useState<string>('registered')
  const [hasFunding, setHasFunding] = useState(true)
  const [supervisionOverdue, setSupervisionOverdue] = useState(false)
  const [result, setResult] = useState<SimilarCasesResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function search() {
    setLoading(true); setError(null)
    try {
      const r = await intelligenceApi.similarCases({
        caseClass,
        subject: {
          case_class: caseClass,
          study_mode: studyMode,
          stage,
          has_active_funding: hasFunding,
          supervision_overdue: supervisionOverdue,
        },
        limit: 8,
      })
      setResult(r)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-page-title">Comparable case explorer</h1>
        <p className="text-helper mt-1">
          Find structurally similar past cases — how they compare, not what to decide.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Search className="h-4 w-4" /> Describe the case
          </CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <Label>Case type</Label>
            <Select value={caseClass} onValueChange={setCaseClass}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {Object.entries(CASE_CLASSES).map(([k, label]) => (
                  <SelectItem key={k} value={k}>{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Study mode</Label>
            <Select value={studyMode} onValueChange={setStudyMode}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {STUDY_MODES.map((m) => <SelectItem key={m} value={m}>{m.replace('_', ' ')}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Stage</Label>
            <Select value={stage} onValueChange={setStage}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {STAGES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col justify-end gap-2 pb-1">
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked={hasFunding} onCheckedChange={(v) => setHasFunding(!!v)} />
              Active funding
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked={supervisionOverdue} onCheckedChange={(v) => setSupervisionOverdue(!!v)} />
              Supervision overdue
            </label>
          </div>
          <div className="col-span-2 md:col-span-4">
            <Button size="sm" onClick={search} disabled={loading}>
              {loading ? 'Searching…' : 'Find comparable cases'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Permanent bias warning — spec §19. Not conditional on results existing. */}
      <div className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/20 px-3 py-2 text-xs text-amber-900 dark:text-amber-200">
        <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" aria-hidden />
        <span>
          Historical frequency is not a rule and may reflect old policy or practice — it
          describes what was done, never what should be done here.
        </span>
      </div>

      {error ? <AIStateBanner state="error" detail={error} action={{ label: 'Retry', onClick: search }} /> : null}

      {loading ? (
        <div className="space-y-2"><Skeleton className="h-20 w-full" /><Skeleton className="h-20 w-full" /></div>
      ) : result ? (
        <Card>
          <CardContent className="p-4 space-y-4">
            <div>
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">Similarity summary</p>
              <p className="text-sm">{result.narration}</p>
            </div>

            {result.candidates.length === 0 ? (
              <p className="text-sm text-muted-foreground">No comparable cases found for this combination.</p>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {result.candidates.map((c) => (
                  <div key={c.caseRef} className="rounded-md border p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs text-muted-foreground">{c.caseRef}</span>
                      <Badge variant="secondary">match {(c.score * 100).toFixed(0)}%</Badge>
                    </div>
                    <div className="flex flex-wrap gap-1.5 text-xs">
                      {c.features.stage ? <Badge variant="outline">{c.features.stage}</Badge> : null}
                      {c.features.study_mode ? <Badge variant="outline">{c.features.study_mode.replace('_', ' ')}</Badge> : null}
                      {c.features.has_active_funding !== null && c.features.has_active_funding !== undefined ? (
                        <Badge variant="outline">{c.features.has_active_funding ? 'funded' : 'unfunded'}</Badge>
                      ) : null}
                    </div>
                    <p className="text-[11px] text-muted-foreground">
                      {c.openedAt ? `Opened ${new Date(c.openedAt).toLocaleDateString()}` : 'Open date unknown'}
                    </p>
                    {/* Deliberately "Use as context / open case" — never "Copy outcome".
                        Disabled: the backend's candidate pool is a Task-row stand-in
                        (documented in memory/service.py) until the case-history
                        projection ships, so there's no real case to route to yet. */}
                    <Button size="sm" variant="ghost" className="h-7 -ml-2" disabled title="Case linking arrives with the case-history projection">
                      Open case <ExternalLink className="h-3 w-3 ml-1" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
