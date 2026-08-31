'use client'

/**
 * Pattern Lab — the governed intelligence workbench (PL-1…PL-6).
 *
 * Six tabs: Overview (home §6.1), Discover (the four-step wizard §6.2–6.7 plus
 * training), Models (the PL-3 registry — versions, honest metrics, permutation
 * importance — plus PL-4 governance: the lifecycle pipeline, rationale-gated
 * decisions, auto-generated model cards and lineage), Predictions (PL-5: batch
 * scoring by production versions only, distribution + highest-risk table with
 * per-student contributing factors, always advisory), and Monitoring (PL-6:
 * per-production-model health, performance vs matured actuals, population
 * drift, the prediction trend, and the manual-first retrain loop — monitoring
 * recommends, it never acts). Viewing needs `ml.read`; building datasets and
 * running discovery needs `ml.analyse`; the candidate search, submitting for
 * review, batch scoring and retraining need `ml.train`; every governance
 * decision (approve/decline/promote/retire) needs `ml.approve` — enforced
 * server-side, mirrored here as a convenience.
 *
 * Design rules honoured: no chart library — every rate/completeness/importance/
 * distribution bar is a plain div; statuses are low-opacity badge fills; backend
 * refusal messages (sufficiency gate, missing ML extra, wrong-state transitions,
 * approver separation and the no-production-version scoring block) are surfaced
 * verbatim. A failed training run is a *result*, not an error — it renders as
 * information.
 */

import { Fragment, useEffect, useMemo, useState, type ReactNode } from 'react'
import Link from 'next/link'
import {
  Activity,
  AlertTriangle,
  Boxes,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Cpu,
  Database,
  FileText,
  FlaskConical,
  Info,
  LayoutDashboard,
  Lock,
  Microscope,
  Plus,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Target,
  TrendingUp,
} from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Collapsible, CollapsibleContent, CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useToast } from '@/components/ui/use-toast'
import { cn } from '@/lib/utils'
import { ApiError } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import {
  useBuildDataset,
  useDatasetFindings,
  useMlAvailability,
  useMlModels,
  useModelCard,
  useMonitoring,
  usePatternDatasets,
  usePatternLabOverview,
  usePatternTargets,
  usePredictionBatches,
  useRetrainModel,
  useRunDiscovery,
  useScoreModel,
  useTrainModel,
  useTransitionVersion,
  useVersionLineage,
  type CandidateResult,
  type DistributionBand,
  type DriftRow,
  type GovernanceAction,
  type GovernanceEntry,
  type MlModel,
  type MlModelVersion,
  type MlVersionStatus,
  type ModelBatch,
  type ModelCard as ModelCardDoc,
  type MonitoringEntry,
  type PatternDataset,
  type PatternFinding,
  type PatternTarget,
  type RetrainResult,
  type TrainRun,
  type TrainRunDetail,
} from '@/features/pattern-lab/api'
import { FactorChips, ProbabilityBar } from '@/features/pattern-lab/StudentPredictionsPanel'

/* ------------------------------- formatting ------------------------------- */

const pct = (rate: number) => `${Math.round(rate * 100)}%`
const fmtP = (p: number) => (p < 0.0001 ? '< 0.0001' : p.toFixed(4))
const fmtEffect = (effect: number) => `${effect.toFixed(1)}× the rate`

const ALGO_LABELS: Record<string, string> = {
  baseline_prior: 'Baseline (class prior)',
  logistic_regression: 'Logistic regression',
  random_forest: 'Random forest',
  gradient_boosting: 'Gradient boosting',
}
const algoLabel = (algo: string) => ALGO_LABELS[algo] ?? algo.replace(/_/g, ' ')
const fmtMetric = (v: number | null | undefined) => (v == null ? '—' : v.toFixed(3))

/** Translate an AUC into words a non-technical reader can act on.
 *  1.0 = perfect separation, 0.5 = a coin toss. */
const aucPlain = (v: number | null | undefined): string | null => {
  if (v == null) return null
  if (v >= 0.8) return 'strong'
  if (v >= 0.7) return 'fair'
  if (v >= 0.6) return 'weak'
  if (v >= 0.55) return 'very weak'
  return 'no better than guessing'
}

/** Rotating status lines while a long job runs, so the wait feels alive and the
 *  user can see WHAT is happening in their own terms. Purely cosmetic — the
 *  real work is one API call. */
function Working({ messages }: { messages: string[] }) {
  const [i, setI] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setI((n) => (n + 1) % messages.length), 2000)
    return () => clearInterval(t)
  }, [messages.length])
  return (
    <div className="flex items-center gap-2.5 rounded-md border border-[hsl(var(--info)/0.3)] bg-[hsl(var(--info)/0.06)] px-3 py-2.5 my-2" role="status" aria-live="polite">
      <span className="h-3.5 w-3.5 shrink-0 rounded-full border-2 border-[hsl(var(--info))] border-t-transparent animate-spin" />
      <span className="text-sm text-foreground/85">{messages[i]}</span>
    </div>
  )
}

/** Progressive disclosure: heavy technical blocks live behind this collapsed
 *  toggle so the default view stays readable for a non-technical admin. */
function TechDetails({ label = 'Technical detail', children }: { label?: string; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
        aria-expanded={open}
      >
        {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        {label}
      </button>
      {open && <div className="mt-2">{children}</div>}
    </div>
  )
}

const BUILD_MSGS = [
  'Reading every student history…',
  'Deciding who counts — and noting who had to be left out, and why…',
  'Locking away answer-sheet facts the model must never see…',
  'Writing the quality report…',
]
const DISCOVER_MSGS = [
  'Splitting students into comparison groups…',
  'Testing pattern after pattern…',
  'Being strict — applying the multiple-comparisons penalty…',
  'Attaching evidence and cautions to each finding…',
]
const TRAIN_MSGS = [
  'Teaching four different model families the same history…',
  'Quizzing each one on students it has never seen…',
  'Making every candidate beat blind guessing before it counts…',
  'Comparing the candidates…',
  'Writing the model card — strengths, limits and all…',
]
const SCORE_MSGS = [
  'Lining up the current cohort…',
  'Scoring each student against the learned pattern…',
  'Attaching the reasons behind every score…',
]

/** The whole Pattern Lab pipeline in one glance — which stage lives in which
 *  tab, so nobody wonders "what do I do next?". Chips are clickable. */
function JourneyBar({ tab, onGo }: { tab: string; onGo: (t: string) => void }) {
  const steps = [
    { n: 1, label: 'Ask & analyse', tab: 'discover', hint: 'pick a question, snapshot, discover, train' },
    { n: 2, label: 'Approve', tab: 'models', hint: 'a person promotes a candidate' },
    { n: 3, label: 'Score students', tab: 'predictions', hint: 'advisory scores with reasons' },
    { n: 4, label: 'Keep it honest', tab: 'monitoring', hint: 'compare predictions with reality' },
  ]
  return (
    <div className="mt-3 flex flex-wrap items-center gap-1.5">
      <span className="text-xs text-muted-foreground mr-1">The journey:</span>
      {steps.map((st, i) => (
        <Fragment key={st.tab}>
          {i > 0 && <span className="text-muted-foreground/50 text-xs">→</span>}
          <button
            type="button"
            onClick={() => onGo(st.tab)}
            title={st.hint}
            className={
              'rounded-full border px-2.5 py-0.5 text-xs transition-colors ' +
              (tab === st.tab
                ? 'border-primary bg-primary text-primary-foreground font-medium'
                : 'border-border text-muted-foreground hover:border-primary/50 hover:text-foreground')
            }
          >
            {st.n}. {st.label}
          </button>
        </Fragment>
      ))}
    </div>
  )
}

/** One friendly paragraph at the top of each tab, written for a registry
 *  administrator, not a data scientist. */
function PlainIntro({ children }: { children: ReactNode }) {
  return (
    <div className="mb-4 rounded-md border border-[hsl(var(--info)/0.3)] bg-[hsl(var(--info)/0.06)] px-4 py-3">
      <p className="text-sm text-foreground/85 leading-relaxed">
        <span className="font-semibold text-[hsl(var(--info))]">In plain terms: </span>
        {children}
      </p>
    </div>
  )
}
const fmtBytes = (b: number) =>
  b >= 1024 * 1024 ? `${(b / (1024 * 1024)).toFixed(1)} MB`
  : b >= 1024 ? `${(b / 1024).toFixed(1)} KB`
  : `${b} B`
const fmtParams = (params: Record<string, unknown>) =>
  Object.keys(params).length === 0
    ? 'defaults'
    : Object.entries(params).map(([k, v]) => `${k}=${String(v)}`).join(', ')
const shortHash = (v: string) => (v.length > 8 ? `${v.slice(0, 8)}…` : v)

/* ------------------------------ small pieces ------------------------------ */

function NoPermission() {
  return (
    <Card className="card-elevated">
      <CardContent className="py-12 text-center space-y-2">
        <ShieldAlert className="h-8 w-8 mx-auto text-muted-foreground" />
        <p className="font-medium">Pattern Lab access required</p>
        <p className="text-helper max-w-md mx-auto">
          This area requires the <span className="font-mono text-xs">ml.read</span> permission.
          Ask an administrator to grant you a role that includes it.
        </p>
      </CardContent>
    </Card>
  )
}

function ErrorCard({ error }: { error: unknown }) {
  if (error instanceof ApiError && error.status === 403) return <NoPermission />
  return (
    <Card className="card-elevated">
      <CardContent className="py-10 text-center space-y-2">
        <AlertTriangle className="h-7 w-7 mx-auto text-danger" />
        <p className="font-medium">Something went wrong</p>
        <p className="text-helper max-w-md mx-auto">{(error as Error)?.message ?? 'Request failed'}</p>
      </CardContent>
    </Card>
  )
}

function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="card-elevated p-4">
      <p className="text-label">{label}</p>
      <p className="mt-1 text-2xl font-semibold tracking-tight num">{value}</p>
      {hint && <p className="text-helper mt-0.5">{hint}</p>}
    </div>
  )
}

function StepChip({ n }: { n: number }) {
  return (
    <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-primary/10 px-1.5 text-[11px] font-semibold text-primary">
      {n}
    </span>
  )
}

/** Plain-div horizontal rate bar — the committee-readable evidence visual. */
function RateBar({
  label, rate, n, tone,
}: { label: string; rate: number; n: number; tone: 'danger' | 'success' }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="truncate">{label}</span>
        <span className="num font-medium shrink-0">
          {pct(rate)} <span className="text-muted-foreground font-normal">of {n}</span>
        </span>
      </div>
      <div className="mt-1 h-2 rounded-full bg-surface-3 overflow-hidden">
        <div
          className={cn('h-full rounded-full', tone === 'danger' ? 'bg-danger/70' : 'bg-success/70')}
          style={{ width: `${Math.max(2, Math.round(rate * 100))}%` }}
        />
      </div>
    </div>
  )
}

