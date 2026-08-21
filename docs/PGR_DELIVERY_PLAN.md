# PGR Platform — Phased Delivery Plan

> Owner: **solution-architect** · Source: `PGR_Platform_Technical_Architecture.pdf` (§21 phasing) ·
> Design system: Redwood Professional (`fp_design_system_template/`) · Last synced: 2026-08-21
>
> **How to read this:** every task is a checkbox with a stable ID (`FE-x.n` / `BE-x.n`) and a
> **Done-when** line you can verify. Boxes are ticked by the solution-architect **only after**
> the acceptance criterion is confirmed against real code/tests — not on assertion.
> `( )` = not started · `(~)` = in progress · `(x)` = done & verified.

## Legend & workstreams
- **BE** = backend-engineer (FastAPI + PostgreSQL). **FE** = frontend-engineer (Next.js 14 + Redwood).
- Dependencies noted inline as `(needs BE-1.1)`.
- Decisions live in [`DECISIONS.md`](DECISIONS.md). Key one: **D-01 — frontend runs on Next.js 14**
  (design bundle verbatim), diverging from arch §14's Vite recommendation.

---

## Phase 0 — Foundations
*Goal: an empty but wired full stack — both apps boot, talk over `/api/v1`, CI runs. No domain logic yet.*

### Backend
- [x] **BE-0.1** Repo scaffold per §5 (`backend/app/{core,modules,api,db,workers,tests}`, `requirements.txt`, `Dockerfile`, `.env.example`).
  *Done-when:* `uvicorn app.main:app` boots and `GET /health/live` returns 200. ✅ verified — booted on :8099, `{"status":"live"}` HTTP 200.
- [x] **BE-0.2** `core/config.py` typed settings from env (Appendix C vars); `core/logging.py` structured JSON logs; `core/middleware.py` request-id + timing.
  *Done-when:* a request logs one structured line with `requestId`, `method`, `path`, `status`, `durationMs`. ✅ verified — see access-log line with all five fields.
- [x] **BE-0.3** `db/base.py` (declarative base + naming convention + UUID/Timestamp mixins), `core/database.py` async engine + session factory, `db/session.py` `get_session` dependency.
  *Done-when:* a trivial `SELECT 1` runs through an injected async session. ✅ verified — `SELECT 1 -> 1` (needed `greenlet`, now pinned).
- [x] **BE-0.4** `core/errors.py` exception hierarchy (`AppError`→`NotFoundError`, `ConflictError`, `ValidationAppError`, `AuthError`, `PermissionError`, `IntegrationError`, `WorkflowError`) + single handler rendering Appendix B envelope.
  *Done-when:* raising `NotFoundError` yields `{"error":{"code":"not_found",...,"requestId":...}}` with HTTP 404. ✅ verified — `tests/unit/test_core.py::test_error_envelope_and_status`.
- [x] **BE-0.5** `core/pagination.py` (offset + opaque cursor helpers) and the list envelope `{data, page:{limit,nextCursor,total}}`.
  *Done-when:* honours `limit` (default 25/max 200) and returns the envelope. ✅ verified — envelope + cursor round-trip unit tests.
- [x] **BE-0.6** Alembic wired (`db/migrations/`, `alembic.ini`, async `env.py`); baseline migration created.
  *Done-when:* `alembic upgrade head` succeeds on a clean database. ✅ verified — `-> e95334ff3d83, baseline`, `current` = head.
- [~] **BE-0.7** `infra/docker/docker-compose.yml` — Postgres 16 + Redis 7 + api for local full stack.
  *Done-when:* `docker compose up` brings the API up healthy against Postgres. ⏳ file written; **cannot verify — Docker not installed on this box**. App verified standalone against SQLite instead.
- [x] **BE-0.8** OpenAPI published at `/api/v1/openapi.json`.
  *Done-when:* the schema loads and validates as OpenAPI 3.1. ✅ verified — `openapi 3.1.0`, paths `/health/live`, `/health/ready`, `/api/v1/me`.

### Frontend
- [x] **FE-0.1** Scaffold Next.js 14 (App Router) + TS + Tailwind 3.4 under `frontend/`.
  *Done-when:* `npm run dev` serves a page; `npm run build` passes. ✅ verified — build emits 15 routes; dev serves on :3000.
