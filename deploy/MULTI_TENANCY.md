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

## Not yet done

- Flip `tenant_id` to `NOT NULL` once every path is confirmed to stamp it.
- Optionally extend RLS to `users` / `composer_run` (scoped columns, RLS currently off).
