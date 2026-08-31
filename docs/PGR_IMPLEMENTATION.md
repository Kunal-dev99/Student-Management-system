# PGR Platform — Implementation Reference

**Postgraduate Research Student Lifecycle Management Platform**
Last updated: 2026-08-22 (end of Phase 6)

A single reference for what actually exists, how it works, and what is deliberately not built yet.
Companion documents: `PGR_DELIVERY_PLAN.md` (phase checklists), `PGR_PHASE4_PLAN.md`,
`PGR_PHASE6_GAP_CLOSURE_PLAN.md`, `PGR_ASSISTANT_DESIGN.md`, `PHASE6_MANUAL_VERIFICATION.md`,
`DECISIONS.md`.

---

## 1. At a glance

| | |
|---|---|
| **Backend** | FastAPI (Python 3.13 runtime, 3.12 target) · SQLAlchemy 2.0 async · Alembic |
| **Database** | PostgreSQL 18 (dev falls back to SQLite; tests run in-memory SQLite) |
| **Frontend** | Next.js 14 App Router · Tailwind 3 · shadcn/ui "Redwood Professional" · TanStack Query |
| **Scale** | **168 API endpoints** · **22 backend modules** · **52 tables** · **21 migrations** · **26 UI routes** |
| **Tests** | **224 passing** (35 files: unit, integration, e2e) |
| **Verified performance** | read p95 **6 ms**, dashboards p95 **9–43 ms**, cohort integrity **0.17 s / 266 students** (targets <300 ms / <2 s) |
| **Migration head** | `800191647194` |
| **Phases complete** | 0, 1, 2, 3, 4A, 4B (4 modules), 5.1, **6 (CIO gap closure)**, **7 (post-gap hardening)**, **8 (real settings)** |

**Run it:** `start-all.bat` (Postgres → backend → worker → frontend → browser).
Demo logins: `admin@example.com` / `admin123` · `elena.ford@example.com` / `super123`.

---

## 2. Architecture

### 2.1 Shape
A **modular monolith**. Each module owns its tables and exposes a router; cross-module work goes
through service classes sharing one transaction, never through another module's tables.

```
app/
├── main.py                 app factory, middleware, health endpoints
├── worker.py               background worker (APScheduler) — separate process
├── api/v1/routes.py        aggregates every module router under /api/v1
├── core/                   config, database, security, dependencies, errors, middleware,
│                           audit, storage, email, authorization, logging
├── db/                     base, session, seed, migrations/
├── scripts/                loadcheck, seed_phase6_demo, seed_hesa_profile
└── modules/                21 modules (§3)
```

### 2.2 Strict layering
`router → service → repository → models`

- **router** — HTTP, Pydantic schemas, permission guard, row-scope resolution
- **service** — business rules, workflow transitions, cross-module orchestration
- **repository** — queries only
- **models** — SQLAlchemy ORM, portable types only

### 2.3 Cross-cutting rules that hold everywhere
| Rule | Where enforced |
|---|---|
| Authorization fails closed | `core/dependencies.require_permission` |
| Row scoping (a supervisor sees only their supervisees) | `core/authorization.student_scope` → `scoped_ids()` |
| One transaction per command; the engine never commits, the caller does | `workflow/engine.py` |
| Reads may route to a replica | `db/session.get_read_session` |
| Every mutation is audited | `core/audit.AuditMiddleware` (pure ASGI) |
| camelCase over the wire, snake_case inside | Pydantic `alias_generator=to_camel` |
| Portable column types (SQLite ↔ Postgres) | decision **D-04** |

---

## 3. Backend modules (21)

