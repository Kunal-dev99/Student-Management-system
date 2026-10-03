# Multi-tenancy — how isolation works and how to harden it

The platform is multi-tenant: every institution's rows are tagged with a `tenant_id` and
**Postgres Row-Level Security (RLS)** — not application code — enforces that a request only
ever sees its own tenant's data. This is defence in depth: even a bug in a query cannot
leak across tenants.

## The moving parts

- **`tenant_id` on every tenant-owned table** (95 tables). New rows are stamped
  automatically from the request's tenant (`TenantMixin` default). Global tables
  (`tenant`, `permission`, `role`, the auth-token tables, national HESA spec tables) are
  intentionally not scoped.
- **The acting tenant per request** comes from two sources, reconciled in
  `get_current_principal`:
  1. the **subdomain** (`icr.<base-domain>` → tenant `icr`; set `TENANT_BASE_DOMAIN`), and
  2. the **JWT** `tenantId` claim.
  The URL wins; a token for tenant A used on tenant B's subdomain is refused (403). It is
  published to Postgres as `SET LOCAL app.current_tenant = <uuid>` and to the ORM for
  insert-stamping.
- **RLS policy** matches `tenant_id` against `current_setting('app.current_tenant')`
  (guarded by `NULLIF(..., '')` so a pooled connection's empty GUC never breaks the uuid
  cast).

## Fail-closed policies (T1)

Since migration `t1_tenant_hardening`, **every** table with a `tenant_id` (all of them, including
`composer_run` and `users`) has:

| Policy | Applies to | Rule |
|---|---|---|
| `tenant_isolation` | every role (PUBLIC) | `tenant_id = current tenant` — no tenant set means **no rows** |
| `tenant_isolation_system` | the owner role only | `app.bypass_tenant = 'on'` — an explicit, opt-in bypass |

and `tenant_id` is `NOT NULL`. Policies are OR'ed per role, so:

| | Owner role (`pgr`) | Any other role (`pgr_app`, reporting roles) |
|---|---|---|
| Tenant set | that tenant only | that tenant only |
| No tenant set | **no rows** | **no rows** |
| Bypass flag on | everything (tooling only) | ignored — still no rows |

The application never sets the bypass. Every ORM session publishes the acting tenant (and the
bypass flag, normally off) at the start of each transaction (`core.database._publish_tenant`), so
sessions a request opens itself — streaming AI features, audit and telemetry writes — are scoped
too. Code that genuinely works across tenants opts in narrowly with `system_scope()`:

- migrations (`migrations/env.py`), `app/db/seed*.py`, `app/db/export_*.py`, `scripts/*` seeds;
- the dev login lookup on a bare host (no subdomain → no tenant to scope to);
- the worker does **not** bypass: it loops over active tenants and runs each job as that tenant
  (`tenant_scope`), so new rows are stamped with the right tenant;
- `scripts/tenant_ops.py` acts as exactly the tenant it operates on.

## Using the restricted app role (recommended for production)

The owner role is already fail-closed for the API (it never sets the bypass). Running the API as a
**non-owner** role adds a second guarantee: it *cannot* bypass, even if code tried.

1. As a **superuser**, run `deploy/provision_app_role.sql` (edit the role name, password and
   owner at the top first). It only creates `pgr_app` and grants table privileges — the T1
   policies already make it fail-closed.
2. Point the **API** at it and restart: `APP_DATABASE_URL=postgresql+asyncpg://pgr_app:<password>@dbhost:5432/pgr`.
   Leave `DATABASE_URL` as the owner — migrations, seeds and the worker keep using it.
3. Sign in through a tenant subdomain (e.g. `icr.localhost` in dev): `pgr_app` cannot use the
   bare-host login bypass.

## Leak tests (T2)

What "protected" means is written down once, in `app/db/tenant_guard.py`: a tenant table has RLS
enabled and forced, `tenant_id NOT NULL`, and exactly the two policies above. Every other table
must be listed in `GLOBAL_TABLES` with the reason it is safe to share. That list is the review
point for any new global table.

