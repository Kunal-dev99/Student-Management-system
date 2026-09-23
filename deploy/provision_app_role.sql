-- ============================================================================
-- MT-6 — provision the fail-closed application DB role.
--
-- Run this ONCE as a Postgres SUPERUSER (e.g. `postgres`) against the app database:
--     psql "postgresql://postgres@dbhost:5432/pgr" -f deploy/provision_app_role.sql
--
-- It creates a NON-OWNER role the API connects as, whose RLS policy is fail-closed (an
-- unset tenant context sees zero rows), and re-targets the owner's policy so migrations,
-- db/seed and the background worker (which run tenant-less as the owner) keep working.
--
-- Idempotent — safe to re-run (e.g. after adding tables). Edit the three settings below
-- before running: the app role name, its PASSWORD (use a real secret), and the OWNER role
-- that owns the tables (the role in DATABASE_URL, usually `pgr`).
--
-- After running: set APP_DATABASE_URL to a DSN for the app role, e.g.
--     APP_DATABASE_URL=postgresql://pgr_app:<password>@dbhost:5432/pgr
-- and restart the API. The worker/migrations keep using DATABASE_URL (the owner).
-- ============================================================================
DO $$
DECLARE
    app_role   text := 'pgr_app';
    app_pass   text := 'CHANGE_ME_IN_PROD';
    owner_role text := 'pgr';
    t          text;
    permissive text := 'NULLIF(current_setting(''app.current_tenant'', true), '''') IS NULL '
                       'OR tenant_id = NULLIF(current_setting(''app.current_tenant'', true), '''')::uuid';
    failclosed text := 'tenant_id = NULLIF(current_setting(''app.current_tenant'', true), '''')::uuid';
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = app_role) THEN
        EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', app_role, app_pass);
    END IF;

    EXECUTE format('GRANT USAGE ON SCHEMA public TO %I', app_role);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I', app_role);
    EXECUTE format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO %I', app_role);
    -- Future tables/sequences created by the owner auto-grant to the app role.
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I', owner_role, app_role);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO %I', owner_role, app_role);

    -- Role-targeted policies: owner permissive (tenant-less paths work), app fail-closed.
    FOR t IN
        SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND rowsecurity = true
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation_app ON %I', t);
        EXECUTE format('CREATE POLICY tenant_isolation ON %I TO %I USING (%s) WITH CHECK (%s)',
                       t, owner_role, permissive, permissive);
        EXECUTE format('CREATE POLICY tenant_isolation_app ON %I TO %I USING (%s) WITH CHECK (%s)',
                       t, app_role, failclosed, failclosed);
    END LOOP;

    RAISE NOTICE 'MT-6 app role % provisioned and fail-closed policies installed.', app_role;
END $$;