| Module | Owns | Key capability |
|---|---|---|
| `identity` | users, role, permission, refresh_token, password_reset_token | JWT auth with embedded claims, RBAC, lockout, password reset |
| `person` | person, person_relationship | one person_id across every identity; **concurrent identities**; 360 timeline |
| `research` | research_award, research_demand | **the context before a student exists** — award references (externally mastered) and stated demand |
| `recruitment` | research_opportunity, application, candidate_stage_history, application_assessment | opportunity FSM, two entry routes, **position provenance + places** |
| `admissions` | offer | offer lifecycle; **accept creates a student atomically** and derives the expected end date |
| `student_record` | student, research_project, **student_lifecycle_event**, department, programme, research_area | the core record, journey summary, **suspensions/extensions with timeline recalculation** |
| `supervision` | supervisor_relationship, supervision_meeting | history-preserving assignment, **meeting log**, compliance, capacity |
| `progression` | milestone_definition, milestone, progression_review, review_panel_member, progression_appeal | configurable milestones, **panels**, conditions, appeals |
| `funding` | funding_source, funding_arrangement, stipend_payment, fee_waiver | funding over time, **payment schedules**, waivers, **lineage + integrity checks** |
| `thesis` | thesis, examiner_nomination, examination, thesis_correction | intention→submit→examiners→**viva**→outcome→**corrections** |
| `completion` | completion, award | **graduation orchestration** (award + funding close + alumni) |
| `workflow` | workflow_definition, workflow_instance, task, notification, outbox_event | task/notification engine, configurable definitions |
| `integration` | integration_log | outbox dispatcher, adapters, **signed webhooks that apply partner messages**, dead-letter |
| `reporting` | — (read models) | dashboards, **Enterprise 360**, risk analytics, **cohort funding integrity** |
| `exports` | export_job, **report_profile, report_field_mapping** | statutory exports **driven by configuration** |
| `scheduler` | — | periodic job definitions (driven by the worker) |
| `portal` | — | student self-service view |
| `documents` | document | file upload/download, row-scoped |
| `notifications` | notification_preference | delivery + per-user channel preferences |
| `audit` | audit_log | immutable trail of privileged actions |
| `assistant` | — | **"Ask PGR"** rules-first natural-language query layer |

---

## 4. The lifecycle (the marquee capability)

One `person_id` carries through every stage, and the chain now starts *before* the student exists:

```
ResearchAward ─▶ ResearchDemand ─▶ Position ─▶ applicant ─▶ offer ─▶ ACCEPT ─▶ student
                                                                        │
                    ┌───────────────────────────────────────────────────┘
                    ▼
   milestones ─▶ thesis ─▶ viva ─▶ corrections ─▶ GRADUATE ─▶ alumni
        ▲                                              │
        └── suspensions/extensions recalculate dates   └── ONE transaction:
                                                           award recorded, funding ended,
                                                           student → alumni (same person_id)
```

`person_service.transition_identity(end_type, open_type)` performs history-preserving changes.
Passing `end_type=None` opens an identity **without** closing another, so a PGR can be an employee
at the same time.

---

## 5. Phase-by-phase

### Phase 0 — Foundations ✅
App factory, layered scaffolding, config, structured logging with `requestId`, error envelope,
health endpoints, Alembic baseline, design system, typed API client generated from the live contract.

### Phase 1 — MVP core lifecycle ✅
Identity & auth, person 360, recruitment pipeline, admissions offers, student record, supervision +
**row-scoping**, configurable milestones, funding over time, thesis & examination, completion &
graduation, dashboards. Closed by an end-to-end test and a 14-page user manual PDF.

### Phase 2 — Workflows, integration, portals ✅
Workflow engine (task/notification/outbox in the *same transaction* as the state change),
integration hub (transactional outbox, anti-corruption adapters, HMAC-signed idempotent webhooks),
scheduler, student/supervisor portals, statutory CSV exports.

### Phase 3 — Analytics & Enterprise 360 ✅
PGR Enterprise 360 (five lenses), explainable rule-based risk scoring with reasons, completion
forecast, read-replica routing. Access tokens now embed roles/permissions so the principal resolves
with **zero DB round-trips** — standard reads ~4–6 ms.

### Phase 4A — Making the stand-ins real ✅
| Was fake | Now |
|---|---|
| Jobs ran only when someone clicked | **Real worker** (`app/worker.py`, APScheduler); `start-worker.bat` |
| Outbox had no failure handling | **Retry + backoff + dead-letter + replay**; real HTTP delivery when a partner URL is set |
| No file storage | **Documents** — `ObjectStore` + local backend, row-scoped, path-traversal guarded |
| Notifications were inert rows | **Email delivery** (console/SMTP) + per-user preferences + notification centre |
| Logout didn't log you out | **Real revocation** (hashed refresh store, rotation, logout-all), lockout, password reset |
| No record of who changed what | **Audit trail** — actor resolved from JWT with no DB hit |

