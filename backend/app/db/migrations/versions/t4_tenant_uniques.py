"""T4 — business keys are unique per institution, not across all institutions.

Programme codes, student numbers, department codes, settings keys and the like were unique over
the whole shared database. Two institutions could not both have programme MSC-ONC, only one
institution could ever save a given setting key, and the "already exists" error told one
institution that another had that value. Each becomes unique within (tenant_id, ...).

Deliberately left global: ``users.email`` (it identifies who is signing in, before the
institution is known) and ``reference_request.token_hash`` (a secret that names one request).

The existing global rule is found by introspection (it may be a constraint or a unique index,
depending on how the table was first created), so this works on every database's history.

Revision ID: t4_tenant_uniques
Revises: t1_tenant_hardening
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "t4_tenant_uniques"
down_revision: Union[str, Sequence[str], None] = "t1_tenant_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# table -> unique column sets (without tenant_id); `lookup` = columns that also keep a plain index.
KEYS: list[tuple[str, tuple[str, ...], bool]] = [
    ("cost_centre", ("code",), False),
    ("project_code", ("code",), False),
    ("department", ("code",), False),
    ("research_area", ("code",), False),
    ("programme", ("code",), False),
    ("student", ("student_ref",), False),
    ("person", ("external_person_ref",), False),
    ("person", ("email",), True),
    ("research_award", ("award_ref",), True),
    ("institution_setting", ("key",), True),
    ("ml_model", ("name",), False),
    ("intervention_plan", ("idempotency_key",), False),
    ("value_set_override", ("enum_name", "value_code"), False),
    ("report_profile", ("code", "academic_year", "version"), False),
    ("integration_log", ("system", "source_id"), False),
    ("workflow_definition", ("key", "version"), False),
]


def _name(table: str, cols: tuple[str, ...]) -> str:
    return f"uq_{table}_tenant_{'_'.join(cols)}"


def _global_uniques(conn, table: str, cols: tuple[str, ...]) -> list[tuple[str, str]]:
    """(kind, name) of every unique constraint / unique index on exactly these columns."""
    rows = conn.execute(sa.text("""
        SELECT CASE WHEN con.oid IS NOT NULL THEN 'constraint' ELSE 'index' END, ic.relname,
               array_agg(a.attname ORDER BY k.ord)
        FROM pg_index i
        JOIN pg_class t ON t.oid = i.indrelid AND t.relname = :t
        JOIN pg_namespace n ON n.oid = t.relnamespace AND n.nspname = 'public'
        JOIN pg_class ic ON ic.oid = i.indexrelid
        LEFT JOIN pg_constraint con ON con.conindid = i.indexrelid AND con.contype = 'u'
        CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord)
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
        WHERE i.indisunique AND NOT i.indisprimary
        GROUP BY con.oid, ic.relname
    """), {"t": table}).all()
    return [(kind, name) for kind, name, got in rows if tuple(got) == cols]


def upgrade() -> None:
    conn = op.get_bind()
    for table, cols, lookup in KEYS:
        for kind, name in _global_uniques(conn, table, cols):
            if kind == "constraint":
                op.drop_constraint(name, table, type_="unique")
            else:
                op.drop_index(name, table_name=table)
        if lookup:   # keep fast lookups by the key alone (it may already exist as a plain index)
            op.execute(f'CREATE INDEX IF NOT EXISTS "ix_{table}_{cols[0]}" ON "{table}" ({cols[0]})')
        op.create_unique_constraint(_name(table, cols), table, ["tenant_id", *cols])


def downgrade() -> None:
    for table, cols, lookup in reversed(KEYS):
        op.drop_constraint(_name(table, cols), table, type_="unique")
        if lookup:
            op.drop_index(f"ix_{table}_{cols[0]}", table_name=table)
            op.create_index(f"ix_{table}_{cols[0]}", table, list(cols), unique=True)
        else:
            op.create_unique_constraint(f"uq_{table}_{'_'.join(cols)}", table, list(cols))
