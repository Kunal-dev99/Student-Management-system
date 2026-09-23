-- ============================================================================
-- Create the prod / test / backup databases (empty). Run ONCE as a SUPERUSER:
--     psql "postgresql://postgres@localhost:5432/postgres" -f deploy/create_environments.sql
--
-- These are created empty; the schema is built afterwards by:
--     python -m scripts.provision_environments
-- which runs the Alembic migrations into each (all tables, FKs, indexes, RLS — no data).
--
-- Alternatively, instead of creating them here, grant the app role the privilege and let
-- the provisioning script create them itself:
--     ALTER ROLE pgr CREATEDB;
-- ============================================================================
CREATE DATABASE pgr_prod   OWNER pgr;
CREATE DATABASE pgr_test   OWNER pgr;
CREATE DATABASE pgr_backup OWNER pgr;
