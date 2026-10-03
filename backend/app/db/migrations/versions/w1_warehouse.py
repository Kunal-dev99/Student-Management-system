"""Data warehouse export (DW-1): change tracking, the warehouse tables, and the client lookup.

* ``updated_at`` on every effective-dated history table (a correction sets ``superseded_by`` on an
  existing row without touching ``recorded_at``), started from ``recorded_at``.
* Two triggers on every published table (the T3 catalogue):
    - ``pgr_touch_updated_at``: BEFORE UPDATE, sets ``updated_at`` - so changes made by plain SQL,
      not just the ORM, are picked up by incremental extracts;
    - ``pgr_log_deleted_row``: AFTER DELETE, records the row id in ``warehouse_deleted_row`` so
      the warehouse can delete it too.
* The warehouse tables, tenant-owned with the fail-closed policy pair.
* ``pgr_tenant_of_warehouse_client(client_id)``: the institution of an OAuth client, for the token
  request (no institution is known yet). Same shape as the t5 lookups: ids only, app login only.

Revision ID: w1_warehouse
Revises: t5_pre_auth_lookups
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.db.tenant_ddl import disable_rls, enable_rls

revision: str = "w1_warehouse"
down_revision: Union[str, Sequence[str], None] = "t5_pre_auth_lookups"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

HISTORY_TABLES = (
    "person_uoa_history", "student_custom_value_history", "student_expected_end_history",
    "student_fee_eligibility_history", "student_fee_status_history", "student_intensity_history",
    "student_location_history", "student_outside_uk_history", "student_programme_history",
    "student_status_history", "student_uoa_history", "module_enrolment_status_history",
)

# The tables behind the T3 catalogue (app.db.tenant_views.CATALOGUE), fixed here so this migration
# stays reproducible. A new catalogue object needs its own migration adding these triggers;
# tests/integration/test_warehouse_tracking.py fails until it has them.
PUBLISHED_TABLES = (
    "person", "student", "student_lifecycle_event", "student_status_history",
    "student_programme_history", "student_intensity_history", "student_fee_status_history",
    "student_location_history", "student_expected_end_history", "student_fee_eligibility_history",
    "student_outside_uk_history", "student_uoa_history", "person_uoa_history", "module_enrolment",
    "module_enrolment_status_history", "funding_arrangement", "funding_source",
    "supervisor_relationship", "programme", "programme_version", "taught_module", "module_version",
    "unit_of_assessment", "department",
)

WAREHOUSE_TABLES = ("warehouse_deleted_row", "warehouse_publication", "warehouse_run",
                    "warehouse_watermark", "warehouse_consumer")


def _tenant_col():
    return sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False)


def upgrade() -> None:
    # 1. updated_at on the history tables.
    for t in HISTORY_TABLES:
        op.add_column(t, sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        op.execute(f"UPDATE {t} SET updated_at = recorded_at")
        op.execute(f"ALTER TABLE {t} ALTER COLUMN updated_at SET DEFAULT now()")
        op.execute(f"ALTER TABLE {t} ALTER COLUMN updated_at SET NOT NULL")

    # 2. The warehouse tables.
    op.create_table(
        "warehouse_deleted_row",
        sa.Column("id", sa.Uuid(), primary_key=True), _tenant_col(),
        sa.Column("table_name", sa.String(80), nullable=False),
        sa.Column("row_id", sa.Uuid(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_warehouse_deleted_row_tenant_id", "warehouse_deleted_row", ["tenant_id"])
    op.create_index("ix_warehouse_deleted_row_lookup", "warehouse_deleted_row", ["tenant_id", "table_name", "deleted_at"])

    op.create_table(
        "warehouse_publication",
        sa.Column("id", sa.Uuid(), primary_key=True), _tenant_col(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("objects", sa.JSON(), nullable=True),
        sa.Column("file_format", sa.String(10), nullable=False, server_default="parquet"),
        sa.Column("frequency", sa.String(10), nullable=False, server_default="daily"),
        sa.Column("run_at_hour", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("personal_data", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("full_every_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_full_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", name="uq_warehouse_publication_tenant_name"),
    )
    op.create_index("ix_warehouse_publication_tenant_id", "warehouse_publication", ["tenant_id"])

    op.create_table(
        "warehouse_run",
        sa.Column("id", sa.Uuid(), primary_key=True), _tenant_col(),
        sa.Column("publication_id", sa.Uuid(), sa.ForeignKey("warehouse_publication.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("mode", sa.String(12), nullable=False),
        sa.Column("triggered_by", sa.String(12), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location", sa.String(400), nullable=True),
        sa.Column("manifest", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_warehouse_run_tenant_id", "warehouse_run", ["tenant_id"])
    op.create_index("ix_warehouse_run_publication_id", "warehouse_run", ["publication_id"])

    op.create_table(
        "warehouse_watermark",
        sa.Column("id", sa.Uuid(), primary_key=True), _tenant_col(),
        sa.Column("publication_id", sa.Uuid(), sa.ForeignKey("warehouse_publication.id", ondelete="CASCADE"), nullable=False),
        sa.Column("object_name", sa.String(80), nullable=False),
        sa.Column("high_water", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "publication_id", "object_name",
                            name="uq_warehouse_watermark_tenant_publication_id_object_name"),
    )
    op.create_index("ix_warehouse_watermark_tenant_id", "warehouse_watermark", ["tenant_id"])
    op.create_index("ix_warehouse_watermark_publication_id", "warehouse_watermark", ["publication_id"])

    op.create_table(
        "warehouse_consumer",
        sa.Column("id", sa.Uuid(), primary_key=True), _tenant_col(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("client_id", sa.String(64), nullable=False),
        sa.Column("secret_hash", sa.String(128), nullable=False),
        sa.Column("objects", sa.JSON(), nullable=True),
        sa.Column("personal_data", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", name="uq_warehouse_consumer_client_id"),
    )
    op.create_index("ix_warehouse_consumer_tenant_id", "warehouse_consumer", ["tenant_id"])
    enable_rls(WAREHOUSE_TABLES)

    # 3. Change and delete triggers on the published tables.
    op.execute("""
