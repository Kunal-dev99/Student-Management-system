# PGR Platform — Non-Functional Acceptance Criteria

Measurable criteria for security, audit, performance, resilience, data protection and operations,
each with **how to verify it** and **honest current status**.

Version 1.0 · 2026-08-22 · covers the platform as of Phase 6

**Status key:** ✅ met and verified · ⚠️ partially met · ❌ not met · ⛔ deliberately out of scope

> This document deliberately marks things ❌ where they are not done. A criteria document that only
> lists successes is a marketing sheet, not an acceptance test.

---

## 1. Security

| # | Criterion | Verify by | Status |
|---|---|---|---|
| S1 | Every API route requires authentication except health checks, login, refresh and password reset | Enumerate routes; assert each has a permission or is explicitly public | ✅ `require_permission` on all business routes |
| S2 | Authorization **fails closed** — an unknown or missing permission denies | Call any route without the permission | ✅ tested |
| S3 | A user can only see records within their row scope; out-of-scope reads return **404, not 403** | Supervisor requests another supervisor's student | ✅ `test_supervision_scoping.py` |
| S4 | Passwords are never stored or logged in recoverable form | Inspect `users.password_hash`; grep logs | ✅ pbkdf2_sha256 |
| S5 | Repeated failed logins lock the account | 5 bad logins, then a good one | ✅ `test_phase4a.py` |
| S6 | Logout genuinely revokes; a stolen refresh token stops working | Log out, then reuse the refresh token | ✅ tested |
| S7 | Inbound webhooks verify an HMAC signature over the raw body | Send a corrupted signature | ✅ returns 401, not recorded |
| S8 | Secrets come from the environment, never source control | `grep -r` for credentials; check `.env` is gitignored | ✅ |
| S9 | Uploaded files cannot escape the storage root | Attempt a `../` traversal key | ✅ guarded in `core/storage.py` |
| S10 | TLS in transit; encryption at rest | Deployment review | ❌ **not configured** — deployment is parked |
| S11 | Rate limiting on authentication and public endpoints | Load a login endpoint | ❌ **not implemented** |
| S12 | Dependency and container vulnerability scanning in CI | CI run | ❌ **CI is parked** |
| S13 | An LLM is never the source of truth for an academic or financial decision | Review assistant write policy | ✅ assistant is read-only; Tier-3 actions blocked by design |

**Gap summary:** S10–S12 are all deployment/CI concerns, parked by explicit decision. They must be
closed before production, and none is a code change to the application itself.

---

## 2. Audit & traceability

| # | Criterion | Verify by | Status |
|---|---|---|---|
| A1 | Every successful state-changing request writes an audit record | PATCH a student, check `/audit` | ✅ |
| A2 | The audit record identifies actor, action, entity, outcome and correlates to a request | Inspect a row for `actorEmail`, `entityType`, `statusCode`, `requestId` | ✅ |
| A3 | Auditing cannot be bypassed by a route author | It is middleware, not per-route code | ✅ `core/audit.py` |
| A4 | An audit failure never fails the user's request | Force an audit error | ✅ caught and logged |
| A5 | Audit records are append-only in the application | No update/delete endpoints exist for `audit_log` | ✅ (DB-level immutability not enforced — see below) |
| A6 | History is preserved rather than overwritten for identities, supervision, funding and progression | Change each, confirm prior rows survive with end dates | ✅ by design throughout |
| A7 | Consequential decisions record **both** requester and approver | Request and approve a suspension | ✅ `student_lifecycle_event` |
| A8 | Every logged action can be traced to its request in the access log | Match `requestId` across audit and log | ✅ |

**Known limitation (A5):** the application never edits audit rows, but a database superuser could.
True immutability needs DB-level grants or append-only storage — a deployment concern.

---

## 3. Performance

| # | Criterion | Target | Verify by | Status |
|---|---|---|---|---|
| P1 | Standard read p95 | < 300 ms | `scripts/loadcheck.py` | ✅ **6 ms** |
| P2 | Dashboard/report p95 | < 2 s | same | ✅ **9–43 ms** |
| P3 | Write p95 | < 600 ms | not yet profiled separately | ⚠️ **not measured** |
| P4 | Authentication adds no database round-trip per request | Inspect `get_current_principal` | ✅ claims embedded in the JWT |
| P5 | The API does not serialise under concurrency | 20 concurrent readers complete | ✅ after the middleware fix (§6) |
| P6 | Reporting reads can be routed off the write primary | Set `DATABASE_REPLICA_URL` | ⚠️ implemented; **no replica provisioned** |
| P7 | Cohort-wide reports remain usable at institutional scale | `generate_cohort.py --students 300`, then time funding-integrity | ✅ **0.09–0.17 s for 266 students** (was 1.2–1.9 s before bulk-loading) |

**Measurement caveat:** latency must be measured **server-side** (from the structured access log).
On a single developer machine, a load generator competing with the API workers and Postgres inflates
client-side timings by an order of magnitude. `scripts/loadcheck.py` does this correctly.