| Test | Guards against |
|---|---|
| `tests/unit/test_tenant_tables_declared.py` | A new model without `tenant_id` that isn't listed as global. Runs in every build, no database. |
| `tests/integration/test_tenant_guard.py` | A table missing forced RLS, a policy, or `NOT NULL`; an extra policy; an undeclared table. Also proves each of those is caught, that no tenant means no rows and refused writes, and that a tenant never carries over on a reused connection. |
| `tests/integration/test_tenant_leak_api.py` | Any GET endpoint returning another tenant's record ids or emails. It calls every endpoint as one institution, with every permission, in both directions. |
| `tests/integration/test_tenant_rls_isolation.py` | The policy pair itself, on a scratch table. |

They need the database at the latest migration and data in two tenants, so run them on a copy:

```bash
python scripts/run_tenant_leak_tests.py
```

This copies the database, migrates the copy, runs the four files and drops it. Stop the API
first, because Postgres won't copy a database with open connections. On the normal suite, with a
database not yet at T1, these tests skip.

**Found by the sweep:** the weekly review queue cached candidates by date only, so one
institution was served another's students for up to 30 seconds. It is now keyed by tenant and
date. In-process caches of tenant data must always include the tenant in the key.

## Reporting views per institution (T3)

BI tools and data-warehouse loaders get their own read-only "virtual database" per institution,
and never touch the core tables.

| Piece | What it is |
|---|---|
| `app/db/tenant_views.py` | The **catalogue**: the 24 published objects (student, person, lifecycle events including HESA leaver data, every dated history, module enrolments, funding, supervision, programmes, modules and their versions, units of assessment, departments). Views are generated from it, never hand-written. |
| `tenant_<sub>` | Standard schema: no names, emails, dates of birth (year of birth only) or free-text notes. |
| `tenant_<sub>_full` | The same objects with personal data. Granted only when the institution asks for it. |
| `<sub>_reporting` / `<sub>_reporting_full` | Read-only login for each schema. It has a connection limit of 5, a 120 s statement timeout and no privileges on the core tables. |
| `pgr_views` | NOLOGIN role that owns every view. It isn't the table owner, so RLS applies to it fail-closed and the owner's bypass does nothing for it. |

**Two locks.** Every view has its institution's id written into it (`WHERE tenant_id = '<uuid>'`)
and is a `security_barrier` view. Underneath, RLS still applies, and each login is pinned to its
institution (`app.current_tenant` set on the role). If a login changes its own tenant setting,
RLS lets the other institution's rows through, but the view's filter then returns nothing. If it
turns on the bypass, nothing changes, because the views don't run as the table owner.

**Kept in step automatically.** Every migration drops the view schemas first (Postgres won't
alter a column a view uses) and rebuilds them from the catalogue at the end. The seed scripts
that create institutions build theirs straight away. Institutions that are deactivated or
removed lose their schemas on the next rebuild.

**One-time setup (superuser).** Run `deploy/provision_reporting.sql` once. It creates
`pgr_views` and lets the owner role create reporting logins and pin their institution. Until
then, views are still built, owned by the table owner, and the fixed filter is the lock. No
logins can be created in that state.

**Day to day (no superuser):**

```bash
python -m scripts.tenant_reporting status
python -m scripts.tenant_reporting create-login icr          # prints the password once
python -m scripts.tenant_reporting create-login icr --full   # personal data, only on request
python -m scripts.tenant_reporting rotate icr
python -m scripts.tenant_reporting drop-login icr
python -m scripts.tenant_reporting rebuild [icr]
```

Store the printed password in the institution's secret store straight away; the tool keeps no
copy. Tests: `tests/unit/test_tenant_view_catalogue.py` (catalogue matches the models, no
personal data or free text in standard views) and `tests/integration/test_tenant_views.py`. The
second creates a real login, checks it can't reach core tables, other schemas or other
institutions' rows, and drops it again. It skips until reporting is provisioned.

## Outside the database (T4) — checklist with evidence

