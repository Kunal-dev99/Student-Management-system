"""Effective dating, Phase 5: the returns.amend permission.

A reporting year closes when its statutory return is signed off. A change dated inside a closed
year is a data amendment, so it needs ``returns.amend`` — granted here to the all-access roles
(Institution Administrator, dev) only. Institutions give it to their returns / student-data team;
it is deliberately not in the PGR Administrator bundle, which signs returns off.

No schema change.

Revision ID: ed5_returns_amend_permission
Revises: ed3_module_enrolment_history
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ed5_returns_amend_permission"
down_revision: Union[str, Sequence[str], None] = "ed3_module_enrolment_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PERMISSION = "returns.amend"
_DESCRIPTION = "Make changes dated inside a signed-off statutory return (data amendment)"


def upgrade() -> None:
    bind = op.get_bind()
    # Separate, explicitly typed parameters: asyncpg can't infer one type for a parameter used
    # both as a selected value and in a comparison.
    bind.execute(
        sa.text("INSERT INTO permission (id, code, description) "
                "SELECT :id, CAST(:code AS VARCHAR), CAST(:description AS VARCHAR) "
                "WHERE NOT EXISTS (SELECT 1 FROM permission WHERE code = CAST(:code_check AS VARCHAR))"),
        {"id": uuid.uuid4(), "code": _PERMISSION, "code_check": _PERMISSION, "description": _DESCRIPTION},
    )
    bind.execute(
        sa.text("INSERT INTO role_permission (role_id, permission_id) "
                "SELECT r.id, p.id FROM role r, permission p "
                "WHERE p.code = :code AND r.name IN ('Institution Administrator', 'dev') "
                "AND NOT EXISTS (SELECT 1 FROM role_permission rp "
                "                WHERE rp.role_id = r.id AND rp.permission_id = p.id)"),
        {"code": _PERMISSION},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM role_permission WHERE permission_id IN "
                "(SELECT id FROM permission WHERE code = :code)"),
        {"code": _PERMISSION},
    )
    bind.execute(sa.text("DELETE FROM permission WHERE code = :code"), {"code": _PERMISSION})