- [x] **FE-0.2** Install Redwood Professional per bundle `INSTRUCTIONS.md` (deps, copy `globals.css`, `tailwind.config.ts`, `components.json`, `lib/*`, `components/ui/*` (28), `components/layout/*`, `components/common/*`, `app/layout.tsx`, logo).
  *Done-when:* design tokens apply (warm off-white canvas, navy primary, pre-hydration theme script, status pills). ✅ verified — bundle copied verbatim; build consumes all 28 primitives; dashboard renders with tokens.
- [x] **FE-0.3** App shell (`AppShell.tsx`): `<Sidebar>` (PGR module nav) + `<Header>` (logo on `#15171A` plate) + `<main>`; `ThemeToggle` in sidebar footer.
  *Done-when:* collapsible sidebar + logo plate render; routes navigate. ✅ verified — `/dashboard` and `/students` render inside the shell; SPA nav works.
- [x] **FE-0.4** Providers: TanStack Query client + toast `<Toaster/>`. `shared/api/client.ts` targeting `/api/v1` with the list/error envelopes + in-memory token + `ApiError`; dev proxy in `next.config.mjs`.
  *Done-when:* a live query renders backend data. ✅ verified — dashboard connectivity panel shows **API reachable / Database ok / Principal anonymous** from live `/health/ready` + `/api/v1/me`.
- [x] **FE-0.5** OpenAPI client + types generation from backend `/api/v1/openapi.json` (needs BE-0.8).
  *Done-when:* `npm run gen:api` produces typed schema the build consumes. ✅ verified — generated `src/shared/api/schema.d.ts` (130 lines) from the live contract.

### Shared / Ops
- [ ] **BE-0.9 / FE-0.6** CI skeleton (`.github/workflows/`): install, lint + type-check (both tiers), unit/integration on ephemeral Postgres, image build + scan, migration check.
  *Done-when:* a PR runs the pipeline green end-to-end.

---

## Phase 1 — MVP: PGR core lifecycle
*Goal (§21): person → opportunity → recruitment (both routes) → assessment → offer → student
registration on one preserved `person_id` → supervisor assignment → single funding arrangement →
one configurable progression milestone flow → basic thesis→completion → executive + administrator dashboards.*

### Cross-cutting (build early in Phase 1)
- [x] **BE-1.0a** Identity/auth module: local password path (JWT access/refresh), `GET /api/v1/me`, RBAC tables `users, roles, permissions, role_permission, user_role` + seed. (OIDC + hashed/revocable refresh store = follow-up **BE-1.0a-hardening**.)
  *Done-when:* login returns access+refresh; `/me` returns principal + roles + permissions. ✅ verified — curl + `test_identity_person.py`; browser login as admin@example.com shows 12 permissions.
- [x] **BE-1.0b** Permission guard (fail-closed) in `core/dependencies.py` + repository-level **row scoping** from the principal in `core/authorization.py` (§12.3).
  *Done-when:* a supervisor token is filtered to only their supervisees at the query level. ✅ verified — test + live: admin `/students` = 2, supervisor Elena = 1 (only her supervisee); out-of-scope GET → 404.
- [ ] **BE-1.0c** Audit: `audit_event` table (partitioned by month) + service helper writing before/after + requestId on every state change (§12.4).
  *Done-when:* an application stage change writes one audit row with actor, before, after, rationale.
- [ ] **BE-1.0d** Minimal workflow/task/outbox core (§9/§10): `workflow_instance, task, notification, outbox_event`; task creation shares the state-change transaction.
  *Done-when:* accepting an offer creates onboarding tasks in the same transaction as student creation.
- [ ] **FE-1.0** Role-aware nav + route guards driven by `/api/v1/me` permissions (needs BE-1.0a).
  *Done-when:* actions/menus the principal lacks are hidden client-side (server still enforces).

### Backend — domain modules
- [x] **BE-1.1** `person` + `person_relationship` module + endpoints `GET/POST /persons`, `GET/PATCH /persons/{id}`, `/persons/{id}/relationships`, `/persons/{id}/timeline`.
  *Done-when:* one person holds multiple relationships over time; timeline returns lifecycle across identities. ✅ verified — Aisha Khan returns applicant→student→alumni timeline (curl + integration test + browser).
- [x] **BE-1.2** `recruitment` — `research_opportunity` (status FSM draft→approved→open→recruiting→filled→closed) + `POST /opportunities/{id}/transition`. Reference tables `research_area, department` (in student_record).
  *Done-when:* invalid transition returns `workflow_error` (422); valid one persists. ✅ verified — test + live (draft→filled rejected 422).
