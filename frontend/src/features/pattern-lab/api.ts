'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

/* ------------------------------------------------------------------ *
 * Pattern Lab (PL-1…PL-6) — /pattern-lab. Governed targets, versioned
 * datasets with a quality report, ranked discovery findings, the model
 * registry from the bounded candidate search, PL-4 governance
 * (lifecycle transitions, auto-generated model cards,
 * dataset→prediction lineage), PL-5 production predictions (batch
 * scoring with per-student contributing factors) and PL-6 monitoring:
 * health, drift and performance-vs-actuals per production model, plus
 * the manual-first retrain loop.
 * `ml.read` to view; `ml.analyse` to build datasets / run discovery;
 * `ml.train` to run the candidate search, submit for review,
 * batch-score the cohort and retrain; `ml.approve` for every
 * governance decision.
 * Shapes mirror backend/app/modules/pattern_lab/router.py verbatim.
 * ------------------------------------------------------------------ */

export interface TargetSufficiency {
  eligible: number
  positives: number
  negatives: number
  sufficient: boolean
  reason: string | null
}

export interface PatternTarget {
  key: string
  label: string
  question: string
  outcomeLabel: string
  outcomeDefinition: string
  population: string
  predictionPoint: string
  minEligible: number
  minMinority: number
  sufficiency: TargetSufficiency
}

export interface ExcludedFeature {
  key: string
  label: string
  reason: string
}

export interface ActiveFeature {
  key: string
  group: string
  label: string
  description: string
}

export interface SkippedTest {
  key: string
  label: string
  reason: string
}

export interface DatasetQuality {
  exclusions: { reason: string; count: number }[]
  completeness: Record<string, number>
  excludedFeatures: ExcludedFeature[]
  activeFeatures: ActiveFeature[]
  predictionPoint: string
  /** Present only after discovery has run on this dataset. */
  discoverySkipped?: SkippedTest[]
  testsRun?: number
  correctedAlpha?: number
}

export interface PatternDataset {
  id: string
  targetKey: string
  name: string
  /** Content hash — same data, same version (backend String(64)). */
  version: string
  status: string
  recordsFound: number
  eligible: number
  positives: number
  negatives: number
  sufficient: boolean
  quality: DatasetQuality
  createdAt: string | null
}

export interface FindingGroup {
  desc: string
  rate: number
  n: number
}

export interface FindingConfounder {
  key: string
  label: string
  phi: number
}

export interface FindingEvidence {
  featureLabel: string
  group: string
  description: string
  worse: FindingGroup
  better: FindingGroup
  pValue: number
  correctedAlpha: number
  testsRun: number
  riskRatio: number | null
  confounders: FindingConfounder[]
  caution: string
}

export interface PatternFinding {
  id: string
  datasetId: string
  featureKey: string
  rank: number
  statement: string
  significant: boolean
  pValue: number
  effect: number | null
  evidence: FindingEvidence
  createdAt: string | null
}

/* ------------------------- PL-3 training & registry ------------------------- */

export interface PermutationImportanceItem {
  feature: string
  importance: number
}

export interface CandidateMetrics {
  aucMean: number
  aucStd: number
  averagePrecision: number
  brierScore: number
  precisionAt50: number | null
  recallAt50: number | null
  cvFolds: number
  n: number
  positives: number
  /** Absent on the baseline candidate. */
  permutationImportance?: PermutationImportanceItem[]
}

export interface CandidateResult {
  algorithm: string
  params: Record<string, unknown>
  metrics: CandidateMetrics
  beatsBaseline: boolean
  isBaseline: boolean
}

export interface DroppedFeature {
  key: string
  reason: string
}

/** The stored run record — also `runs[].detail` in GET /models. */
export interface TrainRunDetail {
  verdict: 'succeeded' | 'failed'
  baselineAuc: number
  baselineMargin: number
  recommended: string | null
  candidates: CandidateResult[]
  droppedFeatures: DroppedFeature[]
  note: string | null
}

/** POST /train response: run identity + the detail, flattened. */
export interface TrainRun extends TrainRunDetail {
  runId: string
  modelId: string
  versionNo: number
  durationMs: number
}

export interface MlModelVersion {
  id: string
  modelId: string
  versionNo: number
  algorithm: string
  params: Record<string, unknown>
  /** Dataset content hash the version was trained on. */
  datasetVersion: string
  featureKeys: string[]
  metrics: CandidateMetrics
  beatsBaseline: boolean
  /**
   * Training produces trained/candidate; the rest is the PL-4 lifecycle:
   * candidate → review → approved → production, with declined/retired terminal.
   */
  status: MlVersionStatus
  createdAt: string | null
  artifactBytes: number
}

