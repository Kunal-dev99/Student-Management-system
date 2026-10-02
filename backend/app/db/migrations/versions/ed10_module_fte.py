"""Effective dating, Phase 8c: module FTE on module versions (Demo 2 item 1.5).

- module_version.fte_pct: the share of a full-time year a module version is (HESA module FTE).
  NULL = derived from credits ÷ the home programme's total credits.
- taught_module.fte_pct: the value of the version in force today (cache).
No backfill: existing versions derive their FTE from credits until one is set.

Revision ID: ed10_module_fte
Revises: ed9_programme_versions
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ed10_module_fte"
down_revision: Union[str, Sequence[str], None] = "ed9_programme_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("module_version", sa.Column("fte_pct", sa.Numeric(5, 2), nullable=True))
    op.add_column("taught_module", sa.Column("fte_pct", sa.Numeric(5, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("taught_module", "fte_pct")
    op.drop_column("module_version", "fte_pct")