### Phase 4B — Functional depth (4 priority modules) ✅
- **Thesis** — examiner affiliation + **conflict-of-interest** (blocks approval), viva scheduling,
  **corrections** (minor 28 d / major 182 d) with sign-off
- **Supervision** — **meeting log**, 90-day compliance on the caseload, capacity limits, weighting
- **Progression** — **review panels** (chair + independent assessor, who cannot be a supervisor),
  mandatory conditions + auto re-review, outcome letters, **appeals** that reopen a milestone
- **Funding** — cost centres, **stipend payment schedules** → approve → paid (emits to Finance),
  payment summary, **fee waivers**

### Phase 5.1 — "Ask PGR" assistant ✅ (read-only, admins only)
Natural-language query layer, **rules first** (§8).

### Phase 6 — CIO vision gap closure ✅ (all slices)
Driven by `PGR_Vision_Implementation_Gap_Analysis.docx`. **First finding: three of the six HIGH gaps
were already substantially built** — the analysis was assessed against documentation, not source.

| Slice | Gap | Delivered |
|---|---|---|
| **6.0** | GAP-02, GAP-04 | Proved both entry routes and employee continuity already worked; added the missing **route-integrity rules** |
| **6.5** | GAP-06 | **Suspensions/extensions** with approval gating, deterministic recalculation, worker auto-return |
| **6.1** | GAP-01 | **`research_award` + `research_demand`**, position provenance, places, demand→position lineage |
| **6.2** | GAP-02 | Entry route flows into Enterprise 360 and the statutory export |
| **6.3** | GAP-03 | **Full funding lineage + 8 integrity checks + cohort view** |
| **6.4** | GAP-04 | Concurrent identity endpoints, **deterministic HR matching** |
| **6.6** | GAP-05 | **Statutory returns as configuration**, versioned by academic year |
| **#12** | integration | Signed webhooks now **apply** partner messages, not just log them |

### Phase 7 — Post-gap hardening ✅
Five follow-ups from the updated gap analysis, none of which were gaps in capability — they were
gaps in *evidence*, *operability*, or *depth*.

| # | Item | Delivered |
|---|---|---|
| **7.1** | Realistic data | `scripts/generate_cohort.py` — builds a cohort **and reports the problems it planted**, so detection can be reconciled rather than eyeballed |
| **7.2** | Partner contract | `docs/PGR_INTEGRATION_CONTRACT.md` — envelope, HMAC signing, idempotency, event types, 8-test go-live plan |
| **7.3** | Non-functional criteria | `docs/PGR_NON_FUNCTIONAL_CRITERIA.md` — 55 criteria with verification method and honest status (**41 met, 4 partial, 10 not met**) |
| **7.4** | Reconciliation | `GET /integration/reconciliation` + panel: what is stuck outbound, what failed inbound, what is waiting on a person |
| **7.5** | Differentiating intelligence | **Explainable supervisor matching** + **relationship graph** (`app/modules/research/matching.py`) |

Two of these changed the product rather than describing it:

- Writing criterion **P7** forced a measurement nobody had taken: `cohort_integrity` ran at
  **1.2–1.9 s for 266 students** because it called `lineage()` per student (~6 queries each).
  Rewritten to bulk-load each table once: **0.09–0.17 s, ~14× faster**.
- Running the matcher against the **generated cohort** (7.1) rather than the test fixture exposed a
  scoring flaw the fixture hid: an area search scored `+45` for the area *and* `+16` for "topic
  overlap: machine, learning" — one signal counted twice, which flattened the ranking between
  supervisors doing genuinely different work. Area-derived words no longer feed topic overlap, and
  the corrected ranking now surfaces specialists **with the most capacity** first (previously it
  ranked a supervisor with 5 supervisees above one with 1).

### Phase 8 — Real settings ✅
The Settings page was previously personal notification preferences only. It is now the
institution's control panel, and — critically — **the settings are wired, not decorative**:
changing a value changes platform behaviour on the next request.

