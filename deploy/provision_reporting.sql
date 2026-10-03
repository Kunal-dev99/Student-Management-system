-- ============================================================================
-- T3 — one-time provisioning for per-institution reporting access.
--
-- Run ONCE as a Postgres SUPERUSER against the app database:
--     psql "postgresql://postgres@dbhost:5432/pgr" -f deploy/provision_reporting.sql
--
-- After this, the owner role (pgr) manages everything itself, with no superuser:
--   * migrations rebuild the per-institution view schemas, owned by pgr_views;
--   * scripts/tenant_reporting.py creates, rotates and drops reporting logins.
--
-- What it grants, and why:
--   pgr_views           NOLOGIN role that owns the views. It is NOT the table owner, so row-level
--                       security applies to it fail-closed (no bypass). It only ever receives
--                       SELECT on the tables the view catalogue publishes.
--   pgr -> pgr_views    membership, so pgr can create schemas and hand view ownership to it.
--   pgr CREATEROLE      so pgr can create reporting logins. Since Postgres 16 a CREATEROLE role
--                       can only manage roles it created itself, and can't grant superuser,
--                       replication or BYPASSRLS.
--   SET app.current_tenant
--                       so pgr can pin each reporting login to its institution
--                       (ALTER ROLE ... SET app.current_tenant). Postgres reserves setting a
--                       custom parameter on another role to superusers unless granted.
--
-- Idempotent — safe to re-run. Edit owner_role if the tables' owner isn't `pgr`.
-- ============================================================================
DO $$
DECLARE
    owner_role text := 'pgr';
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgr_views') THEN
        CREATE ROLE pgr_views NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
    END IF;
    EXECUTE format('GRANT pgr_views TO %I', owner_role);
    EXECUTE format('GRANT CREATE ON DATABASE %I TO pgr_views', current_database());
    GRANT USAGE ON SCHEMA public TO pgr_views;
    EXECUTE format('ALTER ROLE %I CREATEROLE', owner_role);
    EXECUTE format('GRANT SET ON PARAMETER app.current_tenant TO %I', owner_role);
    RAISE NOTICE 'Reporting provisioned: pgr_views created, % may now manage reporting logins.', owner_role;
END $$;
