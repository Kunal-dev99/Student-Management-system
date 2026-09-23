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

## Two operating modes

| | Owner role (`pgr`) | App role (`pgr_app`, MT-6) |
|---|---|---|
| Used by | migrations, `db/seed.py`, the worker | the API request path |
| Unset tenant context | **bypass** (so tenant-less tooling works) | **fail-closed — zero rows** |
| Tenant context set | isolated to that tenant | isolated to that tenant |

Out of the box the API also runs as the **owner** (`FORCE` RLS + a permissive-on-unset
policy), which already isolates every authenticated request (they always set the context).
MT-6 adds the **fail-closed app role** so that even an unexpected tenant-less query on the
API path returns nothing.

## Enabling the fail-closed app role (production)

1. As a **superuser**, run the provisioning script (edit the role name / password / owner
   at the top first):
   ```bash
   psql "postgresql://postgres@dbhost:5432/pgr" -f deploy/provision_app_role.sql
   ```
   It creates `pgr_app`, grants it table/sequence privileges (incl. default privileges for
   future tables), and installs the role-targeted policies (owner = permissive, app =
   fail-closed).
2. Point the **API** at the app role and restart it:
   ```bash
   APP_DATABASE_URL=postgresql://pgr_app:<password>@dbhost:5432/pgr
   ```
   Leave `DATABASE_URL` as the owner — migrations, the seed and the worker keep using it.
3. Verify: an authenticated request still returns its tenant's data; if you strip the
   tenant context, the API returns nothing instead of everything.

If `APP_DATABASE_URL` is unset (dev default), the API uses the owner connection and behaves
exactly as before — MT-6 is inert until you switch it on.

## Not yet done

- Flip `tenant_id` to `NOT NULL` once every path is confirmed to stamp it.
- Optionally extend RLS to `users` / `composer_run` (scoped columns, RLS currently off).