| Piece | What it does |
|---|---|
| **Institution settings** | `institution_setting` table + a typed registry (`app/modules/settings/registry.py`). Defaults *are* the shipped constants (referenced, never copied), overrides are validated (type + range), reset = delete the override. `GET/PUT/DELETE /settings/institution` |
| **Wired reads** | `supervision.max_supervisees` → capacity guard + matching; `supervision.expected_meeting_interval_days` → overdue flags; `lifecycle.part_time_factor` → mode-change recalculation; `funding.min_gap_days` → lineage + cohort integrity; `email.enabled` → institution kill-switch that beats personal prefs; `email.from_name`; `assistant.llm_enabled` |
| **List of values** | CRUD for departments, research areas, programmes, funding sources (`/reference/{kind}`). Delete is **refused while in use**, naming exactly what references the value ("still referenced by 2 students"); every row carries its live usage count. Duplicate codes refused case-insensitively |
| **Value sets** | Every domain enum exposed read-only via `/reference/value-sets` — vocabulary with code attached is visible but not editable, by design |
| **Users & roles** | `/admin/users` + `/admin/roles`: invite (no password ever passes through an admin — the invitation *is* the password-reset email), activate/deactivate, role assignment. **You cannot deactivate yourself or remove your own admin access** — the lockout the guard prevents would need database surgery to undo |

Proven by `test_settings.py` (11 tests), including the one that matters most:
`test_a_changed_setting_changes_real_behaviour` lowers the capacity limit to 2 and asserts the
supervision guard starts refusing a third supervisee, then resets and asserts it succeeds.

### Phase PL — Pattern Lab ✅ (all six phases, governed ML)
Driven by `PGR_Pattern_Lab_Implementation_Plan.docx`; full plan + build records in
`docs/PGR_PATTERN_LAB_PLAN.md`. The institutional learning layer at **Advanced → Pattern
Lab**: Discover → Validate → Train → Approve → Deploy → Monitor → Retrain.

| Phase | Delivered |
|---|---|
| **PL-1** Foundation | 4 governed targets (2 gated by **data-sufficiency gates** with the missing data named), feature registry with **structural leakage exclusion**, content-hashed reproducible datasets with full quality reports |
| **PL-2** Discovery | Dependency-free statistics (median-split comparisons, two-proportion z, **Bonferroni**, φ-confounders); every finding a business-language sentence with evidence and the causation caution |
| **PL-3** Training | Bounded candidate search (sklearn as optional `[ml]` extra — **no pandas, no AutoML framework, no MLflow**), stratified 5-fold CV, out-of-fold metrics, permutation importance; a run that cannot beat the baseline is reported **failed** |
| **PL-4** Governance | trained→candidate→review→approved→production; **approver separation**; mandatory rationale; append-only governance log; auto-generated **model cards with computed limitations**; baseline block; `ml.approve` held by Institution Administrators only |
| **PL-5** Predictions | Batch scoring from **production versions only** (266 students / 700 ms live); per-student **perturbation factors** ("Stipend amount +50.8 pp"); governed task-raising (off by default); student-detail panel beside the deterministic indicators |
| **PL-6** Monitoring | Performance-vs-actuals (rank-statistic AUC, calibration-in-the-wild), **PSI drift** vs the frozen training matrix, health verdicts that name their reasons, review dates, **manual-first retraining** (new versions enter at candidate; nothing auto-promotes) |

**The system caught its own first real issue**: monitoring flagged the live production model
`review` — matured AUC 0.48 vs trained 0.70 with major drift in four features — the
training-serving skew between point-in-time training features and scored-today features.
That the monitor surfaced it, named it, and recommended review *without acting* is the
guardrail architecture working end to end.

New permissions `ml.read` / `ml.analyse` / `ml.train` / `ml.approve`; 4 migrations
(`ddba4187dd3c` → `44faaad53ffb`); 7 tables; ~24 endpoints; 25 Pattern Lab tests across
four files.

**Supervisor matching is deliberately not ML.** The gap analysis suggested sentence-transformers;
that adds a very large dependency to rank a few dozen academics against a bounded vocabulary, and —
decisively — it makes the score unexplainable. Supervisor allocation is contested, so *"why was I
not suggested?"* must have an answer. Every point is attributed to a named factor
(`research area` +45, `topic overlap` ≤25, `capacity` ≤20, `track record` ≤10) with a human-readable
detail, and `score == sum(reasons.points)` is asserted in the tests. A supervisor at capacity is
**scored down, never hidden** — hiding them would make the tool look wrong to anyone who knows the
department.

