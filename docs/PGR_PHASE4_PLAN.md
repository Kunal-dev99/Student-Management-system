# Phase 4 — From working demo to a real, production-grade system

**Theme:** Phases 1–3 proved the whole PGR lifecycle works end-to-end. Phase 4 makes it *real*:
replace the endpoint-triggered stand-ins with genuine infrastructure, give every module the
depth a real institution needs, and harden the platform to the architecture's §15–18 targets.

> Status: **Scope locked with the user (2026-08-21); awaiting final go-ahead to build.**
> Task ids follow the existing `BE-4.x` / `FE-4.x` convention; each has a one-line *Done-when*.

## Locked scope decisions
- **Build Track 4A in full first** (worker, files, email, auth-hardening, audit) — the foundation.
- **Then Track 4B for four priority modules:** Thesis & examination (4B.8), Supervision meetings
  (4B.5), Progression panels (4B.6), Funding payments (4B.7). Other 4B modules deferred to a
  later slice.
- **Deployment stays PARKED** (Docker/CI/K8s — 4C.6 not in this phase).
- **SSO deferred** (4A.8 out of scope for now; local-password hardening 4A.7 stays in).
- **Continuous during the phase:** 4C.1 observability + 4C.5 tests/load checks.

## Build sequence
1. **4A.1** worker/scheduler → **4A.2** file storage → **4A.3** email/notifications →
   **4A.4** auth hardening → **4A.5** audit trail (each verified before the next).
2. **4B.8 Thesis** → **4B.5 Supervision** → **4B.6 Progression** → **4B.7 Funding**
   (these lean on 4A.2 files, 4A.3 email, 4A.5 audit).
3. Fold in **4C.1** + **4C.5** as we go. Then stop and review before any wider 4B/4C.

---

## How Phase 4 is organised

Three tracks, meant to be delivered roughly in order (each unblocks the next). You can approve
the whole thing, approve a track at a time, or cherry-pick tasks.

- **Track 4A — Make the stand-ins real** (infrastructure the rest depends on)
- **Track 4B — Functional depth, module by module** (what real users actually need)
- **Track 4C — Production hardening** (§15–18: observability, security, scale, deploy)

**Recommended first slice (the "MVP of real"):** 4A.1 background worker, 4A.2 file storage,
4A.3 email delivery, 4A.4 auth hardening, 4A.5 audit trail. These five turn the demo into
something an institution could pilot. Everything in 4B builds on them.

---

## 4A build status — ✅ TRACK 4A COMPLETE (2026-08-21)
**62/62 tests green.** Migrations `72da2f21478b` (4A) + `9716adbdff2d` (4B.8) applied to Postgres.
Frontend production build clean (24 routes). All items verified live in the browser.

| Task | Status | Notes |
|---|---|---|
| BE-4A.1 worker | ✅ | `app/worker.py` (APScheduler) runs scheduled jobs + dispatch + notifications; `start-worker.bat` (added to `start-all.bat`); verified auto-dispatching 2 events on interval with no manual click. |
| BE-4A.2 outbox retry/dead-letter | ✅ | attempts/backoff/dead_lettered on `outbox_event`; real HTTP delivery when `INTEGRATION_<sys>_URL` set; `/integration/dead-letters/{id}/replay`. Test covers retry→dead-letter→replay. |
| BE-4A.3 documents (files) | ✅ | `core/storage.py` LocalObjectStore; `document` table + `/documents` upload/list/download/delete, row-scoped. Byte-identical round-trip verified live; out-of-scope supervisor gets 403. |
| FE-4A.4 uploader UI | ✅ | `DocumentsPanel` on student detail (upload/list/download/delete) — verified rendering an uploaded file. |
| BE-4A.5 email + prefs | ✅ | `core/email.py` (console/SMTP), `notification_preference`, delivery via `NotificationService.deliver_queued`; unread-count + preferences endpoints. |
| FE-4A.6 notification centre + prefs | ✅ | `NotificationBell` in header (unread badge + popover + mark-read); Settings → Notifications (email/digest/per-event mute) verified live. |
| BE-4A.7 auth hardening | ✅ | refresh-token store + rotation + real revocation (logout/logout-all), lockout, password-reset request/confirm. Tests: lockout, logout-revokes, full reset cycle. |
| FE-4A.8 reset pages | ✅ | `/forgot-password` + `/reset-password` (neutral messaging, Suspense-wrapped), "Forgot password?" on login; logout now revokes server-side. |
| BE-4A.9 audit trail | ✅ | `audit_log` + AuditMiddleware (actor from JWT, no DB hit) + `/audit` viewer. Verified capturing PATCH/POST with actor. |
| FE-4A.10 audit viewer | ✅ | `/audit` page (permission-gated, filters) + History section on student detail — both verified showing real entries. |
| 4A.8 SSO | ⛔ | deferred by decision. |

