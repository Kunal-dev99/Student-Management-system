"""MT-3 — Enforce tenant isolation with Postgres Row-Level Security.

Turns the MT-2 plumbing into real isolation on the core spine (person, programme,
student, department). This is the step that makes the database — not application code —
refuse to leak rows across tenants.

Design notes (why it is safe to ship):

* FORCE is required. The application connects as the table OWNER (`pgr`), and a plain
  ENABLE lets the owner bypass RLS. FORCE makes the policy apply to the owner too.

* Unset context = bypass. The policy isolates only when `app.current_tenant` is set to a
  real uuid (every authenticated request sets it — see core.dependencies). When it is
  unset/empty — migrations, `db/seed.py`, one-off scripts, health checks — the policy is
  permissive, so single-tenant operation and tooling keep working with no changes. As the
  platform onboards real second tenants, the hardening step is a dedicated non-owner app
  role so an unset context fails closed; that is infra, not schema, and out of scope here.

* Postgres-only. RLS does not exist on SQLite, so the ORM test suite is unaffected; the
  isolation guarantee is proven by tests/integration/test_tenant_rls_isolation.py against
  a real Postgres instance.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "mt3_tenant_rls"
down_revision: Union[str, Sequence[str], None] = "mt2_tenant_scope_core"
branch_labels = None
depends_on = None

_TABLES: tuple[str, ...] = ("person", "programme", "student", "department")

# Isolate when a tenant is set; bypass when the context is absent (system/seed paths).
_PREDICATE = (
    "current_setting('app.current_tenant', true) IS NULL "
    "OR current_setting('app.current_tenant', true) = '' "
    "OR tenant_id = current_setting('app.current_tenant', true)::uuid"
)


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
