'use client'

/**
 * Research Change Radar — document comparison (spec §17-18).
 *
 * Earlier / Current side-by-side, then a review-oriented findings list. Rules:
 *   - Document selector is explicit: pick or register version A and version B,
 *     upload dates and extraction status stay visible.
 *   - Deterministic findings (scope/method/sample-size) are always computed;
 *     the optional LLM semantic pass is additive, clearly tagged "LLM".
 *   - No "breach" language — findings are counted by category, review implications
 *     are neutral.
 *   - Finding disposition (accept/dismiss/note) persists via the same endpoint
 *     the backend uses for governance — never silently forgotten.
 *   - Model-off: the side-by-side compare and any previously-saved findings still
 *     work — nothing here depends on the LLM being reachable.
 */
import { useState } from 'react'
import { AlertTriangle, CheckCircle2, FileText, Sparkles, XCircle } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { AIStateBanner } from './AIStateBanner'
import { intelligenceApi, type ChangeFinding, type DocumentVersion } from './api'

const SEVERITY_TONE: Record<ChangeFinding['severityForReview'], 'warning' | 'destructive'> = {
  notice: 'warning',
  urgent: 'destructive',
}

function VersionSlot({
  label, docRef, setDocRef, text, setText, version, onRegister, registering,
}: {
  label: string
  docRef: string
  setDocRef: (v: string) => void
  text: string
  setText: (v: string) => void
  version: DocumentVersion | null
  onRegister: () => void
  registering: boolean
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm flex items-center gap-2">
          <FileText className="h-4 w-4" /> {label}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <div>
          <Label>Document reference</Label>
          <Input value={docRef} onChange={(e) => setDocRef(e.target.value)}
                 placeholder="e.g. AnnualReview_2026" disabled={!!version} />
        </div>
        <div>
          <Label>Text content</Label>
          <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={10}
                     placeholder="Paste the document text — section headings on their own line become comparison chunks."
                     disabled={!!version} />
        </div>
        {version ? (
          <div className="rounded-md border bg-muted/30 p-2 text-xs space-y-0.5">
            <p><span className="text-muted-foreground">Version registered</span> · {version.extractionStatus}</p>
            <p className="font-mono text-[10px] text-muted-foreground truncate">{version.contentHash.slice(0, 16)}…</p>
          </div>
        ) : (
          <Button size="sm" onClick={onRegister} disabled={registering || !docRef.trim() || !text.trim()}>
            {registering ? 'Registering…' : 'Register version'}
          </Button>
        )}
      </CardContent>
    </Card>
  )
}

