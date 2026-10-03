# PGR Platform — independent security test pack

For the external tester and for us. It covers what to test, how the environment is set up,
the threat model, the controls already in place with their evidence, and the known issues
not worth spending test time on.

---

## 1. The system in one paragraph

A research and postgraduate student records platform for universities, offered as a **shared
(pooled) multi-tenant service**: every institution's data lives in one PostgreSQL 18 database,
and each row carries a `tenant_id`.
- **Frontend:** Next.js 14.
- **API:** FastAPI on Python, under `/api/v1`, with about 185 read endpoints and 80 routers.
- **Database:** PostgreSQL with row-level security (RLS) on every tenant table.
- **Institution:** chosen by subdomain (`<institution>.<base-domain>`) and bound to the
  sign-in token.
- **Reporting tools:** they connect straight to the database through per-institution
  read-only views and logins.
- **Other features:** an assistant and AI features summarise student data; partners (finance,
  HR, email provider) send signed webhooks.

## 2. Objectives, in priority order

1. **Cross-institution access.** Can a user, a token, a file, a webhook or a reporting login of
   institution A read, change or detect anything belonging to institution B? This is the
   top priority.
2. **Privilege escalation inside one institution.**
   - A student reaching other students.
   - A supervisor reaching students outside their caseload.
   - An executive reaching individual records.
   - An administrator granting the vendor-only `dev` role.
3. **Authentication and session handling:**
   - sign-in, lockout and rate limiting;
   - refresh-token rotation and logout;
   - password reset;
   - token replay on another institution's subdomain.
4. **Injection and input handling:** filters and search, file upload (type, size, name), header
   injection through download filenames, and JSON bodies.
5. **The reporting database logins.** Can they escape their institution's views? Ways to try:
   core tables, other schemas, changing `app.current_tenant`, `app.bypass_tenant`, functions,
   `pg_catalog` tricks.
6. **The AI and assistant features.** Can prompt injection pull data the user can't see, or
   get the assistant to act for another user?

## 3. Scope

**In scope (staging only):**
- the web app and API at `https://<a>.<staging-domain>` and `https://<b>.<staging-domain>`;
- the bare host;
- the reporting logins for both institutions, direct to Postgres on the agreed port;
- the webhook endpoints:
  - `POST /api/v1/integration/webhooks/{system}`
  - `POST /api/v1/notifications/webhooks/email/bounce`
  - `POST /api/v1/public/references/{token}`

**Out of scope:**
- production, and any real institution's data (staging holds synthetic data only);
- denial of service and load testing (the API rate limiter is in scope, but flooding is not);
- social engineering and physical access;
- the hosting provider's infrastructure;
- third-party services: model providers, email relay, the partner systems themselves;
- the developer console UI (`dev` role).

## 4. Rules of engagement

- **Window:** _to agree_. **Contacts:** _technical lead, and an out-of-hours number_.
- **Stop and call us** if you reach real personal data, production, or another customer's
  environment, or if staging becomes unstable.
- **Rate:** keep automated scanning modest. The login and reset endpoints rate-limit at
  10 requests per 60 s per IP and path, and accounts lock for 15 minutes after repeated
  failures. Ask us to raise the limits for a specific test.
- **Data handling:** credentials are handed over by a secure channel and destroyed at the end.
  Don't keep extracted data beyond what the report needs.
- **Report:** CVSS v3.1 severity per finding, with reproduction steps and the affected
  institution or role. Flag any cross-institution finding immediately; don't wait for the
  final report.

## 5. Test environment and what you receive

Two institutions, **A** and **B**, each with synthetic students, supervisors, programmes,
documents and returns.

| You receive | Per institution | Notes |
|---|---|---|
| Web/API logins | Institution Administrator, PGR Administrator, Supervisor (with a caseload), Executive, Student (linked to one student record) | `pt-<institution>-<role>@pentest.invalid`, random passwords |
| Reporting login | `<institution>_reporting` (standard views) and `<institution>_reporting_full` (with personal data) | Postgres host, port and database name |
| Webhook secret | One per institution | Sign the raw body with HMAC-SHA256 and send it as `X-Signature` |
| Background | `docs/architecture/Tenant_Isolation_Approach.pdf` and `deploy/MULTI_TENANCY.md` | How isolation is meant to work |

Useful facts:
- Access tokens last 15 minutes and refresh tokens 14 days.
- Uploads are limited to 50 MB.
- Error responses have the form `{error: {code, message, requestId, details}}`; quote the
  `requestId` in findings.

## 6. Threat model

**What we protect:**
- student and staff personal data (names, contact details, dates of birth, nationality, notes);
- academic records and statutory (HESA) returns;
- uploaded documents;
- credentials and tokens;
- each institution's configuration and integration settings.

**Actors:**
- a user of institution A trying to reach institution B;
- a lower-privileged user inside one institution;
- an unauthenticated internet user;
- a partner system holding one institution's webhook secret;
- a reporting-tool user holding one institution's database login;
- a compromised AI prompt (untrusted text in records).

**Trust boundaries:** browser → API; API → database; partner → webhook endpoints; reporting
tool → database; API → external model provider; API → email relay.