export type MlVersionStatus =
  | 'trained'
  | 'candidate'
  | 'review'
  | 'approved'
  | 'production'
  | 'declined'
  | 'retired'

export interface MlTrainingRunSummary {
  id: string
  datasetVersion: string
  status: string
  durationMs: number | null
  /** Same shape as the /train detail; `{}` only if a run was interrupted. */
  detail: TrainRunDetail | Record<string, never>
  createdAt: string | null
}

export interface MlModel {
  id: string
  targetKey: string
  name: string
  description: string | null
  createdAt: string | null
  versions: MlModelVersion[]
  /** Newest-first, capped at 5 by the backend. */
  runs: MlTrainingRunSummary[]
}

export interface MlAvailability {
  available: boolean
  note: string | null
}

/* ------------------------------ PL-4 governance ------------------------------ */

export type GovernanceAction =
  | 'submit_review'
  | 'approve'
  | 'decline'
  | 'promote'
  | 'retire'

/** One append-only governance_log entry (also the model card's `governance`). */
export interface GovernanceEntry {
  action: string
  status: string
  byUserId: string | null
  byEmail: string | null
  at: string
  rationale: string | null
}

/** POST /versions/{id}/transition response. */
export interface TransitionResult {
  id: string
  status: MlVersionStatus
  log: GovernanceEntry[]
  /** e.g. "v1 (gradient_boosting)" when a promotion retired the incumbent. */
  retiredIncumbent: string | null
}

/** GET /versions/{id}/card — generated from the data, never hand-written. */
export interface ModelCard {
  versionId: string
  versionNo: number
  status: MlVersionStatus
  model: { id: string; name: string; targetKey: string } | null
  purpose: {
    question: string | null
    outcome: string | null
    population: string | null
    predictionPoint: string | null
  }
  data: {
    datasetVersion: string
    builtAt: string | null
    recordsFound: number | null
    eligible: number | null
    positives: number | null
    exclusions: { reason: string; count: number }[] | null
    excludedFeatures: ExcludedFeature[] | null
  }
  method: {
    algorithm: string
    params: Record<string, unknown>
    features: string[]
    validation: string
  }
  performance: {
    aucMean: number | null
    aucStd: number | null
    averagePrecision: number | null
    brierScore: number | null
    precisionAt50: number | null
    recallAt50: number | null
    n: number | null
    positives: number | null
  }
  explainability: PermutationImportanceItem[]
  limitations: string[]
  governance: GovernanceEntry[]
}

export interface LineageNode {
  kind: 'dataset' | 'features' | 'trainingRun' | 'version' | 'predictions'
  id: string | null
  label: string
  sub: string | null
}

/** GET /versions/{id}/lineage — dataset → features → run → version → predictions. */
export interface LineageChain {
  chain: LineageNode[]
}

export interface PatternLabStages {
  discover: string
  models: string
  predictions: string
  monitoring: string
}

export interface OverviewModel {
  id: string
  name: string
  targetKey: string
  status: string
  algorithm: string | null
  aucMean: number | null
  beatsBaseline: boolean
}

export interface PatternLabOverview {
  targets: PatternTarget[]
  datasets: PatternDataset[]
  recentFindings: PatternFinding[]
  stages: PatternLabStages
  /** PL-3: best version per model for the home screen's ACTIVE MODELS panel. */
  models?: OverviewModel[]
}

/* ----------------------------- PL-5 predictions ----------------------------- */

/**
 * One perturbation-derived contributing factor: replace the student's value with
 * the population median and measure how the predicted probability moves.
 * `deltaPp` is percentage points; positive means this student's value RAISES
 * their probability versus the median, negative pulls it down.
 */
export interface PredictionFactor {
  feature: string
  label: string
  value: number | null
  deltaPp: number
}

export interface TopPrediction {
  studentId: string
  studentRef: string
  studentName: string
  probability: number
  factors: PredictionFactor[]
  /** Frontend route to the student record, e.g. /students/{id}. */
  link: string
}

export interface DistributionBand {
  /** e.g. '0–20%'. */
  band: string
  count: number
}

/** GET /predictions — the latest batch per model that has one (models without a batch are omitted). */
export interface ModelBatch {
  modelId: string
  modelName: string
  targetKey: string
  batchId: string
  scoredAt: string | null
  scored: number
  meanProbability: number | null
  /** Five 20-point probability bands. */
  distribution: DistributionBand[]
  /** Highest-probability students in the batch, capped at 15 by the backend. */
  top: TopPrediction[]
}