**P7 — measured, then fixed.** The first implementation called `lineage()` per student (~6 queries
each), giving **1.2–1.9 s for 266 students** — inside the 2 s target, but O(n) and heading for a
breach at institutional scale. `cohort_integrity` now reads each table **once** and runs the pure
`_check` in memory: **0.09–0.17 s for the same cohort, a ~14× improvement**, and cost is now a
handful of queries regardless of cohort size. It also now reports accurate totals for the whole
cohort rather than stopping at the display limit.

This is exactly what `scripts/generate_cohort.py` exists for — the problem was invisible on the
10-student demo dataset.

---

## 4. Resilience & data integrity

| # | Criterion | Verify by | Status |
|---|---|---|---|
| R1 | A domain event is never lost if its transaction commits | Outbox is written in the same transaction | ✅ arch §9.4 |
| R2 | Failed outbound deliveries retry with backoff, then dead-letter visibly | Point an adapter at a failing URL | ✅ tested end to end |
| R3 | Dead-lettered events can be replayed after the partner recovers | Replay from the Integration hub | ✅ |
| R4 | A failed inbound message is recorded, never silently dropped | Send a malformed payload | ✅ `logged_with_error` |
| R5 | Repeated partner messages are idempotent | Re-send the same `sourceId` | ✅ |
| R6 | One failing scheduled job does not stop the others | Force an exception in a job | ✅ each job is individually guarded |
| R7 | Multi-step operations are atomic | Accept an offer; confirm student + identity + application + task all commit or none | ✅ single transaction |
| R8 | Date recalculation is idempotent and reversible | Approve, reject and re-approve lifecycle events | ✅ recomputed from an immutable baseline |
| R9 | The system degrades honestly when data is missing | Recalculate for a student with no expected end date | ✅ reports the fact rather than inventing a date |
| R10 | Database migrations are reversible | `alembic downgrade` | ⚠️ downgrades are generated but **untested** |

---

## 5. Data protection & retention

| # | Criterion | Verify by | Status |
|---|---|---|---|
| D1 | Personal data is not sent to third parties by default | Assistant runs on-premise rules; LLM off by default | ✅ `ASSISTANT_LLM_ENABLED=false` |
| D2 | Enabling the LLM path is a conscious, documented act | Requires both a flag and a key | ✅ |
| D3 | Personal data never appears in URLs or query strings | Review endpoints | ✅ ids only |
| D4 | Access to personal data is role-scoped and audited | S3 + A1 | ✅ |
| D5 | A documented retention schedule exists | Policy review | ❌ **not written** — needs institutional input |
| D6 | Subject access: all data for one person can be exported | Ad-hoc query only today | ❌ **no endpoint** |
| D7 | Erasure/anonymisation on request | — | ❌ **not implemented** (Track 4B.1) |
| D8 | Backups exist, are tested, and meet RPO/RTO | Restore drill | ❌ **not configured** — deployment parked |

**This is the weakest section.** D5–D8 are genuine gaps for a system holding personal data, and
D5/D7 need institutional policy decisions before they can be built correctly.

---

## 6. Operability

| # | Criterion | Verify by | Status |
|---|---|---|---|
| O1 | Liveness and readiness endpoints exist and reflect dependencies | `GET /health/live`, `/health/ready` | ✅ readiness checks the database |
| O2 | Logs are structured and correlated by request id | Inspect the access log | ✅ JSON with `requestId` |
| O3 | Background work runs in a separate process from the API | `start-worker.bat` | ✅ |
| O4 | Scheduled work can be triggered manually for support | `POST /admin/scheduled-jobs/run` | ✅ |
| O5 | Configuration is environment-driven with a documented template | `.env.example` | ✅ |
| O6 | A new environment can be stood up from documentation alone | Follow `PGR_IMPLEMENTATION.md` §12 | ⚠️ works on Windows dev; **no container or runbook** |
| O7 | Distributed tracing and metrics | OpenTelemetry / Prometheus | ❌ **not implemented** (Track 4C.1) |
| O8 | Error reporting to an aggregator | Sentry DSN configured | ❌ config slot exists; **not wired** |
| O9 | Documented rollback for a failed release | Runbook | ❌ **not written** |

---

## 7. Acceptance summary

| Area | Met | Partial | Not met |
|---|---|---|---|
| Security | 10 | 0 | 3 |
| Audit | 8 | 0 | 0 |
| Performance | 5 | 2 | 0 |
| Resilience | 9 | 1 | 0 |
| Data protection | 4 | 0 | 4 |
| Operability | 5 | 1 | 3 |
| **Total** | **41** | **4** | **10** |

**The 11 unmet criteria cluster into three groups**, which is the useful way to read this:

1. **Deployment & operations** (S10, S11, S12, D8, O7, O8, O9) — all blocked by the parked
   Docker/CI/K8s decision. None requires application changes; they need an infrastructure phase.
2. **Data protection policy** (D5, D6, D7) — needs institutional decisions on retention and erasure
   before it can be implemented correctly. D6 (subject access export) is the cheapest to build and
   the most likely to be asked for.
3. **Measurement** (P3) — write latency has not been profiled separately. P7 (cohort-scale
   reporting) **has now been measured and optimised**; use the same approach for P3.

**Recommendation:** treat group 3 as immediate (it is measurement, not building), group 2 as needing
a policy conversation, and group 1 as the trigger to unpark deployment.