---

## 6. Security model

### 6.1 Authentication
- Local password (pbkdf2_sha256) → **access JWT (15 min) + refresh JWT (14 days)**
- Access token **embeds** email, personId, roles, permissions → no DB query per request
- Refresh tokens stored by `jti` and **rotated**; logout and logout-all genuinely revoke
- **Lockout** after 5 failures for 15 minutes; **password reset** via hashed single-use token
- ⚠️ Consequence: a permission added to a role reaches a live session only after the token refreshes
  (≤15 min) or the user signs in again

### 6.2 Authorization
| Role | Student visibility |
|---|---|
| Institution Administrator | all (`*`) |
| PGR Administrator | all |
| Supervisor | only current supervisees |
| Student | only themselves |
| Executive | reporting only |

Out-of-scope reads return **404, not 403** (arch §12.3), so record existence isn't leaked.
Notable separate permissions: `student.lifecycle.approve` (approving is what moves dates),
`audit.read`, `assistant.use`, `document.read/write`.

### 6.3 Audit
Every successful mutating request writes an `audit_log` row (actor, action, entity, status,
`requestId`). Visible at `/audit` and as a History section on each student.

---

## 7. Background processing

`python -m app.worker` (or `start-worker.bat`) runs on independent intervals:

| Job | Default | Does |
|---|---|---|
| scheduled jobs | 60 s | **auto-return expired suspensions**, generate due milestones, flag funding expiring, escalate overdue tasks |
| outbox dispatch | 20 s | deliver domain events with retry/backoff → dead-letter |
| notifications | 30 s | mark in-app delivered, send email per preference |

**Paused students are not chased**: suspended/on-leave students are excluded from funding-expiry
flagging, milestone generation and overdue escalation.

**Outbox reliability** — events are written in the same transaction as the state change
(at-least-once); failures back off exponentially and dead-letter after `OUTBOX_MAX_ATTEMPTS`,
visible in the Integration hub and replayable.

**Inbound partner messages** — signed webhooks (`X-Signature` = HMAC-SHA256 of the raw body, plus a
stable `sourceId` for idempotency) now *apply* recognised messages:

| System | eventType | Effect |
|---|---|---|
| `research` | `award.created` / `award.updated` | Upserts the award, marks it externally mastered |
| `hr` | `employee.appointed` / `employee.updated` | Links an `employee` identity; ambiguous → a task |
| anything else | — | Recorded, reported as `logged_only` |

A malformed payload is recorded as `failed` with the error — visible for triage, never dropped.

---

## 8. "Ask PGR" assistant

**Rules first; the LLM is optional and off by default.** The domain is narrow (≈8 filters, bounded
vocabulary, entity names already in the database), so a grammar covers most real questions at zero
cost, ~1 ms, deterministically, and with **no student data leaving the server**.

### 8.1 Two-stage understanding, no model in either
1. **Strict parser** (`intents.py`) — contraction expansion, phrase matching, duration extraction,
   negation detection, and **proximity binding** so two windows in one sentence bind correctly
2. **Concept graph** (`semantics.py`) — stem (incl. doubled-consonant rule) → fuzzy-correct typos via
   stdlib `difflib` → activate concepts → **spread one damped hop** (MEETING→SUPERVISION,
   EXPIRY→FUNDING, ATTRITION→RISK) → score rules conjunctively

### 8.2 Response paths
`rules` (matched, badge *instant*) · `guess` (inferred; answered with a hedge + readback +
alternatives) · `model` (opt-in) · `unmatched` (concrete suggestions, never a guess).
Every answer carries **`understood`** — a plain-English readback so users verify rather than trust.

### 8.3 Verified examples (zero API calls)
| Asked | Understood as |
|---|---|
| "no supervision meeting in 90 days **and** funding expiring in 6 months" | 90 d **and** 180 d, bound separately |
| "which students has **nobody seen** in 6 months" | no supervision meeting in 180 days *(the word "supervision" never appears)* |
| "whose **money is running out**" | funding expiring |
| "who is **falling through the cracks**" | students flagged at risk |
| "no **supervsion** meeting in 90 days" (typo) | corrected and answered |
| "what is the wifi password" | *unmatched* — flexibility didn't become "matches everything" |