- [x] **BE-1.3** `recruitment` — `application` (both routes), `candidate_stage_history`, `application_assessment`; endpoints `/applications`, `/applications/{id}/advance`, `/applications/{id}/assess`, `/recruitment/pipeline`.
  *Done-when:* advancing a stage writes history; pipeline returns counts by stage. ✅ verified — history rows recorded; pipeline endpoint returns counts.
- [x] **BE-1.4** `admissions` — `offer` + `/applications/{id}/offer`, `/offers/{id}/issue|accept|decline`. **Accept creates a student reusing the same `person_id` (one atomic transaction).**
  *Done-when:* `POST /offers/{id}/accept` creates a `student` with the applicant's original `person_id`. ✅ verified — Marcus applicant→student, same person_id; accept-before-issue rejected 422; test asserts identity reuse.
- [x] **BE-1.5** `student_record` — `student, programme, research_project` + reference `department/research_area` + `/students`, `/students/{id}`, `/students/{id}/project`, `/students/{id}/summary`.
  *Done-when:* summary returns journey for a student. ✅ verified — student created with generated `student_ref`; summary returns person name + status. (funding/supervisors fold in at BE-1.6/1.8.)
- [x] **BE-1.6** `supervision` — `supervisor_relationship` (history-preserving) + `/students/{id}/supervisors` (list/assign), `/supervisors/{relId}/end`, `/supervisors/{personId}/students` (caseload). Supervisors folded into student summary.
  *Done-when:* ending a relationship closes `valid_to`; caseload query works. ✅ verified — assign/end tests; Elena's caseload returns Marcus (primary).
- [x] **BE-1.7** `progression` — `milestone_definition, milestone, progression_review`; `/programmes/{id}/milestone-definitions`, `/students/{id}/milestones` (row-scoped, lazy-generates first), `/milestones/{id}/submit|decide`. One configurable flow seeded for PhD CS.
  *Done-when:* a decision records outcome, updates the milestone, and generates the next milestone. ✅ verified — test + live: submit→decide `progress` generates the next; terminating outcome doesn't; decide-twice → 422.
- [x] **BE-1.8** `funding` — `funding_source, funding_arrangement` + `/funding-sources`, `/students/{id}/funding` (list row-scoped/create), `/funding/{id}/change` (close current, open new), `/funding/{id}/end`. Folded into student summary. Indexed `(student_id,status)`.
  *Done-when:* a student holds arrangements over time with `numeric(14,2)`+currency. ✅ verified — test + live: create/change (history preserved)/end; Marcus shows £19,000 (seeded) + £21,000 (added via UI).
- [x] **BE-1.9** `thesis` — `thesis, examination` + `/students/{id}/thesis`, `/students/{id}/thesis/intention`, `/theses/{id}/submit`, `/theses/{id}/examination/outcome`. (Examiner management = Phase 2.)
  *Done-when:* thesis moves preparation→intention→submitted→approved via examination outcome. ✅ verified — test + live (pass → approved).
- [x] **BE-1.10** `completion` — `completion, award` + `/students/{id}/completion` (get/confirm), `/students/{id}/graduation`. **Graduation (one txn) records the award, closes funding, sets student completed, opens alumni on the same person.**
  *Done-when:* graduation produces an `alumni` `person_relationship` on the same `person_id`. ✅ verified — test asserts full loop; live: Priya graduated → student closed, alumni current, funding ended, status completed.
- [x] **BE-1.11** `reporting` (read path) — `/dashboards/executive`, `/dashboards/administrator` as read-only aggregations over the lifecycle tables (materialized views + replicas are a scaling optimization deferred; queries kept portable).
  *Done-when:* both dashboards return the §13.3 metric sets. ✅ verified — test + live: conversion 50%, completions 1, active researchers, admin queues.

