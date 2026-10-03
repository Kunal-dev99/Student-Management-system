-- ============================================================================
-- Provision the restricted application DB role (pgr_app).
--
-- Run this ONCE as a Postgres SUPERUSER (e.g. `postgres`) against the app database:
--     psql "postgresql://postgres@dbhost:5432/pgr" -f deploy/provision_app_role.sql
--
-- It creates a NON-OWNER login for the API with table privileges only. It does NOT touch
-- RLS policies any more: since T1 (migration t1_tenant_hardening) every tenant table carries
--   tenant_isolation         TO PUBLIC  — tenant_id = acting tenant (fail-closed)
--   tenant_isolation_system  TO owner   — explicit bypass, owner only
-- so any non-owner role, this one included, is fail-closed automatically and can never use
-- the bypass. New tables get the same pair from their migration (tenant_ddl.enable_rls).
--
-- Idempotent — safe to re-run. Edit the three settings below first: the app role name, its
-- PASSWORD (use a real secret, never commit it), and the OWNER role that owns the tables (the
-- role in DATABASE_URL, usually `pgr`).
--
-- After running: set APP_DATABASE_URL to a DSN for the app role, e.g.
--     APP_DATABASE_URL=postgresql+asyncpg://pgr_app:<password>@dbhost:5432/pgr
-- and restart the API. Migrations, seeds and the worker keep using DATABASE_URL (the owner).
-- With pgr_app, sign in through a tenant subdomain (e.g. icr.localhost): a bare host has no
-- tenant to scope the login lookup to, and pgr_app cannot use the owner's bypass.
-- ============================================================================
DO $$
DECLARE
    app_role   text := 'pgr_app';
    app_pass   text := 'CHANGE_ME_IN_PROD';
    owner_role text := 'pgr';
    fn         text;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = app_role) THEN
        EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB',
                       app_role, app_pass);
    END IF;

    EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), app_role);
    EXECUTE format('GRANT USAGE ON SCHEMA public TO %I', app_role);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I', app_role);
    EXECUTE format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO %I', app_role);
    -- Future tables/sequences created by the owner auto-grant to the app role.
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I', owner_role, app_role);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO %I', owner_role, app_role);

    -- The narrow pre-sign-in lookups (migration t5_pre_auth_lookups): which institution an email,
    -- user, referee token or bounced address belongs to. Revoked from PUBLIC; only the app may call.
    FOR fn IN SELECT p.oid::regprocedure::text FROM pg_proc p
              JOIN pg_namespace n ON n.oid = p.pronamespace
              WHERE n.nspname = 'public' AND p.proname LIKE 'pgr\_tenant%' LOOP
        EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO %I', fn, app_role);
    END LOOP;

    RAISE NOTICE 'App role % provisioned (privileges only; RLS is fail-closed for it by the T1 policies).', app_role;
END $$;