CREATE OR REPLACE FUNCTION pgr_touch_updated_at() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END
$fn$;""")
    op.execute("""
CREATE OR REPLACE FUNCTION pgr_log_deleted_row() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
    INSERT INTO warehouse_deleted_row (id, tenant_id, table_name, row_id, deleted_at)
    VALUES (gen_random_uuid(), OLD.tenant_id, TG_TABLE_NAME, OLD.id, now());
    RETURN OLD;
END
$fn$;""")
    for t in PUBLISHED_TABLES:
        op.execute(f"CREATE TRIGGER pgr_touch_updated_at BEFORE UPDATE ON {t} "
                   f"FOR EACH ROW EXECUTE FUNCTION pgr_touch_updated_at()")
        op.execute(f"CREATE TRIGGER pgr_log_deleted_row AFTER DELETE ON {t} "
                   f"FOR EACH ROW EXECUTE FUNCTION pgr_log_deleted_row()")

    # 4. The OAuth client lookup (see migration t5_pre_auth_lookups for the pattern).
    op.execute("""
CREATE OR REPLACE FUNCTION pgr_tenant_of_warehouse_client(arg text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    prev text := current_setting('app.bypass_tenant', true);
    result uuid;
BEGIN
    PERFORM set_config('app.bypass_tenant', 'on', true);
    SELECT tenant_id INTO result FROM warehouse_consumer WHERE client_id = arg AND active;
    PERFORM set_config('app.bypass_tenant', coalesce(prev, ''), true);
    RETURN result;
END
$fn$;""")
    op.execute("REVOKE ALL ON FUNCTION pgr_tenant_of_warehouse_client(text) FROM PUBLIC")
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgr_app') THEN "
               "EXECUTE 'GRANT EXECUTE ON FUNCTION pgr_tenant_of_warehouse_client(text) TO pgr_app'; "
               "EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON warehouse_deleted_row, warehouse_publication, "
               "warehouse_run, warehouse_watermark, warehouse_consumer TO pgr_app'; END IF; END $$")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS pgr_tenant_of_warehouse_client(text)")
    for t in PUBLISHED_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS pgr_log_deleted_row ON {t}")
        op.execute(f"DROP TRIGGER IF EXISTS pgr_touch_updated_at ON {t}")
    op.execute("DROP FUNCTION IF EXISTS pgr_log_deleted_row()")
    op.execute("DROP FUNCTION IF EXISTS pgr_touch_updated_at()")
    disable_rls(WAREHOUSE_TABLES)
    for t in reversed(WAREHOUSE_TABLES):
        op.drop_table(t)
    for t in HISTORY_TABLES:
        op.drop_column(t, "updated_at")
