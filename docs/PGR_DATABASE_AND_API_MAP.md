# PGR Platform — Database & API Map

**Generated from the running application** (SQLAlchemy metadata + FastAPI route table), not by hand — 2026-08-24.

---

## 1. The data stores — there are exactly two

| Store | Technology | Holds |
|---|---|---|
| **`pgr` database** | **One PostgreSQL 16+ database** (async via `asyncpg`) | Everything relational: all 66 tables below — records, workflow state, audit trail, settings, ML models (pickled artifacts are table rows), predictions |
| **`STORAGE_ROOT` volume** | Plain filesystem directory | Uploaded document *files* only (their metadata rows live in the `document` table) |

There is **no** second database, no SQLite in production (dev/test convenience only), no Redis, no object store, no search engine. One Postgres backup + one volume backup = the entire state.

---

## 2. All 66 tables, by domain

CRUD philosophy that shapes this schema: the platform is **history-preserving**. Most "changes" close one row (`valid_to`) and open another; hard DELETE exists in only a handful of deliberate places (see §4). That is why an auditor can reconstruct any student's journey.

| Domain | Tables (columns) |
|---|---|
| **Identity & access** (7) | `users` (10) · `role` (5) · `permission` (5) · `role_permission` (2) · `user_role` (2) · `refresh_token` (6) · `password_reset_token` (6) |
| **Person** (4) | `person` (11) · `person_contact` (9) · `person_relationship` (8) — concurrent identities (student *and* employee) · `person_merge_record` (8) |
| **Recruitment** (7) | `research_opportunity` (17) · `application` (13) · `application_assessment` (9) · `candidate_stage_history` (9) · `reference_request` (13) · `interview` (9) · `interview_panellist` (6) |
| **Admissions** (2) | `offer` (9) · `offer_condition` (9) |
| **Student record** (6) | `student` (13) · `programme` (6) · `department` (5) · `research_area` (6) · `research_project` (11) · `student_lifecycle_event` (18) — suspensions/extensions/mode changes |
| **Supervision** (2) | `supervisor_relationship` (11) · `supervision_meeting` (14) |
| **Progression** (5) | `milestone_definition` (11) · `milestone` (7) · `progression_review` (15) · `review_panel_member` (7) · `progression_appeal` (11) |
| **Funding** (4) | `funding_source` (5) · `funding_arrangement` (17) · `stipend_payment` (13) · `fee_waiver` (13) |
| **Thesis & examination** (4) | `thesis` (9) · `examiner_nomination` (11) · `examination` (10) · `thesis_correction` (9) |
| **Completion** (2) | `completion` (8) · `award` (13) — classification/certificate |
| **Research context** (2) | `research_award` (15) — grant references · `research_demand` (12) |
| **Workflow & notifications** (7) | `workflow_definition` (10) · `workflow_instance` (8) · `task` (15) · `notification` (8) · `notification_preference` (9) · `outbox_event` (11) — transactional outbox · `email_bounce` (8) |
| **Integration** (1) | `integration_log` (10) — inbound/outbound message log |
| **Documents** (1) | `document` (13) — metadata; bytes on the volume |
| **Exports & statutory** (3) | `export_job` (9) · `report_profile` (12) · `report_field_mapping` (11) |
| **Audit** (1) | `audit_log` (11) — append-only |
| **Settings** (1) | `institution_setting` (6) — only overridden values; defaults live in code |
| **Assistant** (1) | `assistant_write_intent` (11) — propose→confirm writes |
| **Pattern Lab** (6) | `ml_dataset` (14) — frozen training matrices · `ml_finding` (11) · `ml_model` (7) · `ml_model_version` (18) — incl. pickled artifact + governance log · `ml_training_run` (10) · `ml_prediction` (11) — append-only |

---

## 3. All 217 API routes, by domain

Conventions: **GET = Read** · **POST = Create or a named domain action** (transition/approve/submit — the platform prefers explicit verbs over generic updates) · **PATCH/PUT = Update** · **DELETE = hard delete (rare, §4)**. All routes live under `/api/v1` and require a JWT except `auth/*`, `public/*`, webhooks (HMAC-signed) and `/health/*`.

### Platform (6)
| Method | Route | CRUD |
|---|---|---|
| GET | `/health/live`, `/health/ready` | Read (unauthenticated probes) |
| GET | `/api/v1/openapi.json`, `/api/v1/docs`, `/redoc` | Read (API docs) |
| GET | `/me` | Read — current principal, roles, permissions |

### Auth (6)
| Method | Route | CRUD |
|---|---|---|
| POST | `/auth/login` · `/auth/refresh` · `/auth/logout` · `/auth/logout-all` | session create/rotate/revoke |
| POST | `/auth/password-reset/request` · `/auth/password-reset/confirm` | reset flow (also the invite flow) |

