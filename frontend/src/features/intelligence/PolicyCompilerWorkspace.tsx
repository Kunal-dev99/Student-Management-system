'use client'

/**
 * Policy Compiler — three-column workspace (spec §20).
 *
 * SOURCE POLICY -> PROPOSED CHANGE -> IMPACT PREVIEW, side by side so a reviewer
 * can see the approved clause, the structured setting change it maps to, and how
 * many records it touches, all at once — this should look like governed
 * configuration management, never a chat prompt.
 *
 * Governance rules enforced by the backend and reflected here:
 *   - Only allow-listed settings can be proposed; anything else becomes an
 *     explicit "Manual implementation required" card.
 *   - The LLM path is additive and clearly marked; the regex-matched candidates
 *     are never replaced by it.
 *   - Publish is a real state transition (draft -> approved/rejected/published)
 *     with an audit trail (reviewedAt/publishedAt) — but it only records the
 *     governance decision. It does NOT write the setting value anywhere; applying
 *     an approved change is still a separate step in the settings screen today.
 *     Don't overclaim this in the UI — say what actually happens.
 */
import { useState } from 'react'
import { AlertTriangle, CheckCircle2, FileText, GitCompare, Sparkles, XCircle } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { AIStateBanner } from './AIStateBanner'
import { intelligenceApi, type PolicyProposal } from './api'

