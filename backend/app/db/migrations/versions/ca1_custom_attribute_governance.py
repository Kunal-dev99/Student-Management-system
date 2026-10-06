"""Custom attribute governance, Phase 1: request → maker-checker decision → active.

- ``student_custom_field`` gains a lifecycle ``status`` (pending | approved | rejected | active |
  review | retired) plus who decided, when and why. Attributes that already exist were created
  under the old one-step flow and are in use, so they are backfilled as ``active`` — HESA
  returns built on them keep working unchanged. New rows default to ``pending``.
- ``student_custom_field_event``: the append-only decision trail (tenant-scoped, RLS).
- Two permissions: ``custom_attribute.request`` (the maker) and ``custom_attribute.approve``
  (the checker). Both go to the all-access roles; requesting also goes to PGR Administrator,
  who runs the return day to day but does not decide on new statutory attributes.

Revision ID: ca1_custom_attribute_governance
Revises: w1_warehouse
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.db.tenant_ddl import disable_rls, enable_rls

revision: str = "ca1_custom_attribute_governance"
down_revision: Union[str, Sequence[str], None] = "w1_warehouse"
branch_labels = None
depends_on = None

_FIELD = "student_custom_field"
_EVENT = "student_custom_field_event"
_PERMISSIONS = {
    "custom_attribute.request": (
        "Request a new custom student attribute",
        ("Institution Administrator", "dev", "PGR Administrator"),
    ),
    "custom_attribute.approve": (
        "Approve, reject or activate custom student attribute requests",
        ("Institution Administrator", "dev"),
    ),
}


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # Existing attributes are live → active; the default flips to pending for new requests.
    op.add_column(_FIELD, sa.Column("status", sa.String(length=20), nullable=False,
                                    server_default="active"))
    op.alter_column(_FIELD, "status", server_default="pending")
    op.add_column(_FIELD, sa.Column("decided_by_user_id", sa.Uuid(), nullable=True))
    op.add_column(_FIELD, sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(_FIELD, sa.Column("decision_reason", sa.Text(), nullable=True))
    op.create_foreign_key("fk_custom_field_decided_by", _FIELD, "users",
                          ["decided_by_user_id"], ["id"], ondelete="SET NULL")
    op.create_index(op.f(f"ix_{_FIELD}_status"), _FIELD, ["status"])

    op.create_table(
        _EVENT,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("custom_field_id", sa.Uuid(), nullable=True),
        sa.Column("field_key", sa.String(length=60), nullable=False),
        sa.Column("field_label", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_email", sa.String(length=320), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["custom_field_id"], [f"{_FIELD}.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f(f"ix_{_EVENT}_tenant_id"), _EVENT, ["tenant_id"])
    op.create_index(op.f(f"ix_{_EVENT}_custom_field_id"), _EVENT, ["custom_field_id"])
    if is_pg:
        enable_rls((_EVENT,))

    # Open the trail for the attributes that already exist, so their history isn't blank.
    bind.execute(sa.text(
        f"INSERT INTO {_EVENT} (id, tenant_id, custom_field_id, field_key, field_label, action, "
        "from_status, to_status, actor_user_id, notes, created_at) "
        "SELECT gen_random_uuid(), tenant_id, id, "
        "key, label, 'migrated', NULL, 'active', created_by_user_id, "
        "'Created before attribute governance; carried over as active.', created_at "
        f"FROM {_FIELD}"
    ))

    for code, (description, roles) in _PERMISSIONS.items():
        _grant(bind, code, description, roles)


def _grant(bind, code: str, description: str, roles: tuple[str, ...]) -> None:
    # Separate, explicitly typed parameters: asyncpg can't infer one type for a parameter used
    # both as a selected value and in a comparison.
    bind.execute(
        sa.text("INSERT INTO permission (id, code, description) "
                "SELECT :id, CAST(:code AS VARCHAR), CAST(:description AS VARCHAR) "
                "WHERE NOT EXISTS (SELECT 1 FROM permission WHERE code = CAST(:code_check AS VARCHAR))"),
        {"id": uuid.uuid4(), "code": code, "code_check": code, "description": description},
    )
    bind.execute(
        sa.text("INSERT INTO role_permission (role_id, permission_id) "
                "SELECT r.id, p.id FROM role r, permission p "
                "WHERE p.code = :code AND r.name IN :roles "
                "AND NOT EXISTS (SELECT 1 FROM role_permission rp "
                "                WHERE rp.role_id = r.id AND rp.permission_id = p.id)"
                ).bindparams(sa.bindparam("roles", expanding=True)),
        {"code": code, "roles": list(roles)},
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        disable_rls((_EVENT,))
    op.drop_table(_EVENT)
    op.drop_index(op.f(f"ix_{_FIELD}_status"), table_name=_FIELD)
    op.drop_constraint("fk_custom_field_decided_by", _FIELD, type_="foreignkey")
    for col in ("decision_reason", "decided_at", "decided_by_user_id", "status"):
        op.drop_column(_FIELD, col)
    for code in _PERMISSIONS:
        bind.execute(sa.text("DELETE FROM role_permission WHERE permission_id IN "
                             "(SELECT id FROM permission WHERE code = :code)"), {"code": code})
        bind.execute(sa.text("DELETE FROM permission WHERE code = :code"), {"code": code})