| Threat | Boundary | Control | Evidence |
|---|---|---|---|
| Read another institution's rows by id (IDOR) | API → DB | RLS on every tenant table, fail-closed: no institution set means no rows | `tests/integration/test_tenant_guard.py`, `test_tenant_leak_api.py` (every GET endpoint, both directions) |
| Replay a token on another institution's subdomain | Browser → API | Host institution reconciled with the token's institution; a mismatch gets 403 | `app/core/dependencies.py` (`_reconcile_tenant`) |
| A request that forgets to set the institution | API → DB | Fail-closed policy, `tenant_id NOT NULL`, guard test on every table | migration `t1_tenant_hardening`; `app/db/tenant_guard.py` |
| Institution carried over on a pooled connection | API → DB | Setting is transaction-local and published per transaction | `test_tenant_guard.py::test_tenant_does_not_carry_over_on_a_reused_connection` |
| A new table shipped without protection | Build | Model-level and database-level guard tests fail the build | `tests/unit/test_tenant_tables_declared.py` |
| A unique key that reveals or blocks another institution | API → DB | Business keys unique per institution | migration `t4_tenant_uniques`; guard test |
| A reporting login escaping its institution | Tool → DB | Views with a fixed institution filter and `security_barrier`, owned by a non-owner role (RLS applies), login pinned to its institution, no core-table privileges | `tests/integration/test_tenant_views.py` |
| Downloading another institution's file | Browser → API | Download loads an RLS-scoped row first; file key carries the institution and is checked again | `tests/unit/test_storage_tenant.py` |
| A forged or cross-institution webhook | Partner → API | HMAC with a per-institution secret; institution resolved before any query | `app/core/inbound.py`; `test_unsigned_bounce_is_refused` |
| Cache serving one institution's data to another | API | Data caches keyed by institution | T2 sweep (found and fixed one) |
| Privilege escalation inside an institution | API | Permission per endpoint; row scoping for supervisors and students; vendor role grantable only by its holders | `app/core/authorization.py`; `admin_router.py` |
| Brute-force sign-in | Browser → API | Rate limiting and lockout | `tests/unit/test_security_middleware.py` |
| Personal data in logs | API | Tenant-tagged JSON logs; no email bodies or query strings; generic stream errors | `app/core/logging.py`, `email.py` |
| Known default credentials | Deploy | Production seed has no demo accounts | `app/db/seed.py` |
| Prompt injection exfiltrating data | API → model | Prompts are built only from the caller's RLS-scoped session; assistant writes need the proposer's confirmation | `app/modules/assistant/` |

## 7. Known issues and accepted risks (no need to report these)

- **Model egress:** external AI models receive student data whenever a provider key is set.
  Only the composer has a per-institution switch. Staging uses the mock provider unless you
  ask otherwise. This is an accepted risk.
- **Global sign-in emails:** sign-in emails are unique across institutions, so "user already
  exists" can reveal that an address is registered somewhere. This is by design.
- **Schema names:** reporting logins can see other institutions' schema names (not contents)
  in `pg_catalog`.
- **No signed links:** download links are not signed or expiring. Every download is an
  authenticated API call (there are no public links yet).
- **No malware scanning:** uploads are not malware-scanned (`scan_status` is set to "clean").

## 8. Our checklist before the test

1. **Deploy and migrate:** deploy current `master` to staging with `APP_ENV=staging`, then run
   `alembic upgrade head`. This builds the reporting views.
2. **Superuser steps:** run `deploy/provision_app_role.sql` and
   `deploy/provision_reporting.sql` as a superuser.
3. **Configure the app:**
   - Set `APP_DATABASE_URL` so the API runs as the restricted `pgr_app` role.
   - Set `TENANT_BASE_DOMAIN`, and `TRUST_FORWARDED_HOST=true` if the API sits behind the
     Next.js proxy. See "Domains and subdomains" in `deploy/MULTI_TENANCY.md`.
   - Set `LLM_PROVIDER=mock` unless model testing is agreed.
   - Run uvicorn with `--no-access-log`.
4. **Load data:** load synthetic data for two institutions, A and B, each with at least one
   supervisor who has a caseload and one student.
5. **Create the logins and secrets:**
   ```bash
   python -m scripts.pentest_accounts create <a> <b> --out creds.txt
   python -m scripts.tenant_reporting create-login <a>
   python -m scripts.tenant_reporting create-login <a> --full
   python -m scripts.tenant_reporting create-login <b>
   python -m scripts.tenant_reporting create-login <b> --full
   python -m scripts.tenant_ops webhook-secret <a>
   python -m scripts.tenant_ops webhook-secret <b>
   ```
   Hand everything over by a secure channel, then delete `creds.txt`.
6. **Check isolation is green:** run `python scripts/run_tenant_leak_tests.py` against a copy of
   staging. It must be green.
7. **Back up** staging.

## 9. After the test

```bash
python -m scripts.pentest_accounts remove <a> <b>
python -m scripts.tenant_reporting drop-login <a>
python -m scripts.tenant_reporting drop-login <a> --full
python -m scripts.tenant_reporting drop-login <b>
python -m scripts.tenant_reporting drop-login <b> --full
```

Then:
- Rotate the webhook secrets by changing `APP_SECRET_KEY` on staging. That also signs everyone
  out.
- Triage the findings. Every cross-institution finding gets a leak test that reproduces it
  before it's fixed.