/** GET /students/{id}/predictions — latest prediction per model for one student. */
export interface StudentPrediction {
  modelId: string
  modelName: string
  versionId: string
  /** The target's outcome label, e.g. 'withdrew within 12 months'. */
  outcome: string
  probability: number
  factors: PredictionFactor[]
  scoredAt: string | null
  /** Backend advisory note — rendered verbatim under the prediction. */
  note: string
}

/** POST /models/{id}/score response. 409 when the model has no production version. */
export interface ScoreResult {
  batchId: string
  modelId: string
  versionNo: number
  scored: number
  meanProbability: number
  highRisk: number
  tasksRaised: number
  durationMs: number
}

/* ----------------------------- PL-6 monitoring ----------------------------- */

/** One prediction batch in the trend line, oldest first. */
export interface TrendPoint {
  batchId: string
  scoredAt: string | null
  scored: number
  meanProbability: number
  /** Counts across the five 20-point probability bands (0–20% … 80–100%). */
  bands: number[]
}

/** Realised outcome rate for one predicted-probability band — calibration in the wild. */
export interface RealizedBand {
  /** e.g. '0–20%'. */
  band: string
  n: number
  positives: number
  /** null when the band has no matured predictions. */
  realizedRate: number | null
}

/**
 * Matured predictions from the OLDEST batch compared against what actually
 * happened. Below the maturity threshold `judged` is false and `note` says so —
 * the numbers are reported, not judged.
 */
export interface ActualsReport {
  batchScoredAt: string | null
  matured: number
  /** Rank-statistic AUC on the matured subset; null when only one class matured. */
  aucOnMatured: number | null
  realizedByBand: RealizedBand[]
  judged: boolean
  note: string | null
}

/** PSI between the training matrix and the current cohort, one row per feature. */
export interface DriftRow {
  feature: string
  label: string
  /** null when either sample is too small (<10). */
  psi: number | null
  /** <0.1 stable, 0.1–0.25 moderate, ≥0.25 major; null when psi is null. */
  band: 'stable' | 'moderate' | 'major' | null
}

/** GET /monitoring — one entry per PRODUCTION model (delivered worst-drift-first). */
export interface MonitoringEntry {
  modelId: string
  modelName: string
  targetKey: string
  versionNo: number
  versionId: string
  /** aucMean recorded at training time; null if metrics were not stored. */
  trainedAuc: number | null
  health: 'ok' | 'watch' | 'review'
  /** The sentences that justify the verdict — rendered verbatim. */
  reasons: string[]
  /** YYYY-MM-DD; pulled to today when reasons are present. */
  recommendedReviewAt: string
  trend: TrendPoint[]
  /** null until the model has scored at least one batch. */
  actuals: ActualsReport | null
  drift: DriftRow[]
  /** Standing advisory — rendered verbatim. */
  note: string
}

/**
 * POST /models/{id}/retrain — a fresh dataset plus the same candidate search.
 * `note` (the CANDIDATE-must-pass-governance advisory) replaces the run note.
 */
export interface RetrainResult extends TrainRun {
  /** Content hash of the freshly built dataset. */
  datasetVersion: string
  note: string
}

/* ---------------------------------- queries ---------------------------------- */

export const usePatternLabOverview = () =>
  useQuery({
    queryKey: ['pattern-lab', 'overview'],
    queryFn: () => api.get<PatternLabOverview>('/pattern-lab/overview'),
  })

export const usePatternTargets = () =>
  useQuery({
    queryKey: ['pattern-lab', 'targets'],
    queryFn: () => api.get<PatternTarget[]>('/pattern-lab/targets'),
  })

export const usePatternDatasets = () =>
  useQuery({
    queryKey: ['pattern-lab', 'datasets'],
    queryFn: () => api.get<PatternDataset[]>('/pattern-lab/datasets'),
  })

export const usePatternDataset = (id: string | null) =>
  useQuery({
    queryKey: ['pattern-lab', 'datasets', id],
    queryFn: () => api.get<PatternDataset>(`/pattern-lab/datasets/${id}`),
    enabled: !!id,
  })

export const useDatasetFindings = (datasetId: string | null) =>
  useQuery({
    queryKey: ['pattern-lab', 'findings', datasetId],
    queryFn: () => api.get<PatternFinding[]>(`/pattern-lab/datasets/${datasetId}/findings`),
    enabled: !!datasetId,
  })

