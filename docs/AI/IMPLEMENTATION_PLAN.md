# PGR Intelligence — Implementation Plan (Backend only)

Derived from `PGR_AI_01_Idea_and_Value.pdf` and `PGR_AI_02_Backend_Architecture.pdf`.
Frontend doc deliberately out of scope per instruction.

## North star
Understand → Predict → Simulate → Act, with evidence attached to every claim and
human confirmation on every mutation.

## Design invariants (never violated)
1. Domain services stay authoritative — LLM never writes source-of-truth rows.
2. Row-scoping is applied BEFORE any AI call — prompts see only authorised data.
3. Every user-visible feature has a valid deterministic / manual result when Groq is off.
4. All app/ai calls and intelligence objects are Pydantic-schema-validated.
5. Actions are staged as drafts and executed only through existing domain services after confirmation.
6. Every factual conclusion cites its source row / document / model artefact.
7. Rule simulation and model sensitivity are separate outputs, never mixed.

## Package layering (new)
```
backend/app/intelligence/
    context/         — CaseContext builder + session working set
    evidence/        — EvidenceClaim schema + freshness / value-hash checks
    twin/            — StudentTwinSnapshot + pressure-point / dependency assembly
    scenario/        — deterministic previews + Pattern Lab sensitivity adapter
    interventions/   — action templates, planner, staging, idempotency
    supervision_ai/  — meeting brief augmentation + commitment extraction
    documents/       — extraction metadata, locators, comparison orchestration
    memory/          — governed case features + similarity
    policy/          — approved policy ingestion, mapping proposals + simulation
    investigation/   — Composer drill graph / monitor definitions
    observability/   — AI telemetry, fallback / cost / quality metrics
```
Dependency rule: `app/intelligence → app/ai + read/query/domain interfaces`.
Domain modules never depend on LLM output.

---

## Phase 1 — Foundations (this phase)
Build the shared contracts and trust layer first — everything else composes on top.

**Deliverables**
- Migration adding four tables: `evidence_claim`, `prediction_snapshot`, `driver_snapshot`, `intelligence_telemetry`.
- `app/intelligence/` package skeleton with `evidence`, `context`, `observability`, `interventions` subpackages.
- Pydantic schemas: `EvidenceClaim`, `CaseContext`, `ActionPlan`, `PredictionSnapshot`, `DriverSnapshot`.
- Services: `EvidenceService`, `CaseContextBuilder`, `TelemetryLogger`, `PredictionSnapshotService`.
- Router `/api/v1/intelligence/*`:
  - `GET /students/{id}` → CaseContext (initial version, evidence-annotated).
  - `GET /evidence/{artefact_id}` → EvidenceClaim list with freshness.
  - `GET /predictions/{student_id}/history` → PredictionSnapshot series.
- Wire assistant service to record EvidenceClaims for every factual response.
- Integration test: contract, permission, model-off — evidence still renders when Groq is off.

**Gate to Phase 2**: permission tests pass + model-off E2E passes + evidence endpoint returns valid claims for a real student.

## Phase 2 — Existing feature upgrades
Case Copilot (multi-turn CaseContext), Intervention planner, Supervision commitments, Engagement trajectory. Reuses P1 contracts.
**Gate**: confirmed actions idempotent; reassessment scheduled correctly.

## Phase 3 — Digital Twin + scenarios
`StudentTwinSnapshot`, pressure-point assembler, side-effect-free scenario engine, Pattern Lab sensitivity adapter.
**Gate**: no-side-effect tests pass; scenario assumptions visible.

## Phase 4 — Document intelligence
Versioned extraction, chunk locators, Research Change Radar with strict finding schema + human disposition.
**Gate**: source passage accuracy + prompt-injection tests pass.

## Phase 5 — Institutional Memory
Governed case features + hybrid similarity + de-identified precedent summaries.
**Gate**: privacy / permission review + outcome-bias language tested.

## Phase 6 — Policy Compiler
Approved policy ingestion, allow-listed RuleCandidate / ConfigCandidate mapping, cohort simulation.
**Gate**: Registry sign-off; config rollback + impact tests pass.

---

## Environment / infra notes
- Egress: Groq HTTPS destination must be added to production network policy (documented in P1 README).
- Model routing: keep centralised in `app/ai` — never split.
- Read replica: use for prediction-history reads and Composer aggregates; writes go primary.
- Idempotency keys: `case_ref + action_type + target + source_event` for all confirmed multi-action plans and worker jobs.