### 8.4 Safety
No permissions of its own (executes as the signed-in user, row scope applied); never invents an ID;
**read-only** in this release with a three-tier policy declared in `constants.BLOCKED_ACTIONS`; tool
results labelled untrusted so record content is never followed as an instruction.

---

## 9. Frontend

**24 routes.** Notable surfaces:

| Route | Contains |
|---|---|
| `/dashboard` | executive metrics, administrator queues, connectivity |
| `/analytics` | risk/completion/forecast tiles, at-risk list with reasons, 5-lens Enterprise 360 |
| `/research` | **research demand** (FSM transitions) and **awards** (externally-mastered = read-only) |
| `/recruitment` | opportunities with **places filled/available** and a **provenance lineage** dialog |
| `/students/[id]` | record, **lifecycle changes**, supervisors, supervision meetings, milestones + panels/appeals, funding + payments/waivers, **funding lineage**, thesis + viva/corrections, documents, history |
| `/funding-integrity` | **every student whose funding chain has a problem**, errors first |
| `/statutory` | **report profiles**, field mappings, validation report, generate, clone to a new year |
| `/supervision` | caseload with last-meeting and overdue columns |
| `/persons/[id]` | **identities** (concurrent, effective-dated) and full timeline |
| `/integration` | dispatcher, scheduled jobs, exports, integration log, dead letters |
| `/audit` | filterable audit trail |
| `/forgot-password`, `/reset-password` | unauthenticated reset flow |

**Global:** floating **"✨ Ask PGR"** launcher (also **Cmd/Ctrl+K** and the header search),
notification bell with unread count.

**Client conventions:** access token in memory only, refresh token in `localStorage` with silent
refresh and one 401-retry; list envelope `{data, page}`; error envelope
`{error:{code,message,requestId}}`.

---

## 10. Testing

**199 tests across 32 files.**

| Kind | Covers |
|---|---|
| **Unit** (49, 0.06 s, no DB/network) | intent parser (durations, negation, two-window binding, navigation); concept graph (stemming, activation spread, typos, veto rules, unmatched-stays-unmatched) |
| **Integration** | every module: auth/lockout/revocation/reset, row scoping, recruitment pipeline **both routes**, progression + panels + appeals, funding + payments + waivers + **lineage/integrity**, thesis + CoI + viva + corrections, supervision meetings, **lifecycle events**, **research demand/awards**, **person↔employee**, **inbound partner messages**, **statutory profiles**, workflow, integration retry→dead-letter→replay, documents, audit, notifications, assistant (permission gate + scope) |
| **E2E** | the full applicant→alumni journey in one test |

Tests run on in-memory SQLite via `create_all`, with `get_session`/`get_read_session` overridden —
nothing touches the live database.

**Load check:** `python scripts/loadcheck.py <api-log>` measures **server-side** handler latency from
the structured access log (client wall-clock on a single dev box is polluted by co-locating the load
generator with the workers and Postgres).

---

## 11. Notable engineering decisions & incidents

