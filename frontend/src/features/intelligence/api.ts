/**
 * PGR Intelligence API client.
 *
 * Every call here is additive over the existing domain surfaces — the intelligence
 * layer NEVER writes to a source-of-truth table. Endpoints marked `enable_llm` return
 * the deterministic result with `enable_llm=false` (default) and add narrated fields
 * only when the caller opts in.
 */
import { api } from '@/shared/api/client'

// Backend intelligence schemas ship snake_case (the module doesn't inherit the
// platform-wide camelCase alias generator). Every response passes through this
// walker so the frontend types match. Keys inside `evidence`, `state`, `payload`
// and other freeform dict values are left as-is — those are user-defined shapes.
const OPAQUE_KEYS = new Set([
  'state', 'evidence', 'payload', 'principal_scope', 'active_filters',
  'target_ref', 'owner_ref', 'source_signal', 'source_a_ref', 'source_b_ref',
  'locator', 'detail', 'model_health', 'drivers', 'counts', 'facts',
  'rule_candidates', 'config_candidates', 'simulation_result', 'from_ref', 'to_ref',
  'features', 'subject',
])
function snakeToCamel(s: string): string { return s.replace(/_([a-z0-9])/g, (_, c) => c.toUpperCase()) }
function camelize<T>(v: unknown, opaque = false): T {
  if (Array.isArray(v)) return v.map((x) => camelize(x, opaque)) as unknown as T
  if (v && typeof v === 'object') {
    const out: Record<string, unknown> = {}
    for (const [k, val] of Object.entries(v as Record<string, unknown>)) {
      const isOpaque = opaque || OPAQUE_KEYS.has(k)
      out[snakeToCamel(k)] = isOpaque && val && typeof val === 'object' ? val : camelize(val, isOpaque)
    }
    return out as T
  }
  return v as T
}
function camelToSnake(s: string): string { return s.replace(/([A-Z])/g, (m) => `_${m.toLowerCase()}`) }
function snakeize(v: unknown, opaque = false): unknown {
  if (Array.isArray(v)) return v.map((x) => snakeize(x, opaque))
  if (v && typeof v === 'object' && !(v instanceof Date)) {
    const out: Record<string, unknown> = {}
    for (const [k, val] of Object.entries(v as Record<string, unknown>)) {
      const key = camelToSnake(k)
      const isOpaque = opaque || OPAQUE_KEYS.has(key)
      out[key] = isOpaque && val && typeof val === 'object' && !Array.isArray(val) ? val : snakeize(val, isOpaque)
    }
    return out
  }
  return v
}
async function getJson<T>(path: string): Promise<T> { return camelize<T>(await api.get<unknown>(path)) }
async function postJson<T>(path: string, body?: unknown): Promise<T> {
  return camelize<T>(await api.post<unknown>(path, body ? snakeize(body) : undefined))
}

// ---- Types (mirror app/intelligence/schemas.py) ----------------------------

export interface EvidenceClaim {
  id: string
  artefactId: string
  claimType: string
  sourceType: string
  sourceId: string | null
  locator: Record<string, unknown> | null
  valueHash: string
  asOf: string
  permissionScope: Record<string, unknown> | null
  status: string
  detail: Record<string, unknown> | null
}

export interface DomainSummary {
  domain: string
  highlights: string[]
  counts: Record<string, number>
  facts: Array<Record<string, unknown>>
}

export interface MissingSource {
  source: string
  reason: string
}

export interface CaseContext {
  principalScope: Record<string, unknown>
  studentId: string | null
  cohortFilter: Record<string, unknown> | null
  timeWindow: { from?: string | null; to?: string | null; label?: string | null } | null
  activeFilters: Record<string, unknown>
  domainSummaries: DomainSummary[]
  missingSources: MissingSource[]
  pendingActionPlanId: string | null
  narratedSummary: { body: string; source: 'model' | 'fallback'; model: string | null } | null
}

export type PressureKind =
  | 'milestone_due' | 'milestone_overdue' | 'supervision_gap'
  | 'funding_expiring' | 'no_active_funding' | 'thesis_correction_window'