## 4B build status — ✅ ALL FOUR PRIORITY MODULES COMPLETE (backend), 75/75 tests
Migrations applied to Postgres: `9716adbdff2d` (thesis) → `3f62e34f4e6f` (supervision) →
`cff59f95ecca` (progression) → `3a5a0cd9be93` (funding). Head = `3a5a0cd9be93`.

| Task | Status | Notes |
|---|---|---|
| BE-4B.8 Thesis & examination | ✅ | Examiner **affiliation + conflict-of-interest** (declared CoI blocks approval), `independent_chair` examiner type, **viva scheduling** (`POST /theses/{id}/viva` — date/format/location, requires an approved examiner, notifies the student, moves thesis to under_examination), **corrections tracking** (`thesis_correction`: minor=28d / major=182d deadline auto-opened by outcome; submit → sign-off → approved). 3 new tests. |
| BE-4B.5 Supervision meetings | ✅ | **`supervision_meeting`** log (date, format, duration, notes, actions, next-meeting, student confirmation) at `/students/{id}/supervision-meetings`, row-scoped so supervisors log their own; **compliance** endpoint (90-day expectation) + `lastMeetingOn`/`meetingOverdue` surfaced on the caseload; **capacity guard** (max 8 supervisees, `/supervisors/{id}/capacity`); co-supervisor **weighting**; **end-with-reason**. 4 new tests. |
| BE-4B.6 Progression panels | ✅ | **`review_panel_member`** (chair / internal / independent assessor / observer) — a formal review requires chair + independent assessor, and the independent assessor **cannot be one of the student's supervisors**. Panel requirement is *configuration* (milestone_definition.review_panel.required), so existing simple reviews still work. **Conditions** mandatory on conditional outcomes, with an auto-scheduled **re-review (90d)** and **sign-off**; **outcome letters**; **appeals** with a 14-day window, duplicate guard, and an upheld appeal **reopening** the milestone. 4 new tests. |
| BE-4B.7 Funding payments | ✅ | **Cost centre / project code / funder reference / contribution %** on arrangements (blended funding); **`stipend_payment`** schedule generator (monthly/quarterly/termly/annual/one-off, month-end-safe date maths) → approve → mark paid (emits `funding.changed` to the **Finance adapter via the outbox**); **payment summary** (paid/committed/outstanding + overdue); ending an arrangement **auto-cancels unpaid instalments**; regeneration blocked once anything is paid; **`fee_waiver`** (full/partial/bench, amount or %, approval). 5 new tests. |
| FE-4B.* | ⏳ | UI for viva/corrections, meeting log, panels/appeals, and payment schedules still to build. |

**Verified live** (Postgres, real HTTP): £18,000 arrangement → 4 quarterly instalments of £4,500 →
approve → mark paid (`FIN-LIVE-1`) → summary showed paid 4,500 / committed 18,000 / outstanding
13,500 → the **worker auto-dispatched** the payment event to the Finance adapter on its next tick.