| Decision / incident | Outcome |
|---|---|
| **D-01** Next.js instead of Vite | keeps the design bundle verbatim |
| **D-04** portable column types | one codebase on SQLite (dev/test) and Postgres (prod) |
| JWT-embedded claims | removed a DB query per request; read p95 → 6 ms |
| **BaseHTTPMiddleware deadlock** (found + fixed) | two stacked Starlette `BaseHTTPMiddleware` layers hung the API at 20 concurrent requests. Both rewritten as **pure ASGI**. Would have been a production outage. |
| **Radix dialog left mounted after navigation** | exit animations are interrupted by a route change so `animationend` never fires; the palette now unmounts on close. *Any dialog whose links navigate needs this.* |
| Assistant **rules-first**, LLM opt-in | zero cost, deterministic, and no personal data leaves the server — a GDPR advantage |
| Panel requirement as **configuration** | avoided breaking every existing progression decision |
| Recalculate **from a baseline**, not incrementally | idempotent; a rejected or corrected event leaves no residue |
| Only **undecided** milestones shift | a decided milestone is a historical fact |
| Statutory mapping is a **dotted path, not an expression language** | executable configuration is a security *and* an operations problem |
| HR matching is **deterministic only** | a wrong merge silently joins two people's records and is very hard to undo — ambiguity becomes a task |
| **No pandas/intervaltree** for funding integrity | for the handful of arrangements a student holds, a sorted list plus date arithmetic is clearer, faster and easier to audit |
| Alembic + enums | Alembic does **not** autogenerate enum creation for `add_column`, nor new enum values — create with `checkfirst=True` + `create_type=False`, and `ALTER TYPE … ADD VALUE IF NOT EXISTS` |
| New NOT NULL columns | always need `server_default` to backfill |
| SQLite drops tzinfo | `_aware()` coercion before Python-side datetime comparison |
| MissingGreenlet on fresh rows | never touch a relationship collection on a just-flushed row — query children via the repository |
| New model fields | must also be added to the **create schema**, or Pydantic silently drops them (this bit once) |

---

## 12. Environment & operations

**Local paths:** backend venv `backend/.venv` · psql `C:\Program Files\PostgreSQL\18\bin`
**Batch files:** `setup.bat`, `start-all.bat`, `start-backend.bat`, `start-worker.bat`,
`start-frontend.bat`, `start-postgres.bat`, `test.bat`, `stop.bat`

**Seed scripts** (from `backend/`, idempotent):
```bash
PYTHONPATH=. .venv/Scripts/python.exe scripts/seed_phase6_demo.py
```
```bash
PYTHONPATH=. .venv/Scripts/python.exe scripts/seed_hesa_profile.py
```

**Environment gotchas**
- The project lives in a **OneDrive** folder, which corrupts Next.js *dev* chunk cache → the frontend
  runs a **production build** (`npm run build` + `npm run start`)
- Orphaned uvicorn sockets can squat port 8000 — `Get-Process python | Stop-Process -Force`

**Key settings** (`backend/.env`, template in `.env.example`): `DATABASE_URL`,
`DATABASE_REPLICA_URL`, `STORAGE_BACKEND`/`STORAGE_ROOT`, `EMAIL_BACKEND`/SMTP, worker intervals,
`OUTBOX_MAX_ATTEMPTS`, `MAX_FAILED_LOGINS`/`LOCKOUT_MINUTES`, `ASSISTANT_LLM_ENABLED`,
`ANTHROPIC_API_KEY`, `APP_SECRET_KEY` (also signs inbound webhooks).

---

## 13. Deliberately not built yet

**Parked by decision**
- Docker / compose, CI pipeline, Kubernetes manifests, PgBouncer, real read replica
- OIDC / institutional SSO (local password hardening shipped instead)

**Built but not connected to anything live**
- **No partner system points at the webhook yet.** Research-award and HR-employee mappings are built,
  tested and verified with signed payloads — but nothing is sending.
- **Finance messages have no handler** — recorded as `logged_only`, they change nothing.
- Object storage is a local filesystem backend (S3/MinIO is a config swap — the interface exists).
- Enterprise 360 is computed on read through the replica session rather than as refreshed
  materialized views.

**Illustrative, not production-ready**
- The **HESA profile is a worked example** (12 fields chosen to prove the engine), not a compliant
  return. A specialist must confirm field names, coding frames and mandatory fields.

**Data caveat**
- Students created before Phase 6 have no research project, so their funding lineage shows warnings.
  Everyone admitted from now on is linked automatically. A backfill script has not been written.

**Not started**
- Track 4B remaining modules: Person contacts/GDPR/merge, Recruitment references & interviews,
  Admissions conditional offers/fee status/visa, Completion classification & certificates,
  Workflow SLA timers, Integration reconciliation UI, Reporting cohort/trend analysis, richer portals
- Track 4C: Redis caching + materialized views, OpenTelemetry/Prometheus/Sentry, rate limiting,
  backup/restore runbook
- Assistant 5.2+ (writes with confirm), 5.3 (saved queries), 5.4 (proactive briefings)
- **FE-6.2**: route badges/filters in the recruitment pipeline (route integrity is enforced
  server-side and the route already appears in reporting and exports)