export interface PressurePoint {
  kind: PressureKind
  label: string
  when: string | null
  weight: number
  evidence: Record<string, unknown> | null
}

export interface DependencyEdge {
  fromRef: Record<string, unknown>
  toRef: Record<string, unknown>
  reason: string
}

export interface ModelSignal {
  target: string
  probability: number
  modelVersionId: string | null
  modelHealth: 'healthy' | 'review' | 'unknown'
}

export interface StudentTwinSnapshot {
  studentId: string
  asOf: string
  state: Record<string, unknown>
  pressurePoints: PressurePoint[]
  dependencies: DependencyEdge[]
  modelSignals: ModelSignal[]
  blockers: string[]
  narratedState: { body: string; source: 'model' | 'fallback'; model: string | null } | null
}

export type ActionType =
  | 'create_task' | 'prepare_meeting_brief' | 'request_funding_review'
  | 'open_review_evidence_check' | 'schedule_reassessment'

export interface InterventionAction {
  id: string
  actionType: ActionType
  targetRef: Record<string, unknown>
  ownerRef: Record<string, unknown> | null
  dueAt: string | null
  status: 'pending' | 'executed' | 'failed' | 'skipped'
  executedAt: string | null
  executionRef: Record<string, unknown> | null
  errorReason: string | null
}

export interface InterventionPlan {
  id: string
  caseRef: string
  studentId: string | null
  rationale: string
  sourceSignal: Record<string, unknown> | null
  reassessAt: string | null
  status: 'draft' | 'confirmed' | 'cancelled' | 'expired'
  confirmedAt: string | null
  actions: InterventionAction[]
}

export interface EngagementSnapshot {
  id: string
  studentId: string
  computedAt: string
  label: 'thriving' | 'steady' | 'drifting' | 'strained'
  score: number
  drivers: Record<string, number>
  engine: 'rules' | 'llm'
}

export interface EngagementTrajectory {
  studentId: string
  points: EngagementSnapshot[]
  recentEvents: Array<{ kind: string; weight: number; occurredAt: string; reasonCode: string | null }>
}

export type ScenarioChangeKind =
  | 'suspend_for_weeks' | 'extend_expected_end_by_months'
  | 'change_study_mode' | 'shift_next_milestone_by_days'

export interface ScenarioResult {
  studentId: string
  request: {
    studentId: string
    change: ScenarioChangeKind
    params: Record<string, unknown>
    includeSensitivity: boolean
  }
  deterministicDiff: {
    expectedEndBefore: string | null
    expectedEndAfter: string | null
    milestonesShifted: Array<Record<string, unknown>>
    fundingCoverageBefore: Record<string, unknown>
    fundingCoverageAfter: Record<string, unknown>
    assumptions: string[]
  }
  modelSensitivity: Array<{
    target: string
    baselineProbability: number
    sensitivityProbability: number
    deltaPp: number
    modelVersionId: string | null
    note: string
  }>
  qualitativeSensitivity: Array<{
    target: string
    direction: 'likely_increase' | 'likely_decrease' | 'no_clear_change' | 'uncertain'
    rationale: string
    baselineProbability: number | null
    engine: 'model' | 'fallback'
    model: string | null
    note: string
  }>
  missingData: string[]
  computedAt: string
}

export interface RiskStoryline {
  studentId: string
  target: string
  points: Array<{
    id: string; predictedAt: string; probability: number; threshold: number | null
    modelVersionId: string; modelHealth: Record<string, unknown> | null
  }>
  driversByPrediction: Record<string, Array<{
    id: string; feature: string; direction: 'up' | 'down' | 'flat'
    method: string; deltaPpOrSensitivity: number | null
  }>>
  modelVersionBoundaries: Array<Record<string, unknown>>
}

// ---- Callers ---------------------------------------------------------------

