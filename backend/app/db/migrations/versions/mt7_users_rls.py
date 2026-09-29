"""MT-7 — extend RLS to the users table.

`users` carries tenant_id (since MT-1) but had no row-level security, so an admin user list
(`GET /admin/users`) returned users across every tenant. This enables the same ENABLE+FORCE
policy the domain tables use. Login is unaffected: it runs with no tenant context, and the
policy is permissive when the context is unset (NULLIF(...) IS NULL), so email lookup at
sign-in still finds the user; authenticated admin reads set the context and are scoped.

(composer_run also carries tenant_id without RLS; it is a feature-analytics table, lower
risk, and left for a later pass.)
"""
from __future__ import annotations

from typing import Sequence, Union

from app.db.tenant_ddl import disable_rls, enable_rls

revision: str = "mt7_users_rls"
down_revision: Union[str, Sequence[str], None] = "mt6_app_role_failclosed"
branch_labels = None
depends_on = None

_TABLES = ("users",)


def upgrade() -> None:
    enable_rls(_TABLES)


def downgrade() -> None:
    disable_rls(_TABLES)