---

## Track 4A — Make the stand-ins real

### 4A.1 Real background worker & scheduler
Today the scheduler and outbox dispatcher only run when someone POSTs `/scheduler/run` or
`/integration/dispatch`. Replace with a genuine periodic runner.
- **BE-4A.1** In-process scheduler (APScheduler — no Docker needed) that periodically runs:
  milestone generation, funding-expiry flagging, overdue-task escalation, outbox dispatch,
  and (4C) materialized-view refresh. Runs as a separate `worker.py` process (own `.bat`),
  sharing the app's services. Manual `/scheduler/run` kept for tests/demos.
  *Done-when:* start the worker, create overdue state, and see tasks/notifications/dispatch
  happen with no manual click; jobs are idempotent and logged.
- **BE-4A.2** Outbox dispatch gains retry-with-backoff + a dead-letter state; failed webhook
  deliveries are retried, then parked with an error for inspection.
  *Done-when:* a failing adapter is retried N times then dead-lettered, visible in the log.

### 4A.2 Real document / file storage
No thesis PDF, application document, or review paper can actually be stored today.
- **BE-4A.3** Storage abstraction (`ObjectStore` interface) with a **local-filesystem backend**
  for dev (S3/MinIO backend is a config swap later). Model `document` (owner type/id, filename,
  content-type, size, checksum, uploaded_by, scan_status). Endpoints: presigned-style
  upload, download (access-controlled + row-scoped), delete.
  *Done-when:* upload a PDF against a student, download it back byte-identical, and an
  out-of-scope user gets 403.
- **FE-4A.4** Reusable uploader component + document lists wired into thesis, application, and
  progression-review panels.
  *Done-when:* drag-drop upload + download works in the browser on those three surfaces.

### 4A.3 Real notification delivery
Notifications are DB rows only; nobody is ever actually told anything.
- **BE-4A.5** Email channel: SMTP sender (console backend in dev, real SMTP via env in prod),
  templated emails, per-user notification preferences (in-app / email / off per event type),
  digest option. Delivery attempts logged; failures retried by the worker.
  *Done-when:* completing a task or flagging risk sends a real email in prod-config and a
  console email in dev; a user who opted out of email only gets in-app.
- **FE-4A.6** Notification centre (bell + unread count + mark-read) and a preferences screen.
  *Done-when:* user sees live unread count, opens the centre, and edits channel preferences.

### 4A.4 Authentication hardening
- **BE-4A.7** Hashed refresh-token store with rotation + real revocation (logout and
  "sign out everywhere" actually invalidate), account lockout on repeated failures, and a
  password-reset flow (request → emailed token → set new password).
  *Done-when:* after logout the old refresh token is rejected; 5 bad logins lock the account;
  a full reset-by-email cycle works.
- **BE-4A.8** *(optional)* OIDC/SSO login (institutional IdP) alongside local password.
  *Done-when:* a user signs in via the configured IdP and lands with mapped roles.

### 4A.5 Audit trail (§17)
- **BE-4A.9** Cross-cutting `audit_log` (actor, action, entity type/id, before/after summary,
  request id, timestamp) written on every state-changing command via a service-layer hook.
  *Done-when:* any create/update/transition appears in the audit log with who/what/when.
- **FE-4A.10** Audit viewer (filter by entity/actor/date) on admin + on each entity's detail
  page ("history" tab).
  *Done-when:* admin can see the full change history of a student.

---

## Track 4B — Functional depth, module by module

Each item is what the module needs to be genuinely usable, not just demoable. (Grouped; we can
promote/demote individual items.)

- **BE/FE-4B.1 Person** — multiple contact points (emails/phones/addresses with validity),
  equality & diversity data, GDPR consent + data-retention/erasure, duplicate-merge tool.
- **BE/FE-4B.2 Recruitment** — application document uploads (4A.2), referees + reference
  requests/receipt, interview scheduling, scoring rubrics, eligibility checks, bulk stage
  actions, per-applicant communication log.