export const intelligenceApi = {
  caseContext: (studentId: string, opts: { enableLlm?: boolean; recordEvidence?: boolean } = {}) =>
    getJson<CaseContext>(
      `/intelligence/students/${studentId}` +
      `?enable_llm=${opts.enableLlm ? 'true' : 'false'}` +
      `&record_evidence=${opts.recordEvidence ? 'true' : 'false'}`,
    ),

  evidenceForArtefact: (artefactId: string) =>
    getJson<EvidenceClaim[]>(`/intelligence/evidence/${artefactId}`),

  twin: (studentId: string, opts: { enableLlm?: boolean } = {}) =>
    getJson<StudentTwinSnapshot>(
      `/intelligence/twin/${studentId}?enable_llm=${opts.enableLlm ? 'true' : 'false'}`,
    ),

  insights: (studentId: string) =>
    getJson<{
      studentId: string
      engineUsed: string
      situation: string
      observations: string[]
      suggestedNext: string[]
    }>(`/intelligence/students/${studentId}/insights`),

  scenarioPreview: (body: {
    studentId: string
    change: ScenarioChangeKind
    params: Record<string, unknown>
    includeSensitivity?: boolean
  }) => postJson<ScenarioResult>('/intelligence/scenarios', body),

  proposeFromSignal: (body: {
    signalKind: string; signalDetail: string; caseRef: string; studentId?: string | null
  }) => postJson<{
    actionType: ActionType; rationale: string; source: 'model' | 'fallback'
    model: string | null; caseRef: string; studentId: string | null
    signal: { kind: string; detail: string }
  }>('/intelligence/interventions/propose-from-signal', body),

  stagePlan: (body: {
    caseRef: string
    studentId?: string | null
    rationale: string
    sourceSignal?: Record<string, unknown> | null
    reassessAt?: string | null
    actions: Array<{
      actionType: ActionType
      targetRef: Record<string, unknown>
      ownerRef?: Record<string, unknown> | null
      dueAt?: string | null
      payload?: Record<string, unknown> | null
    }>
  }) => postJson<InterventionPlan>('/intelligence/interventions/plan', body),

  confirmPlan: (planId: string) =>
    postJson<InterventionPlan>(`/intelligence/interventions/${planId}/confirm`),

  cancelPlan: (planId: string, reason?: string) =>
    postJson<InterventionPlan>(
      `/intelligence/interventions/${planId}/cancel${reason ? `?reason=${encodeURIComponent(reason)}` : ''}`,
    ),

  listInterventionsForStudent: (studentId: string) =>
    getJson<InterventionPlan[]>(`/intelligence/students/${studentId}/interventions`),

  engagement: (studentId: string) =>
    getJson<EngagementTrajectory>(`/intelligence/engagement/${studentId}`),

  computeEngagement: (studentId: string, opts: { windowDays?: number; engine?: 'rules' | 'llm' } = {}) =>
    postJson<EngagementSnapshot>(
      `/intelligence/engagement/${studentId}/compute` +
      `?window_days=${opts.windowDays ?? 90}&engine=${opts.engine ?? 'rules'}`,
    ),

  predictionHistory: (studentId: string, target: string) =>
    getJson<RiskStoryline>(`/intelligence/predictions/${studentId}/history?target=${encodeURIComponent(target)}`),

  // ---- Institutional Memory (spec §19) -------------------------------------

  similarCases: (body: { caseClass: string; subject: Record<string, unknown>; limit?: number }) =>
    postJson<SimilarCasesResult>('/intelligence/cases/similar', body),

  // ---- Policy Compiler (spec §20) ------------------------------------------

  registerPolicyVersion: (body: { policyRef: string; versionLabel: string; documentVersionId?: string | null }) =>
    postJson<{ id: string; policyRef: string; versionLabel: string }>('/intelligence/policy/versions', body),

  proposePolicyChanges: (body: { policyVersionId: string; policyText: string; enableLlm?: boolean }) =>
    postJson<PolicyProposal>('/intelligence/policy/proposals', body),

  getPolicyProposal: (proposalId: string) =>
    getJson<PolicyProposal>(`/intelligence/policy/proposals/${proposalId}`),

  reviewPolicyProposal: (proposalId: string, disposition: 'reviewed' | 'approved' | 'rejected' | 'published') =>
    postJson<{ id: string; status: string; reviewedAt: string | null }>(
      `/intelligence/policy/proposals/${proposalId}/review`, { disposition },
    ),

  // ---- Research Change Radar (spec §17-18) ---------------------------------

  registerDocumentVersion: (body: {
    documentRef: string; objectKey: string; content: string
    studentId?: string | null; mimeType?: string | null
  }) => postJson<DocumentVersion>('/intelligence/documents/versions', body),

  listDocumentVersions: (documentRef: string) =>
    getJson<DocumentVersion[]>(`/intelligence/documents/${encodeURIComponent(documentRef)}/versions`),

  compareDocuments: (versionA: string, versionB: string, includeSemantic = false) =>
    postJson<ChangeFinding[]>(
      `/intelligence/documents/compare?version_a=${versionA}&version_b=${versionB}&include_semantic=${includeSemantic}`,
    ),

  disposeFinding: (findingId: string, disposition: string, note?: string) =>
    postJson<{ id: string; disposition: string }>(
      `/intelligence/findings/${findingId}/disposition`, { disposition, note },
    ),

  // ---- Supervision commitment extraction (spec §9-10) ----------------------

  proposeCommitments: (meetingId: string, studentId: string, notes: string) =>
    postJson<ProposedCommitment[]>(
      `/intelligence/supervision/meetings/${meetingId}/commitments/propose`,
      { studentId, notes },
    ),

  persistCommitments: (meetingId: string, studentId: string, confirmed: ProposedCommitment[]) =>
    postJson<SupervisionCommitment[]>(
      `/intelligence/supervision/meetings/${meetingId}/commitments`,
      { studentId, confirmed },
    ),

  listCommitments: (meetingId: string) =>
    getJson<SupervisionCommitment[]>(`/intelligence/supervision/meetings/${meetingId}/commitments`),
}

