"""MT-6 — fail-closed app DB role.

Adds a NON-OWNER application role (default `pgr_app`) whose RLS policy is fail-closed: with
no tenant context it sees zero rows, so a request that somehow reaches the DB without a
tenant leaks nothing. The OWNER role (which runs migrations, db/seed and the background
worker) keeps a permissive-on-unset policy so those tenant-less paths keep working.

Mechanism — two role-targeted policies per RLS table (permissive policies are OR'd only
within the same role, so targeting them at different roles keeps them independent):
  * tenant_isolation      TO <owner>    — unset bypasses (seeds/migrations/worker/dev API)
  * tenant_isolation_app  TO <app_role> — unset = no rows (the production API connection)

Enabling it is a deploy-time switch: set APP_DATABASE_URL to a DSN for <app_role>; until
then the API uses the owner connection and behaves exactly as before. Postgres-only.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.config import get_settings

revision: str = "mt6_app_role_failclosed"
down_revision: Union[str, Sequence[str], None] = "mt4_25_fix_rls_predicate"
branch_labels = None
depends_on = None

_PERMISSIVE = (
    "NULLIF(current_setting('app.current_tenant', true), '') IS NULL "
    "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
)
_FAIL_CLOSED = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"


def _rls_tables(bind) -> list[str]:
    return [r[0] for r in bind.execute(sa.text(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' AND rowsecurity=true "
        "ORDER BY tablename"
    ))]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    s = get_settings()
    role = s.app_db_role
    pwd = (s.app_db_password or "").replace("'", "''")
    owner = bind.execute(sa.text("SELECT current_user")).scalar()

    role_exists = bind.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :r)"
    ).bindparams(r=role)).scalar()
    can_create = bind.execute(sa.text(
        "SELECT rolcreaterole OR rolsuper FROM pg_roles WHERE rolname = current_user"
    )).scalar()

    # Provision the role if we can; if not and it is absent, MT-6 stays INACTIVE (the
    # existing permissive policy is untouched) so the migration never fails on a restricted
    # role. A DBA provisions the role out-of-band (see deploy/provision_app_role.sql) and
    # re-runs this migration to wire the fail-closed policies.
    if not role_exists:
        if not can_create:
            op.execute(
                "DO $$ BEGIN RAISE NOTICE "
                "'MT-6 inactive: role \"%\" absent and current_user cannot CREATE ROLE; "
                "provision it as a superuser, then re-run this migration.', "
                f"'{role}'; END $$;"
            )
            return
        op.execute(f"CREATE ROLE {role} LOGIN PASSWORD '{pwd}'")

    # 1) Grants for the app role (idempotent).
    op.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}")
    # Future tables/sequences created by the owner auto-grant to the app role.
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {role}")

    # 2) Re-target the isolation policy to the owner (permissive) and add a fail-closed
    #    policy for the app role.
    for t in _rls_tables(bind):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_app ON {t}")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {t} TO {owner} "
            f"USING ({_PERMISSIVE}) WITH CHECK ({_PERMISSIVE})"
        )
        op.execute(
            f"CREATE POLICY tenant_isolation_app ON {t} TO {role} "
            f"USING ({_FAIL_CLOSED}) WITH CHECK ({_FAIL_CLOSED})"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    role = get_settings().app_db_role
    for t in _rls_tables(bind):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_app ON {t}")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        # Restore the single PUBLIC permissive policy (pre-MT-6 state).
        op.execute(
            f"CREATE POLICY tenant_isolation ON {t} "
            f"USING ({_PERMISSIVE}) WITH CHECK ({_PERMISSIVE})"
        )
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {role}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM {role}")
    # Role and its grants are left in place (dropping a role that may own nothing is safe to
    # skip; a deploy that wants it gone can DROP ROLE after REVOKE).