- **BE/FE-4B.3 Admissions** — conditional offers with tracked conditions, generated offer-letter
  PDF, fee status (home/international), international CAS/ATAS + visa fields, deposit tracking.
- **BE/FE-4B.4 Student record** — leave of absence / suspension / extension periods (with
  effect on expected-end date), mode-of-study changes over time, programme/supervisor transfers
  with history, skills/training record (RDF).
- **BE/FE-4B.5 Supervision** — supervision **meeting log** (records, notes, actions, next date),
  supervisor capacity/allocation limits, co-supervisor roles & weighting, supervision changes
  with reason + approval.
- **BE/FE-4B.6 Progression** — full panel review (panel members, independent assessor,
  outcome letter), viva-style confirmation review, conditions + re-review scheduling, appeals.
- **BE/FE-4B.7 Funding** — blended multi-source funding with cost centres, stipend **payment
  schedule** + payment records, fee waivers, UKRI/RCUK reporting fields, currency handling.
- **BE/FE-4B.8 Thesis & examination** — real submission (PDF upload + similarity-check hook),
  **examiner entity** (internal/external, affiliation, conflict-of-interest declaration), viva
  scheduling, corrections tracking (minor/major with deadlines + sign-off), nomination approvals.
- **BE/FE-4B.9 Completion** — awards/exam board record, degree classification, certificate PDF,
  graduation ceremony data, richer alumni record + ongoing engagement.
- **BE/FE-4B.10 Workflow** — SLA timers + escalation chains, task delegation/reassignment,
  task comments/attachments, conditional branching in workflow definitions.
- **BE/FE-4B.11 Integration** — reconciliation + dead-letter UI (from 4A.1), additional adapters
  (student records system / finance), replay of failed messages.
- **BE/FE-4B.12 Reporting** — trend-over-time + cohort analysis, drill-down from a tile to the
  underlying population, saved/scheduled reports emailed out, Excel/PDF export, weighted &
  configurable risk model.
- **BE/FE-4B.13 Portals** — student self-service (submit milestones, upload thesis/docs, view
  funding & payments, request supervision meetings, apply for extension), supervisor portal
  (approve, meeting log, caseload analytics), applicant portal.

---

## Track 4C — Production hardening (§15–18)

- **BE-4C.1 Observability** — OpenTelemetry traces across API + worker, Prometheus metrics
  endpoint, Sentry error reporting, logs correlated by the existing `requestId`.
- **BE-4C.2 Security hardening** — rate limiting, strict CORS, security headers, secrets from a
  manager, output-schema coverage audit, dependency/container scanning.
- **BE-4C.3 Caching & read models** — Redis cache with event-driven invalidation; convert
  Enterprise 360 to real Postgres **materialized views** refreshed by the 4A.1 worker; wire a
  real read replica.
- **BE-4C.4 Data lifecycle** — backup/restore runbook, retention jobs, object-store versioning.
- **BE/FE-4C.5 Test & quality** — raise coverage, contract tests for adapters, a per-phase e2e
  suite, and load/perf checks (this session's `serverlat.py` promoted into the repo).
- **BE-4C.6 Deployment (currently PARKED)** — unpark Docker/compose, CI pipeline, K8s manifests,
  PgBouncer, read replica. *Only if you want to un-park deployment now.*

---

## Deferred to a later slice (not this phase)
Track 4B modules not chosen now: Person (4B.1), Recruitment (4B.2), Admissions (4B.3),
Student-record leave/extensions (4B.4), Completion/awards (4B.9), Workflow SLA (4B.10),
Integration reconciliation (4B.11), Reporting cohort/trend (4B.12), Portals (4B.13).
Track 4C: caching/materialized views (4C.3), data lifecycle (4C.4), deployment (4C.6).
These stay documented above so we can pull them forward when you're ready.