export function ChangeRadarWorkspace() {
  const [refA, setRefA] = useState('')
  const [refB, setRefB] = useState('')
  const [textA, setTextA] = useState('')
  const [textB, setTextB] = useState('')
  const [versionA, setVersionA] = useState<DocumentVersion | null>(null)
  const [versionB, setVersionB] = useState<DocumentVersion | null>(null)
  const [registeringA, setRegisteringA] = useState(false)
  const [registeringB, setRegisteringB] = useState(false)
  const [includeSemantic, setIncludeSemantic] = useState(false)
  const [findings, setFindings] = useState<ChangeFinding[] | null>(null)
  const [comparing, setComparing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dispositions, setDispositions] = useState<Record<string, string>>({})

  async function registerA() {
    setRegisteringA(true); setError(null)
    try {
      const v = await intelligenceApi.registerDocumentVersion({
        documentRef: refA, objectKey: `${refA}-a.txt`, content: textA,
      })
      setVersionA(v)
    } catch (e) { setError((e as Error).message) } finally { setRegisteringA(false) }
  }
  async function registerB() {
    setRegisteringB(true); setError(null)
    try {
      const v = await intelligenceApi.registerDocumentVersion({
        documentRef: refB || refA, objectKey: `${refB || refA}-b.txt`, content: textB,
      })
      setVersionB(v)
    } catch (e) { setError((e as Error).message) } finally { setRegisteringB(false) }
  }

  async function compare() {
    if (!versionA || !versionB) return
    setComparing(true); setError(null); setFindings(null)
    try {
      const f = await intelligenceApi.compareDocuments(versionA.id, versionB.id, includeSemantic)
      setFindings(f)
    } catch (e) { setError((e as Error).message) } finally { setComparing(false) }
  }

  async function dispose(findingId: string, disposition: 'accepted' | 'dismissed') {
    try {
      await intelligenceApi.disposeFinding(findingId, disposition)
      setDispositions((d) => ({ ...d, [findingId]: disposition }))
    } catch (e) { setError((e as Error).message) }
  }

  const bothRegistered = !!versionA && !!versionB
  const counts = findings?.reduce<Record<string, number>>((acc, f) => {
    acc[f.changeType] = (acc[f.changeType] ?? 0) + 1
    return acc
  }, {}) ?? {}

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-page-title">Research Change Radar</h1>
        <p className="text-helper mt-1">
          Compare two document versions — material changes surfaced as review flags, not verdicts.
        </p>
      </header>

      {error ? <AIStateBanner state="error" detail={error} /> : null}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <VersionSlot label="Earlier" docRef={refA} setDocRef={setRefA} text={textA} setText={setTextA}
                     version={versionA} onRegister={registerA} registering={registeringA} />
        <VersionSlot label="Current" docRef={refB} setDocRef={setRefB} text={textB} setText={setTextB}
                     version={versionB} onRegister={registerB} registering={registeringB} />
      </div>

      <div className="flex items-center gap-3">
        <label className="flex items-center gap-2 text-sm">
          <Checkbox checked={includeSemantic} onCheckedChange={(v) => setIncludeSemantic(!!v)} />
          Also run LLM semantic diff (beyond the deterministic pattern matcher)
        </label>
        <Button size="sm" onClick={compare} disabled={!bothRegistered || comparing}>
          {comparing ? 'Comparing…' : 'Compare versions'}
        </Button>
      </div>

      {comparing ? (
        <div className="space-y-2"><Skeleton className="h-16 w-full" /><Skeleton className="h-16 w-full" /></div>
      ) : findings ? (
        <Card>
          <CardContent className="p-4 space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-medium">
                {findings.length === 0 ? 'No material changes detected.' : `${findings.length} finding(s)`}
              </p>
              {Object.entries(counts).map(([type, n]) => (
                <Badge key={type} variant="outline">{n} × {type.replace(/_/g, ' ')}</Badge>
              ))}
            </div>

            {findings.length === 0 ? null : (
              <ul className="space-y-2">
                {findings.map((f) => {
                  const isLlm = f.sourceARef?.engine === 'llm' || f.sourceBRef?.engine === 'llm'
                  const disposition = dispositions[f.id] ?? f.reviewerDisposition
                  return (
                    <li key={f.id} className="rounded-md border p-3 space-y-2">
                      <div className="flex items-center justify-between gap-2 flex-wrap">
                        <div className="flex items-center gap-1.5">
                          <Badge variant={SEVERITY_TONE[f.severityForReview]}>{f.severityForReview}</Badge>
                          <Badge variant="outline">{f.changeType.replace(/_/g, ' ')}</Badge>
                          {isLlm ? (
                            <Badge variant="secondary" className="gap-1"><Sparkles className="h-3 w-3" /> LLM</Badge>
                          ) : null}
                        </div>
                        {disposition ? (
                          <Badge variant={disposition === 'accepted' ? 'success' : 'secondary'}>{disposition}</Badge>
                        ) : (
                          <div className="flex gap-1.5">
                            <Button size="sm" variant="ghost" className="h-7" onClick={() => dispose(f.id, 'accepted')}>
                              <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> Accept
                            </Button>
                            <Button size="sm" variant="ghost" className="h-7" onClick={() => dispose(f.id, 'dismissed')}>
                              <XCircle className="h-3.5 w-3.5 mr-1" /> Dismiss
                            </Button>
                          </div>
                        )}
                      </div>
                      <p className="text-sm">{f.summary}</p>
                      {f.sourceARef?.section_heading || f.sourceBRef?.section_heading ? (
                        <p className="text-[11px] font-mono text-muted-foreground">
                          section: {f.sourceARef?.section_heading ?? f.sourceBRef?.section_heading}
                        </p>
                      ) : null}
                    </li>
                  )
                })}
              </ul>
            )}
          </CardContent>
        </Card>
      ) : null}

      {/* Manual side-by-side stays available even with the model off — spec §17. */}
      {textA || textB ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-muted-foreground" /> Manual side-by-side
            </CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <pre className="text-xs whitespace-pre-wrap rounded-md border p-2 max-h-64 overflow-y-auto bg-muted/20">{textA || '—'}</pre>
            <pre className="text-xs whitespace-pre-wrap rounded-md border p-2 max-h-64 overflow-y-auto bg-muted/20">{textB || '—'}</pre>
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