/** The excluded-features governance callout — headline, not fine print. */
function LeakageCallout({ features }: { features: { key: string; label: string; reason: string }[] }) {
  if (features.length === 0) return null
  return (
    <div className="rounded-md border border-warning/40 bg-warning/10 p-4">
      <div className="flex items-center gap-2">
        <ShieldAlert className="h-4 w-4 text-warning shrink-0" />
        <p className="text-sm font-medium">Excluded to prevent leakage</p>
        <p className="text-xs text-muted-foreground">
          These facts arrive only after the outcome is known — letting the model see them would be
          letting it cheat by reading the answer sheet.
        </p>
      </div>
      <p className="text-xs text-muted-foreground mt-1">
        These features would only be knowable after the prediction point, so using them would
        let the outcome leak into the analysis. They are excluded structurally, not by review.
      </p>
      <ul className="mt-3 space-y-1.5">
        {features.map((f) => (
          <li key={f.key} className="text-sm flex flex-wrap items-baseline gap-x-2">
            <span className="font-medium">{f.label}</span>
            <span className="text-muted-foreground text-xs">{f.reason}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/* ------------------------- PL-3 shared training pieces ------------------------- */

/**
 * The run verdict, styled honestly: success is green; a failed run is amber
 * *information* (the backend note verbatim), never an error banner — a documented
 * failure is a result.
 */
function VerdictBanner({ detail }: { detail: TrainRunDetail }) {
  if (detail.verdict === 'succeeded') {
    return (
      <div className="rounded-md border border-[hsl(var(--success)/0.3)] bg-[hsl(var(--success)/0.08)] p-3 flex gap-2">
        <CheckCircle2 className="h-4 w-4 text-success shrink-0 mt-0.5" />
        <div className="text-sm">
          <p className="font-medium">Recommended: {algoLabel(detail.recommended ?? '')}</p>
          <p className="text-muted-foreground text-xs mt-0.5">
            Beat the baseline (AUC <span className="num">{detail.baselineAuc.toFixed(3)}</span>) by
            the required margin of <span className="num">{detail.baselineMargin}</span>, with
            mean − std above 0.5. The recommended version is now the{' '}
            <span className="font-medium text-foreground">candidate</span>.
          </p>
        </div>
      </div>
    )
  }
  return (
    <div className="rounded-md border border-warning/40 bg-warning/10 p-3 flex gap-2">
      <Info className="h-4 w-4 text-warning shrink-0 mt-0.5" />
      <div className="text-sm">
        <p className="font-medium">No candidate beat the baseline</p>
        {detail.note && <p className="text-xs mt-0.5">{detail.note}</p>}
      </div>
    </div>
  )
}

/** The honest comparison table — every candidate incl. the baseline, same metrics. */
function CandidateTable({
  candidates, recommended,
}: { candidates: CandidateResult[]; recommended: string | null }) {
  return (
    <div className="rounded-md border border-border overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Candidate</TableHead>
            <TableHead className="text-right">AUC (mean ± std)</TableHead>
            <TableHead className="text-right">Avg precision</TableHead>
            <TableHead className="text-right">Brier</TableHead>
            <TableHead className="text-right">Precision @0.5</TableHead>
            <TableHead className="text-right">Recall @0.5</TableHead>
            <TableHead>Verdict</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {candidates.map((c) => (
            <TableRow key={c.algorithm} className={cn(c.isBaseline && 'text-muted-foreground')}>
              <TableCell>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className={cn('text-sm', !c.isBaseline && 'font-medium')}>
                    {algoLabel(c.algorithm)}
                  </span>
                  {c.isBaseline && <Badge variant="outline">baseline</Badge>}
                  {recommended != null && c.algorithm === recommended && (
                    <Badge variant="success">recommended</Badge>
                  )}
                </div>
                {!c.isBaseline && (
                  <p className="text-[11px] text-muted-foreground font-mono mt-0.5">
                    {fmtParams(c.params)}
                  </p>
                )}
              </TableCell>
              <TableCell className="text-right num whitespace-nowrap">
                {c.metrics.aucMean.toFixed(3)}{' '}
                <span className="text-muted-foreground">± {c.metrics.aucStd.toFixed(3)}</span>
              </TableCell>
              <TableCell className="text-right num">{fmtMetric(c.metrics.averagePrecision)}</TableCell>
              <TableCell className="text-right num">{fmtMetric(c.metrics.brierScore)}</TableCell>
              <TableCell className="text-right num">{fmtMetric(c.metrics.precisionAt50)}</TableCell>
              <TableCell className="text-right num">{fmtMetric(c.metrics.recallAt50)}</TableCell>
              <TableCell>
                {c.isBaseline
                  ? <span className="text-xs text-muted-foreground">the bar to clear</span>
                  : c.beatsBaseline
                    ? <Badge variant="success">beats baseline</Badge>
                    : <Badge variant="secondary">does not beat baseline</Badge>}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

/** Full run report: verdict banner + comparison table + dropped features. */
function TrainRunReport({ detail }: { detail: TrainRunDetail }) {
  return (
    <div className="space-y-3">
      <VerdictBanner detail={detail} />
      <CandidateTable candidates={detail.candidates} recommended={detail.recommended} />
      {detail.droppedFeatures.length > 0 && (
        <div>
          <p className="text-label mb-1.5">Features dropped before training</p>
          <ul className="space-y-1">
            {detail.droppedFeatures.map((f) => (
              <li key={f.key} className="text-xs text-muted-foreground">
                <span className="font-mono text-foreground/80">{f.key}</span> — {f.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

const hasDetail = (d: TrainRunDetail | Record<string, never>): d is TrainRunDetail =>
  !!d && typeof (d as TrainRunDetail).verdict === 'string'

/* --------------------------- PL-4 governance pieces --------------------------- */

/** Low-opacity pill classes per lifecycle status — the design system's status idiom. */
const STATUS_TONES: Record<MlVersionStatus, string> = {
  trained: 'border-border bg-surface-2 text-muted-foreground',
  candidate: 'border-[hsl(var(--info)/0.3)] bg-[hsl(var(--info)/0.1)] text-[hsl(var(--info))]',
  review: 'border-[hsl(var(--warning)/0.3)] bg-[hsl(var(--warning)/0.1)] text-[hsl(var(--warning))]',
  approved: 'border-[hsl(var(--primary)/0.3)] bg-[hsl(var(--primary)/0.1)] text-[hsl(var(--primary))]',
  production: 'border-[hsl(var(--success)/0.3)] bg-[hsl(var(--success)/0.1)] text-[hsl(var(--success))]',
  declined: 'border-[hsl(var(--danger)/0.3)] bg-[hsl(var(--danger)/0.1)] text-[hsl(var(--danger))]',
  retired: 'border-border bg-surface-2 text-muted-foreground',
}

const isVersionStatus = (s: string): s is MlVersionStatus => s in STATUS_TONES

/** Shared status badge — sensible tones for every lifecycle status, low-opacity fills. */
function StatusBadge({ status, className }: { status: string; className?: string }) {
  return (
    <Badge
      variant="outline"
      className={cn(isVersionStatus(status) && STATUS_TONES[status], className)}
    >
      {status}
    </Badge>
  )
}

const PIPELINE: MlVersionStatus[] = ['trained', 'candidate', 'review', 'approved', 'production']

/**
 * The compact lifecycle stepper: trained → candidate → review → approved →
 * production, current stage highlighted in its status tone. The two terminal
 * exits (declined, retired) render as a badge beside the pipeline, next to the
 * stage they exited from.
 */
function StatusPipeline({ status }: { status: MlVersionStatus }) {
  const terminal = status === 'declined' || status === 'retired'
  // declined exits from review; retired exits from production.
  const currentIdx = terminal
    ? PIPELINE.indexOf(status === 'declined' ? 'review' : 'production')
    : PIPELINE.indexOf(status)
  return (
    <div className="flex flex-wrap items-center gap-1 text-[11px]">
      {PIPELINE.map((stage, i) => (
        <Fragment key={stage}>
          {i > 0 && <span aria-hidden className="text-muted-foreground/50">→</span>}
          <span
            className={cn(
              'rounded-sm border px-1.5 py-0.5',
              i === currentIdx && !terminal
                ? cn('font-semibold', STATUS_TONES[stage])
                : i <= currentIdx
                  ? 'border-border/60 bg-transparent text-muted-foreground'
                  : 'border-border/40 bg-transparent text-muted-foreground/50',
            )}
          >
            {stage}
          </span>
        </Fragment>
      ))}
      {terminal && <StatusBadge status={status} className="ml-1" />}
    </div>
  )
}

interface DecisionConfig {
  label: string
  title: string
  /** One-line explanation of the decision being made. */
  explain: (v: MlModelVersion) => string
  confirmLabel: string
  successTitle: string
}

/** The four rationale-gated decisions. `submit_review` is direct (no rationale). */
const DECISIONS: Partial<Record<GovernanceAction, DecisionConfig>> = {
  approve: {
    label: 'Approve…',
    title: 'Approve this version',
    explain: (v) =>
      `Approving v${v.versionNo} (${algoLabel(v.algorithm)}) records that its evidence and limitations were reviewed and it may be promoted to production.`,
    confirmLabel: 'Approve version',
    successTitle: 'Version approved',
  },
  decline: {
    label: 'Decline…',
    title: 'Decline this version',
    explain: (v) =>
      `Declining v${v.versionNo} (${algoLabel(v.algorithm)}) ends its lifecycle — a declined version cannot re-enter review.`,
    confirmLabel: 'Decline version',
    successTitle: 'Version declined',
  },
  promote: {
    label: 'Promote to production…',
    title: 'Promote to production',
    explain: (v) =>
      `Promoting v${v.versionNo} (${algoLabel(v.algorithm)}) makes it this model's production version — any current production version is retired automatically.`,
    confirmLabel: 'Promote to production',
    successTitle: 'Promoted to production',
  },
  retire: {
    label: 'Retire…',
    title: 'Retire this version',
    explain: (v) =>
      `Retiring v${v.versionNo} (${algoLabel(v.algorithm)}) removes it from production — retirement is terminal.`,
    confirmLabel: 'Retire version',
    successTitle: 'Version retired',
  },
}

/**
 * Governance actions for one version, appropriate to its current status.
 * Decisions open a rationale dialog — the rationale is required and lands on
 * the append-only log. Backend refusals (wrong state, approver separation,
 * baseline block) are governance copy: surfaced verbatim, never rephrased.
 */
function GovernanceActions({ version }: { version: MlModelVersion }) {
  const { hasPermission } = useAuth()
  const canTrain = hasPermission('ml.train')
  const canApprove = hasPermission('ml.approve')
  const { toast } = useToast()
  const transition = useTransitionVersion()
  const [pending, setPending] = useState<GovernanceAction | null>(null)
  const [rationale, setRationale] = useState('')

  const run = async (action: GovernanceAction, withRationale?: string) => {
    try {
      const res = await transition.mutateAsync({
        versionId: version.id,
        action,
        rationale: withRationale,
      })
      const config = DECISIONS[action]
      toast({
        title: config?.successTitle ?? 'Submitted for review',
        description: res.retiredIncumbent
          ? `Retired ${res.retiredIncumbent}.`
          : `Now in status '${res.status}'.`,
      })
      setPending(null)
      setRationale('')
    } catch (e) {
      // 409s (wrong state, approver separation, baseline block), 400s and 403s
      // are the governance model speaking — show them verbatim.
      toast({ title: 'Governance refused', description: (e as Error).message, variant: 'destructive' })
    }
  }

  const openDecision = (action: GovernanceAction) => {
    setRationale('')
    setPending(action)
  }

  const decisionButton = (action: GovernanceAction, variant: 'default' | 'outline' = 'default') => {
    const config = DECISIONS[action]
    if (!config) return null
    return (
      <Button
        key={action}
        size="sm"
        variant={variant}
        disabled={!canApprove || transition.isPending}
        title={canApprove ? undefined : 'Requires the ml.approve permission'}
        onClick={() => openDecision(action)}
      >
        {config.label}
      </Button>
    )
  }

  const buttons: ReactNode[] = []
  if (version.status === 'candidate') {
    buttons.push(
      <Button
        key="submit_review"
        size="sm"
        disabled={!canTrain || transition.isPending}
        title={canTrain ? undefined : 'Requires the ml.train permission'}
        onClick={() => run('submit_review')}
      >
        {transition.isPending ? 'Submitting…' : 'Submit for review'}
      </Button>,
    )
  } else if (version.status === 'review') {
    buttons.push(decisionButton('approve'), decisionButton('decline', 'outline'))
  } else if (version.status === 'approved') {
    buttons.push(decisionButton('promote'))
  } else if (version.status === 'production') {
    buttons.push(decisionButton('retire', 'outline'))
  }

  const needsApprove =
    version.status === 'review' || version.status === 'approved' || version.status === 'production'
  const pendingConfig = pending ? DECISIONS[pending] : undefined

  if (buttons.length === 0) return null
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        {buttons}
        {needsApprove && !canApprove && (
          <span className="text-xs text-muted-foreground">
            requires <span className="font-mono">ml.approve</span>
          </span>
        )}
      </div>

      <Dialog open={!!pending} onOpenChange={(open) => { if (!open) setPending(null) }}>
        <DialogContent className="max-w-lg">
          {pending && pendingConfig && (
            <>
              <DialogHeader>
                <DialogTitle>{pendingConfig.title}</DialogTitle>
                <DialogDescription>{pendingConfig.explain(version)}</DialogDescription>
              </DialogHeader>
              <div>
                <label htmlFor="pl-gov-rationale" className="text-label mb-1.5 block">
                  Rationale
                </label>
                <Textarea
                  id="pl-gov-rationale"
                  value={rationale}
                  onChange={(e) => setRationale(e.target.value)}
                  placeholder="Why this decision is being made…"
                  autoFocus
                />
                <p className="text-helper text-xs mt-1.5">
                  A written rationale is recorded permanently on this version.
                </p>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setPending(null)}>Cancel</Button>
                <Button
                  disabled={!rationale.trim() || transition.isPending}
                  onClick={() => run(pending, rationale.trim())}
                >
                  {transition.isPending ? 'Recording…' : pendingConfig.confirmLabel}
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}

const LINEAGE_KIND_LABELS: Record<string, string> = {
  dataset: 'Dataset',
  features: 'Features',
  trainingRun: 'Training run',
  version: 'Version',
  predictions: 'Predictions',
}

/** The five-node provenance chain, as small connected boxes — plain divs. */
function LineageStrip({ versionId }: { versionId: string }) {
  const lineageQ = useVersionLineage(versionId)
  if (lineageQ.isLoading) return <Skeleton className="h-12 w-full" />
  if (lineageQ.isError) {
    return (
      <p className="text-helper text-xs">
        Lineage unavailable — {(lineageQ.error as Error)?.message ?? 'request failed'}
      </p>
    )
  }
  if (!lineageQ.data) return null
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {lineageQ.data.chain.map((node, i) => (
        <Fragment key={node.kind}>
          {i > 0 && <span aria-hidden className="text-muted-foreground/60 text-xs">→</span>}
          <div className="rounded-md border border-border bg-surface-2 px-2.5 py-1.5 min-w-0 max-w-[14rem]">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
              {LINEAGE_KIND_LABELS[node.kind] ?? node.kind}
            </p>
            <p className="text-xs font-medium truncate" title={node.label}>{node.label}</p>
            {node.sub && (
              <p className="text-[11px] text-muted-foreground truncate" title={node.sub}>
                {node.sub}
              </p>
            )}
          </div>
        </Fragment>
      ))}
    </div>
  )
}

const GOV_ACTION_LABELS: Record<string, string> = {
  submit_review: 'Submitted for review',
  approve: 'Approved',
  decline: 'Declined',
  promote: 'Promoted to production',
  retire: 'Retired',
}

/** Governance history as a timeline — action, decider, date, rationale in quotes. */
function GovernanceTimeline({ entries }: { entries: GovernanceEntry[] }) {
  if (entries.length === 0) {
    return <p className="text-helper text-xs">No governance actions recorded yet.</p>
  }
  return (
    <ol className="relative border-l border-border pl-4 space-y-3">
      {entries.map((g, i) => (
        <li key={`${g.action}-${g.at}-${i}`} className="relative">
          <span
            aria-hidden
            className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-primary/70"
          />
          <div className="flex flex-wrap items-center gap-1.5 text-sm">
            <span className="font-medium">{GOV_ACTION_LABELS[g.action] ?? g.action}</span>
            <StatusBadge status={g.status} />
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            {g.byEmail ?? 'system'} · {new Date(g.at).toLocaleString()}
          </p>
          {g.rationale && <p className="text-sm mt-1 italic">“{g.rationale}”</p>}
        </li>
      ))}
    </ol>
  )
}

function CardField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="text-sm mt-0.5">{children}</p>
    </div>
  )
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-surface-1 p-2.5 text-center">
      <p className="text-sm font-medium num">{value}</p>
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground mt-0.5">{label}</p>
    </div>
  )
}

/** The card body — a formal document you could print for a committee. */
function ModelCardDocument({ card }: { card: ModelCardDoc }) {
  const perf = card.performance
  return (
    <div className="space-y-5">
      <StatusPipeline status={card.status} />

      <section>
        <p className="text-label mb-2">Purpose</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <CardField label="Question">{card.purpose.question ?? '—'}</CardField>
          <CardField label="Outcome">{card.purpose.outcome ?? '—'}</CardField>
          <CardField label="Population">{card.purpose.population ?? '—'}</CardField>
          <CardField label="Prediction point">{card.purpose.predictionPoint ?? '—'}</CardField>
        </div>
      </section>

      <section>
        <p className="text-label mb-2">Data</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <CardField label="Dataset version">
            <span className="font-mono text-xs" title={card.data.datasetVersion}>
              {shortHash(card.data.datasetVersion)}
            </span>
          </CardField>
          <CardField label="Built">
            {card.data.builtAt ? new Date(card.data.builtAt).toLocaleString() : '—'}
          </CardField>
          <CardField label="Records found → eligible">
            <span className="num">{card.data.recordsFound ?? '—'} → {card.data.eligible ?? '—'}</span>
          </CardField>
          <CardField label="Positives">
            <span className="num">{card.data.positives ?? '—'}</span>
          </CardField>
        </div>
        {(card.data.exclusions ?? []).length > 0 && (
          <div className="mt-3">
            <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">
              Records excluded
            </p>
            <ul className="space-y-1">
              {(card.data.exclusions ?? []).map((e) => (
                <li
                  key={e.reason}
                  className="text-sm flex items-baseline justify-between gap-3 border-b border-border/40 pb-1 last:border-0"
                >
                  <span className="text-muted-foreground">{e.reason}</span>
                  <span className="num font-medium shrink-0">{e.count}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="mt-3">
          <LeakageCallout features={card.data.excludedFeatures ?? []} />
        </div>
      </section>

      <section>
        <p className="text-label mb-2">Method</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <CardField label="Algorithm">{algoLabel(card.method.algorithm)}</CardField>
          <CardField label="Parameters">
            <span className="font-mono text-xs">{fmtParams(card.method.params)}</span>
          </CardField>
          <CardField label="Validation">{card.method.validation}</CardField>
        </div>
        <p className="text-[11px] uppercase tracking-wider text-muted-foreground mt-3 mb-1.5">
          Features ({card.method.features.length})
        </p>
        <div className="flex flex-wrap gap-1.5">
          {card.method.features.map((k) => (
            <span
              key={k}
              className="inline-flex items-center rounded-sm border border-border bg-surface-2 px-2 py-0.5 text-xs font-mono"
            >
              {k}
            </span>
          ))}
        </div>
      </section>

      <section>
        <p className="text-label mb-2">Performance</p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <MetricTile
            label="AUC (mean ± std)"
            value={perf.aucMean == null
              ? '—'
              : `${perf.aucMean.toFixed(3)} ± ${perf.aucStd == null ? '?' : perf.aucStd.toFixed(3)}`}
          />
          <MetricTile label="Avg precision" value={fmtMetric(perf.averagePrecision)} />
          <MetricTile label="Brier score" value={fmtMetric(perf.brierScore)} />
          <MetricTile label="Precision @0.5" value={fmtMetric(perf.precisionAt50)} />
          <MetricTile label="Recall @0.5" value={fmtMetric(perf.recallAt50)} />
          <MetricTile label="n" value={perf.n == null ? '—' : String(perf.n)} />
          <MetricTile label="Positives" value={perf.positives == null ? '—' : String(perf.positives)} />
        </div>
      </section>

      <section>
        <p className="text-label mb-2">
          Explainability{' '}
          <span className="normal-case font-normal text-muted-foreground">
            — permutation importance; negative means noise
          </span>
        </p>
        {card.explainability.length === 0 ? (
          <p className="text-helper text-xs">Not recorded for this version.</p>
        ) : (
          <ImportanceBars items={card.explainability} />
        )}
      </section>

      {/* The honesty section — prominent by design, never a footnote. */}
      <section className="rounded-md border border-warning/40 bg-warning/10 p-4">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-warning shrink-0" />
          <p className="text-sm font-semibold">Limitations</p>
        </div>
        <p className="text-xs text-muted-foreground mt-1">
          Computed from the data, not curated. Anyone acting on this model&apos;s predictions
          should read these first.
        </p>
        <ul className="mt-2.5 space-y-1.5 list-disc pl-5 text-sm">
          {card.limitations.map((l) => <li key={l}>{l}</li>)}
        </ul>
      </section>

      <section>
        <p className="text-label mb-2">Governance history</p>
        <GovernanceTimeline entries={card.governance} />
      </section>
    </div>
  )
}

/** Full-width dialog around the auto-generated model card. */
function ModelCardDialog({
  versionId, onClose,
}: { versionId: string | null; onClose: () => void }) {
  const cardQ = useModelCard(versionId)
  const card = cardQ.data
  return (
    <Dialog open={!!versionId} onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-primary" />
            {card
              ? <>Model card — {card.model?.name ?? 'model'} v{card.versionNo}</>
              : 'Model card'}
          </DialogTitle>
          <DialogDescription>
            Generated from the recorded data and governance log — never hand-written.
          </DialogDescription>
        </DialogHeader>
        {cardQ.isLoading && (
          <div className="space-y-3">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        )}
        {cardQ.isError && <ErrorCard error={cardQ.error} />}
        {card && <ModelCardDocument card={card} />}
      </DialogContent>
    </Dialog>
  )
}

/* ------------------------------ Overview tab ------------------------------ */

function OverviewTab({ onNewAnalysis }: { onNewAnalysis: () => void }) {
  const overview = usePatternLabOverview()

  if (overview.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-36 w-full" />
        <Skeleton className="h-36 w-full" />
        <Skeleton className="h-36 w-full" />
      </div>
    )
  }
  if (overview.isError) return <ErrorCard error={overview.error} />
  // A query can be neither loading nor errored and still have no data yet (e.g. gated or
  // pending-idle during auth hydration) — never non-null-assert query data.
  if (!overview.data) return <Skeleton className="h-36 w-full" />
  const data = overview.data
  const latestByTarget = new Map<string, PatternDataset>()
  for (const ds of data.datasets) {
    if (!latestByTarget.has(ds.targetKey)) latestByTarget.set(ds.targetKey, ds) // list is newest-first
  }

  return (
    <div className="space-y-4">
      <PageSection
        icon={Boxes}
        title="Active models"
        description="Best version per model — governed from candidate to production in the Models tab."
        accent="primary"
        headerRight={<Badge variant="secondary">{data.models?.length ?? 0} model{(data.models?.length ?? 0) === 1 ? '' : 's'}</Badge>}
      >
        {(data.models?.length ?? 0) === 0 ? (
          <p className="text-helper">
            No models yet — build a dataset in Discover and run the candidate search.
          </p>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {data.models!.map((m) => (
              <div key={m.id} className="card-elevated p-3">
                <p className="text-sm font-medium truncate" title={m.name}>{m.name}</p>
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                  <StatusBadge status={m.status} />
                  {m.algorithm && <span className="text-helper">{algoLabel(m.algorithm)}</span>}
                </div>
                {m.aucMean != null && (
                  <p className="text-helper mt-1">
                    Accuracy <span className="num font-medium">{m.aucMean.toFixed(3)}</span>
                    {' — '}{aucPlain(m.aucMean)}
                    {!m.beatsBaseline && ' · did not beat simply guessing'}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </PageSection>

      <PageSection
        icon={Sparkles}
        title="Recent discoveries"
        description="Statistically significant patterns from the latest discovery runs."
        accent="accent"
        actions={
          <Button size="sm" onClick={onNewAnalysis}>
            <Plus className="h-4 w-4 mr-1.5" /> New analysis
          </Button>
        }
      >
        {data.recentFindings.length === 0 ? (
          <p className="text-helper">
            No discoveries yet. Start a new analysis: pick a question, build a dataset, run discovery.
          </p>
        ) : (
          <div className="space-y-2">
            {/* The same pattern can be rediscovered on every run — show each once. */}
            {data.recentFindings.filter((f, i, a) => a.findIndex((x) => x.statement === f.statement) === i).map((f) => (
              <div key={f.id} className="card-elevated p-3 flex items-start gap-3">
                <div className="h-7 w-7 shrink-0 rounded-md bg-accent/10 text-accent flex items-center justify-center">
                  <Sparkles className="h-3.5 w-3.5" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm leading-snug">{f.statement}</p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    <Badge variant="success">significant</Badge>
                    {f.effect != null && <Badge variant="info">{fmtEffect(f.effect)}</Badge>}
                    <Badge variant="outline">{f.evidence.group}</Badge>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </PageSection>

      <PageSection
        icon={Database}
        title="Data health"
        description="Whether each governed question has enough labelled history to analyse honestly."
        accent="primary"
      >
        <div className="grid gap-3 md:grid-cols-2">
          {data.targets.map((t) => {
            const s = t.sufficiency
            const latest = latestByTarget.get(t.key)
            return (
              <div key={t.key} className="card-elevated p-4">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-medium text-sm">{t.label}</p>
                  {s.sufficient
                    ? <Badge variant="success">ready</Badge>
                    : <Badge variant="warning"><Lock className="h-3 w-3 mr-1" /> locked</Badge>}
                </div>
                <p className="text-sm text-muted-foreground mt-2">
                  {s.sufficient
                    ? <>Of <span className="num font-medium text-foreground">{s.eligible}</span> students with a known outcome, <span className="num font-medium text-foreground">{s.positives}</span> experienced it — enough history to analyse honestly.</>
                    : 'Not enough reliable history yet.'}
                </p>
                {!s.sufficient && s.reason && (
                  <p className="mt-1.5 text-xs text-warning">{s.reason}</p>
                )}
                <p className="text-helper mt-1.5 text-xs">
                  {latest ? `Last analysed ${latest.createdAt ? new Date(latest.createdAt).toLocaleDateString() : 'recently'}.` : 'Not analysed yet.'}
                </p>
              </div>
            )
          })}
        </div>
      </PageSection>
    </div>
  )
}

/* ------------------------------ Discover tab ------------------------------ */

function TargetCard({
  target, selected, onSelect,
}: { target: PatternTarget; selected: boolean; onSelect: () => void }) {
  const s = target.sufficiency
  const locked = !s.sufficient
  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={locked}
      aria-pressed={selected}
      className={cn(
        'card-elevated p-4 text-left transition-all w-full',
        selected && 'ring-2 ring-primary border-primary/50',
        locked ? 'opacity-70 cursor-not-allowed' : 'hover:border-primary/40',
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="font-medium text-sm">{target.label}</p>
        {locked
          ? <Badge variant="warning"><Lock className="h-3 w-3 mr-1" /> locked</Badge>
          : <Badge variant="success">ready</Badge>}
      </div>
      <p className="text-sm mt-1.5 leading-snug">{target.question}</p>
      <p className="text-xs text-muted-foreground mt-2">{target.population}</p>
      <p className="text-xs text-muted-foreground mt-1 num">
        {s.eligible} eligible · {s.positives} positives · {s.negatives} negatives
        <span className="text-muted-foreground/70"> (needs ≥{target.minEligible} / ≥{target.minMinority} minority)</span>
      </p>
      {locked && s.reason && (
        <p className="mt-2 text-xs text-warning leading-snug">{s.reason}</p>
      )}
    </button>
  )
}

function QualityReport({ dataset }: { dataset: PatternDataset }) {
  const q = dataset.quality
  const featureLabel = useMemo(() => {
    const map = new Map<string, string>()
    for (const f of q.activeFeatures) map.set(f.key, f.label)
    return (key: string) => map.get(key) ?? key
  }, [q.activeFeatures])
  const total = Math.max(1, dataset.positives + dataset.negatives)

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile label="Records found" value={String(dataset.recordsFound)} hint="in population" />
        <StatTile label="Eligible" value={String(dataset.eligible)} hint="outcome knowable" />
        <StatTile label="Positives" value={String(dataset.positives)} hint="outcome occurred" />
        <StatTile label="Negatives" value={String(dataset.negatives)} hint="outcome did not occur" />
      </div>

      {/* Outcome balance — a single stacked bar, plain divs. */}
      <div>
        <p className="text-label mb-1.5">Outcome balance</p>
        <div className="flex h-2.5 rounded-full overflow-hidden bg-surface-3">
          <div className="bg-danger/70" style={{ width: `${(dataset.positives / total) * 100}%` }} />
          <div className="bg-success/50" style={{ width: `${(dataset.negatives / total) * 100}%` }} />
        </div>
        <div className="mt-1.5 flex gap-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-danger/70" /> positives {dataset.positives}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-success/50" /> negatives {dataset.negatives}
          </span>
        </div>
      </div>

      <div className="rounded-md border border-[hsl(var(--info)/0.3)] bg-[hsl(var(--info)/0.08)] p-3 flex gap-2">
        <Info className="h-4 w-4 text-[hsl(var(--info))] shrink-0 mt-0.5" />
        <p className="text-sm">
          <span className="font-medium">Prediction point.</span>{' '}
          {q.predictionPoint}
        </p>
      </div>

      <LeakageCallout features={q.excludedFeatures} />

      {q.exclusions.length > 0 && (
        <div>
          <p className="text-label mb-1.5">Records excluded</p>
          <ul className="space-y-1">
            {q.exclusions.map((e) => (
              <li key={e.reason} className="text-sm flex items-baseline justify-between gap-3 border-b border-border/40 pb-1 last:border-0">
                <span className="text-muted-foreground">{e.reason}</span>
                <span className="num font-medium shrink-0">{e.count}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <p className="text-label mb-2">Feature completeness</p>
        <div className="grid gap-x-6 gap-y-2.5 sm:grid-cols-2">
          {Object.entries(q.completeness).map(([key, value]) => (
            <div key={key}>
              <div className="flex items-baseline justify-between text-xs">
                <span className="truncate">{featureLabel(key)}</span>
                <span className="num text-muted-foreground shrink-0">{pct(value)}</span>
              </div>
              <div className="mt-1 h-1.5 rounded-full bg-surface-3 overflow-hidden">
                <div
                  className={cn('h-full rounded-full', value < 0.5 ? 'bg-warning/80' : 'bg-primary/70')}
                  style={{ width: `${Math.max(2, Math.round(value * 100))}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function EvidenceDialog({
  finding, onClose,
}: { finding: PatternFinding | null; onClose: () => void }) {
  const ev = finding?.evidence
  return (
    <Dialog open={!!finding} onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-w-lg">
        {finding && ev && (
          <>
            <DialogHeader>
              <DialogTitle>{ev.featureLabel}</DialogTitle>
              <DialogDescription>{ev.description}</DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div className="space-y-3">
                <RateBar label={ev.worse.desc} rate={ev.worse.rate} n={ev.worse.n} tone="danger" />
                <RateBar label={ev.better.desc} rate={ev.better.rate} n={ev.better.n} tone="success" />
              </div>

              <div className="grid grid-cols-3 gap-2 text-center rounded-md border border-border bg-surface-1 p-3">
                <div>
                  <p className="text-sm font-medium num">{fmtP(ev.pValue)}</p>
                  <p className="text-[11px] uppercase tracking-wider text-muted-foreground">p-value</p>
                </div>
                <div>
                  <p className="text-sm font-medium num">{fmtP(ev.correctedAlpha)}</p>
                  <p className="text-[11px] uppercase tracking-wider text-muted-foreground">corrected α</p>
                </div>
                <div>
                  <p className="text-sm font-medium num">{ev.testsRun}</p>
                  <p className="text-[11px] uppercase tracking-wider text-muted-foreground">tests run</p>
                </div>
              </div>

              <div>
                <p className="text-label mb-1.5">Possible confounders</p>
                {ev.confounders.length === 0 ? (
                  <p className="text-helper text-xs">
                    No strongly co-varying features detected (|φ| ≥ 0.3).
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {ev.confounders.map((c) => (
                      <span
                        key={c.key}
                        className="inline-flex items-center rounded-sm border border-[hsl(var(--warning)/0.3)] bg-[hsl(var(--warning)/0.1)] px-2 py-0.5 text-xs text-[hsl(var(--warning))]"
                      >
                        {c.label} <span className="num ml-1">φ {c.phi}</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>

              <div className="rounded-md border border-warning/40 bg-warning/10 p-3 flex gap-2">
                <AlertTriangle className="h-4 w-4 text-warning shrink-0 mt-0.5" />
                <p className="text-sm">{ev.caution}</p>
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

function FindingCard({
  finding, onViewEvidence,
}: { finding: PatternFinding; onViewEvidence: () => void }) {
  return (
    <div className={cn('card-elevated p-4', !finding.significant && 'opacity-70')}>
      <div className="flex items-start gap-3">
        <div className="h-7 w-7 shrink-0 rounded-md bg-primary/10 text-primary flex items-center justify-center text-sm font-semibold num">
          {finding.rank}
        </div>
        <div className="min-w-0 flex-1">
          <p className={cn('leading-snug', finding.significant ? 'text-[15px]' : 'text-sm')}>
            {finding.statement}
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {finding.significant
              ? <Badge variant="success">significant</Badge>
              : <Badge variant="secondary">not significant after correction</Badge>}
            {finding.effect != null && <Badge variant="info">{fmtEffect(finding.effect)}</Badge>}
            <Badge variant="outline">{finding.evidence.group}</Badge>
            <Badge variant="outline" className="num">p {fmtP(finding.pValue)}</Badge>
          </div>
        </div>
        <Button variant="outline" size="sm" className="shrink-0" onClick={onViewEvidence}>
          View evidence
        </Button>
      </div>
    </div>
  )
}

/**
 * Step 4 — the bounded candidate search (PL-3). Mount with `key={dataset.id}` so
 * the suggested name and the last run reset when the working dataset changes.
 */
function TrainStep({
  dataset, targetLabel, canTrain,
}: { dataset: PatternDataset | null; targetLabel: string | null; canTrain: boolean }) {
  const { toast } = useToast()
  const availability = useMlAvailability()
  const train = useTrainModel()
  const [name, setName] = useState(targetLabel ? `${targetLabel} model` : '')
  const [result, setResult] = useState<TrainRun | null>(null)
  const [trainError, setTrainError] = useState<string | null>(null)

  const mlUnavailable = availability.data ? !availability.data.available : false

  const runTrain = async () => {
    if (!dataset) return
    setTrainError(null)
    try {
      const res = await train.mutateAsync({
        datasetId: dataset.id,
        name: name.trim() || undefined,
      })
      setResult(res)
      toast({
        title: 'Candidate search complete',
        description: res.verdict === 'succeeded'
          ? `Recommended: ${algoLabel(res.recommended ?? '')} — saved as version ${res.versionNo}.`
          : 'No candidate beat the baseline. The full comparison is recorded below.',
      })
    } catch (e) {
      // 400 refusals (insufficient dataset, missing ML extra) are governance copy —
      // surface them verbatim.
      setTrainError((e as Error).message)
      toast({ title: 'Training refused', description: (e as Error).message, variant: 'destructive' })
    }
  }

  return (
    <PageSection
      icon={Cpu}
      title="Train a model"
      description="Tries four different approaches on the snapshot and keeps only candidates that beat blind guessing. Takes about half a minute."
      accent="primary"
      headerRight={<StepChip n={4} />}
      actions={
        dataset && (
          <Button
            size="sm"
            onClick={runTrain}
            disabled={!canTrain || mlUnavailable || train.isPending}
            title={!canTrain ? 'Requires the ml.train permission' : undefined}
          >
            <Cpu className="h-4 w-4 mr-1.5" />
            {train.isPending ? 'Searching…' : 'Run candidate search'}
          </Button>
        )
      }
    >
      {train.isPending && <Working messages={TRAIN_MSGS} />}
      {!dataset ? (
        <p className="text-helper">Build a dataset first — training runs on a versioned snapshot.</p>
      ) : (
        <div className="space-y-4">
          {mlUnavailable && availability.data?.note && (
            <div className="rounded-md border border-warning/40 bg-warning/10 p-3 flex gap-2">
              <Info className="h-4 w-4 text-warning shrink-0 mt-0.5" />
              <p className="text-sm">{availability.data.note}</p>
            </div>
          )}

          <div className="max-w-md">
            <label htmlFor="pl-model-name" className="text-label mb-1.5 block">Model name</label>
            <Input
              id="pl-model-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={targetLabel ? `${targetLabel} model` : 'Model name'}
              disabled={!canTrain || mlUnavailable}
            />
            <p className="text-helper text-xs mt-1">
              Reusing an existing name adds a new version to that model; a new name starts a new one.
            </p>
          </div>

          {!canTrain && (
            <p className="text-xs text-warning">
              Running the candidate search requires the <span className="font-mono">ml.train</span>{' '}
              permission — you can view existing models in the Models tab.
            </p>
          )}

          {trainError && (
            <div className="rounded-md border border-danger/40 bg-danger/10 p-3 flex gap-2">
              <AlertTriangle className="h-4 w-4 text-danger shrink-0 mt-0.5" />
              <p className="text-sm">{trainError}</p>
            </div>
          )}

          {result && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-sm">Run result</span>
                <Badge variant="secondary">version {result.versionNo}</Badge>
                <span className="text-xs text-muted-foreground num">
                  {(result.durationMs / 1000).toFixed(1)}s
                </span>
              </div>
              <TrainRunReport detail={result} />
            </div>
          )}
        </div>
      )}
    </PageSection>
  )
}

function DiscoverTab({ canAnalyse, canTrain }: { canAnalyse: boolean; canTrain: boolean }) {
  const { toast } = useToast()
  const targetsQ = usePatternTargets()
  const datasetsQ = usePatternDatasets()
  const build = useBuildDataset()
  const discover = useRunDiscovery()

  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [builtId, setBuiltId] = useState<string | null>(null)
  const [discoverError, setDiscoverError] = useState<string | null>(null)
  const [evidenceFor, setEvidenceFor] = useState<PatternFinding | null>(null)

  // The working dataset: the one just built, else the latest existing one for the target.
  const dataset = useMemo(() => {
    const list = datasetsQ.data ?? []
    if (builtId) return list.find((d) => d.id === builtId) ?? null
    if (!selectedKey) return null
    return list.find((d) => d.targetKey === selectedKey) ?? null // list is newest-first
  }, [datasetsQ.data, builtId, selectedKey])

  const findingsQ = useDatasetFindings(dataset?.id ?? null)
  const findings = findingsQ.data ?? []
  const significant = findings.filter((f) => f.significant)
  const notSignificant = findings.filter((f) => !f.significant)
  const skipped = dataset?.quality.discoverySkipped ?? []

  const selectTarget = (key: string) => {
    setSelectedKey(key)
    setBuiltId(null)
    setDiscoverError(null)
  }

  const runBuild = async () => {
    if (!selectedKey) return
    try {
      const ds = await build.mutateAsync(selectedKey)
      setBuiltId(ds.id)
      setDiscoverError(null)
      toast({ title: 'Dataset built', description: `${ds.name} v${ds.version} — ${ds.eligible} eligible records.` })
    } catch (e) {
      toast({ title: 'Dataset build failed', description: (e as Error).message, variant: 'destructive' })
    }
  }

  const runDiscovery = async () => {
    if (!dataset) return
    setDiscoverError(null)
    try {
      const res = await discover.mutateAsync(dataset.id)
      toast({
        title: 'Discovery complete',
        description: `${res.significant} significant pattern${res.significant === 1 ? '' : 's'} out of ${res.findings.length} tested.`,
      })
    } catch (e) {
      // The sufficiency-gate refusal (400) is governance copy — surface it verbatim.
      setDiscoverError((e as Error).message)
      toast({ title: 'Discovery refused', description: (e as Error).message, variant: 'destructive' })
    }
  }

  if (targetsQ.isLoading || datasetsQ.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    )
  }
  if (targetsQ.isError) return <ErrorCard error={targetsQ.error} />
  if (datasetsQ.isError) return <ErrorCard error={datasetsQ.error} />

  const selectedTarget = targetsQ.data?.find((t) => t.key === selectedKey) ?? null

  return (
    <div className="space-y-4">
      {/* Step 1 — Question */}
      <PageSection
        icon={Target}
        title="Choose the question"
        description="Analysis runs only against governed targets — there is no “predict anything”. Locked questions say exactly what data is missing."
        accent="primary"
        headerRight={<StepChip n={1} />}
      >
        <div className="grid gap-3 md:grid-cols-2">
          {(targetsQ.data ?? []).map((t) => (
            <TargetCard
              key={t.key}
              target={t}
              selected={t.key === selectedKey}
              onSelect={() => selectTarget(t.key)}
            />
          ))}
        </div>
      </PageSection>

      {/* Step 2 — Dataset */}
      <PageSection
        icon={Database}
        title="Build the dataset"
        description="Takes a dated snapshot of the history so the analysis is repeatable and auditable — the full quality report is under Technical detail."
        accent="primary"
        headerRight={<StepChip n={2} />}
        actions={
          selectedTarget && (
            <Button
              size="sm"
              onClick={runBuild}
              disabled={!canAnalyse || build.isPending}
              title={canAnalyse ? undefined : 'Requires the ml.analyse permission'}
            >
              {build.isPending ? 'Building…' : dataset ? 'Build new version' : 'Build dataset'}
            </Button>
          )
        }
      >
        {build.isPending && <Working messages={BUILD_MSGS} />}
        {!selectedTarget ? (
          <p className="text-helper">Select a question above to begin.</p>
        ) : !dataset ? (
          <div className="space-y-2">
            <p className="text-helper">
              No dataset built yet for <span className="font-medium text-foreground">{selectedTarget.label}</span>.
              Building one snapshots the current data into a versioned, auditable analysis set.
            </p>
            {!canAnalyse && (
              <p className="text-xs text-warning">
                Building datasets requires the <span className="font-mono">ml.analyse</span> permission — you can view existing results.
              </p>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-sm">{dataset.name}</span>
              <Badge variant="secondary">v{dataset.version}</Badge>
              <Badge variant={dataset.sufficient ? 'success' : 'warning'}>
                {dataset.sufficient ? 'passed sufficiency gate' : 'failed sufficiency gate'}
              </Badge>
              <Badge variant="outline">{dataset.status}</Badge>
              {dataset.createdAt && (
                <span className="text-xs text-muted-foreground">
                  built {new Date(dataset.createdAt).toLocaleString()}
                </span>
              )}
            </div>
            <TechDetails label="Technical detail — who was excluded, and what the model is not allowed to see">
              <QualityReport dataset={dataset} />
            </TechDetails>
          </div>
        )}
      </PageSection>

      {/* Step 3 — Discovery */}
      <PageSection
        icon={FlaskConical}
        title="Run discovery"
        description="Compares groups of students and reports only differences too big to be luck — each finding carries its evidence."
        accent="accent"
        headerRight={<StepChip n={3} />}
        actions={
          dataset && (
            <Button
              size="sm"
              onClick={runDiscovery}
              disabled={!canAnalyse || discover.isPending}
              title={canAnalyse ? undefined : 'Requires the ml.analyse permission'}
            >
              <Sparkles className="h-4 w-4 mr-1.5" />
              {discover.isPending ? 'Running…' : findings.length > 0 ? 'Run again' : 'Run discovery'}
            </Button>
          )
        }
      >
        {discover.isPending && <Working messages={DISCOVER_MSGS} />}
        {!dataset ? (
          <p className="text-helper">Build a dataset first — discovery runs on a versioned snapshot.</p>
        ) : (
          <div className="space-y-3">
            {discoverError && (
              <div className="rounded-md border border-danger/40 bg-danger/10 p-3 flex gap-2">
                <AlertTriangle className="h-4 w-4 text-danger shrink-0 mt-0.5" />
                <p className="text-sm">{discoverError}</p>
              </div>
            )}

            {findingsQ.isLoading ? (
              <Skeleton className="h-24 w-full" />
            ) : findings.length === 0 ? (
              !discoverError && (
                <p className="text-helper">
                  No discovery run yet on {dataset.name} v{dataset.version}.
                  {dataset.sufficient
                    ? ' Run discovery to test every eligible feature.'
                    : ' This dataset failed the sufficiency gate — the run will be refused with the reason.'}
                </p>
              )
            ) : (
              <>
                {significant.length > 0 && (
                  <div className="space-y-2">
                    {significant.map((f) => (
                      <FindingCard key={f.id} finding={f} onViewEvidence={() => setEvidenceFor(f)} />
                    ))}
                  </div>
                )}
                {notSignificant.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-label pt-1">
                      Tested, not significant after correction
                    </p>
                    {notSignificant.map((f) => (
                      <FindingCard key={f.id} finding={f} onViewEvidence={() => setEvidenceFor(f)} />
                    ))}
                  </div>
                )}
                {skipped.length > 0 && (
                  <div className="pt-1">
                    <p className="text-label mb-1.5">Not tested</p>
                    <ul className="space-y-1">
                      {skipped.map((s) => (
                        <li key={s.key} className="text-xs text-muted-foreground">
                          <span className="text-foreground/80">{s.label}</span> — {s.reason}
                        </li>
                      ))}
                    </ul>
                    <p className="text-[11px] text-muted-foreground/80 mt-1.5">
                      Skipped tests are part of the record — silence must not read as “no pattern”.
                    </p>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </PageSection>

      {/* Step 4 — Train (PL-3). Keyed so name suggestion + last result track the dataset. */}
      <TrainStep
        key={dataset?.id ?? selectedKey ?? 'none'}
        dataset={dataset}
        targetLabel={selectedTarget?.label ?? null}
        canTrain={canTrain}
      />

      <EvidenceDialog finding={evidenceFor} onClose={() => setEvidenceFor(null)} />
    </div>
  )
}

/* -------------------------------- Models tab -------------------------------- */

/** Permutation importance as plain-div bars around a zero line — negatives allowed. */
function ImportanceBars({ items }: { items: { feature: string; importance: number }[] }) {
  const sorted = [...items].sort((a, b) => Math.abs(b.importance) - Math.abs(a.importance))
  const maxAbs = Math.max(0.0001, ...sorted.map((i) => Math.abs(i.importance)))
  return (
    <div className="space-y-1.5">
      {sorted.map((i) => (
        <div key={i.feature} className="flex items-center gap-3 text-xs">
          <span className="w-44 truncate shrink-0 font-mono" title={i.feature}>{i.feature}</span>
          <div className="flex-1 flex items-center">
            <div className="flex-1 flex justify-end">
              {i.importance < 0 && (
                <div
                  className="h-2 rounded-l-full bg-warning/70"
                  style={{ width: `${Math.max(1, (Math.abs(i.importance) / maxAbs) * 100)}%` }}
                />
              )}
            </div>
            <div className="w-px self-stretch min-h-3 bg-border" />
            <div className="flex-1">
              {i.importance >= 0 && (
                <div
                  className="h-2 rounded-r-full bg-primary/70"
                  style={{ width: `${Math.max(1, (i.importance / maxAbs) * 100)}%` }}
                />
              )}
            </div>
          </div>
          <span className="num w-14 text-right shrink-0 text-muted-foreground">
            {i.importance.toFixed(3)}
          </span>
        </div>
      ))}
    </div>
  )
}

function VersionDetail({ version }: { version: MlModelVersion }) {
  const importance = version.metrics.permutationImportance ?? []
  const [cardOpen, setCardOpen] = useState(false)
  return (
    <div className="space-y-4 py-1">
      {/* PL-4 — where this version stands, and what can happen to it next. */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <StatusPipeline status={version.status} />
        <div className="flex flex-wrap items-center gap-2">
          <GovernanceActions version={version} />
          <Button variant="outline" size="sm" onClick={() => setCardOpen(true)}>
            <FileText className="h-4 w-4 mr-1.5" /> Model card
          </Button>
        </div>
      </div>
      <div>
        <p className="text-label mb-1.5">Lineage</p>
        <LineageStrip versionId={version.id} />
      </div>
      <div>
        <p className="text-label mb-1">Parameters</p>
        <p className="text-sm font-mono">{fmtParams(version.params)}</p>
      </div>
      <div>
        <p className="text-label mb-1.5">Features ({version.featureKeys.length})</p>
        <div className="flex flex-wrap gap-1.5">
          {version.featureKeys.map((k) => (
            <span
              key={k}
              className="inline-flex items-center rounded-sm border border-border bg-surface-2 px-2 py-0.5 text-xs font-mono"
            >
              {k}
            </span>
          ))}
        </div>
      </div>
      <div>
        <p className="text-label mb-2">
          Permutation importance{' '}
          <span className="normal-case font-normal text-muted-foreground">
            — held-out AUC change when the feature is shuffled; negative means noise
          </span>
        </p>
        {importance.length === 0 ? (
          <p className="text-helper text-xs">Not recorded for this version.</p>
        ) : (
          <ImportanceBars items={importance} />
        )}
      </div>
      <ModelCardDialog
        versionId={cardOpen ? version.id : null}
        onClose={() => setCardOpen(false)}
      />
    </div>
  )
}

function ModelCard({ model }: { model: MlModel }) {
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [comparisonOpen, setComparisonOpen] = useState(false)
  const latestRun = model.runs[0] // backend returns runs newest-first
  const latestDetail = latestRun && hasDetail(latestRun.detail) ? latestRun.detail : null

  return (
    <PageSection
      icon={Boxes}
      title={model.name}
      description={model.description ?? undefined}
      accent="primary"
      headerRight={<Badge variant="outline" className="font-mono">{model.targetKey}</Badge>}
    >
      <div className="space-y-4">
        <p className="text-xs text-muted-foreground">
          {model.createdAt && <>Created {new Date(model.createdAt).toLocaleDateString()} · </>}
          {model.versions.length} version{model.versions.length === 1 ? '' : 's'} ·{' '}
          {model.runs.length} recent run{model.runs.length === 1 ? '' : 's'}
          {latestRun?.durationMs != null && (
            <> · latest run <span className="num">{(latestRun.durationMs / 1000).toFixed(1)}s</span></>
          )}
        </p>

        {latestDetail && (
          <div className="space-y-3">
            <VerdictBanner detail={latestDetail} />
            <Collapsible open={comparisonOpen} onOpenChange={setComparisonOpen}>
              <CollapsibleTrigger asChild>
                <Button variant="outline" size="sm">
                  <ChevronDown
                    className={cn('h-4 w-4 mr-1.5 transition-transform', comparisonOpen && 'rotate-180')}
                  />
                  Latest run — candidate comparison
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent className="mt-3 space-y-3">
                <CandidateTable
                  candidates={latestDetail.candidates}
                  recommended={latestDetail.recommended}
                />
                {latestDetail.droppedFeatures.length > 0 && (
                  <div>
                    <p className="text-label mb-1.5">Features dropped before training</p>
                    <ul className="space-y-1">
                      {latestDetail.droppedFeatures.map((f) => (
                        <li key={f.key} className="text-xs text-muted-foreground">
                          <span className="font-mono text-foreground/80">{f.key}</span> — {f.reason}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </CollapsibleContent>
            </Collapsible>
          </div>
        )}

        {model.versions.length === 0 ? (
          <p className="text-helper">
            No versions stored — the run produced no artifacts.
          </p>
        ) : (
          <div className="rounded-md border border-border overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Version</TableHead>
                  <TableHead>Algorithm</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">AUC (mean ± std)</TableHead>
                  <TableHead className="text-right">Avg precision</TableHead>
                  <TableHead className="text-right">Brier</TableHead>
                  <TableHead>Dataset</TableHead>
                  <TableHead className="text-right">Artifact</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {model.versions.map((v) => (
                  <Fragment key={v.id}>
                    <TableRow
                      className="cursor-pointer"
                      onClick={() => setExpandedId(expandedId === v.id ? null : v.id)}
                      aria-expanded={expandedId === v.id}
                    >
                      <TableCell className="num">
                        <span className="inline-flex items-center gap-1.5">
                          <ChevronDown
                            className={cn(
                              'h-3.5 w-3.5 text-muted-foreground transition-transform',
                              expandedId === v.id && 'rotate-180',
                            )}
                          />
                          v{v.versionNo}
                        </span>
                      </TableCell>
                      <TableCell className="text-sm">{algoLabel(v.algorithm)}</TableCell>
                      <TableCell>
                        <StatusBadge status={v.status} />
                      </TableCell>
                      <TableCell className="text-right num whitespace-nowrap">
                        {v.metrics.aucMean.toFixed(3)}{' '}
                        <span className="text-muted-foreground">± {v.metrics.aucStd.toFixed(3)}</span>
                      </TableCell>
                      <TableCell className="text-right num">{fmtMetric(v.metrics.averagePrecision)}</TableCell>
                      <TableCell className="text-right num">{fmtMetric(v.metrics.brierScore)}</TableCell>
                      <TableCell>
                        <span className="font-mono text-xs" title={v.datasetVersion}>
                          {shortHash(v.datasetVersion)}
                        </span>
                      </TableCell>
                      <TableCell className="text-right num text-xs">{fmtBytes(v.artifactBytes)}</TableCell>
                    </TableRow>
                    {expandedId === v.id && (
                      <TableRow className="hover:bg-transparent">
                        <TableCell colSpan={8} className="bg-surface-1">
                          <VersionDetail version={v} />
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        <p className="text-[11px] text-muted-foreground/80">
          Lifecycle: trained → candidate → review → approved → production. Every decision
          requires a written rationale, and the administrator who started the training run
          cannot decide on its versions — expand a version to act on it.
        </p>
      </div>
    </PageSection>
  )
}

function ModelsTab({ onGoDiscover }: { onGoDiscover: () => void }) {
  const modelsQ = useMlModels()
  const availability = useMlAvailability()

  if (modelsQ.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }
  if (modelsQ.isError) return <ErrorCard error={modelsQ.error} />
  const models = modelsQ.data ?? []

  return (
    <div className="space-y-4">
      {availability.data && !availability.data.available && availability.data.note && (
        <Card className="card-elevated">
          <CardContent className="py-4">
            <div className="flex gap-2">
              <Info className="h-4 w-4 text-warning shrink-0 mt-0.5" />
              <div className="text-sm">
                <p className="font-medium">Training is unavailable on this server</p>
                <p className="text-muted-foreground text-xs mt-0.5">{availability.data.note}</p>
                <p className="text-muted-foreground text-xs mt-0.5">
                  Existing models and their evaluation records remain viewable.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {models.length === 0 ? (
        <Card className="card-elevated">
          <CardContent className="py-14 text-center space-y-3">
            <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Boxes className="h-5 w-5" />
            </div>
            <p className="font-medium">No models yet</p>
            <p className="text-helper max-w-lg mx-auto">
              No models yet — build a dataset in Discover and run the candidate search.
            </p>
            <Button variant="outline" size="sm" onClick={onGoDiscover}>
              <Microscope className="h-4 w-4 mr-1.5" /> Go to Discover
            </Button>
          </CardContent>
        </Card>
      ) : (
        models.map((m) => <ModelCard key={m.id} model={m} />)
      )}
    </div>
  )
}

/* ---------------------------- Predictions tab (PL-5) ---------------------------- */

/** The standing advisory — verbatim, always visible on the tab. */
const PREDICTIONS_ADVISORY =
  'Predictions are advisory. They sit beside the deterministic indicators, describe ' +
  'association rather than causation, and a human decides what, if anything, happens next.'

/** The governance rule, taught in the empty state when no batches exist. */
const NO_PRODUCTION_EXPLANATION =
  'Predictions come only from production versions — promote a model through governance ' +
  'in the Models tab first.'

/** The five-band probability distribution as a plain-div mini-histogram. */
function DistributionHistogram({ distribution }: { distribution: DistributionBand[] }) {
  const max = Math.max(1, ...distribution.map((d) => d.count))
  return (
    <div className="flex items-end gap-2 max-w-md">
      {distribution.map((d) => (
        <div key={d.band} className="flex-1 min-w-0 text-center">
          <p className="text-xs num text-muted-foreground">{d.count}</p>
          <div className="mt-1 h-20 flex items-end rounded-sm bg-surface-2 overflow-hidden">
            <div
              className="w-full rounded-t-sm bg-primary/60"
              style={{ height: `${Math.max(3, Math.round((d.count / max) * 100))}%` }}
            />
          </div>
          <p className="text-[10px] text-muted-foreground mt-1 whitespace-nowrap">{d.band}</p>
        </div>
      ))}
    </div>
  )
}

/** One production model's latest batch: header stats, distribution, highest risk. */
function BatchSection({
  batch, outcome, canTrain, scoring, onScore,
}: {
  batch: ModelBatch
  outcome: string | null
  canTrain: boolean
  scoring: boolean
  onScore: () => void
}) {
  return (
    <PageSection
      icon={TrendingUp}
      title={batch.modelName}
      description={outcome ? `Predicted outcome: ${outcome}.` : undefined}
      accent="primary"
      headerRight={<Badge variant="outline" className="font-mono">{batch.targetKey}</Badge>}
      actions={
        <Button
          size="sm"
          onClick={onScore}
          disabled={!canTrain || scoring}
          title={canTrain ? undefined : 'Requires the ml.train permission'}
        >
          <Cpu className="h-4 w-4 mr-1.5" />
          {scoring ? 'Scoring…' : 'Rescore cohort'}
        </Button>
      }
    >
      <div className="space-y-4">
        {scoring && <Working messages={SCORE_MSGS} />}
        <p className="text-xs text-muted-foreground">
          {batch.scoredAt && <>Scored {new Date(batch.scoredAt).toLocaleString()} · </>}
          <span className="num text-foreground/80">{batch.scored}</span> student
          {batch.scored === 1 ? '' : 's'} scored · mean probability{' '}
          <span className="num text-foreground/80">
            {batch.meanProbability == null ? '—' : pct(batch.meanProbability)}
          </span>
        </p>

        <div>
          <p className="text-label mb-1.5">Probability distribution</p>
          <DistributionHistogram distribution={batch.distribution} />
        </div>

        <div>
          <p className="text-label mb-1.5">Highest predicted risk</p>
          <div className="rounded-md border border-border overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Student</TableHead>
                  <TableHead>Ref</TableHead>
                  <TableHead className="w-44">Probability</TableHead>
                  <TableHead>Contributing factors</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {batch.top.map((t) => (
                  <TableRow key={t.studentId}>
                    <TableCell>
                      <Link
                        href={t.link}
                        className="text-sm font-medium text-primary hover:underline"
                      >
                        {t.studentName}
                      </Link>
                    </TableCell>
                    <TableCell className="font-mono text-xs">{t.studentRef}</TableCell>
                    <TableCell><ProbabilityBar probability={t.probability} /></TableCell>
                    <TableCell><FactorChips factors={t.factors} /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <p className="text-[11px] text-muted-foreground/80 mt-1.5">
            A positive factor means the student&apos;s value raises their probability versus
            the cohort median; a negative one pulls it down.
          </p>
        </div>
      </div>
    </PageSection>
  )
}

function PredictionsTab({ canTrain }: { canTrain: boolean }) {
  const { toast } = useToast()
  const batchesQ = usePredictionBatches()
  const modelsQ = useMlModels()
  const targetsQ = usePatternTargets()
  const score = useScoreModel()
  const [scoringId, setScoringId] = useState<string | null>(null)

  const outcomeByTarget = useMemo(() => {
    const map = new Map<string, string>()
    for (const t of targetsQ.data ?? []) map.set(t.key, t.outcomeLabel)
    return map
  }, [targetsQ.data])

  const runScore = async (modelId: string) => {
    setScoringId(modelId)
    try {
      const res = await score.mutateAsync(modelId)
      toast({
        title: 'Cohort scored',
        description: `Scored ${res.scored} students · ${res.highRisk} high risk · ${res.tasksRaised} tasks raised`,
      })
    } catch (e) {
      // The 409 (no production version) and 400 (missing ML extra / no active
      // students) refusals are governance copy — surface them verbatim.
      toast({ title: 'Scoring refused', description: (e as Error).message, variant: 'destructive' })
    } finally {
      setScoringId(null)
    }
  }

  if (batchesQ.isLoading || modelsQ.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }
  if (batchesQ.isError) return <ErrorCard error={batchesQ.error} />
  if (modelsQ.isError) return <ErrorCard error={modelsQ.error} />

  const batches = batchesQ.data ?? []
  const models = modelsQ.data ?? []
  const hasProduction = (m: MlModel) => m.versions.some((v) => v.status === 'production')
  const batchModelIds = new Set(batches.map((b) => b.modelId))
  // Production versions that have never scored — offer the first "Score now".
  const scoreable = models.filter((m) => hasProduction(m) && !batchModelIds.has(m.id))
  const unpromoted = models.filter((m) => !hasProduction(m))

  return (
    <div className="space-y-4">
      {/* The standing advisory — never folded away. */}
      <div className="rounded-md border border-[hsl(var(--info)/0.3)] bg-[hsl(var(--info)/0.08)] p-3 flex gap-2">
        <Info className="h-4 w-4 text-[hsl(var(--info))] shrink-0 mt-0.5" />
        <p className="text-sm">{PREDICTIONS_ADVISORY}</p>
      </div>

      {batches.length === 0 && (
        <Card className="card-elevated">
          <CardContent className="py-14 text-center space-y-3">
            <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <TrendingUp className="h-5 w-5" />
            </div>
            <p className="font-medium">No prediction batches yet</p>
            <p className="text-helper max-w-lg mx-auto">{NO_PRODUCTION_EXPLANATION}</p>
          </CardContent>
        </Card>
      )}

      {batches.map((b) => (
        <BatchSection
          key={b.modelId}
          batch={b}
          outcome={outcomeByTarget.get(b.targetKey) ?? null}
          canTrain={canTrain}
          scoring={score.isPending && scoringId === b.modelId}
          onScore={() => runScore(b.modelId)}
        />
      ))}

      {scoreable.length > 0 && (
        <PageSection
          icon={Cpu}
          title="Ready to score"
          description="Models with a production version that has not scored the live cohort yet."
          accent="primary"
        >
          <div className="space-y-2">
            {scoreable.map((m) => (
              <div
                key={m.id}
                className="card-elevated p-3 flex flex-wrap items-center justify-between gap-2"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate" title={m.name}>{m.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {outcomeByTarget.get(m.targetKey) ?? m.targetKey}
                  </p>
                </div>
                <Button
                  size="sm"
                  onClick={() => runScore(m.id)}
                  disabled={!canTrain || score.isPending}
                  title={canTrain ? undefined : 'Requires the ml.train permission'}
                >
                  <Cpu className="h-4 w-4 mr-1.5" />
                  {score.isPending && scoringId === m.id ? 'Scoring…' : 'Score now'}
                </Button>
              </div>
            ))}
          </div>
        </PageSection>
      )}

      {unpromoted.length > 0 && (
        <div>
          <p className="text-label mb-1.5">Not yet in production</p>
          <div className="space-y-1.5">
            {unpromoted.map((m) => (
              <div
                key={m.id}
                className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground"
              >
                <span className="truncate">{m.name}</span>
                <Badge variant="outline" className="text-muted-foreground">
                  no production version
                </Badge>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/* ---------------------------- Monitoring tab (PL-6) ---------------------------- */

const BAND_LABELS = ['0–20%', '20–40%', '40–60%', '60–80%', '80–100%']

/** Health verdict tones — the design system's low-opacity status idiom. */
const HEALTH_TONES: Record<MonitoringEntry['health'], string> = {
  ok: 'border-[hsl(var(--success)/0.3)] bg-[hsl(var(--success)/0.1)] text-[hsl(var(--success))]',
  watch: 'border-[hsl(var(--warning)/0.3)] bg-[hsl(var(--warning)/0.1)] text-[hsl(var(--warning))]',
  review: 'border-[hsl(var(--danger)/0.3)] bg-[hsl(var(--danger)/0.1)] text-[hsl(var(--danger))]',
}

const DRIFT_TONES: Record<'stable' | 'moderate' | 'major', string> = {
  stable: 'border-border bg-surface-2 text-muted-foreground',
  moderate:
    'border-[hsl(var(--warning)/0.3)] bg-[hsl(var(--warning)/0.1)] text-[hsl(var(--warning))]',
  major:
    'border-[hsl(var(--danger)/0.3)] bg-[hsl(var(--danger)/0.1)] text-[hsl(var(--danger))]',
}

const fmtPsi = (psi: number | null) => (psi == null ? '—' : psi.toFixed(3))

/** The five band counts as tiny inline bars — the histogram idiom at small scale. */
function TinyBands({ bands }: { bands: number[] }) {
  const max = Math.max(1, ...bands)
  return (
    <div className="flex items-end gap-0.5 h-6" role="img"
      aria-label={bands.map((c, i) => `${BAND_LABELS[i] ?? i}: ${c}`).join(', ')}>
      {bands.map((c, i) => (
        <div
          key={i}
          className="w-2.5 h-full flex items-end rounded-[2px] bg-surface-2 overflow-hidden"
          title={`${BAND_LABELS[i] ?? i}: ${c}`}
        >
          <div
            className="w-full rounded-t-[2px] bg-primary/60"
            style={{ height: `${c > 0 ? Math.max(10, Math.round((c / max) * 100)) : 0}%` }}
          />
        </div>
      ))}
    </div>
  )
}

/** Performance vs actuals: matured count, AUC side-by-side, calibration in the wild. */
function ActualsSection({
  entry,
}: { entry: MonitoringEntry & { actuals: NonNullable<MonitoringEntry['actuals']> } }) {
  const a = entry.actuals
  const withData = a.realizedByBand.filter((b) => b.n > 0)
  return (
    <div>
      <p className="text-label mb-1.5">Performance vs actuals</p>
      <p className="text-sm">
        <span className="num font-medium">{a.matured}</span> of the oldest batch&apos;s
        predictions have matured
        {a.batchScoredAt && (
          <span className="text-muted-foreground">
            {' '}(batch scored {new Date(a.batchScoredAt).toLocaleDateString()})
          </span>
        )}
        .
      </p>
      {!a.judged && a.note && (
        <p className="text-xs text-muted-foreground mt-1">{a.note}</p>
      )}
      <div className="mt-3 grid grid-cols-2 gap-3 max-w-md">
        <StatTile
          label="Accuracy in reality"
          value={fmtMetric(a.aucOnMatured)}
          hint={aucPlain(a.aucOnMatured) ? `what actually happened — ${aucPlain(a.aucOnMatured)}` : 'what actually happened'}
        />
        <StatTile
          label="Accuracy when trained"
          value={fmtMetric(entry.trainedAuc)}
          hint={aucPlain(entry.trainedAuc) ? `the promise at training — ${aucPlain(entry.trainedAuc)}` : 'the promise at training'}
        />
      </div>
      {withData.length > 0 && (
        <TechDetails label="Technical detail — calibration against reality">
        <div className="mt-1">
          <p className="text-label mb-1.5">Calibration in the wild</p>
          <p className="text-xs text-muted-foreground mb-2.5">
            If the model is honest, higher predicted bands should realise the outcome more often.
          </p>
          <div className="space-y-3 max-w-md">
            {withData.map((b) => (
              b.realizedRate != null
                ? (
                  <RateBar
                    key={b.band}
                    label={`predicted ${b.band}`}
                    rate={b.realizedRate}
                    n={b.n}
                    tone="danger"
                  />
                )
                : null
            ))}
          </div>
        </div>
        </TechDetails>
      )}
    </div>
  )
}

/** PSI per feature against the training matrix — delivered worst-first. */
function DriftSection({ drift }: { drift: DriftRow[] }) {
  return (
    <div>
      <p className="text-label mb-1.5">Population drift</p>
      <p className="text-xs text-muted-foreground mb-2">
        Has the mix of students changed since the model learned? Big shifts mean the model is
        describing a world that no longer exists.
      </p>
      <p className="text-xs text-muted-foreground mb-2">
        PSI compares today&apos;s cohort with the training snapshot: &lt;0.1 stable, 0.1–0.25
        moderate, ≥0.25 major. Drift means today&apos;s cohort looks different from the one
        the model learned.
      </p>
      {drift.length === 0 ? (
        <p className="text-helper text-xs">
          No drift comparison available — the training dataset snapshot was not found.
        </p>
      ) : (
        <div className="rounded-md border border-border overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Feature</TableHead>
                <TableHead className="text-right">PSI</TableHead>
                <TableHead>Band</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {drift.map((d) => (
                <TableRow key={d.feature}>
                  <TableCell className="text-sm">{d.label}</TableCell>
                  <TableCell className="text-right num">{fmtPsi(d.psi)}</TableCell>
                  <TableCell>
                    {d.band == null
                      ? <span className="text-xs text-muted-foreground">too few values</span>
                      : (
                        <Badge variant="outline" className={DRIFT_TONES[d.band]}>
                          {d.band}
                        </Badge>
                      )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

/** One production model's monitoring card: verdict, actuals, drift, trend, retrain. */
function MonitoringCard({ entry, canTrain }: { entry: MonitoringEntry; canTrain: boolean }) {
  const { toast } = useToast()
  const retrain = useRetrainModel()
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [result, setResult] = useState<RetrainResult | null>(null)
  const [retrainError, setRetrainError] = useState<string | null>(null)

  const runRetrain = async () => {
    setRetrainError(null)
    setConfirmOpen(false)
    try {
      const res = await retrain.mutateAsync(entry.modelId)
      setResult(res)
      toast({
        title: res.verdict === 'succeeded'
          ? `Retrain succeeded — recommended ${algoLabel(res.recommended ?? '')}`
          : 'Retrain complete — no candidate beat the baseline',
        description: `v${res.versionNo} candidates created — see the Models tab.`,
      })
    } catch (e) {
      // 400 (missing ML extra, insufficient fresh dataset) and 409 (target cannot
      // be rebuilt) refusals are governance copy — surface them verbatim.
      setRetrainError((e as Error).message)
      toast({ title: 'Retrain refused', description: (e as Error).message, variant: 'destructive' })
    }
  }

  return (
    <PageSection
      icon={Activity}
      title={entry.modelName}
      description={`Production version v${entry.versionNo}.`}
      accent="primary"
      headerRight={
        <Badge variant="outline" className={cn('uppercase tracking-wide', HEALTH_TONES[entry.health])}>
          {entry.health}
        </Badge>
      }
      actions={
        <Button
          size="sm"
          variant="outline"
          onClick={() => setConfirmOpen(true)}
          disabled={!canTrain || retrain.isPending}
          title={canTrain ? undefined : 'Requires the ml.train permission'}
        >
          <RefreshCw className={cn('h-4 w-4 mr-1.5', retrain.isPending && 'animate-spin')} />
          {retrain.isPending ? 'Retraining…' : 'Retrain on fresh data…'}
        </Button>
      }
    >
      <div className="space-y-5">
        <p className="text-xs text-muted-foreground">
          <Badge variant="outline" className="font-mono mr-2">{entry.targetKey}</Badge>
          Review by{' '}
          <span className="text-foreground/80 font-medium">
            {new Date(entry.recommendedReviewAt).toLocaleDateString()}
          </span>{' '}
          · trained AUC <span className="num text-foreground/80">{fmtMetric(entry.trainedAuc)}</span>
        </p>

        {/* The sentences that justify the verdict — verbatim, never paraphrased. */}
        {entry.reasons.length > 0 && (
          <div className="rounded-md border border-danger/40 bg-danger/10 p-3">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-danger shrink-0" />
              <p className="text-sm font-medium">Why this model needs review</p>
            </div>
            <ul className="mt-1.5 space-y-1 list-disc pl-5 text-sm">
              {entry.reasons.map((r) => <li key={r}>{r}</li>)}
            </ul>
          </div>
        )}

        {entry.actuals != null && (
          <ActualsSection entry={{ ...entry, actuals: entry.actuals }} />
        )}

        <TechDetails label="Technical detail — has the student population shifted since training?">
          <DriftSection drift={entry.drift} />
        </TechDetails>

        <div>
          <p className="text-label mb-1.5">Prediction trend</p>
          {entry.trend.length === 0 ? (
            <p className="text-helper text-xs">
              No prediction batches yet — score the cohort in the Predictions tab.
            </p>
          ) : (
            <div className="space-y-2">
              {entry.trend.map((t) => (
                <div key={t.batchId} className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
                  <span className="text-muted-foreground w-40 shrink-0">
                    {t.scoredAt ? new Date(t.scoredAt).toLocaleString() : '—'}
                  </span>
                  <span className="num w-20 shrink-0">{t.scored} scored</span>
                  <span className="num w-20 shrink-0">mean {pct(t.meanProbability)}</span>
                  <TinyBands bands={t.bands} />
                </div>
              ))}
            </div>
          )}
        </div>

        {retrainError && (
          <div className="rounded-md border border-danger/40 bg-danger/10 p-3 flex gap-2">
            <AlertTriangle className="h-4 w-4 text-danger shrink-0 mt-0.5" />
            <p className="text-sm">{retrainError}</p>
          </div>
        )}

        {result && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-sm">Retrain result</span>
              <Badge variant="secondary">version {result.versionNo}</Badge>
              <span className="text-xs text-muted-foreground">
                fresh dataset{' '}
                <span className="font-mono" title={result.datasetVersion}>
                  {shortHash(result.datasetVersion)}
                </span>
              </span>
              <span className="text-xs text-muted-foreground num">
                {(result.durationMs / 1000).toFixed(1)}s
              </span>
            </div>
            {/* The retrain advisory — verbatim. */}
            <div className="rounded-md border border-[hsl(var(--info)/0.3)] bg-[hsl(var(--info)/0.08)] p-3 flex gap-2">
              <Info className="h-4 w-4 text-[hsl(var(--info))] shrink-0 mt-0.5" />
              <p className="text-sm">{result.note}</p>
            </div>
            {/* note nulled: the retrain advisory above replaces the run note in the response. */}
            <TrainRunReport detail={{ ...result, note: null }} />
          </div>
        )}
      </div>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Retrain {entry.modelName} on fresh data</DialogTitle>
            <DialogDescription>
              Retraining builds a fresh dataset and re-runs the candidate search. The result
              enters as a CANDIDATE and must pass review and approval — nothing is promoted
              automatically.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>Cancel</Button>
            <Button onClick={runRetrain} disabled={retrain.isPending}>
              <RefreshCw className="h-4 w-4 mr-1.5" /> Retrain model
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageSection>
  )
}

function MonitoringTab({ canTrain }: { canTrain: boolean }) {
  const monitoringQ = useMonitoring()

  if (monitoringQ.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }
  if (monitoringQ.isError) return <ErrorCard error={monitoringQ.error} />
  if (!monitoringQ.data) return <Skeleton className="h-40 w-full" />
  const entries = monitoringQ.data

  if (entries.length === 0) {
    return (
      <Card className="card-elevated">
        <CardContent className="py-14 text-center space-y-3">
          <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Activity className="h-5 w-5" />
          </div>
          <p className="font-medium">No production models to monitor</p>
          <p className="text-helper max-w-lg mx-auto">
            Monitoring watches production models. Promote a model through governance to begin.
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      {/* The standing advisory — the backend's note, verbatim, never folded away. */}
      <div className="rounded-md border border-[hsl(var(--info)/0.3)] bg-[hsl(var(--info)/0.08)] p-3 flex gap-2">
        <Info className="h-4 w-4 text-[hsl(var(--info))] shrink-0 mt-0.5" />
        <p className="text-sm">{entries[0].note}</p>
      </div>

      {entries.map((e) => (
        <MonitoringCard key={e.modelId} entry={e} canTrain={canTrain} />
      ))}
    </div>
  )
}

/* ---------------------------------- page ---------------------------------- */

export default function PatternLabPage() {
  const { hasPermission } = useAuth()
  const canRead = hasPermission('ml.read')
  const canAnalyse = hasPermission('ml.analyse')
  const canTrain = hasPermission('ml.train')
  const [tab, setTab] = useState('overview')

  if (!canRead) {
    return (
      <>
        <PageHeader
          title="Pattern Lab"
          description="Governed pattern discovery over the institution's own lifecycle data."
        />
        <div className="px-6 pb-6"><NoPermission /></div>
      </>
    )
  }

  return (
    <>
      <PageHeader
        title="Pattern Lab"
        description="Governed pattern discovery over the institution's own lifecycle data — every number carries its evidence."
        actions={
          <Button onClick={() => setTab('discover')}>
            <Plus className="h-4 w-4 mr-1.5" /> New analysis
          </Button>
        }
      />
      <div className="px-6 pb-6">
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="overview"><LayoutDashboard className="h-4 w-4 mr-1.5" /> Overview</TabsTrigger>
            <TabsTrigger value="discover"><Microscope className="h-4 w-4 mr-1.5" /> Discover</TabsTrigger>
            <TabsTrigger value="models"><Boxes className="h-4 w-4 mr-1.5" /> Models</TabsTrigger>
            <TabsTrigger value="predictions"><TrendingUp className="h-4 w-4 mr-1.5" /> Predictions</TabsTrigger>
            <TabsTrigger value="monitoring"><Activity className="h-4 w-4 mr-1.5" /> Monitoring</TabsTrigger>
          </TabsList>
          <JourneyBar tab={tab} onGo={setTab} />
          <TabsContent value="overview" className="mt-4">
            <PlainIntro>
              Pattern Lab studies your own students&apos; history and highlights patterns — for
              example, which current students resemble past students who ran into funding trouble.
              Everything here is <b>advisory</b>: it never changes a record, and a person always
              decides what to do about it.
            </PlainIntro>
            <OverviewTab onNewAnalysis={() => setTab('discover')} />
          </TabsContent>
          <TabsContent value="discover" className="mt-4">
            <PlainIntro>
              An analysis starts here. Pick one of the pre-approved questions, take a snapshot of
              the history, and run it. If there isn&apos;t enough reliable history to answer a
              question honestly, that question is <b>locked</b> and tells you exactly what&apos;s
              missing — the platform would rather refuse than guess.
            </PlainIntro>
            <DiscoverTab canAnalyse={canAnalyse} canTrain={canTrain} />
          </TabsContent>
          <TabsContent value="models" className="mt-4">
            <PlainIntro>
              A &ldquo;model&rdquo; is a rule-of-thumb learned from your history. New models start
              as <b>candidates</b>; a person decides whether one is good enough to use — and
              whoever built it is not allowed to approve it. The accuracy score runs from 0.5
              (a coin toss) to 1.0 (perfect).
            </PlainIntro>
            <ModelsTab onGoDiscover={() => setTab('discover')} />
          </TabsContent>
          <TabsContent value="predictions" className="mt-4">
            <PlainIntro>
              Each approved model gives every current student a score — &ldquo;this student looks
              74% similar to past students who lost funding&rdquo;. A score is a prompt for a human
              conversation, never an automatic decision, and each one lists the factors behind it.
            </PlainIntro>
            <PredictionsTab canTrain={canTrain} />
          </TabsContent>
          <TabsContent value="monitoring" className="mt-4">
            <PlainIntro>
              This tab checks whether the models are still telling the truth: old predictions are
              compared with what actually happened. A model doing badly is flagged for
              <b> review</b> right here — the platform grades its own work and says so honestly.
            </PlainIntro>
            <MonitoringTab canTrain={canTrain} />
          </TabsContent>
        </Tabs>
      </div>
    </>
  )
}