// ---- Change Radar types -----------------------------------------------------

export interface DocumentVersion {
  id: string
  documentRef: string
  contentHash: string
  extractionStatus: string
  extractorVersion: string | null
  pageCount: number | null
}

export interface ChangeFinding {
  id: string
  changeType: 'scope_changed' | 'method_changed' | 'sample_size_changed' | 'ethical_shift' | 'other'
  severityForReview: 'notice' | 'urgent'
  summary: string
  sourceARef: { section_heading?: string; chunk_id?: string; engine?: string; detected?: unknown } | null
  sourceBRef: { section_heading?: string; chunk_id?: string; engine?: string; detected?: unknown } | null
  reviewerDisposition: string | null
}

// ---- Commitment extraction types ---------------------------------------------

export interface ProposedCommitment {
  text: string
  ownerPersonOrRole: string | null
  dueAt?: string | null
}

export interface SupervisionCommitment {
  id: string
  meetingId: string
  studentId: string
  text: string
  ownerPersonOrRole: string | null
  dueAt: string | null
  status: 'open' | 'done' | 'cancelled'
  source: string
}

// ---- Institutional Memory types --------------------------------------------

export interface CaseFeatures {
  case_class?: string | null
  study_mode?: string | null
  stage?: string | null
  has_active_funding?: boolean | null
  supervision_overdue?: boolean | null
  programme_code?: string | null
}

export interface SimilarCaseCandidate {
  caseRef: string
  score: number
  features: CaseFeatures
  openedAt: string | null
}

export interface SimilarCasesResult {
  caseClass: string
  candidates: SimilarCaseCandidate[]
  narration: string
}

// ---- Policy Compiler types --------------------------------------------------

export interface PolicyRuleCandidate {
  setting_key: string
  from_value?: unknown
  to_value?: unknown
  rationale?: string
  kind?: string
  matched_span?: string
  engine?: string
  manual?: boolean
  reason?: string
}

export interface PolicyProposal {
  id: string
  sourceVersionId: string
  status: 'draft' | 'reviewed' | 'approved' | 'rejected' | 'published'
  ruleCandidates: PolicyRuleCandidate[]
  configCandidates: unknown[]
  simulationResult: { candidates: number; milestone_universe: number; computed_at: string } | null
  reviewedAt?: string | null
  publishedAt?: string | null
}