**Open question:** the Tier-3 blocked-action list for assistant writes has one unspecified item the
user selected as "Something else" — needed before 5.2.

---

## 14. CIO vision alignment — evidence

Assessed against `PGR_Vision_Implementation_Gap_Analysis.docx`. All six HIGH gaps plus the AMBER
integration item are now closed in code.

| Requirement | Evidence | Status |
|---|---|---|
| **Two distinct entry routes** | `ApplicationRoute` enum + stored `route`; nullable opportunity FK; `proposal_document_ref` carries Route B's intent. Integrity enforced in `recruitment/service.create_application`. Route reaches Enterprise 360 + statutory export. | ✅ `test_vision_gaps.py` |
| **Person ↔ employee continuity** | `transition_identity(end_type=None, …)` opens an identity **without** closing another; effective dates + `source_system`; open/close endpoints. | ✅ `test_vision_gaps.py`, `test_person_employee.py` |
| **PGR exception lifecycle** | `student_lifecycle_event` with **approval required**; immutable `original_expected_end_date`; deterministic recalculation shifting **undecided milestones only**; overlap guards; worker auto-return; paused students not chased. | ✅ `test_lifecycle_events.py` |
| **Research demand → position** | `research_award` (externally mastered = read-only) + `research_demand` (award optional) + position provenance + `positions_filled` with over-fill refusal + `GET /opportunities/{id}/lineage` naming gaps. | ✅ `test_research_demand.py` |
| **Award ↔ funding lineage** | `GET /students/{id}/funding-lineage` (every hop, paid/committed roll-up) + 8 integrity checks each carrying the values that produced them + `GET /reports/funding-integrity` cohort view. Admission auto-links the project to the award. | ✅ `test_funding_lineage.py` |
| **Statutory as an evolving layer** | `report_profile` + `report_field_mapping` versioned by year; dotted-path engine with 8 pure transforms; unknown transform refused at configuration time; validation per student per field; clone-to-new-year. | ✅ `test_statutory_profiles.py` |
| **Research/Finance/HR integration** | Signed webhooks now **apply** partner messages (research award upsert, HR employee link); unrecognised → `logged_only`; malformed → `logged_with_error`; idempotent by `sourceId`. | ✅ `test_inbound_partner_messages.py` |

**Guardrails honoured:** the platform is not grants management (awards are *references* with no
budget lines or claims), not Finance/payroll (we schedule and record; Finance disburses), not HR (we
record the employee *relationship*, not employment terms), not an undergraduate SIS, and no LLM is
the source of truth for any academic or financial decision. **No second workflow engine** — the
existing workflow + worker + outbox architecture covers lifecycle automation.

Plan and manual checks: `PGR_PHASE6_GAP_CLOSURE_PLAN.md`, `PHASE6_MANUAL_VERIFICATION.md`.

### 14.1 Independent re-assessment (2026-08-22)

`PGR_Vision_Implementation_Gap_Analysis_UPDATED.docx` re-scored the platform against this document
and rated **all six HIGH gaps and the AMBER integration item CLOSED**, with **all 15 CIO vision
requirements GREEN**. Its verdict: *"the project should stop treating these areas as feature gaps."*

It reframes the remaining work as **validation, not gaps**:

| | Item | Where it already sits |
|---|---|---|
| **R1** | Institutional UAT on representative data | `PHASE6_MANUAL_VERIFICATION.md` §1–6 |
| **R2** | Confirm institutional policy rules | the "judgement calls" in that guide (90-day meeting expectation, part-time factor, approver separation, 7-day funding-gap threshold) |
| **R3** | Validate live Finance/Research/HR contracts | §5b + "no partner system points at the webhook yet" (§13) |
| **R4** | Validate statutory content with Registry/HESA owners | §5 — the profile is explicitly a worked example |
| **R5** | Research/supervisor semantic matching | an enhancement, never a gap |
| **R6** | Assistant write policy | the open Tier-3 question (§13) |

R1–R4 and R6 were already anticipated in the manual-verification guide, which is the intended
reading order for anyone picking this up.

**One new guardrail** from the re-assessment, added to the list in §14: *do not introduce a second
workflow engine* — the existing workflow + worker + outbox architecture already covers lifecycle
automation.
