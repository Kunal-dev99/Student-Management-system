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

## Not yet done

- Accepting a HESA advisory updates the shared specification for every institution
  (`statutory_spec_version` is global). Decide whether that stays a platform-admin action.
- T3: tenant reporting views; T4: leak paths outside the database (files, exports, jobs).