export function PolicyCompilerWorkspace() {
  const [policyRef, setPolicyRef] = useState('')
  const [versionLabel, setVersionLabel] = useState('')
  const [policyText, setPolicyText] = useState('')
  const [enableLlm, setEnableLlm] = useState(false)
  const [versionId, setVersionId] = useState<string | null>(null)
  const [proposal, setProposal] = useState<PolicyProposal | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reviewing, setReviewing] = useState(false)

  async function compile() {
    if (!policyRef.trim() || !versionLabel.trim() || !policyText.trim()) {
      setError('Policy reference, version label and policy text are all required.')
      return
    }
    setLoading(true); setError(null); setProposal(null)
    try {
      const ver = await intelligenceApi.registerPolicyVersion({ policyRef, versionLabel })
      setVersionId(ver.id)
      const prop = await intelligenceApi.proposePolicyChanges({
        policyVersionId: ver.id, policyText, enableLlm,
      })
      setProposal(prop)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  async function review(disposition: 'approved' | 'rejected' | 'published') {
    if (!proposal) return
    setReviewing(true)
    try {
      const r = await intelligenceApi.reviewPolicyProposal(proposal.id, disposition)
      setProposal({ ...proposal, status: r.status as PolicyProposal['status'], reviewedAt: r.reviewedAt })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setReviewing(false)
    }
  }

  const ruleCandidates = proposal?.ruleCandidates.filter((c) => !c.manual) ?? []
  const manualItems = proposal?.ruleCandidates.filter((c) => c.manual) ?? []

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-page-title">Policy Compiler</h1>
        <p className="text-helper mt-1">
          Source policy → proposed mapping → affected population — governed configuration
          management, not a chat prompt.
        </p>
      </header>

      {error ? <AIStateBanner state="error" detail={error} /> : null}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* ---- Column 1: Source policy ---- */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <FileText className="h-4 w-4" /> Source policy
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <Label>Policy reference</Label>
              <Input value={policyRef} onChange={(e) => setPolicyRef(e.target.value)}
                     placeholder="e.g. 2027-PGR-Progression-Regs" />
            </div>
            <div>
              <Label>Version label</Label>
              <Input value={versionLabel} onChange={(e) => setVersionLabel(e.target.value)}
                     placeholder="e.g. v3" />
            </div>
            <div>
              <Label>Approved clause text</Label>
              <Textarea
                value={policyText}
                onChange={(e) => setPolicyText(e.target.value)}
                rows={10}
                placeholder="Paste the approved policy clauses here — e.g. 'Clause 4.2: Annual review must occur within 10 months of registration.'"
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked={enableLlm} onCheckedChange={(v) => setEnableLlm(!!v)} />
              Also try LLM extraction for clauses the pattern matcher misses
            </label>
            <Button size="sm" onClick={compile} disabled={loading} className="w-full">
              {loading ? 'Compiling…' : 'Compile proposal'}
            </Button>
          </CardContent>
        </Card>

        {/* ---- Column 2: Proposed change ---- */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <GitCompare className="h-4 w-4" /> Proposed change
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {loading ? (
              <div className="space-y-2"><Skeleton className="h-10 w-full" /><Skeleton className="h-10 w-full" /></div>
            ) : !proposal ? (
              <p className="text-sm text-muted-foreground">Compile a proposal to see the structured mapping.</p>
            ) : (
              <>
                {ruleCandidates.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No allow-listed setting changes detected.</p>
                ) : (
                  <ul className="space-y-2">
                    {ruleCandidates.map((c, i) => (
                      <li key={i} className="rounded-md border p-2.5 space-y-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-medium font-mono">{c.setting_key}</span>
                          {c.engine === 'llm' ? (
                            <Badge variant="secondary" className="gap-1">
                              <Sparkles className="h-3 w-3" /> LLM
                            </Badge>
                          ) : (
                            <Badge variant="outline">rule</Badge>
                          )}
                        </div>
                        <p className="text-sm">
                          <span className="text-muted-foreground">{String(c.from_value ?? '—')}</span>
                          <span className="mx-1.5">→</span>
                          <span className="font-semibold">{String(c.to_value ?? '—')}</span>
                        </p>
                        <p className="text-xs text-muted-foreground">{c.rationale}</p>
                      </li>
                    ))}
                  </ul>
                )}

                {manualItems.length > 0 ? (
                  <div>
                    <p className="text-[11px] uppercase tracking-wide text-muted-foreground mt-3 mb-1.5">
                      Unsupported clauses
                    </p>
                    <ul className="space-y-2">
                      {manualItems.map((m, i) => (
                        <li key={i} className="rounded-md border border-dashed border-amber-300 dark:border-amber-800 p-2.5">
                          <div className="flex items-center gap-1.5 text-amber-800 dark:text-amber-200 text-xs font-medium">
                            <AlertTriangle className="h-3.5 w-3.5" /> Manual implementation required
                          </div>
                          <p className="text-xs text-muted-foreground mt-1">{m.reason}</p>
                          {m.matched_span ? (
                            <p className="text-[11px] font-mono text-muted-foreground/70 mt-1 truncate">"{m.matched_span}"</p>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </>
            )}
          </CardContent>
        </Card>

        {/* ---- Column 3: Impact preview ---- */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Impact preview</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {loading ? (
              <Skeleton className="h-24 w-full" />
            ) : !proposal ? (
              <p className="text-sm text-muted-foreground">Impact numbers appear once a proposal is compiled.</p>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-md border p-3">
                    <p className="text-2xl font-semibold tabular-nums">{ruleCandidates.length}</p>
                    <p className="text-xs text-muted-foreground">setting change(s) proposed</p>
                  </div>
                  <div className="rounded-md border p-3">
                    <p className="text-2xl font-semibold tabular-nums">
                      {proposal.simulationResult?.milestone_universe ?? '—'}
                    </p>
                    <p className="text-xs text-muted-foreground">milestones in scope</p>
                  </div>
                </div>

                <div className="pt-2 border-t">
                  <p className="text-xs text-muted-foreground mb-2">
                    Status: <Badge variant={
                      proposal.status === 'published' ? 'success'
                      : proposal.status === 'rejected' ? 'destructive'
                      : proposal.status === 'approved' ? 'secondary'
                      : 'outline'
                    }>{proposal.status}</Badge>
                  </p>
                  {proposal.status === 'draft' ? (
                    <div className="flex flex-wrap gap-2">
                      <Button size="sm" variant="outline" onClick={() => review('approved')} disabled={reviewing}>
                        <CheckCircle2 className="h-3.5 w-3.5 mr-1.5" /> Approve
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => review('rejected')} disabled={reviewing}>
                        <XCircle className="h-3.5 w-3.5 mr-1.5" /> Reject
                      </Button>
                    </div>
                  ) : proposal.status === 'approved' ? (
                    <Button size="sm" onClick={() => review('published')} disabled={reviewing}>
                      Publish
                    </Button>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      {proposal.reviewedAt ? `Reviewed ${new Date(proposal.reviewedAt).toLocaleString()}` : null}
                    </p>
                  )}
                </div>

                <p className="text-[11px] text-muted-foreground pt-2 border-t">
                  {proposal.status === 'published'
                    ? 'Published records governance approval and timestamps it. Applying each setting still requires the platform\'s own configuration screen — this does not write the value automatically.'
                    : 'Approve/Reject/Publish record a governed decision and audit trail. Applying an approved setting change is a separate step in the platform\'s configuration screen.'}
                </p>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
