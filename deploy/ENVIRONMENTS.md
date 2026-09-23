# Database environments

The platform uses **four Postgres databases on the same server** (`localhost:5432`), all
owned by the `pgr` role. They share one identical schema; they differ only in what data
they hold and what they are used for.

| Database | Purpose | Data | `DATABASE_URL` (swap the last segment) |
|---|---|---|---|
| `pgr` | **Dev** (current working DB) | full dev/demo data | `postgresql+asyncpg://pgr:<pw>@localhost:5432/pgr` |
| `pgr_test` | **Test** | empty (seed on demand) | `…/pgr_test` |
| `pgr_prod` | **Prod** | empty until go-live | `…/pgr_prod` |
| `pgr_backup` | **Backup / restore scratch** | empty | `…/pgr_backup` |

Point the backend at an environment by setting `DATABASE_URL` (in `.env` or as an env var
at launch) to that database's URL. The app also reads `DATABASE_REPLICA_URL` (read replica,
optional) and `APP_DATABASE_URL` (the MT-6 fail-closed app role, optional — see
`MULTI_TENANCY.md`).

## Multi-tenancy applies to every environment

This is **not** database-per-tenant. Each of the four databases is itself a shared,
row-isolated multi-tenant database: every tenant-owned table carries `tenant_id`, and
Postgres Row-Level Security enforces isolation. So a single environment (e.g. `pgr_prod`)
holds *all* institutions, kept apart by RLS — the four databases are **deployment stages**
(dev/test/prod/backup), not tenants.

Verified on all four: **95 tables** with RLS **enabled + FORCE**, **95** `tenant_isolation`
policies using the `NULLIF(current_setting('app.current_tenant',''))` predicate, and a live
check where a new tenant sees only its own rows and an unknown tenant sees zero. Full model
in `MULTI_TENANCY.md`.

## How they were created (and how to recreate)

Empty schema clones of dev, built from the migrations (no data):

```bash
# one-time: a superuser grants the app role the right to create databases
psql -U postgres -c "ALTER ROLE pgr CREATEDB;"

# create all three + build the full schema (tables, FKs, indexes, RLS) — dev untouched
python -m scripts.provision_environments            # or: --only test
```

`scripts/provision_environments.py` creates `pgr_prod` / `pgr_test` / `pgr_backup` if
missing, runs `alembic upgrade head` in each, and verifies table/FK/RLS counts match dev.
The migrations create the structural **default tenant** row in each (plumbing, not seed
data); there is no application data.

## Keeping the four in sync

Apply every new migration to each environment — run `alembic upgrade head` with that
database's `DATABASE_URL`, or re-run `python -m scripts.provision_environments` (it skips
databases that already exist and just brings the schema to head). All four are currently at
Alembic head `mt6_app_role_failclosed`.

## Notes

- The **MT-6 fail-closed `pgr_app` role** is not provisioned in these databases (needs
  `CREATEROLE`/superuser); they run in the owner + FORCE + permissive-on-unset mode, which
  isolates every request that sets a tenant context (the app always does). To enable
  fail-closed on an environment (recommended for prod), run `deploy/provision_app_role.sql`
  as a superuser against it and set `APP_DATABASE_URL`.
- Per-tenant data operations (export / delete / stats) and single-tenant restore work the
  same in any environment — see `scripts/tenant_ops.py` and `RESTORE_ONE_TENANT.md`.