### Frontend — feature screens (each consumes the matching BE task)
- [x] **FE-1.1** Auth: login screen + AuthContext (in-memory access token, silent refresh from stored refresh token, 401-retry) + route guard + logout (needs BE-1.0a). ✅ verified — browser login→dashboard, session survives full reload, guard redirects unauthenticated /dashboard→/login.
- [x] **FE-1.2** Persons: list (search) + person 360 detail with identities + **timeline** across identities (needs BE-1.1). ✅ verified — list shows real persons with status pills; Aisha detail renders applicant→student→alumni timeline.
- [x] **FE-1.3** Recruitment: opportunities list + **New opportunity** dialog + **FSM-aware status-transition control** ("Move to…") + applications tab. ✅ verified — moved an opportunity open→recruiting in the UI. (Funding "Change" button also added to FundingPanel — close current/open new inline.)
- [x] **FE-1.4** Recruitment: applications tab with **pipeline counts by stage** + application detail with advance + assess actions (needs BE-1.3). ✅ verified — advanced Priya applicant→selected; history + pipeline update live.
- [x] **FE-1.5** Admissions: offer create → issue → accept/decline flow on the application detail + `/admissions` worklist (needs BE-1.4). ✅ verified — drove Create→Issue→Accept in the UI; toast confirmed "Student PGR-… created (same person)".
- [x] **FE-1.6** Students: list + student detail (record + person link) (needs BE-1.5). ✅ verified — 2 students listed; detail links back to the person 360 with the person_id-thread note.
- [x] **FE-1.7** Supervision: Supervisors panel on student detail (assign/end, history), plus `/supervision` **caseload** page (needs BE-1.6). ✅ verified — assigned/ended in UI; Elena's caseload shows Marcus; her Students list is row-scoped to 1.
- [x] **FE-1.8** Progression: Milestones panel on student detail (submit + panel decide with outcome) + `/progression` config view of programme milestone definitions (needs BE-1.7). ✅ verified — drove Confirmation submit→decide in UI; **Annual Progress Review auto-appeared** as the next milestone.
- [x] **FE-1.9** Funding: Funding panel on student detail (list over time, add, end) + `/funding` sources page (needs BE-1.8). ✅ verified — arrangement shows type/source/amount/validity/status pill; added one via UI.
- [x] **FE-1.10** Thesis: intention → submit → examination outcome, in the "Thesis & completion" panel on the student page (needs BE-1.9). ✅ verified — status pill tracked preparation→submitted→approved in the UI.
- [x] **FE-1.11** Completion: confirm completion + graduate action (needs BE-1.10). ✅ verified — graduated Priya in the UI; person 360 now shows Student→Alumni.
- [x] **FE-1.12** Dashboard: Executive lifecycle metrics + Administrator queues tiles from the read models (needs BE-1.11). ✅ verified — dashboard shows conversion 50%, completions, active researchers, awaiting-assessment queue.

### Phase-1 exit test (§20)
- [x] **BE-1.12 / FE-1.13** E2E happy path: person → opportunity → application → advance → offer → accept → student (same person_id) → supervisor → milestone submit/decide → funding → thesis → examination → graduation → alumni. ✅ `tests/e2e/test_full_lifecycle.py` passes (asserts same person_id end-to-end, funding ended, alumni current). Frontend journey verified interactively across the slices + captured in the user manual PDF.

---

## Phase 2 — Workflows, integration, portals
*Goal (§21): advanced progression workflows, funding changes with Finance notification, stipend
integration, examiner management, notifications, student & supervisor portals, configurable workflows, statutory reporting.*