| Area | Status | Evidence |
|---|---|---|
| **Stored files** | Keys are `<tenant id>/<random>.<ext>`. Opening or deleting a key that belongs to another institution reads as "not found" (a second lock behind the RLS-scoped `document` row every download loads first). Path containment is a real check. Pre-T4 keys still read. | `app/core/storage.py`; `tests/unit/test_storage_tenant.py` |
| **Downloads** | There are no public or unauthenticated links. All 5 download endpoints need a token and load a tenant-scoped row first. Filenames are sanitised in the header. Signed, expiring links come with the S3 backend (not built). | `app/core/storage.py:content_disposition`; documents, portal, certificate and export routers |
| **Exports** | Statutory and report CSVs live in tenant-scoped rows. `tenant_ops export` now includes the institution's files (hashed in the manifest). `tenant_ops delete` removes them after the rows commit. `export_taught.py` exports the default institution only. | `scripts/tenant_ops.py`; `app/db/export_taught.py` |
| **Background jobs** | The worker runs every job once per active (activated, not deactivated) institution. "Run now" endpoints use the caller's institution. AI streams inherit the request's institution. | `app/worker.py`; T2 connection-reuse test |
| **Requests with no user token** | Partner webhooks and email-bounce hooks take their institution from the host (bare host = default) before any query. Each is signed with that institution's own secret, so institution A's secret can't post into B. Bounces now need a signature (a forged one could switch off someone's email). Referee submissions take the institution from the host, or else from the secret token. | `app/core/inbound.py`; `python -m scripts.tenant_ops webhook-secret <tenant>`; `test_f6_assistant_notif.py::test_unsigned_bounce_is_refused` |
| **Unique keys** | Business keys (programme and department codes, student numbers, setting keys, external refs and 11 more) are unique **per institution**, not across all of them. Before, two institutions couldn't share a code, only one could ever save a given setting, and the clash revealed another institution's data. Only `users.email` and the referee-token hash stay global, on purpose. | migration `t4_tenant_uniques`; `test_tenant_tables_declared.py::test_business_keys_are_unique_per_institution` |
| **Caches** | The only data cache (weekly review queue) is keyed by institution. The others hold no tenant data (static registries) or are keyed by user. | `app/modules/reviews/service.py`; T2 sweep |
| **Assistant and AI** | Every AI artefact (pattern-lab models, predictions, telemetry, write intents) lives in tenant-scoped tables. Prompts are built from the request's RLS-scoped session. A write intent can only be run or cancelled by the user who proposed it. | `app/modules/assistant/f6_router.py` |
| **Logs** | Every JSON line carries `tenantId` when an institution is acting, and request lines carry `userId`. The access line logs the path without the query string. Outside dev, the console email backend never writes bodies (reset links) or full addresses. Account lockouts log the user id, not the email. AI streams send a generic error to the browser; the detail goes to the log only. | `app/core/logging.py`, `middleware.py`, `email.py` |
| **Support access** | No impersonation or shared cross-institution login exists. In production the seed loads roles and permissions only, never demo accounts with known passwords. A first admin comes from `SEED_ADMIN_EMAIL`/`SEED_ADMIN_PASSWORD` and is never reset. `seed_demo_logins` refuses to run in production. Only a holder of `platform.configure` can grant the `dev` role. | `app/db/seed.py`; `scripts/seed_demo_logins.py`; `admin_router.py` |

**Deployment notes:** run uvicorn with `--no-access-log`; its own access log includes query
strings and has no tenant. Ours replaces it. Give each institution's partners its webhook secret,
and have them post to the institution's subdomain.

## Not yet done

- **Decisions for the product owner:**
  - External AI models receive student data (names, meeting notes) whenever an API key is
    configured. Only the composer has a per-institution switch. Decide whether every AI
    feature needs a per-institution opt-in.
  - Accepting a HESA advisory updates the specification every institution shares. Decide
    whether that becomes a platform-admin action.
  - `GET /tenants` (the login-page selector) is public and lists every institution.
  - Sign-in emails are unique across institutions, so creating a user whose email exists at
    another institution answers "already exists".
- Reporting logins can see the names of other institutions' schemas in the system catalogue
  (not their contents). Hiding those names needs a separate database per institution.
- Password-reset and notification links use the global `APP_BASE_URL`, not the institution's
  subdomain. With the restricted app role, reset confirmation needs the subdomain link.
- The SLA sweep isn't scheduled (only the manual endpoint runs it). This isn't a tenancy issue.
- T5: independent security test preparation.