### Persons (15) → `person*` tables
List/create/get/update person · relationships open/close/list · timeline · contacts CRUD (incl. **DELETE**) · **merge** (FK-rewriting) · GDPR **export** (subject access) · GDPR **erase** (pseudonymise).

### Recruitment (23) → `research_opportunity`, `application`, `interview*`, `reference_request`
Opportunities CRUD + transition · applications create/list/get, advance stage, assess · pipeline counts · references request/list + **public token submission** (`POST /public/references/{token}`) · interviews schedule/panellists/outcome · visa-check PATCH.

### Admissions / offers (8) → `offer`, `offer_condition`
Offer create/get, issue, accept (creates the student, same person), decline · conditions add/list/satisfy/waive.

### Students & lifecycle (11) → `student`, `student_lifecycle_event`, `programme`
Students list/get/update (row-scoped) · project · journey summary · lifecycle events request/list, **approve** / **reject** (approver-separated) · return-from-suspension · programmes list.

### Supervision (9) → `supervisor_relationship`, `supervision_meeting`
Assign/list/end supervisors · meetings record/list/confirm · compliance check · capacity · caseload.

### Progression (12) → `milestone*`, `progression_review`, `review_panel_member`, `progression_appeal`
Milestone definitions per programme (list/add) · student milestones · submit/decide · review detail · panel add/list · conditions sign-off · appeals submit/list/decide.

### Funding (16) → `funding_arrangement`, `stipend_payment`, `fee_waiver`, `funding_source`
Sources list · student funding create/list · payments list/summary/schedule/approve/paid/status · fee waivers create/list/approve · funding change/end (close-and-open, never edit-in-place) · **funding lineage** (student→project→award→funder→stipend integrity chain).

### Thesis & examination (11) → `thesis`, `examiner_nomination`, `examination`, `thesis_correction`
Intention → submit → examiners nominate/approve → viva → outcome → corrections submit/approve.

### Completion & classification (8) → `completion`, `award`
Completion get/confirm · graduation · classification propose → confirm (approver-separated) → publish (renders certificate) · certificate download.

### Dashboards, reporting & portal (8)
Supervisor / executive / administrator dashboards · Enterprise 360 · funding-integrity report · risk analytics · student portal journey — all **Read**.

### Tasks, notifications & workflow (14) → `task`, `notification*`, `workflow_*`
My tasks · complete · SLA report/sweep/target · notifications list/read/unread-count · preferences get/**PUT** · email bounce webhook · workflow definitions create/activate/list · instances start/event/list.

### Integration (6) → `integration_log`, `outbox_event`
Outbox dispatch · logs · **reconciliation** · dead-letter replay (single + bulk) · signed inbound webhook per system.

### Documents (4) → `document` + volume
List / upload / download / **DELETE**.

### Exports & statutory (17) → `export_job`, `report_profile`, `report_field_mapping`
Export jobs start/list/status/download · statutory profiles CRUD-ish: create/list/get/clone/validate/generate/compile · field mappings add/**PATCH**/**DELETE** (both refused once signed off) · sign-off/unsign.

### Research context (10) → `research_award`, `research_demand`
Awards list/create/update (externally mastered; read-only when synced) · demand raise/list/transition · position lineage · **supervisor-suggestions** (explainable matching) · relationship **graph** · research-areas lookup.

### Settings & administration (14) → `institution_setting`, `users`, `role`, reference tables
Institution settings list/**PUT**/**DELETE**(=reset) · reference lists (LOVs): kinds/value-sets/list/add/**PATCH**/**DELETE** (refused while in use) · admin users list/create(invite)/**PATCH** · roles list · send-reset · scheduled-jobs run.

### Assistant (6) → `assistant_write_intent`
Query (read-only) · capabilities · write intents propose/execute/cancel (two-step confirmation).

### Audit (1) → `audit_log`
Filterable trail — **Read** (append happens via middleware, not an endpoint).

### Pattern Lab (18) → the six `ml_*` tables
Overview · targets · datasets build/list/get/discover/findings · train · models list · version transition (governance) · model card · lineage · score · predictions (cohort + per-student) · monitoring · retrain · ml-availability.

---

## 4. Hard DELETE exists in exactly 5 places — everything else preserves history

| Route | Why deletion is acceptable here |
|---|---|
| `DELETE /persons/{id}/contacts/{cid}` | a wrong phone number is not history |
| `DELETE /documents/{doc_id}` | uploads can be mistakes; the audit log records the act |
| `DELETE /report-profiles/{id}/fields/{mid}` | draft mapping config; refused once signed off |
| `DELETE /reference/{kind}/{row_id}` | LOV values; **refused while any row references them** |
| `DELETE /settings/institution/{key}` | not data loss — resets to the shipped default |

Domain records (students, applications, funding, milestones, theses…) are never deleted through the API — they transition, close, or are pseudonymised (GDPR erase). `person merge` is the one FK-rewriting operation, and it writes a `person_merge_record`.