export const useMlModels = () =>
  useQuery({
    queryKey: ['pattern-lab', 'models'],
    queryFn: () => api.get<MlModel[]>('/pattern-lab/models'),
  })

export const useMlAvailability = () =>
  useQuery({
    queryKey: ['pattern-lab', 'ml-availability'],
    queryFn: () => api.get<MlAvailability>('/pattern-lab/ml-availability'),
  })

export const useModelCard = (versionId: string | null, enabled = true) =>
  useQuery({
    queryKey: ['pattern-lab', 'card', versionId],
    queryFn: () => api.get<ModelCard>(`/pattern-lab/versions/${versionId}/card`),
    enabled: !!versionId && enabled,
  })

export const useVersionLineage = (versionId: string | null, enabled = true) =>
  useQuery({
    queryKey: ['pattern-lab', 'lineage', versionId],
    queryFn: () => api.get<LineageChain>(`/pattern-lab/versions/${versionId}/lineage`),
    enabled: !!versionId && enabled,
  })

export const usePredictionBatches = () =>
  useQuery({
    queryKey: ['pattern-lab', 'predictions'],
    queryFn: () => api.get<ModelBatch[]>('/pattern-lab/predictions'),
  })

export const useMonitoring = () =>
  useQuery({
    queryKey: ['pattern-lab', 'monitoring'],
    queryFn: () => api.get<MonitoringEntry[]>('/pattern-lab/monitoring'),
  })

export const useStudentPredictions = (studentId: string, enabled = true) =>
  useQuery({
    queryKey: ['pattern-lab', 'student-predictions', studentId],
    queryFn: () =>
      api.get<StudentPrediction[]>(`/pattern-lab/students/${studentId}/predictions`),
    enabled: !!studentId && enabled,
  })

/* --------------------------------- mutations --------------------------------- */

export function useBuildDataset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (targetKey: string) =>
      api.post<PatternDataset>('/pattern-lab/datasets', { targetKey }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pattern-lab', 'datasets'] })
      qc.invalidateQueries({ queryKey: ['pattern-lab', 'overview'] })
    },
  })
}

export function useTrainModel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { datasetId: string; name?: string }) =>
      api.post<TrainRun>('/pattern-lab/train', body),
    onSuccess: () => {
      // Training touches models, runs, versions and the overview stage line —
      // invalidate every pattern-lab-prefixed key rather than enumerating.
      qc.invalidateQueries({ queryKey: ['pattern-lab'] })
    },
  })
}

export function useTransitionVersion() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ versionId, action, rationale }: {
      versionId: string
      action: GovernanceAction
      rationale?: string
    }) =>
      api.post<TransitionResult>(
        `/pattern-lab/versions/${versionId}/transition`,
        { action, ...(rationale != null ? { rationale } : {}) },
      ),
    onSuccess: () => {
      // A transition touches version status, the overview ACTIVE MODELS panel,
      // the model card's governance history and the lineage `sub` — invalidate
      // every pattern-lab-prefixed key rather than enumerating.
      qc.invalidateQueries({ queryKey: ['pattern-lab'] })
    },
  })
}

export function useScoreModel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (modelId: string) =>
      api.post<ScoreResult>(`/pattern-lab/models/${modelId}/score`),
    onSuccess: () => {
      // A batch changes /predictions, every student-predictions panel and the
      // lineage `sub` counts — invalidate every pattern-lab-prefixed key rather
      // than enumerating.
      qc.invalidateQueries({ queryKey: ['pattern-lab'] })
    },
  })
}

export function useRetrainModel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (modelId: string) =>
      api.post<RetrainResult>(`/pattern-lab/models/${modelId}/retrain`),
    onSuccess: () => {
      // Retraining builds a dataset, adds a run and new versions, and shifts the
      // overview + monitoring pictures — invalidate every pattern-lab-prefixed
      // key rather than enumerating.
      qc.invalidateQueries({ queryKey: ['pattern-lab'] })
    },
  })
}

export function useRunDiscovery() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (datasetId: string) =>
      api.post<{ findings: PatternFinding[]; significant: number }>(
        `/pattern-lab/datasets/${datasetId}/discover`,
      ),
    onSuccess: (_data, datasetId) => {
      qc.invalidateQueries({ queryKey: ['pattern-lab', 'findings', datasetId] })
      // Discovery also stamps testsRun / correctedAlpha / discoverySkipped onto quality.
      qc.invalidateQueries({ queryKey: ['pattern-lab', 'datasets'] })
      qc.invalidateQueries({ queryKey: ['pattern-lab', 'overview'] })
    },
  })
}
