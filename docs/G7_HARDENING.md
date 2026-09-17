# G7 — Enterprise hardening tracker

G7 was the last item in the ICR feedback plan, described as "non-functional; scope separately".
The plan named it a bag of things — auth, rate limiting, secrets, backup/restore, HESA-grade
retention, accessibility, load, pen test — without a concrete backlog. This document is the
concrete backlog. It stays with the code so what's *actually* shipped is visible next to what
still isn't.

Priority key: **P1** = ship before ICR go-live · **P2** = fits a v1.1 · **P3** = ongoing operational

## Shipped

| Item | What | Where | Test coverage | Commit |
|---|---|---|---|---|
| Security response headers | HSTS (https-only), X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy on every response | `app/core/security_middleware.py::SecurityHeadersMiddleware` | `tests/unit/test_security_middleware.py` (4) | this tranche |
| Auth brute-force rate limit | 10 req / 60s sliding window per-IP on `/auth/login` + `/auth/password-reset/request`; HTTP 429 with Retry-After; honours `x-forwarded-for` behind a proxy; per-IP bucket so one attacker can't lock out others | `app/core/security_middleware.py::AuthRateLimitMiddleware` | `tests/unit/test_security_middleware.py` (6) | this tranche |
| Row-scoping leak on `/research/graph` | Awards / opportunities / funders / supervisor labels now filtered by principal scope; unscoped principals still see catalog | `app/modules/research/matching.py::relationship_graph` | `tests/integration/test_supervisor_matching.py` | `b6d148e` |
| Row-scoping matrix pinned | Every role's student scope covered by unit tests | `tests/unit/test_authorization_scope.py` (6) | `e560caa` |
| Structured logging + request-id | One JSON line per request; `x-request-id` echoed on every response for incident correlation | `app/core/middleware.py::RequestContextMiddleware`, `app/core/logging.py` | integration | (pre-G7, listed for completeness) |
| Rule-suppression audit trail | Every rule suppression on a statutory profile carries reason + user + timestamp, visible on the sign-off card | `app/modules/exports/statutory.py::suppress_rule` | `tests/unit/test_fix_assistant.py` + integration | `8eb74bf` |

## Ranked backlog

### P1 — before go-live

- **Refresh-token rotation & absolute expiry.** Confirm the refresh flow rotates the token on every use, has an absolute max lifetime (e.g. 30 days) irrespective of refresh, and revokes all sessions on password change. Some of this already exists in `IdentityService` — an audit + test is what's owed.
- **CSRF posture.** JWT-bearer APIs called from a same-origin SPA over `Authorization: Bearer` don't need cookie-flavoured CSRF, but any state-changing endpoint used from an unauthenticated form (only reset-request today) should be checked. Document the model in `docs/PGR_IMPLEMENTATION.md` and add a same-origin check where it matters.
- **CSP for the frontend.** A Content-Security-Policy on the served HTML: `default-src 'self'`, allowlist for the fonts/CDN we actually use, `object-src 'none'`, `frame-ancestors 'none'` (belt-and-braces with `X-Frame-Options`). Adds visibility into third-party script drift.
- **HESA-grade data retention.** A policy — how long PII survives after graduation / withdrawal, how deletion is cascaded across audit + backups, what's exportable on subject-access request. Needs a decision from Registry before implementation; scope is a settings-driven scheduler that soft-then-hard-deletes with an audit stamp.
- **Backup / restore runbook.** Postgres 18 has `pg_basebackup` + WAL archiving; document the exact commands, a target RPO/RTO, and a quarterly restore drill. Ship as `docs/OPERATIONS_BACKUP.md`.

### P2 — v1.1

- **Password policy hardening.** Minimum length, denylist of the top-N common passwords (`have-i-been-pwned` k-anonymity API or an on-disk list), configurable rotation, optional TOTP as a second factor. Enforcement in `IdentityService.set_password`.
- **Session listing + remote revoke.** A "Sessions" panel on the user profile showing active refresh tokens with device / IP / last-used, and a per-session revoke. `/auth/logout-all` already exists as the sledgehammer; this is the surgical version.
- **Accessibility baseline.** Add `@axe-core/react` in dev, an `eslint-plugin-jsx-a11y` ruleset, and a first pass against WCAG 2.2 AA on the primary flows (login, students list + detail, /statutory, /programmes).
- **Rate limit on other classes of endpoint.** File-upload endpoints, `/report-advisories/ingest*` (heavier than a login attempt), any composer endpoints that call an LLM. Same middleware, different `protected_paths`.
- **Structured audit query API.** Audit entries are written today (see `app/core/audit.py`); expose them as a filterable list for sign-off attestation ("show me every mapping edit on this profile before it was signed off").

### P3 — ongoing operational

- **Distributed rate-limit storage.** The current limiter is in-process — fine for the single-node ICR install. When we go multi-node, swap the `_hits` dict for Redis with the same interface (a 30-line change).
- **Load test at real ICR cohort size.** Locust or k6 hitting `/students` + `/statutory generate` + `/graph` with 5k students. Establishes a p95 baseline and catches N+1s before Registry does. Non-blocking for launch, sanity for month 1.
- **Pen test.** External engagement once the app is behind ICR's real reverse proxy + auth boundary; the middleware here is table stakes but not a substitute.
- **SSO / OIDC.** Config already exists (`app/core/config.py`), the flow isn't wired. Once ICR names a provider we plug it in and remove the local password path for their tenant.
- **Secrets management.** Env-file today; document how to move each secret (DB password, JWT signing key, Groq/OpenAI keys, SMTP password, HESA institution code) to a managed store per environment.
- **Dependency + vuln scanning in CI.** `pip-audit` on the backend, `npm audit` on the frontend, `dependabot` for both, run on every PR.

## Verification snippets

Live-check the security headers with just `curl -I`:

```bash
curl -s -I http://<host>/health/ready | grep -iE "^(x-|referrer|permissions|strict|content-type|x-request)"
```

Live-check the rate limit trips at attempt 11:

```bash
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "attempt $i: %{http_code}\n" \
    -X POST http://<host>/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"nobody@t.com","password":"x"}'
done
```

## Configuration

The rate-limit knobs are on `app.core.config.Settings`:

- `AUTH_RATE_LIMIT_ENABLED` (bool, default `true`) — turn the whole limiter off; used in tests
- `AUTH_RATE_LIMIT_PER_WINDOW` (int, default `10`)
- `AUTH_RATE_LIMIT_WINDOW_SECS` (float, default `60`)

Set via env-var or `.env` next to any other `Settings` field.