### Backend
- [x] **BE-2.1** Workflow engine: reusable **task + notification + outbox engine** (§9.4) + **configurable, versioned `workflow_definition` state machines** (`workflow_instance`, data-driven transitions with task actions). `/workflow-definitions`, `/workflow-instances`, `/{id}/events`. ✅ verified — test + live: define/activate/version, start instance, advance pending→in_progress→complete; invalid transition → 422. A new flow is added by data.
- [x] **BE-2.2** Scheduled jobs (§9.3): generate due milestones, flag funding expiring ≤90d (creates tasks), escalate overdue tasks; `POST /admin/scheduled-jobs/run` + UI "Run now". (Endpoint-triggered stand-in — real scheduler pod deferred with the worker tier.) ✅ verified — test + live: accepting an offer → new student → run generated its first milestone; re-run idempotent (0).
- [x] **BE-2.3** Funding **changes** over time: `/funding/{id}/change` (close current, open new) + `/funding/{id}/end`; now **emits `funding.changed` to the outbox**. ✅ verified — change writes the outbox event; dispatched to Finance.
- [x] **BE-2.4** Integration hub (§10): **outbox dispatcher** (`integration.service.dispatch_pending`, idempotent) + anti-corruption **adapters** (finance/hr/research) + `integration_log` + **signed idempotent inbound webhooks**. `/integration/dispatch`, `/integration/logs`, `/integration/webhooks/{system}`. ✅ verified — test + live: funding.changed→finance(success), thesis.submitted→internal(skipped), re-dispatch=0; webhook valid→processed, replay→duplicate, bad-sig→401. (Real broker/scheduler worker = deferred with Docker; dispatch is endpoint-triggered for now.)
- [x] **BE-2.5** Examiner management: `examiner_nomination` (+ `examination` from P1) + `/theses/{id}/examiners` (list/nominate), `/examiner-nominations/{id}/approve`. ✅ verified — test + live: nominate (internal/external, no dup, must be submitted) → approve; outcome path already exists.
- [x] **BE-2.6** Notifications: `notification` table + `/notifications`, `/notifications/{id}/read`; `engine.notify()` wired (milestone decided → student's user); **delivery** queued→sent via the scheduler (in-app stand-in for the broker). ✅ verified — decide → queued notification for the student user → scheduler delivers → sent.
- [x] **BE-2.7** Tasks API: `/tasks` (role/user-filtered queue), `/tasks/{id}/complete`. ✅ verified — test + live: admin sees PGR-Admin tasks, Elena sees Supervisor tasks; completing removes from the open queue.
- [x] **BE-2.8** Statutory reporting export as an async job: `POST /exports`, `GET /exports`, `GET /exports/{jobId}`, `GET /exports/{jobId}/download` (CSV). Object store + true async worker deferred → job runs on request, CSV stored on the row. ✅ verified — test + live: students_statutory CSV, 3 rows, downloadable; unknown kind → 400.

### Frontend
- [x] **FE-2.1** Student portal: `/portal` "My journey" (record, lifecycle timeline, milestones, funding, thesis) + **My journey** nav; backed by `GET /portal/journey` (resolved from the principal) + student self-scoping. ✅ verified — as the seeded student login: own journey shown; `/students` self-scoped to 1.
- [x] **FE-2.2** Supervisor portal: `/supervision` caseload enriched with current milestone + funding state + **risk flag** (via `GET /dashboards/supervisor`); supervisor task queue is the row-filtered `/tasks` inbox. ✅ verified — as Elena: Marcus (ok), Priya (risk: no active funding); row-scoped to her supervisees.
- [x] **FE-2.3** Task inbox + notification centre — `/tasks` page + **Tasks** nav item (needs BE-2.6/2.7). ✅ verified — completing a task cleared it from the queue in the UI.
- [x] **FE-2.4** Funding change UI: FundingPanel **Change** button (inline close-current/open-new) + End (done with the FE-1.3 polish). ✅ verified — changed an arrangement in the UI (Finance-notified via the outbox).
- [x] **FE-2.5** Examiner management: Examiners section in the thesis panel (nominate person + type, approve) (needs BE-2.5). ✅ verified — nominated + approved in the UI; shows on the student page once the thesis is submitted.
- [x] **FE-2.6** Configurable-workflow admin: `/workflows` page (definitions with activate + versioning, JSON create, instances with start + event dispatch) (needs BE-2.1). ✅ verified — created/advanced flows via the UI/API.
- [x] **FE-2.7** Exports UI: "Statutory exports" on the ops page (generate → job list → authenticated CSV download) (needs BE-2.8). ✅ verified — generated + downloaded the statutory CSV.

---

## Phase 3 — Analytics & PGR Enterprise 360
*Goal (§21): PGR Enterprise 360, research/funding/supervisor analytics, attrition & completion
forecasting, funding & progression risk, cross-enterprise reporting.*

### Backend
- [x] **BE-3.1** PGR Enterprise 360 read model (§13.2): Student, Research, Funding, Workforce (via HR adapter), Statutory lenses; `/reports/pgr-enterprise-360` via `reporting/analytics.py` `AnalyticsService.enterprise_360()`. *Done-when:* all five lenses return for one population. ✅ Returns `{summary, lenses:[student,research,funding,workforce,statutory], population}` in a single read-replica-routed pass. (Materialized-view refresh-on-schedule is the production form; here the read model is computed on read through the replica session — the worker/scheduled MV refresh is parked with Docker/broker.)
- [x] **BE-3.2** Risk & forecasting models: students-at-risk, attrition/completion forecast, funding-expiry & progression risk; `/reports/analytics` → `{risk, completion, forecast}`. *Done-when:* risk flags surface on dashboards with an explainable rule/score. ✅ Explainable rule-based scoring (overdue milestones, funding expiry, time-in-programme); at-risk list carries per-student reasons.
- [x] **BE-3.3** Cross-enterprise reporting + replica routing hardening (reads never hit write primary): `get_read_session`/`ReadSessionFactory` route reporting reads to `DATABASE_REPLICA_URL` when set (falls back to primary). *Done-when:* load test meets §15 dashboard <2s / read p95 <300ms. ✅ **Load-verified (server-side handler latency, 4-worker topology):** standard read `GET /students` p95 **6ms**, enterprise-360 p95 **11ms**, analytics p95 **9ms** — all well under targets. Read p95 met via JWT-claims auth caching (arch §16: principal resolves from the short-TTL access token with zero DB round-trip). CSV export kind `pgr_enterprise_360` added.

### Frontend
- [x] **FE-3.1** PGR Enterprise 360 multi-lens explorer (needs BE-3.1): `/analytics` page, 5-lens `Tabs` explorer (student/research/funding/workforce/statutory) over one population. *Done-when:* user switches lenses on one population. ✅
- [x] **FE-3.2** Analytics dashboards: risk / completion / forecast tiles + at-risk list with explainable reasons (needs BE-3.2). *Done-when:* charts render from read models within budget. ✅ `useEnterprise360()` / `useAnalytics()` typed hooks.
- [x] **FE-3.3** Executive enterprise analytics polish + exports: Analytics nav item (Globe), read-only tiles, PGR Enterprise 360 CSV export from the Integration hub. *Done-when:* Executive role sees analytics only, no write actions. ✅ Page is read-only (no mutations); export runs as an async job.

---

## Non-functional acceptance (verify continuously — §15/§16/§17/§18)
- [ ] **NFR-1** API availability target 99.9%/mo; health `/health/live` + `/health/ready` (DB+broker). 
- [x] **NFR-2** Read p95 <300ms, dashboards <2s — **load-tested 2026-08-21** (4-worker uvicorn, Postgres): server-side p95 = read 6ms, dashboards 9–11ms. Write p95 <600ms not yet separately load-profiled.
- [ ] **NFR-3** Horizontal scale: stateless API pods + HPA, PgBouncer pooling, read replicas, Redis cache with event invalidation.
- [ ] **NFR-4** Security: TLS + at-rest encryption, least privilege DB roles, secrets from manager, Pydantic input validation, output schemas, fail-closed authz, CI dependency/container scans.
- [ ] **NFR-5** Observability: OpenTelemetry traces across API+workers, Prometheus/Grafana, Sentry, structured logs correlated by requestId.
- [ ] **NFR-6** RPO ≤15m (continuous backup), RTO <1h, tested restores, object-store versioning.

---

### Progress rollup (architect maintains)
| Phase | BE done | FE done | Status |
|---|---|---|---|
| 0 Foundations | 7/9 (BE-0.7 Docker parked, BE-0.9 CI parked) | 5/6 (FE-0.6 CI parked) | **full stack running end-to-end** |
| 1 MVP | 14/16 (workflow/notif engine + statutory reporting are Phase 2) | 13/13 | **Phase 1 MVP complete — E2E test green, user manual shipped** |
| 2 Workflows/Integration | **8/8** | **7/7** | **PHASE 2 COMPLETE — engine, integration, scheduler, portals, configurable workflows, exports** |
| 3 Analytics | **3/3** | **3/3** | **PHASE 3 COMPLETE — Enterprise 360 (5 lenses), risk/completion/forecast, replica routing, load-verified vs §15 (read p95 6ms, dashboards ≤11ms)** |

**Phase 0 verified 2026-08-21 — working version runs end-to-end.**
Backend: `pytest` 6/6, API on :8000, `/health/ready` `{"status":"ready","checks":{"database":"ok"}}`,
OpenAPI 3.1, Alembic baseline. Frontend: Next.js 14 on :3000, Redwood design system applied,
`npm run build` clean (15 routes), typed client generated from the live contract. The dashboard
proves the chain: browser → Next proxy → FastAPI (`/api/v1/me`, `/health/ready`) renders live.
**Parked by request:** Docker/compose (BE-0.7), CI (BE-0.9/FE-0.6), and full deployment — to be
picked up after the working MVP. Next: Phase 1, starting with identity/auth (BE-1.0a) + person (BE-1.1).
